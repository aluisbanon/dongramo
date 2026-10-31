#!/usr/bin/env python3
"""Don Gramo: motor de la dieta del hogar (CLI). Todo el cálculo vive aquí y en plan.py/coach.py:
el modelo solo interpreta mensajes y llama a estos subcomandos. Solo stdlib.
P = id de una persona (`personas`) o "todos". F = AAAA-MM-DD, hoy, mañana, ayer o un día (lunes...).

Hogar y personas
  hogar          [--nombre N] [--thermomix si|no] [--modelo TM6|TM7] [--zona Europe/Madrid]
  personas
  persona-alta   --nombre N --sexo h|m --edad N --altura CM --peso KG [--actividad sedentaria|ligera|moderada|alta|muy alta]
                 [--meta-kg N] [--ritmo KG_SEM] [--modo perder|mantener] [--kcal N] [--embarazo] [--entrenos TEXTO]
  persona-baja   --persona P
  extra-diario   --persona P --alimento X --g N [--nota TEXTO] | --persona P --quitar [--alimento X]
  preferencia    --de X --a Y [--persona P]      sustitución fija (alergias, gustos), todas las semanas
  preferencias   [--quitar N]

Día a día
  hoy | manana   [--persona P] [--fecha F] [--detalle]
  racion         [--fecha F]                   reparto de lo cocinado en la olla
  receta         TEXTO | hoy cena | jueves
  registrar      --persona P --tipo extra|fuera|saltada --desc "..." --kcal N --prot N --hid N --gras N
                 [--comida Desayuno|"Media mañana"|Comida|Merienda|Cena] [--hora HH:MM] [--fecha F]
  eventos        [--persona P] [--dias 7]
  borrar         [N|ID]                        sin nada: lista; N=1 es el más reciente
  ajustes        [--persona P]

Menú de la semana
  menu           [--semana actual|proxima|AAAA-MM-DD]
  elegir-menu    --menu A|B|C [--semana ...]
  catalogo       [--comida TIPO] [--buscar TEXTO]
  cambiar-plato  --fecha F --comida TIPO --opcion ID    (ID del catálogo, p. ej. B-3-Comida)
  plato-nuevo    --fecha F --comida TIPO --nombre "..." --items "alimento:gramos; ..."  (gramos de referencia)
  sustituir      --de ALIMENTO --a ALIMENTO [--semana ...] [--fecha F] [--comida TIPO] [--persona P]
  quitar         --alimento X (--fecha F | --semana ...) [--comida T] [--persona P]
  cantidad       --alimento X --fecha F [--comida T] --gramos [P=]N ...
  anadir         --alimento X --fecha F --comida T --gramos [P=]N ...
  intercambiar   --fecha F --comida T [--con-fecha F2] [--con-comida T2]
  cambios | deshacer N [--semana ...]
  alimentos      [--buscar TEXTO]
  alimento-nuevo --nombre N --kcal --prot --hid --gras --cat CATEGORIA [--flex]
  compra         [--semana actual|proxima] [--nota]

Cookidoo: extensión aparte (plugin don-gramo-cookidoo).

Entrenador
  peso           --persona P --kg N [--grasa N] [--visceral N] [--musculo N] [--fecha F]
  pesos          [--persona P] [--n 10]
  progreso       [--persona P]
  semana         [--fecha F]
  revision       [--sin-guardar]
  aceptar        [--persona P] | rechazar
  perfil         [--persona P]
  objetivo       --persona P [--meta-kg N] [--ritmo N] [--kcal N] [--suelo N] [--entrenos TEXTO] [--modo perder|mantener]
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coach  # noqa: E402
import perfiles  # noqa: E402
from common import HOME, SCRIPTS, ahora, cookidoo_listo, hoy, load_config, registrar_plugin  # noqa: E402
from plan import (CFG, DIAS_ES, FOODS, FRUTA, HORAS, MENU, PERSONAS, TIPOS, ALIMENTOS_EXTRA,  # noqa: E402
                  PREFERENCIAS, anadir_jsonl, escala_raciones, buscar_alimento, calcular_recortes, catalogo, cocinado,
                  comida_por_id, comidas_base, config_semana, es_todos, escribir_json, eventos,
                  gramos_equivalentes, guardar_semana, kcal_items, leer_json, lista_compra, lunes_de, mac,
                  nombre, nombres, plan_dia, preferencias, prot_items, registrar, REGISTRO, semana_arg,
                  plato_slot, nombre_corto, PLATO_TIPOS)
import re  # noqa: E402


# --------------------------------------------------------------------------- utilidades
def fecha_arg(s):
    if not s:
        return hoy()
    s = s.strip().lower()
    if s in ("hoy", "today"):
        return hoy()
    if s in ("mañana", "manana"):
        return hoy() + dt.timedelta(days=1)
    if s == "ayer":
        return hoy() - dt.timedelta(days=1)
    for i, d in enumerate(["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]):
        if s in (d, d.replace("é", "e").replace("á", "a")):
            delta = (i - hoy().weekday()) % 7
            return hoy() + dt.timedelta(days=delta)
    return dt.date.fromisoformat(s)


def persona_arg(s):
    """Id o nombre (o su comienzo) de una persona del hogar; vacío o "todos" = todas."""
    if not PERSONAS:
        raise SystemExit("Aún no hay nadie en el plan. Empieza con `persona-alta` (o /don-gramo:configurar).")
    if not s or es_todos(s.lower()):
        return list(PERSONAS)
    q = perfiles.slug(s)
    for p in PERSONAS:
        if q == p or q == perfiles.slug(nombre(p)):
            return [p]
    cand = [p for p in PERSONAS if p.startswith(q) or perfiles.slug(nombre(p)).startswith(q)]
    if len(cand) == 1:
        return cand
    raise SystemExit(f"persona desconocida: {s}. En el plan: " + ", ".join(f"{p} ({nombre(p)})" for p in PERSONAS))


def thermomix():
    return bool(CFG["hogar"].get("thermomix"))


def es_tm(receta):
    return bool(receta) and thermomix() and bool(MENU["recetas"].get(receta, {}).get("tm"))


def marca_tm(receta):
    return " (TM)" if es_tm(receta) else ""


def tipo_arg(s):
    if not s:
        return None
    for t in TIPOS:
        if s.lower().replace("ñ", "n") == t.lower().replace("ñ", "n"):
            return t
    raise SystemExit(f"comida desconocida: {s}. Usa una de: {', '.join(TIPOS)}")


def nombre_alimento(f):
    for a, b in ((" (+90% carne)", ""), (" (bote, escurridos)", ""), (" (bote, escurridas)", ""), (" (escurrido)", ""),
                 (" (seco)", ""), (" (secas)", ""), (" virgen extra", ""), (" (cookidoo)", "")):
        f = f.replace(a, b)
    return f


def _raciones_txt(r):
    r = round(r * 4) / 4
    txt = f"{r:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{txt} " + ("ración" if r == 1 else "raciones")


def cantidad(f, g):
    if FOODS.get(f, {}).get("racion"):
        return _raciones_txt(g / 100)
    g = round(g)
    if g <= 0:
        return "—"
    if f == "huevo":
        n = g / 55
        if abs(n - round(n)) < 0.05:
            n = round(n)
            return f"{n} huevo" + ("s" if n != 1 else "")
        return "¼ huevo" if g < 20 else f"{g} g de huevo"
    if f.startswith("atún"):
        n = max(1, round(g / 52))
        return f"{n} lata" + ("s" if n != 1 else "")
    if f.startswith("leche"):
        return f"{g} ml"
    ud = FOODS[f].get("ud")
    if ud:
        r = round(g / ud * 2) / 2
        txt = "½" if r == 0.5 else (str(int(r)) if r == int(r) else f"{int(r)}½")
        return f"{g} g ({txt} ud)"
    return f"{g} g"


def kc(n):
    return f"{round(n):,}".replace(",", ".")


def dfmt(d):
    return f"{DIAS_ES[d.weekday()]} {d.day}/{d.month}"


CORTOS = {"pan integral": "pan", "queso fresco Burgos 0%": "queso fresco", "queso fresco batido 0%": "queso batido",
          "aceite de oliva virgen extra": "aceite", "almendras naturales": "almendras", "yogur natural desnatado": "yogur",
          "claras de huevo": "claras", "leche desnatada": "leche", "fiambre de pavo (+90% carne)": "pavo",
          "proteína whey": "whey", "mozzarella light": "mozzarella", "skyr natural": "skyr",
          "jamón serrano": "jamón", "copos de avena": "avena"}
VERDURA_EXTRA = {"tomate triturado", "pimientos asados (conserva)"}


def es_verdura(f):
    if f in VERDURA_EXTRA:
        return True
    return FOODS[f]["cat"] == "Fruta y verdura" and f not in FRUTA and f not in ("patata", "aguacate", "guisantes congelados")


def texto_item(i, corto=False):
    if corto and (i["f"] == "huevo" or i["f"].startswith("atún")):
        s = cantidad(i["f"], i["g"]) + ("" if i["f"] == "huevo" else " de atún")
    else:
        n = CORTOS.get(i["f"], nombre_alimento(i["f"])) if corto else nombre_alimento(i["f"])
        s = f"{n} {cantidad(i['f'], i['g'])}"
    if "antes" in i:
        s += f" (antes {cantidad(i['f'], i['antes'])})"
    return s


def corto_comp(etiqueta):
    t = etiqueta.split(" (")[0]
    return t[:1].lower() + t[1:]


def texto_cocinado(comp, p):
    g = comp["g"][p]
    if comp["ud"]:
        n = round(g / 55)
        return f"{n} huevo" + ("s" if n != 1 else "")
    return f"≈ {g} g"


def olla_comun(comidas_por_persona):
    """Reparto de la olla entre quienes comen en casa ese plato (todos con la misma receta)."""
    en_casa = {p: c for p, c in comidas_por_persona.items() if not c.get("sustituida")}
    recetas = {c.get("receta") for c in en_casa.values()}
    if not en_casa or len(recetas) != 1 or not next(iter(recetas)):
        return None
    return cocinado(next(iter(recetas)), {p: c["items_aj"] for p, c in en_casa.items()})


def texto_olla(comp):
    """'pesa la olla y sirve: Ana 45 %, Luis 35 %, Leo 20 %'."""
    return ", ".join(f"{nombre(p)} {v} %" for p, v in comp["pct"].items())


# --------------------------------------------------------------------------- vista del día
def resumen_comida(c, comp, p):
    partes, cubiertos = [], set()
    for x in comp or []:
        if p not in x["g"]:
            continue
        if "items" not in x:  # lote (natillas): un tarro
            cubiertos |= {i["f"] for i in c["items_aj"] if i["f"] not in FRUTA}
            partes.append(f"{corto_comp(x['c'])} ({x['g'][p]} g)")
        else:
            cubiertos |= set(x["items"])
            partes.append(f"{corto_comp(x['c'])} {texto_cocinado(x, p)}")
    for i in c["items_aj"]:
        if i["f"] in cubiertos or es_verdura(i["f"]) or i["g"] <= 0:
            continue
        partes.append(texto_item(i, corto=True))
    return ", ".join(partes)


def render_dia(fecha, personas, detalle=False):
    planes = {p: plan_dia(fecha, p) for p in PERSONAS}
    sem = config_semana(lunes_de(fecha))
    lineas = [f"*{dfmt(fecha)}* · {MENU['menus'][sem['menu']]['nombre']}"]
    for p in personas:
        t = planes[p]["total"]
        lineas.append(f"{nombre(p)}: {kc(t[0])} kcal · P {round(t[1])} g")
    for idx, tipo in enumerate(TIPOS):
        base = planes[personas[0]]["comidas"][idx]
        lineas.append(f"\n*{HORAS[tipo]} · {tipo}*: {base['plato']}{marca_tm(base.get('receta'))}")
        comp = olla_comun({p: planes[p]["comidas"][idx] for p in PERSONAS})
        for p in personas:
            c = planes[p]["comidas"][idx]
            if c.get("sustituida"):
                e = c["sustituida"]
                que = "fuera de casa" if e["tipo"] == "fuera" else "saltada"
                lineas.append(f"  {nombre(p)}: {que} — {e['desc']} (~{kc(e.get('kcal') or 0)} kcal)")
                continue
            ajuste = " ✂️" if c.get("recorte", 0) >= 10 else ""
            if c["plato"] != base["plato"] and not base.get("sustituida"):
                ajuste += f" ({c['plato']})"
            if detalle:
                linea = ", ".join(texto_item(i) for i in c["items_aj"])
                if comp:
                    linea += " · cocinado: " + ", ".join(f"{corto_comp(x['c'])} {texto_cocinado(x, p)}" for x in comp if p in x["g"])
            else:
                linea = resumen_comida(c, comp, p)
            lineas.append(f"  {nombre(p)}{ajuste}: {linea}")
        if comp and len(personas) > 1:
            ollas = [x for x in comp if x.get("olla") and len(x["g"]) > 1]
            if ollas:
                lineas.append("  🍲 " + "; ".join(f"{corto_comp(x['c'])}: {texto_olla(x)}" for x in ollas))
    for p in personas:
        pl = planes[p]
        if pl["diario"]:
            lineas.append(f"\n{nombre(p)} además: " + ", ".join(f"{x.get('nota') or x['f']} ({x['g']} g)" for x in pl["diario"]))
        for e in pl["extras"]:
            lineas.append(f"{nombre(p)} extra: {e['desc']} (~{kc(e['kcal'])} kcal)")
    if not detalle:
        lineas.append("\n_Verdura sin pesar._ Todo el detalle: `/hoy detalle`")
    return "\n".join(lineas)


def render_racion(fecha):
    planes = {p: plan_dia(fecha, p) for p in PERSONAS}
    lineas = []
    for idx, tipo in enumerate(TIPOS):
        comidas = {p: planes[p]["comidas"][idx] for p in PERSONAS}
        comp = olla_comun(comidas)
        if not comp:
            continue
        base = next(c for c in comidas.values() if not c.get("sustituida"))
        lineas.append(f"*{tipo}: {base['plato']}*")
        for x in comp:
            linea = f"  {x['c']}: " + " · ".join(f"{nombre(p)} {texto_cocinado(x, p)}" for p in x["g"])
            if x.get("olla") and len(x["g"]) > 1:
                linea += f" → pesa la olla y sirve: {texto_olla(x)}"
            lineas.append(linea)
    return "\n".join(lineas) or "Hoy no hay platos de olla que repartir."


def cmd_receta(palabras):
    """`receta lentejas` (genérica) o `receta hoy cena` / `receta jueves` (la del día, con cambios)."""
    ws = [w.lower() for w in palabras]
    try:
        f = fecha_arg(ws[0])
    except Exception:  # noqa: BLE001
        return render_receta(" ".join(palabras))
    resto = " ".join(ws[1:]).replace("ñ", "n")
    tipos = [t for t in TIPOS if t.lower().replace("ñ", "n") in resto] or ["Comida", "Cena"]
    out = render_receta_dia(f, tipos)
    if "(Thermomix)" in out and cookidoo_listo():
        dia = DIAS_ES[f.weekday()].lower()
        out += f"\n\n📲 Para Cookidoo: `/cookidoo {dia} {tipos[0].lower()}`" if len(tipos) == 1 else f"\n\n📲 Para Cookidoo: `/cookidoo {dia} comida` o `/cookidoo {dia} cena`"
    return out


def pasos_receta(r):
    """Pasos para Thermomix si el hogar tiene una; si no, la versión de cocina tradicional."""
    if r.get("tm") and not thermomix() and r.get("pasos_sin_tm"):
        return list(r["pasos_sin_tm"])
    return list(r["pasos"])


def render_receta(q):
    q = q.lower()
    rid = q if q in MENU["recetas"] else next((k for k, v in MENU["recetas"].items() if q in v["nombre"].lower()), None)
    if not rid:
        return "No encuentro esa receta. Recetas: " + ", ".join(v["nombre"] for v in MENU["recetas"].values())
    r = MENU["recetas"][rid]
    pasos = "\n".join(f"{i}. {s}" for i, s in enumerate(pasos_receta(r), 1))
    nota = f"\n_{r['nota']}_" if r.get("nota") else ""
    return f"*{r['nombre']}*{' (Thermomix)' if es_tm(rid) else ''}\n{pasos}{nota}"


# --------------------------------------------------------------------------- extras y ajustes
def render_ajustes(personas):
    lineas = []
    for p in personas:
        recortes, informe = calcular_recortes(p)
        futuros = {k: v for k, v in recortes.items() if k[0] >= hoy().isoformat() and v >= 10}
        pend = [f for f in informe if f["pendiente"] > 0 and f["fecha"] >= (hoy() - dt.timedelta(days=7)).isoformat()]
        if not futuros and not pend:
            lineas.append(f"{nombre(p)}: sin ajustes pendientes.")
            continue
        lineas.append(f"*{nombre(p)}*")
        por_fecha = {}
        for (f, t), v in sorted(futuros.items()):
            por_fecha.setdefault(f, []).append((t, v))
        for f, lst in por_fecha.items():
            lineas.append(f"  {dfmt(dt.date.fromisoformat(f))}: " + ", ".join(f"{t} −{round(v)} kcal" for t, v in lst))
        for f in pend:
            lineas.append(f"  Sin compensar del {f['fecha']}: {f['pendiente']} kcal (se absorbe en la semana)")
    return "\n".join(lineas)


def render_cambios_cantidad(persona, desde):
    recortes, _ = calcular_recortes(persona)
    fechas = sorted({f for (f, _t), v in recortes.items() if v >= 10 and f >= max(desde, hoy()).isoformat()})
    if not fechas:
        return "Sin cambios en las cantidades."
    lineas = [f"*Cambios para {nombre(persona)}*"]
    for f in fechas:
        d = dt.date.fromisoformat(f)
        for c in plan_dia(d, persona)["comidas"]:
            cambios = [f"{CORTOS.get(i['f'], nombre_alimento(i['f']))} {cantidad(i['f'], i['antes'])} → {cantidad(i['f'], i['g'])}"
                       for i in c.get("items_aj", []) if "antes" in i]
            if cambios:
                lineas.append(f"{dfmt(d)} · {c['tipo']}: " + ", ".join(cambios))
    return "\n".join(lineas)


def cmd_registrar(a):
    persona = persona_arg(a.persona)[0]
    fecha = fecha_arg(a.fecha)
    comida = tipo_arg(a.comida)
    if a.tipo in ("fuera", "saltada") and not comida:
        raise SystemExit(f"--comida es obligatoria para '{a.tipo}': {TIPOS}")
    ev = registrar(persona, a.tipo, a.desc, a.kcal, fecha, comida, a.hora, a.prot, a.hid, a.gras)
    _, informe = calcular_recortes(persona)
    fila = next((f for f in informe if f["fecha"] == fecha.isoformat()), None)
    lineas = [f"Anotado para {nombre(persona)}: {a.desc} (~{kc(ev['kcal'])} kcal)."]
    if fila:
        if fila["exceso"] < CFG["reajuste"]["umbral_kcal"]:
            lineas.append(f"Exceso del día: {fila['exceso']} kcal. No hace falta ajustar nada.")
        else:
            lineas.append(f"Exceso del día: {fila['exceso']} kcal.")
            if fila["compensado_hoy"]:
                lineas.append(f"Se compensan hoy: {fila['compensado_hoy']} kcal.")
            for r in fila["repartido"]:
                lineas.append(f"Se reparten el {dfmt(dt.date.fromisoformat(r['fecha'])).lower()}: {r['kcal']} kcal.")
            if fila["pendiente"]:
                lineas.append(f"Quedan {fila['pendiente']} kcal sin compensar: se dejan, no se recorta más.")
    lineas += ["", render_cambios_cantidad(persona, fecha), "", "Si me he equivocado: `/borrar 1`."]
    return "\n".join(lineas)


def cmd_borrar(arg):
    recientes = sorted(eventos(), key=lambda e: e.get("ts", ""), reverse=True)[:8]
    if not arg:
        if not recientes:
            return "No hay nada registrado que borrar."
        return "*Últimos registros* (el 1 es el más reciente):\n" + "\n".join(
            f"{n}. {nombre(e['persona'])} · {e['fecha'][8:]}/{e['fecha'][5:7]}: {e['desc']} (~{e['kcal']} kcal)"
            for n, e in enumerate(recientes, 1)) + "\n\nPara borrar uno: `/borrar 1`"
    ev = recientes[int(arg) - 1] if arg.isdigit() and 1 <= int(arg) <= len(recientes) else next(
        (e for e in eventos() if e["id"] == arg), None)
    if not ev:
        return "No encuentro ese registro. Escribe `/borrar` para ver la lista."
    anadir_jsonl(REGISTRO, {"id": ev["id"], "tipo": "_borrado", "ts": ahora().isoformat(timespec="seconds"), "persona": "-"})
    return f"🗑️ Borrado: {nombre(ev['persona'])} · {ev['desc']} (~{ev['kcal']} kcal). Ajustes recalculados.\n\n" + render_ajustes([ev["persona"]])


# --------------------------------------------------------------------------- menú de la semana
def render_menu(lunes):
    sem = config_semana(lunes)
    fin = lunes + dt.timedelta(days=6)
    lineas = [f"*{MENU['menus'][sem['menu']]['nombre']}* · semana del {lunes.day}/{lunes.month} al {fin.day}/{fin.month}"]
    for d in range(7):
        f = lunes + dt.timedelta(days=d)
        ca = comidas_base(f, PERSONAS[0] if PERSONAS else "_referencia")
        com = next(c for c in ca if c["tipo"] == "Comida")
        cen = next(c for c in ca if c["tipo"] == "Cena")
        lineas.append(f"*{DIAS_ES[d][:3]}* · {com['plato']}{marca_tm(com['receta'])} / {cen['plato']}{marca_tm(cen['receta'])}")
    if sem["cambios"]:
        lineas.append("\n*Cambios esta semana:*\n" + render_lista_cambios(lunes))
    lineas.append("\nDesayunos, media mañana y meriendas: `/hoy` cada día.")
    return "\n".join(lineas)


def describir_cambio(c):
    alcance = f" el {dfmt(dt.date.fromisoformat(c['fecha']))}" if c.get("fecha") else " toda la semana"
    if c.get("comida"):
        alcance += f" ({c['comida'].lower()})"
    if not es_todos(c.get("persona")):
        alcance += f", solo {nombre(c['persona'])}"
    if c["tipo"] == "sustituir":
        return f"{nombre_alimento(c['de'])} → {nombre_alimento(c['a'])}{alcance}"
    if c["tipo"] == "cambiar_plato":
        return f"{c['comida']} del {dfmt(dt.date.fromisoformat(c['fecha']))}: {comida_por_id(c['opcion'])['plato']}"
    if c["tipo"] == "plato_nuevo":
        return f"{c['comida']} del {dfmt(dt.date.fromisoformat(c['fecha']))}: {c['plato']} (nuevo)"
    if c["tipo"] == "plato_fijo":
        return f"{c['comida']} del {dfmt(dt.date.fromisoformat(c['fecha']))}: {c['plato']} ({c.get('nota', 'movido')})"
    if c["tipo"] == "quitar":
        return f"sin {nombre_alimento(c['f'])}{alcance}"
    if c["tipo"] == "cantidad":
        gs = ", ".join(f"{'todos (referencia)' if p == '*' else nombre(p)} {round(g)} g" for p, g in c["g"].items())
        return f"{nombre_alimento(c['f'])}: {gs}{alcance}"
    if c["tipo"] == "anadir":
        gs = ", ".join(f"{'todos (referencia)' if p == '*' else nombre(p)} {round(g)} g" for p, g in c["g"].items() if g)
        return f"+ {nombre_alimento(c['f'])} ({gs}){alcance}"
    return str(c)


def render_lista_cambios(lunes):
    cambios = config_semana(lunes)["cambios"]
    return "\n".join(f"{n}. {describir_cambio(c)}" for n, c in enumerate(cambios, 1)) or "Sin cambios."


def anadir_cambio(lunes, cambio):
    sem = config_semana(lunes)
    sem["cambios"] = [c for c in sem["cambios"] if not (
        (c["tipo"] in PLATO_TIPOS and cambio["tipo"] in PLATO_TIPOS
         and c.get("fecha") == cambio.get("fecha") and c.get("comida") == cambio.get("comida"))
        or (c["tipo"] == cambio["tipo"] == "cantidad" and c.get("f") == cambio.get("f")
            and c.get("fecha") == cambio.get("fecha") and c.get("comida") == cambio.get("comida")
            and set(c["g"]) == set(cambio["g"])))]
    sem["cambios"].append(cambio)
    guardar_semana(lunes, sem)


def comparar_comida(fecha, tipo):
    return {p: next(c for c in comidas_base(fecha, p) if c["tipo"] == tipo) for p in PERSONAS}


def cmd_sustituir(a):
    de, aa = buscar_alimento(a.de), buscar_alimento(a.a)
    if not de:
        return f"No encuentro '{a.de}' en los alimentos. Mira `alimentos --buscar`."
    if not aa:
        return (f"No tengo '{a.a}' en la base de alimentos. Añádelo con `alimento-nuevo` "
                f"(kcal, proteína, hidratos y grasa por 100 g) y repite.")
    if a.fecha:
        f = fecha_arg(a.fecha)
        lunes = lunes_de(f)
    else:
        f, lunes = None, semana_arg(a.semana)
    cambio = {"tipo": "sustituir", "de": de, "a": aa, "fecha": f.isoformat() if f else None,
              "comida": tipo_arg(a.comida), "persona": _persona_cambio(a)}
    # ¿afecta a algo?
    afectadas = []
    for d in range(7):
        dia = lunes + dt.timedelta(days=d)
        if f and dia != f:
            continue
        quien = PERSONAS[0] if es_todos(cambio["persona"]) else cambio["persona"]
        for c in comidas_base(dia, quien):
            if any(i["f"] == de for i in c["items"]) and (not cambio["comida"] or c["tipo"] == cambio["comida"]):
                afectadas.append((dia, c))
    if not afectadas:
        return f"No hay {nombre_alimento(de)} en esos días: no cambio nada."
    anadir_cambio(lunes, {k: v for k, v in cambio.items() if v is not None})
    ej = afectadas[0]
    g_de = next(i["g"] for i in ej[1]["items"] if i["f"] == de)
    return (f"✅ Cambiado {nombre_alimento(de)} por {nombre_alimento(aa)} en {len(afectadas)} comida(s): "
            + ", ".join(f"{DIAS_ES[d.weekday()][:3]} {c['tipo'].lower()}" for d, c in afectadas)
            + f".\nCantidad equivalente ({nombre(quien)}): {cantidad(de, g_de)} → {cantidad(aa, gramos_equivalentes(de, aa, g_de))}."
            + "\nLas cantidades del día se reajustan solas al objetivo de cada uno.")


def cmd_cambiar_plato(a):
    f, tipo = fecha_arg(a.fecha), tipo_arg(a.comida)
    try:
        nuevo = comida_por_id(a.opcion)
    except Exception:  # noqa: BLE001
        return "Opción no válida. Mira `catalogo --comida ...`."
    if nuevo["tipo"] != tipo:
        return f"Ese plato es de {nuevo['tipo'].lower()}, no de {tipo.lower()}."
    anadir_cambio(lunes_de(f), {"tipo": "cambiar_plato", "fecha": f.isoformat(), "comida": tipo, "opcion": a.opcion})
    return f"✅ {dfmt(f)} · {tipo}: ahora toca *{nuevo['plato']}*. Cantidades ajustadas a cada uno."


def cmd_plato_nuevo(a):
    """Plato propuesto por el chat, en gramos de referencia (adulto medio): se escala a cada uno.
    Solo se acepta si queda en ±20 % de kcal y con al menos el 80 % de la proteína del plato que sustituye."""
    f, tipo = fecha_arg(a.fecha), tipo_arg(a.comida)
    items = []
    for trozo in a.items.split(";"):
        if not trozo.strip():
            continue
        partes = [x.strip() for x in trozo.rsplit(":", 1)]
        if len(partes) != 2:
            return f"Formato de ingrediente no válido: '{trozo}'. Usa alimento:gramos (gramos de referencia)."
        fid = buscar_alimento(partes[0])
        if not fid:
            return f"No tengo '{partes[0]}' en la base de alimentos. Añádelo antes con `alimento-nuevo`."
        items.append({"f": fid, "g": float(partes[1])})
    original = [{"f": x["f"], "g": x["g"]} for x in plato_slot(f, tipo)["items"] if "g" in x]
    k0, k1 = kcal_items(original), kcal_items(items)
    p0, p1 = prot_items(original), prot_items(items)
    problemas = []
    if not (0.8 * k0 <= k1 <= 1.2 * k0):
        problemas.append(f"{round(k1)} kcal frente a {round(k0)} del plato original (debe quedar entre {round(0.8 * k0)} y {round(1.2 * k0)})")
    if p1 < 0.8 * p0:
        problemas.append(f"{round(p1)} g de proteína frente a {round(p0)} g (mínimo {round(0.8 * p0)})")
    if problemas:
        return ("❌ No lo aplico, no cuadra con el plan (cantidades de referencia):\n" + "\n".join(problemas)
                + "\nAjusta las cantidades y vuelve a probar.")
    anadir_cambio(lunes_de(f), {"tipo": "plato_nuevo", "fecha": f.isoformat(), "comida": tipo, "plato": a.nombre, "items": items})
    return f"✅ {dfmt(f)} · {tipo}: *{a.nombre}*. Cuadra en calorías y proteína; cada uno tendrá su cantidad."


def cmd_deshacer(n, lunes):
    sem = config_semana(lunes)
    if not n:
        return render_lista_cambios(lunes) + "\n\nPara quitar uno: `/deshacer N`"
    i = int(n) - 1
    if not 0 <= i < len(sem["cambios"]):
        return "No hay ese cambio. Lista: `/cambios`."
    quitado = sem["cambios"].pop(i)
    guardar_semana(lunes, sem)
    return f"↩️ Deshecho: {describir_cambio(quitado)}"


FMT_UD = {"huevo": 55, "atún al natural (escurrido)": 52}


def _qty_compra(f, g):
    import math
    if FOODS[f].get("racion"):
        return f"{_raciones_txt(g / 100)} (sus ingredientes, en la lista de Cookidoo)"
    if f == "huevo":
        return f"{math.ceil(g / 55)} huevos"
    if f.startswith("atún"):
        return f"{math.ceil(g / 52)} latas"
    if f.startswith("leche"):
        return f"{math.ceil(g / 1000)} L"
    if FOODS[f].get("ud"):
        return f"{math.ceil(g / FOODS[f]['ud'])} ud"
    g = math.ceil(g / 10) * 10 if g < 100 else math.ceil(g / 50) * 50
    if g >= 1000:
        return f"{g / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " kg"
    return f"{g} g"


def render_compra(lunes, nota=False):
    fin = lunes + dt.timedelta(days=6)
    menu = MENU['menus'][config_semana(lunes)['menu']]['nombre']
    secciones = [(cat, [f"{nombre_alimento(f)} {_qty_compra(f, g)}" if nota else f"- {nombre_alimento(f)}: {_qty_compra(f, g)}"
                        for f, g in items]) for cat, items in lista_compra(lunes)]
    if nota:
        # Texto plano para pegar en Notas: una línea por producto (se convierte en checklist)
        lineas = [f"Compra {lunes.day}/{lunes.month}–{fin.day}/{fin.month} ({menu})"]
        for cat, items in secciones:
            lineas.append(f"\n{cat.upper()}")
            lineas += items
        lineas.append("\nMIRAR EN CASA")
        lineas += list(MENU["despensa"])
        return ("📲 *Para tu app de notas*: toca el bloque para copiarlo y pégalo en una nota nueva "
                "(en Notas de iPhone, selecciona todo y pulsa ☑️ para convertirlo en lista).\n\n```\n" + "\n".join(lineas).replace("`", "'") + "\n```")
    lineas = [f"*Lista de la compra* ({menu}, {lunes.day}/{lunes.month}–{fin.day}/{fin.month}, "
              f"{'para ' + nombre(PERSONAS[0]) if len(PERSONAS) == 1 else f'para {len(PERSONAS)} personas'})"]
    for cat, items in secciones:
        lineas.append(f"\n*{cat}*")
        lineas += items
    lineas.append("\nComprobar en casa: " + ", ".join(MENU["despensa"]))
    return "\n".join(lineas)


# --------------------------------------------------------------------------- resumen semanal de ingesta
def render_semana(fecha):
    lunes = lunes_de(fecha)
    domingo = lunes + dt.timedelta(days=6)
    lineas = [f"*Resumen de la semana* ({lunes.day}/{lunes.month} – {domingo.day}/{domingo.month})"]
    for p in PERSONAS:
        plan_total = real_total = 0.0
        dias_extra = 0
        n = min(7, (fecha - lunes).days + 1)
        for i in range(n):
            pl = plan_dia(lunes + dt.timedelta(days=i), p)
            plan_total += pl["base_kcal"]
            real_total += pl["total"][0]
            if any(c.get("sustituida") for c in pl["comidas"]) or pl["extras"]:
                dias_extra += 1
        dif = real_total - plan_total
        _, informe = calcular_recortes(p, fecha.isoformat())
        pendiente = sum(f["pendiente"] for f in informe if lunes.isoformat() <= f["fecha"] <= domingo.isoformat())
        lineas.append(f"\n*{nombre(p)}*: previsto {kc(plan_total)} kcal en {n} días · estimado {kc(real_total)} kcal "
                      f"({'+' if dif >= 0 else '−'}{kc(abs(dif))}). Días con extras o comidas fuera: {dias_extra}."
                      + (f" Sin compensar: {pendiente} kcal." if pendiente else ""))
    return "\n".join(lineas)


# --------------------------------------------------------------------------- cambios de última hora
def _franjas(f, tipo, lunes=None):
    """Días/comidas afectados: una fecha (y comida) o toda la semana."""
    dias = [f] if f else [lunes + dt.timedelta(days=d) for d in range(7)]
    return [(d, t) for d in dias for t in TIPOS if not tipo or t == tipo]


def _foto(franjas):
    return {(d, t, p): next(c for c in comidas_base(d, p) if c["tipo"] == t) for d, t in franjas for p in PERSONAS}


def _impacto(antes, franjas, f_alimento):
    """Resumen del efecto de un cambio y aviso si baja mucho la proteína."""
    despues = _foto(franjas)
    tocadas, avisos = [], []
    for d, t in franjas:
        cambiada = False
        for p in PERSONAS:
            a, b = antes[(d, t, p)], despues[(d, t, p)]
            if a["items"] == b["items"]:
                continue
            cambiada = True
            p0, p1 = prot_items(a["items"]), prot_items(b["items"])
            if p0 >= 15 and p1 < 0.8 * p0:
                avisos.append(f"⚠️ {nombre(p)}, {DIAS_ES[d.weekday()][:3].lower()} {t.lower()}: la proteína baja de "
                              f"{round(p0)} g a {round(p1)} g. Mejor cambiarla por otra (`sustituir`) que quitarla.")
        if cambiada:
            tocadas.append((d, t))
    return tocadas, avisos


def _alcance_arg(a):
    if a.fecha:
        f = fecha_arg(a.fecha)
        return f, lunes_de(f)
    return None, semana_arg(a.semana)


def _persona_cambio(a):
    return persona_arg(a.persona)[0] if a.persona and not es_todos(a.persona.lower()) else "todos"


def _lista_franjas(tocadas):
    return ", ".join(f"{DIAS_ES[d.weekday()][:3]} {t.lower()}" for d, t in tocadas)


def cmd_quitar(a):
    fid = buscar_alimento(a.alimento)
    if not fid:
        return f"No encuentro '{a.alimento}' en los alimentos. Mira `alimentos --buscar`."
    f, lunes = _alcance_arg(a)
    tipo = tipo_arg(a.comida)
    franjas = _franjas(f, tipo, lunes)
    antes = _foto(franjas)
    cambio = {"tipo": "quitar", "f": fid, "fecha": f.isoformat() if f else None, "comida": tipo, "persona": _persona_cambio(a)}
    anadir_cambio(lunes, {k: v for k, v in cambio.items() if v is not None})
    tocadas, avisos = _impacto(antes, franjas, fid)
    if not tocadas:
        config = config_semana(lunes); config["cambios"].pop(); guardar_semana(lunes, config)
        return f"No hay {nombre_alimento(fid)} en esas comidas: no cambio nada."
    return "\n".join([f"✅ Sin {nombre_alimento(fid)} en: {_lista_franjas(tocadas)}.",
                      "El resto del día se reajusta solo para mantener las calorías de cada uno."] + avisos)


def _gramos(a):
    """--gramos 60 (para todos: cantidad de referencia, escalada a cada uno) o --gramos ana=60 luis=40."""
    g = {}
    for x in a.gramos or []:
        quien, _, v = x.rpartition("=")
        try:
            v = float(v.replace(",", "."))
        except ValueError:
            raise SystemExit(f"gramos no válidos: {x}")
        if not quien or es_todos(quien.lower()):
            g["*"] = v
        else:
            g[persona_arg(quien)[0]] = v
    return g


def cmd_cantidad(a):
    fid = buscar_alimento(a.alimento)
    if not fid:
        return f"No encuentro '{a.alimento}' en los alimentos."
    g = _gramos(a)
    if not g:
        return "Dime los gramos: `--gramos N` (para todos) o `--gramos persona=N`."
    f, tipo = fecha_arg(a.fecha), tipo_arg(a.comida)
    franjas = _franjas(f, tipo)
    if not any(i["f"] == fid for d, t in franjas for p in PERSONAS
               for i in next(c for c in comidas_base(d, p) if c["tipo"] == t)["items"]):
        return f"No hay {nombre_alimento(fid)} ese día. Para añadirlo usa `anadir`."
    antes = _foto(franjas)
    anadir_cambio(lunes_de(f), {k: v for k, v in {"tipo": "cantidad", "f": fid, "g": g, "fecha": f.isoformat(),
                                                   "comida": tipo}.items() if v is not None})
    tocadas, avisos = _impacto(antes, franjas, fid)
    gs = ", ".join(f"{'todos' if p == '*' else nombre(p)} {cantidad(fid, v)}" for p, v in g.items())
    return "\n".join([f"✅ {dfmt(f)}: {nombre_alimento(fid)} → {gs}" + (f" ({_lista_franjas(tocadas)})" if tocadas else "") + ".",
                      "Esa cantidad queda fija; el resto del día se reajusta a las calorías de cada uno."] + avisos)


def cmd_anadir(a):
    fid = buscar_alimento(a.alimento)
    if not fid:
        return (f"No tengo '{a.alimento}' en la base de alimentos. Añádelo con `alimento-nuevo` "
                f"(kcal, proteína, hidratos y grasa por 100 g) y repite.")
    g = _gramos(a)
    if not g:
        return "Dime los gramos: `--gramos N` (para todos) o `--gramos persona=N`."
    f, tipo = fecha_arg(a.fecha), tipo_arg(a.comida)
    if not tipo:
        return "Dime a qué comida lo añado (`--comida`)."
    anadir_cambio(lunes_de(f), {"tipo": "anadir", "f": fid, "g": g, "fecha": f.isoformat(), "comida": tipo})
    extra = ", ".join(f"{'cada uno ~' if p == '*' else nombre(p) + ' '}+{round(mac(fid, v)[0])} kcal" for p, v in g.items() if v)
    return (f"✅ {dfmt(f)} · {tipo}: + {nombre_alimento(fid)} ({extra}).\n"
            "Lo compenso en el resto del día recortando hidratos y grasas, no la proteína.")


def cmd_intercambiar(a):
    f1, t1 = fecha_arg(a.fecha), tipo_arg(a.comida)
    f2 = fecha_arg(a.con_fecha) if a.con_fecha else f1
    t2 = tipo_arg(a.con_comida) if a.con_comida else t1
    if not t1:
        return "Dime qué comida mueves (`--comida`)."
    if (f1, t1) == (f2, t2):
        return "Es la misma comida: nada que cambiar."
    principales = {"Comida", "Cena"}
    if t1 != t2 and not {t1, t2} <= principales:
        return "Solo intercambio comidas del mismo tipo, o la comida con la cena."
    s1, s2 = plato_slot(f1, t1), plato_slot(f2, t2)
    d1 = f"{DIAS_ES[f1.weekday()][:3].lower()} {t1.lower()}"
    d2 = f"{DIAS_ES[f2.weekday()][:3].lower()} {t2.lower()}"
    anadir_cambio(lunes_de(f1), {"tipo": "plato_fijo", "fecha": f1.isoformat(), "comida": t1, "plato": s2["plato"],
                                 "receta": s2["receta"], "origen": s2["origen"], "items": s2["items"], "nota": f"antes era del {d2}"})
    anadir_cambio(lunes_de(f2), {"tipo": "plato_fijo", "fecha": f2.isoformat(), "comida": t2, "plato": s1["plato"],
                                 "receta": s1["receta"], "origen": s1["origen"], "items": s1["items"], "nota": f"antes era del {d1}"})
    return (f"🔁 Hecho:\n- {dfmt(f1)} · {t1}: *{s2['plato']}*\n- {dfmt(f2)} · {t2}: *{s1['plato']}*\n"
            "Las cantidades se reajustan solas a cada día.")


AGUA = re.compile(r"(\d{1,2}\.\d{3}|\d+) g de (agua|caldo)")


def escalar_agua(texto, escala):
    """'700 g de agua' -> '1.400 g de agua' cuando cocináis para más (o menos) de 2."""
    def cambia(m):
        g = int(m.group(1).replace(".", "")) * escala
        return f"{kc(50 * round(g / 50))} g de {m.group(2)}"
    return AGUA.sub(cambia, texto)


def pasos_del_dia(r, comidas):
    """Pasos de la receta con los alimentos sustituidos ese día ("Añade la ternera...") y el agua
    ajustada a cuántos coméis."""
    comidas = list(comidas)
    pasos = pasos_receta(r)
    escala = escala_raciones([c["_persona"] for c in comidas if c.get("_persona")]) if comidas else 1
    if abs(escala - 1) > 0.15:
        pasos = [escalar_agua(p, escala) for p in pasos]
    comunes, _ = sustituciones(comidas)
    for orig, f in comunes:
        viejo, nuevo = nombre_corto(orig), nombre_corto(f)
        art = "la" if nuevo.split()[0].endswith("a") else "el"
        pasos = [re.sub(r"\b(el|la) " + re.escape(viejo), f"{art} {nuevo}", p, flags=re.I) for p in pasos]
        pasos = [re.sub(re.escape(viejo), nuevo, p, flags=re.I) for p in pasos]
    return pasos


def sustituciones(comidas):
    """(cambios que tienen todos, {persona: cambios solo suyos}); cada cambio es (alimento original, nuevo)."""
    comidas = list(comidas)
    por = {c.get("_persona", i): {(x["orig"], x["f"]) for x in c.get("items", []) if x.get("orig")}
           for i, c in enumerate(comidas)}
    comunes = set.intersection(*por.values()) if por else set()
    return sorted(comunes), {p: sorted(v - comunes) for p, v in por.items() if v - comunes}


def notas_parciales(comidas):
    _, parciales = sustituciones(comidas)
    return [f"_{nombre(p)}: " + ", ".join(f"{nombre_corto(f)} en vez de {nombre_corto(o)}" for o, f in v)
            + " (hazlo aparte o en la misma olla si os da igual)._" for p, v in parciales.items()]


def comidas_en_casa(f, tipo):
    """{persona: comida del plan} de quienes comen ese plato en casa."""
    idx = TIPOS.index(tipo)
    out = {}
    for p in PERSONAS:
        c = plan_dia(f, p)["comidas"][idx]
        if not c.get("sustituida"):
            out[p] = dict(c, _persona=p)
    return out


CAPACIDAD_VASO = 2000  # g útiles en el vaso de TM5/TM6/TM7 (2,2 L)


def render_receta_dia(f, tipos):
    """La receta tal y como toca ese día, con los cambios y las cantidades de cada uno."""
    bloques = []
    for t in TIPOS:
        if t not in tipos:
            continue
        casa = comidas_en_casa(f, t)
        if not casa:
            bloques.append(f"*{t}*: hoy fuera de casa o saltada.")
            continue
        base = next(iter(casa.values()))
        r = MENU["recetas"].get(base["receta"]) if base.get("receta") else None
        lineas = [f"*{t} · {dfmt(f)}: {base['plato']}*" + (" (Thermomix)" if r and es_tm(base["receta"]) else "")]
        notas = sorted({n for c in casa.values() for n in c.get("notas", [])})
        if notas:
            lineas.append("Cambios: " + "; ".join(notas))
        gramos = {p: {i["f"]: i["g"] for i in c.get("items_aj", [])} for p, c in casa.items()}
        fids = list(dict.fromkeys(fid for g in gramos.values() for fid in g))
        if len(casa) == 1:
            p = next(iter(casa))
            lineas.append(f"\n_Ingredientes en crudo_ ({nombre(p)})")
            lineas += [f"- {nombre_alimento(fid)}: {cantidad(fid, gramos[p][fid])}" for fid in fids]
        else:
            lineas.append("\n_Ingredientes en crudo_ (" + " · ".join(nombre(p) for p in casa) + " · total)")
            for fid in fids:
                vs = [gramos[p].get(fid, 0) for p in casa]
                lineas.append(f"- {nombre_alimento(fid)}: " + " · ".join(cantidad(fid, v) if v else "—" for v in vs)
                              + f" · *{cantidad(fid, sum(vs))}*")
        if r:
            pasos = pasos_del_dia(r, casa.values())
            if es_tm(base["receta"]):
                en_vaso = sum(x["g"][p] for x in (olla_comun(casa) or []) if x.get("olla") for p in x["g"])
                if en_vaso > CAPACIDAD_VASO:
                    lineas.append(f"\n⚠️ Sale ~{kc(en_vaso)} g de guiso: no cabe en el vaso de una vez (máx. ~2 kg). "
                                  "Hazlo en dos tandas o la mitad en una olla.")
            lineas.append("\n_Pasos_")
            lineas += [f"{i}. {p}" for i, p in enumerate(pasos, 1)]
            lineas += notas_parciales(casa.values())
            sin = [n[4:] for n in notas if n.startswith("sin ")]
            if sin:
                lineas.append(f"_Sáltate lo que lleve {', '.join(sin)}._")
            anadidos = [n[2:] for n in notas if n.startswith("+ ")]
            if anadidos:
                lineas.append(f"_Añade {', '.join(anadidos)} aparte o al final._")
            if r.get("nota"):
                lineas.append(f"_{r['nota']}_")
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques) or "No hay nada que cocinar en esa comida."


# --------------------------------------------------------------------------- preferencias permanentes
def cmd_preferencia(a):
    de, aa = buscar_alimento(a.de), buscar_alimento(a.a)
    if not de or not aa:
        return f"No encuentro '{a.de if not de else a.a}' en los alimentos. Mira `alimentos --buscar` o añádelo con `alimento-nuevo`."
    quien = _persona_cambio(a)
    prefs = [x for x in preferencias() if not (x["de"] == de and x.get("persona", "todos") == quien)]
    prefs.append({"de": de, "a": aa, "persona": quien})
    escribir_json(PREFERENCIAS, prefs)
    para = "todos" if es_todos(quien) else nombre(quien)
    return (f"✅ Desde ya, {nombre_alimento(de)} → {nombre_alimento(aa)} ({para}), todas las semanas. "
            "Cantidades equivalentes en proteína o calorías.\nPara quitarlo: `preferencias`.")


def cmd_preferencias(quitar=None):
    prefs = preferencias()
    if quitar:
        if not 1 <= quitar <= len(prefs):
            return "No hay esa preferencia."
        x = prefs.pop(quitar - 1)
        escribir_json(PREFERENCIAS, prefs)
        return f"↩️ Quitada: {nombre_alimento(x['de'])} → {nombre_alimento(x['a'])}."
    if not prefs:
        return "No hay sustituciones fijas. Ejemplo: `preferencia --de gambas --a merluza --persona ana`."
    return "*Sustituciones fijas*\n" + "\n".join(
        f"{n}. {nombre_alimento(x['de'])} → {nombre_alimento(x['a'])} ({'todos' if es_todos(x.get('persona')) else nombre(x['persona'])})"
        for n, x in enumerate(prefs, 1)) + "\n\nPara quitar una: `preferencias --quitar N`"


# --------------------------------------------------------------------------- CLI
SIN_PERSONAS = {"hogar", "personas", "persona-alta", "receta", "catalogo", "alimentos", "alimento-nuevo", "menu"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Don Gramo: motor de la dieta del hogar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("hogar"); s.add_argument("--nombre"); s.add_argument("--thermomix"); s.add_argument("--modelo")
    s.add_argument("--zona")
    sub.add_parser("personas")
    s = sub.add_parser("persona-alta"); s.add_argument("--nombre", required=True); s.add_argument("--sexo", required=True)
    s.add_argument("--edad", type=int, required=True); s.add_argument("--altura", type=float, required=True)
    s.add_argument("--peso", type=float, required=True); s.add_argument("--actividad"); s.add_argument("--meta-kg", type=float)
    s.add_argument("--ritmo", type=float); s.add_argument("--modo", choices=["perder", "mantener"]); s.add_argument("--kcal", type=float)
    s.add_argument("--embarazo", action="store_true"); s.add_argument("--entrenos"); s.add_argument("--telegram-id")
    s = sub.add_parser("persona-baja"); s.add_argument("--persona", required=True)
    s = sub.add_parser("vincular-telegram"); s.add_argument("--persona", required=True); s.add_argument("--id", required=True)
    s = sub.add_parser("extra-diario"); s.add_argument("--persona", required=True); s.add_argument("--alimento")
    s.add_argument("--g", type=float); s.add_argument("--nota"); s.add_argument("--quitar", action="store_true")
    s = sub.add_parser("preferencia"); s.add_argument("--de", required=True); s.add_argument("--a", required=True); s.add_argument("--persona")
    s = sub.add_parser("preferencias"); s.add_argument("--quitar", type=int)
    for n in ("hoy", "manana"):
        s = sub.add_parser(n); s.add_argument("--persona"); s.add_argument("--fecha")
        s.add_argument("--detalle", action="store_true"); s.add_argument("--compacto", action="store_true")
    s = sub.add_parser("racion"); s.add_argument("--fecha")
    s = sub.add_parser("receta"); s.add_argument("q", nargs="+")
    s = sub.add_parser("registrar")
    s.add_argument("--persona", required=True); s.add_argument("--tipo", required=True, choices=["extra", "fuera", "saltada"])
    s.add_argument("--desc", required=True); s.add_argument("--kcal", type=float, default=0); s.add_argument("--comida")
    s.add_argument("--prot", type=float); s.add_argument("--hid", type=float); s.add_argument("--gras", type=float)
    s.add_argument("--fecha"); s.add_argument("--hora")
    s = sub.add_parser("eventos"); s.add_argument("--persona"); s.add_argument("--dias", type=int, default=7)
    s = sub.add_parser("borrar"); s.add_argument("id", nargs="?")
    s = sub.add_parser("ajustes"); s.add_argument("--persona")
    s = sub.add_parser("menu"); s.add_argument("--semana")
    s = sub.add_parser("elegir-menu"); s.add_argument("--menu", required=True); s.add_argument("--semana")
    s = sub.add_parser("catalogo"); s.add_argument("--comida"); s.add_argument("--buscar")
    s = sub.add_parser("cambiar-plato"); s.add_argument("--fecha", required=True); s.add_argument("--comida", required=True); s.add_argument("--opcion", required=True)
    s = sub.add_parser("plato-nuevo"); s.add_argument("--fecha", required=True); s.add_argument("--comida", required=True)
    s.add_argument("--nombre", required=True); s.add_argument("--items", required=True)
    s = sub.add_parser("sustituir"); s.add_argument("--de", required=True); s.add_argument("--a", required=True)
    s.add_argument("--semana"); s.add_argument("--fecha"); s.add_argument("--comida"); s.add_argument("--persona")
    s = sub.add_parser("quitar"); s.add_argument("--alimento", required=True); s.add_argument("--fecha")
    s.add_argument("--semana"); s.add_argument("--comida"); s.add_argument("--persona")
    for n in ("cantidad", "anadir"):
        s = sub.add_parser(n); s.add_argument("--alimento", required=True); s.add_argument("--fecha", required=True)
        s.add_argument("--comida"); s.add_argument("--gramos", nargs="+", help="N (todos) o persona=N")
    s = sub.add_parser("intercambiar"); s.add_argument("--fecha", required=True); s.add_argument("--comida", required=True)
    s.add_argument("--con-fecha"); s.add_argument("--con-comida")
    s = sub.add_parser("cambios"); s.add_argument("--semana")
    s = sub.add_parser("deshacer"); s.add_argument("n", nargs="?"); s.add_argument("--semana")
    s = sub.add_parser("alimentos"); s.add_argument("--buscar")
    s = sub.add_parser("alimento-nuevo"); s.add_argument("--nombre", required=True)
    for k in ("kcal", "prot", "hid", "gras"):
        s.add_argument(f"--{k}", type=float, required=True)
    s.add_argument("--cat", required=True); s.add_argument("--flex", action="store_true")
    s = sub.add_parser("compra"); s.add_argument("--semana"); s.add_argument("--nota", action="store_true")
    s = sub.add_parser("peso"); s.add_argument("--persona", required=True); s.add_argument("--kg", type=float, required=True)
    s.add_argument("--grasa", type=float); s.add_argument("--visceral", type=float); s.add_argument("--musculo", type=float); s.add_argument("--fecha")
    s = sub.add_parser("pesos"); s.add_argument("--persona"); s.add_argument("--n", type=int, default=10)
    s = sub.add_parser("progreso"); s.add_argument("--persona")
    s = sub.add_parser("semana"); s.add_argument("--fecha")
    s = sub.add_parser("revision"); s.add_argument("--sin-guardar", action="store_true")
    s = sub.add_parser("aceptar"); s.add_argument("--persona")
    sub.add_parser("rechazar")
    s = sub.add_parser("perfil"); s.add_argument("--persona")
    s = sub.add_parser("objetivo"); s.add_argument("--persona", required=True)
    s.add_argument("--meta-kg", type=float); s.add_argument("--meta-final-kg", type=float); s.add_argument("--ritmo", type=float)
    s.add_argument("--kcal", type=float); s.add_argument("--suelo", type=float); s.add_argument("--entrenos"); s.add_argument("--modo", choices=["perder", "mantener"])
    a = ap.parse_args(argv)
    c = a.cmd
    registrar_plugin("don-gramo", SCRIPTS)
    if not PERSONAS and c not in SIN_PERSONAS:
        print("Aún no hay nadie en el plan. Configúralo primero: `persona-alta --nombre ... --sexo ... --edad ... "
              "--altura ... --peso ...` (o /don-gramo:configurar en Claude Code).")
        return 1

    if c == "hogar":
        out = perfiles.hogar(a.nombre, a.thermomix, a.zona, a.modelo) if any(
            v is not None for v in (a.nombre, a.thermomix, a.zona, a.modelo)) else perfiles.render_hogar()
    elif c == "personas":
        out = perfiles.render_hogar() + ("\n\n" + coach.render_perfil() if PERSONAS else "")
    elif c == "persona-alta":
        out = perfiles.alta(a.nombre, a.sexo, a.edad, a.altura, a.peso, a.actividad, a.meta_kg, a.ritmo, a.modo, a.kcal,
                            a.embarazo, a.entrenos, a.telegram_id)
    elif c == "persona-baja":
        out = perfiles.baja(persona_arg(a.persona)[0])
    elif c == "vincular-telegram":
        out = perfiles.vincular_telegram(persona_arg(a.persona)[0], a.id)
    elif c == "extra-diario":
        out = perfiles.extra_diario(persona_arg(a.persona)[0], a.alimento, a.g, a.nota, a.quitar)
    elif c == "preferencia":
        out = cmd_preferencia(a)
    elif c == "preferencias":
        out = cmd_preferencias(a.quitar)
    elif c in ("hoy", "manana"):
        f = fecha_arg(a.fecha) if a.fecha else (hoy() + dt.timedelta(days=1) if c == "manana" else hoy())
        out = render_dia(f, persona_arg(a.persona), a.detalle)
    elif c == "racion":
        out = render_racion(fecha_arg(a.fecha))
    elif c == "receta":
        out = cmd_receta(a.q)
    elif c == "registrar":
        out = cmd_registrar(a)
    elif c == "eventos":
        desde = (hoy() - dt.timedelta(days=a.dias)).isoformat()
        ps = persona_arg(a.persona)
        evs = [e for e in eventos() if e["persona"] in ps and e["fecha"] >= desde]
        out = "\n".join(f"{e['fecha']} {nombre(e['persona'])} · {e['tipo']}{' · ' + e['comida'] if e.get('comida') else ''}: "
                        f"{e['desc']} (~{e['kcal']} kcal)" for e in evs) or "No hay nada registrado."
    elif c == "borrar":
        out = cmd_borrar(a.id)
    elif c == "ajustes":
        out = render_ajustes(persona_arg(a.persona))
    elif c == "menu":
        out = render_menu(semana_arg(a.semana))
    elif c == "elegir-menu":
        m = a.menu.upper()
        if m not in MENU["menus"]:
            out = f"Menús disponibles: {', '.join(MENU['menus'])}"
        else:
            lunes = semana_arg(a.semana)
            sem = config_semana(lunes)
            sem["menu"] = m
            guardar_semana(lunes, sem)
            out = f"✅ Semana del {lunes.day}/{lunes.month}: {MENU['menus'][m]['nombre']}.\n\n" + render_menu(lunes)
    elif c == "catalogo":
        cat = catalogo(tipo_arg(a.comida))
        if a.buscar:
            cat = [x for x in cat if a.buscar.lower() in x["plato"].lower()]
        out = "\n".join(f"{x['id']} · {x['plato']}" + (" (TM)" if x["receta"] and MENU["recetas"].get(x["receta"], {}).get("tm") else "")
                        for x in cat) or "Nada."
    elif c == "cambiar-plato":
        out = cmd_cambiar_plato(a)
    elif c == "plato-nuevo":
        out = cmd_plato_nuevo(a)
    elif c == "sustituir":
        out = cmd_sustituir(a)
    elif c == "quitar":
        out = cmd_quitar(a)
    elif c == "cantidad":
        out = cmd_cantidad(a)
    elif c == "anadir":
        out = cmd_anadir(a)
    elif c == "intercambiar":
        out = cmd_intercambiar(a)
    elif c == "cambios":
        out = render_lista_cambios(semana_arg(a.semana))
    elif c == "deshacer":
        out = cmd_deshacer(a.n, semana_arg(a.semana))
    elif c == "alimentos":
        lista = [f for f in FOODS if not a.buscar or a.buscar.lower() in f.lower()]
        out = "\n".join(f"{f}: {FOODS[f]['kcal']} kcal, P {FOODS[f]['p']} g /100 g" for f in sorted(lista)) or "Nada."
    elif c == "alimento-nuevo":
        extra = leer_json(ALIMENTOS_EXTRA, {})
        extra[a.nombre.lower()] = {"kcal": a.kcal, "p": a.prot, "h": a.hid, "g": a.gras, "cat": a.cat, "ud": None,
                                   "flex": bool(a.flex), "paso": 5}
        escribir_json(ALIMENTOS_EXTRA, extra)
        out = f"Añadido '{a.nombre.lower()}' ({a.kcal} kcal, P {a.prot} g por 100 g)."
    elif c == "compra":
        out = render_compra(semana_arg(a.semana), a.nota)
    elif c == "peso":
        p = persona_arg(a.persona)[0]
        coach.anotar_peso(p, a.kg, fecha_arg(a.fecha), a.grasa, a.visceral, a.musculo)
        out = f"⚖️ Anotado: {nombre(p)} {coach.num(a.kg, 2)} kg" + (f", grasa {coach.num(a.grasa)} %" if a.grasa else "") + ".\n\n" + coach.render_progreso([p])
    elif c == "pesos":
        filas = []
        for p in persona_arg(a.persona):
            filas += coach.pesos(p)[-a.n:]
        out = "\n".join(f"{x['fecha']} {nombre(x['persona'])}: {coach.num(x['kg'], 2)} kg" + (f", {coach.num(x['grasa'])} % grasa" if x.get("grasa") else "")
                        for x in sorted(filas, key=lambda x: x["fecha"])) or "Sin pesadas."
    elif c == "progreso":
        out = coach.render_progreso(persona_arg(a.persona))
    elif c == "semana":
        out = render_semana(fecha_arg(a.fecha))
    elif c == "revision":
        out = coach.revision(guardar=not a.sin_guardar)
    elif c == "aceptar":
        out = coach.aceptar(persona_arg(a.persona)[0] if a.persona else None)
    elif c == "rechazar":
        out = coach.rechazar()
    elif c == "perfil":
        out = coach.render_perfil(persona_arg(a.persona))
    elif c == "objetivo":
        out = coach.cambiar_objetivo(persona_arg(a.persona)[0], a.meta_kg, a.ritmo, a.kcal, a.suelo, a.entrenos, a.modo, a.meta_final_kg)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
