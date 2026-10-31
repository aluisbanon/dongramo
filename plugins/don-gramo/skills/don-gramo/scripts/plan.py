"""Plan de comidas: menús que rotan, cambios por semana, escalado al objetivo de cada persona,
recortes por extras y reparto de lo cocinado. Solo stdlib (python3 del sistema, 3.9+).

Las cantidades del menú (`g`) son de referencia, para un adulto de ~`referencia.kcal_dia` kcal.
Cada persona las recibe escaladas a su objetivo:
  - proteína, verdura y lácteos (no flexibles) × (kcal persona / kcal referencia) ^ 0,6
  - los flexibles (pan, arroz, pasta, aceite, fruta, frutos secos...) cuadran el total exacto.
Así una persona que come menos recorta sobre todo hidratos y grasas, y mantiene la proteína.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path

from common import STATE, ahora, hoy, load_config, load_menu

MENU = load_menu()
CFG = load_config()
PERSONAS = tuple(CFG["personas"])
DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
HORAS = dict(MENU["horas"], **CFG.get("horas", {}))
TIPOS = list(MENU["horas"])
PRIORIDAD = ["Cena", "Comida", "Merienda", "Media mañana", "Desayuno"]
LOTE = {"natillas"}
FRUTA = {"manzana", "plátano", "mandarina", "kiwi", "pera", "arándanos"}
TODOS = ("todos", "ambos", "los dos", "*")
REF_KCAL = MENU["referencia"]["kcal_dia"]
EXPONENTE_FIJOS = 0.6

REGISTRO = STATE / "registro.jsonl"
SEMANAS = STATE / "semanas.json"
PERFIL = STATE / "perfil.json"
ALIMENTOS_EXTRA = STATE / "alimentos_extra.json"
PREFERENCIAS = STATE / "preferencias.json"


# --------------------------------------------------------------------------- ficheros
def leer_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except json.JSONDecodeError:
        return default


def escribir_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    limpiar_cache()


def leer_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(linea))
        except json.JSONDecodeError:
            pass
    return out


def anadir_jsonl(path: Path, fila: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    limpiar_cache()


def limpiar_cache() -> None:
    for f in (comidas_base, calcular_recortes, perfil):
        f.cache_clear()


# --------------------------------------------------------------------------- alimentos y perfil
FOODS = dict(MENU["foods"])
FOODS.update(leer_json(ALIMENTOS_EXTRA, {}))


def nombre(p: str) -> str:
    return CFG["personas"].get(p, {}).get("nombre", p.capitalize())


def nombres(ps) -> str:
    ns = [nombre(p) for p in ps]
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " y " + ns[-1]


@lru_cache(maxsize=None)
def perfil(p: str) -> dict:
    """Perfil vigente: lo que se guardó al configurar (config.json) y los cambios posteriores (state/perfil.json)."""
    base = dict(CFG["personas"].get(p, {}).get("perfil", {}))
    base.update(leer_json(PERFIL, {}).get(p, {}))
    return base


def guardar_perfil(p: str, cambios: dict) -> dict:
    todo = leer_json(PERFIL, {})
    actual = dict(todo.get(p, {}))
    actual.update(cambios)
    actual.setdefault("historial", [])
    actual["historial"] = (actual["historial"] + [{"fecha": hoy().isoformat(), **{k: v for k, v in cambios.items() if k != "historial"}}])[-30:]
    todo[p] = actual
    escribir_json(PERFIL, todo)
    return dict(perfil(p))


def extra_diario(p: str) -> list:
    """Lo que la persona toma cada día fuera del menú (p. ej. un batido de proteína)."""
    return [x for x in CFG["personas"].get(p, {}).get("extra_diario", []) if x.get("f") in FOODS]


def mac(f: str, g: float) -> list:
    x = FOODS[f]
    return [x["kcal"] * g / 100, x["p"] * g / 100, x["h"] * g / 100, x["g"] * g / 100]


def suma(listas) -> list:
    t = [0.0, 0.0, 0.0, 0.0]
    for v in listas:
        for i in range(4):
            t[i] += v[i]
    return t


def kcal_items(items) -> float:
    return sum(mac(i["f"], i["g"])[0] for i in items)


def prot_items(items) -> float:
    return sum(mac(i["f"], i["g"])[1] for i in items)


def buscar_alimento(texto: str) -> str | None:
    t = texto.lower().strip()
    if t in FOODS:
        return t
    cand = [f for f in FOODS if t in f.lower()]
    if len(cand) == 1:
        return cand[0]
    exactos = [f for f in cand if f.lower().split(" (")[0] == t]
    return exactos[0] if len(exactos) == 1 else (min(cand, key=len) if cand else None)


# --------------------------------------------------------------------------- semanas y menús
def lunes_de(fecha: dt.date) -> dt.date:
    return fecha - dt.timedelta(days=fecha.weekday())


def semana_arg(s: str | None) -> dt.date:
    if not s or s == "actual":
        return lunes_de(hoy())
    if s in ("proxima", "próxima", "siguiente"):
        return lunes_de(hoy()) + dt.timedelta(days=7)
    return lunes_de(dt.date.fromisoformat(s))


def config_semana(lunes: dt.date) -> dict:
    sem = leer_json(SEMANAS, {}).get(lunes.isoformat(), {})
    if not sem.get("menu"):
        rot = MENU["rotacion"]
        n = (lunes - dt.date.fromisoformat(rot["inicio"])).days // 7
        sem = dict(sem)
        sem["menu"] = rot["orden"][n % len(rot["orden"])]
    sem.setdefault("cambios", [])
    return sem


def guardar_semana(lunes: dt.date, sem: dict) -> None:
    todo = leer_json(SEMANAS, {})
    todo[lunes.isoformat()] = sem
    escribir_json(SEMANAS, todo)


def comida_de_menu(menu_id: str, dia: int, tipo: str) -> dict:
    for m in MENU["menus"][menu_id]["dias"][dia]["comidas"]:
        if m["tipo"] == tipo:
            return m
    raise KeyError(tipo)


def catalogo(tipo: str | None = None) -> list:
    """Todos los platos validados de los menús: id = MENU-dia-tipo (p. ej. B-3-Comida)."""
    out, vistos = [], set()
    for mid, menu in MENU["menus"].items():
        for d, dia in enumerate(menu["dias"]):
            for m in dia["comidas"]:
                if tipo and m["tipo"] != tipo:
                    continue
                if (m["tipo"], m["plato"]) in vistos:
                    continue
                vistos.add((m["tipo"], m["plato"]))
                out.append({"id": f"{mid}-{d}-{m['tipo']}", "tipo": m["tipo"], "plato": m["plato"], "receta": m["receta"]})
    return out


def comida_por_id(cid: str) -> dict:
    mid, d, tipo = cid.split("-", 2)
    return comida_de_menu(mid, int(d), tipo)


def es_todos(p) -> bool:
    return not p or p in TODOS


def _aplica(cambio: dict, fecha: dt.date, tipo: str, persona: str) -> bool:
    if cambio.get("fecha") and cambio["fecha"] != fecha.isoformat():
        return False
    if cambio.get("comida") and cambio["comida"] != tipo:
        return False
    if not es_todos(cambio.get("persona")) and cambio["persona"] != persona:
        return False
    return True


def gramos_equivalentes(de: str, a: str, g: float) -> int:
    """Misma proteína si el alimento es proteico; si no, mismas kcal."""
    if FOODS[de]["p"] >= 8 and FOODS[a]["p"] >= 8:
        nuevo = g * FOODS[de]["p"] / FOODS[a]["p"]
    else:
        nuevo = g * FOODS[de]["kcal"] / max(FOODS[a]["kcal"], 1)
    paso = FOODS[a].get("paso", 5)
    return int(paso * round(nuevo / paso))


# --------------------------------------------------------------------------- preferencias permanentes
def preferencias() -> list:
    """Sustituciones fijas (alergias, gustos): [{de, a, persona}] que se aplican todas las semanas."""
    return leer_json(PREFERENCIAS, [])


# --------------------------------------------------------------------------- plan base del día
def flex_escalable(f: str, receta: str | None) -> bool:
    if receta in LOTE:
        return f in FRUTA
    return FOODS[f]["flex"]


def paso_de(f: str) -> float:
    ud = FOODS[f].get("ud")
    if f in FRUTA and ud:
        return ud / 2
    return FOODS[f].get("paso", 5)


def redondear(f: str, g: float) -> int:
    p = paso_de(f)
    return max(0, int(round(p * round(g / p))))


def redondear_fijo(f: str, g: float) -> int:
    """Alimentos que no se escalan finos: los que van por unidades (huevo, lata) a unidades enteras."""
    ud = FOODS[f].get("ud")
    if ud and f not in FRUTA:
        return int(ud * max(1, round(g / ud)))
    return redondear(f, g)


PLATO_TIPOS = ("cambiar_plato", "plato_nuevo", "plato_fijo")


def plato_slot(fecha: dt.date, tipo: str) -> dict:
    """Plato de una franja (menú + cambios de plato), sin cambios de ingrediente.
    items: [{f, g}] en gramos de referencia; pueden traer gramos fijos por persona ({f, ana: 120})."""
    sem = config_semana(lunes_de(fecha))
    dia = fecha.weekday()
    m = comida_de_menu(sem["menu"], dia, tipo)
    out = {"plato": m["plato"], "receta": m["receta"], "origen": f"{sem['menu']}-{dia}-{tipo}",
           "items": [dict(it) for it in m["items"]]}
    for c in sem["cambios"]:
        if c["tipo"] not in PLATO_TIPOS or c.get("fecha") != fecha.isoformat() or c.get("comida") != tipo:
            continue
        if c["tipo"] == "cambiar_plato":
            o = comida_por_id(c["opcion"])
            out = {"plato": o["plato"], "receta": o["receta"], "origen": c["opcion"],
                   "items": [dict(it) for it in o["items"]]}
        else:
            out = {"plato": c["plato"], "receta": c.get("receta"), "origen": c.get("origen", "nuevo"),
                   "items": [dict(x) for x in c["items"]]}
    return out


def _sufijo(plato: str, texto: str) -> str:
    if plato.endswith(")") and " (" in plato:
        return plato[:-1] + ", " + texto + ")"
    return f"{plato} ({texto})"


def _cambiar_nombre(plato: str, de: str, a: str) -> str:
    viejo, nuevo = nombre_corto(de), nombre_corto(a)
    if re.search(re.escape(viejo), plato, flags=re.I):
        plato = re.sub(re.escape(viejo), nuevo, plato, count=1, flags=re.I)
        return plato[:1].upper() + plato[1:]
    return _sufijo(plato, f"con {nuevo}")


def factor_fijos(persona: str, ref_items: list) -> float:
    """Cuánto se escalan proteína, lácteos y verdura para esta persona (1 = adulto de referencia).
    Adultos: (kcal persona / kcal referencia) ^ 0,6, así quien come menos conserva la proteína.
    Menores (modo "crecer"): lo justo para que la proteína ronde el 20 % de sus kcal; el resto
    lo ponen hidratos, fruta y grasas buenas."""
    pf = perfil(persona)
    objetivo = pf.get("objetivo_kcal") or REF_KCAL
    diario = sum(mac(x["f"], x["g"])[0] for x in extra_diario(persona))
    kcal_ref = sum(mac(x["f"], x["g"])[0] for x in ref_items) or 1
    r = max(0.3, (objetivo - diario) / kcal_ref)
    if pf.get("modo") == "crecer":
        p_fijos = sum(mac(x["f"], x["g"])[1] for x in ref_items if not FOODS[x["f"]]["flex"]) or 1
        p_flex = sum(mac(x["f"], x["g"])[1] for x in ref_items if FOODS[x["f"]]["flex"]) * r
        return max(0.3, min(1.2, (0.20 * objetivo / 4 - p_flex) / p_fijos))
    nf = max(0.45, min(1.35, r ** EXPONENTE_FIJOS))
    return 1.0 if abs(nf - 1) < 0.05 else nf  # cerca de la referencia: las cantidades del menú tal cual


def gramos_de(item: dict, persona: str, nf: float) -> tuple:
    """(gramos, explícito) de un ingrediente para una persona."""
    if persona in item:
        return item[persona], True
    if "g" not in item:
        return 0, True
    return item["g"] * nf, False


@lru_cache(maxsize=None)
def _comidas_base(fiso: str, persona: str) -> tuple:
    fecha = dt.date.fromisoformat(fiso)
    lunes = lunes_de(fecha)
    sem = config_semana(lunes)
    slots = [plato_slot(fecha, tipo) for tipo in TIPOS]
    nf = factor_fijos(persona, [x for s in slots for x in s["items"] if "g" in x])
    prefs = [p for p in preferencias() if es_todos(p.get("persona")) or p.get("persona") == persona]
    comidas = []
    for tipo, s in zip(TIPOS, slots):
        plato, receta, origen = s["plato"], s["receta"], s["origen"]
        items = []
        for x in s["items"]:
            g, explicito = gramos_de(x, persona, nf)
            if g > 0:
                items.append({"f": x["f"], "g": g if explicito else (g if FOODS[x["f"]]["flex"] else redondear_fijo(x["f"], g))})
        notas = []
        # Preferencias permanentes (alergias, lo que no les gusta), antes que los cambios de la semana
        for pr in prefs:
            if any(i["f"] == pr["de"] for i in items):
                items = [{"f": pr["a"], "g": gramos_equivalentes(pr["de"], pr["a"], i["g"]), "orig": pr["de"]}
                         if i["f"] == pr["de"] else i for i in items]
                plato = _cambiar_nombre(plato, pr["de"], pr["a"])
        # Cambios de ingrediente de la semana, en el orden en que se pidieron
        for c in sem["cambios"]:
            if c["tipo"] not in ("sustituir", "quitar", "cantidad", "anadir") or not _aplica(c, fecha, tipo, persona):
                continue
            if c["tipo"] == "sustituir":
                if not any(i["f"] == c["de"] for i in items):
                    continue
                items = [{"f": c["a"], "g": gramos_equivalentes(c["de"], c["a"], i["g"]), "orig": i.get("orig") or c["de"]}
                         if i["f"] == c["de"] else i for i in items]
                notas.append(f"{nombre_corto(c['de'])} → {nombre_corto(c['a'])}")
                plato = _cambiar_nombre(plato, c["de"], c["a"])
            elif c["tipo"] == "quitar":
                if not any(i["f"] == c["f"] for i in items):
                    continue
                items = [i for i in items if i["f"] != c["f"]]
                notas.append(f"sin {nombre_corto(c['f'])}")
                plato = _sufijo(plato, f"sin {nombre_corto(c['f'])}")
            elif c["tipo"] == "cantidad":
                g = gramos_cambio(c, persona, nf)
                if g is None:
                    continue
                if any(i["f"] == c["f"] for i in items):
                    items = [dict(i, g=g, fijo=True) if i["f"] == c["f"] else i for i in items]
                else:
                    items.append({"f": c["f"], "g": g, "fijo": True})
                items = [i for i in items if i["g"] > 0]
                notas.append(f"{nombre_corto(c['f'])} {round(g)} g" + ("" if "*" in c["g"] else f" ({nombre(persona)})"))
            elif c["tipo"] == "anadir":
                g = gramos_cambio(c, persona, nf) or 0
                if g <= 0:
                    continue
                if any(i["f"] == c["f"] for i in items):
                    items = [dict(i, g=i["g"] + g, fijo=True) if i["f"] == c["f"] else i for i in items]
                else:
                    items.append({"f": c["f"], "g": g, "fijo": True, "anadido": True})
                notas.append(f"+ {nombre_corto(c['f'])}")
                plato = _sufijo(plato, f"+ {nombre_corto(c['f'])}")
        comidas.append({"tipo": tipo, "plato": plato, "receta": receta, "origen": origen, "items": items, "notas": notas})
    # Ajuste fino al objetivo diario de la persona (solo alimentos flexibles)
    diario = sum(mac(x["f"], x["g"])[0] for x in extra_diario(persona))
    objetivo = perfil(persona).get("objetivo_kcal")
    if objetivo:
        actual = sum(kcal_items(c["items"]) for c in comidas) + diario
        flex = sum(mac(i["f"], i["g"])[0] for c in comidas for i in c["items"] if (flex_escalable(i["f"], c["receta"]) and not i.get("fijo")))
        factor = max(0.6, min(1.6, 1 + (objetivo - actual) / flex)) if flex > 0 and abs(objetivo - actual) > 25 else 1.0
        aceite_min = CFG["reajuste"]["aceite_minimo_g"]
        for c in comidas:
            for i in c["items"]:
                if flex_escalable(i["f"], c["receta"]) and not i.get("fijo"):
                    g = i["g"] * factor
                    if i["f"].startswith("aceite"):
                        g = max(min(aceite_min, i["g"]), g)
                    i["g"] = redondear(i["f"], g)
    for c in comidas:
        for i in c["items"]:
            i["g"] = round(i["g"]) if isinstance(i["g"], float) and not FOODS[i["f"]].get("racion") else i["g"]
    return tuple(json.dumps(c, ensure_ascii=False) for c in comidas)


def gramos_cambio(c: dict, persona: str, nf: float):
    """Gramos de un cambio de cantidad/añadido: por persona, o '*' (referencia, escalada a cada uno)."""
    g = c["g"]
    if persona in g:
        return g[persona]
    if "*" in g:
        return redondear_fijo(c["f"], g["*"] * nf)
    return None


def comidas_base(fecha: dt.date, persona: str) -> list:
    return [json.loads(x) for x in _comidas_base(fecha.isoformat(), persona)]


comidas_base.cache_clear = _comidas_base.cache_clear  # type: ignore[attr-defined]


def nombre_corto(f: str) -> str:
    return f.split(" (")[0].replace("pechuga de ", "").replace(" magra para guisar", "").replace(" peladas", "").lower()


# --------------------------------------------------------------------------- registro de extras
def eventos(persona: str | None = None) -> list:
    filas = leer_jsonl(REGISTRO)
    borrados = {f["id"] for f in filas if f.get("tipo") == "_borrado"}
    out = [f for f in filas if f.get("tipo") != "_borrado" and f.get("id") not in borrados]
    return [f for f in out if not persona or f["persona"] == persona]


def registrar(persona: str, tipo: str, desc: str, kcal: float, fecha: dt.date, comida=None, hora=None,
              p=None, h=None, g=None) -> dict:
    ev = {"id": uuid.uuid4().hex[:6], "ts": ahora().isoformat(timespec="seconds"), "fecha": fecha.isoformat(),
          "persona": persona, "tipo": tipo, "comida": comida, "desc": desc, "kcal": round(kcal or 0),
          "p": p, "h": h, "g": g, "hora": hora or (ahora().strftime("%H:%M") if fecha == hoy() else None)}
    anadir_jsonl(REGISTRO, ev)
    return ev


def indice_comida(ev: dict) -> int:
    if ev.get("comida") in TIPOS:
        return TIPOS.index(ev["comida"])
    hora = ev.get("hora") or "23:59"
    idx = 0
    for i, t in enumerate(TIPOS):
        if HORAS[t] <= hora:
            idx = i
    return idx


# --------------------------------------------------------------------------- recortes por extras
def flex_max(items, receta=None) -> float:
    frac = CFG["reajuste"]["recorte_max_alimento_flexible"]
    aceite_min = CFG["reajuste"]["aceite_minimo_g"]
    total = 0.0
    for i in items:
        if not flex_escalable(i["f"], receta) or i.get("fijo"):
            continue
        quitar = i["g"] * frac
        if i["f"].startswith("aceite"):
            quitar = min(quitar, max(0.0, i["g"] - aceite_min))
        total += mac(i["f"], quitar)[0]
    return total


def aplicar_recorte(items, kcal_cut: float, receta=None):
    cap = flex_max(items, receta)
    if cap <= 0 or kcal_cut <= 0:
        return [dict(i) for i in items], 0.0
    r = min(1.0, kcal_cut / cap)
    frac = CFG["reajuste"]["recorte_max_alimento_flexible"]
    aceite_min = CFG["reajuste"]["aceite_minimo_g"]
    out = []
    for i in items:
        n = dict(i)
        if flex_escalable(i["f"], receta) and not i.get("fijo"):
            quitar = i["g"] * frac
            if i["f"].startswith("aceite"):
                quitar = min(quitar, max(0.0, i["g"] - aceite_min))
            n["g"] = redondear(i["f"], i["g"] - quitar * r)
            if n["g"] != i["g"]:
                n["antes"] = i["g"]
        out.append(n)
    return out, kcal_items(items) - kcal_items(out)


def _limites(p: str) -> dict:
    """Topes del reajuste. Por defecto, proporcionales al objetivo (≈18 % hoy, ≈14 % cada día siguiente)."""
    pf, c = perfil(p), CFG["personas"].get(p, {})
    k = pf.get("objetivo_kcal") or REF_KCAL
    return {"suelo": pf.get("suelo_kcal", 1200),
            "hoy": c.get("recorte_max_hoy") or int(round(0.18 * k / 50) * 50),
            "futuro": c.get("recorte_max_dia_futuro") or int(round(0.14 * k / 50) * 50)}


@lru_cache(maxsize=None)
def calcular_recortes(persona: str, hasta_iso: str | None = None):
    lim = _limites(persona)
    adelante = CFG["reajuste"]["dias_hacia_delante"]
    por_dia: dict = {}
    for e in eventos(persona):
        por_dia.setdefault(e["fecha"], []).append(e)
    recortes: dict = {}
    recorte_dia: dict = {}
    informe = []

    def sustituidas(fiso):
        return {e["comida"] for e in por_dia.get(fiso, []) if e["tipo"] in ("fuera", "saltada") and e.get("comida")}

    def capacidad(fecha, tipos, tope, origen):
        fiso = fecha.isoformat()
        base = comidas_base(fecha, persona)
        libres = [m for m in base if m["tipo"] in tipos and m["tipo"] not in sustituidas(fiso)]
        libres.sort(key=lambda m: PRIORIDAD.index(m["tipo"]))
        disponible = max(0.0, tope - recorte_dia.get(fiso, 0.0))
        if not origen:
            plan = sum(kcal_items(m["items"]) for m in base) - recorte_dia.get(fiso, 0.0)
            disponible = min(disponible, max(0.0, plan - lim["suelo"]))
        out = []
        for m in libres:
            c = max(0.0, flex_max(m["items"], m["receta"]) - recortes.get((fiso, m["tipo"]), 0.0))
            k = min(c, disponible)
            if k >= 15:
                out.append((m["tipo"], k))
                disponible -= k
        return out

    for fiso in sorted(por_dia):
        if hasta_iso and fiso > hasta_iso:
            continue
        fecha = dt.date.fromisoformat(fiso)
        base = {m["tipo"]: m for m in comidas_base(fecha, persona)}
        exceso, pos = 0.0, 0
        for e in por_dia[fiso]:
            pos = max(pos, indice_comida(e))
            plan = kcal_items(base[e["comida"]]["items"]) if e.get("comida") in base else 0
            exceso += {"extra": e["kcal"], "fuera": e["kcal"] - plan, "saltada": -plan}.get(e["tipo"], 0)
        fila = {"fecha": fiso, "exceso": round(exceso), "compensado_hoy": 0, "repartido": [], "pendiente": 0}
        if exceso >= CFG["reajuste"]["umbral_kcal"]:
            resto = exceso
            for t, k in capacidad(fecha, TIPOS[pos + 1:], lim["hoy"], True):
                k = min(k, resto)
                recortes[(fiso, t)] = recortes.get((fiso, t), 0.0) + k
                recorte_dia[fiso] = recorte_dia.get(fiso, 0.0) + k
                resto -= k
                fila["compensado_hoy"] += round(k)
            for d in range(1, adelante + 1):
                if resto <= 1:
                    break
                f2 = fecha + dt.timedelta(days=d)
                puesto = 0.0
                for t, k in capacidad(f2, TIPOS, lim["futuro"], False):
                    k = min(k, resto - puesto)
                    if k < 15:
                        break
                    recortes[(f2.isoformat(), t)] = recortes.get((f2.isoformat(), t), 0.0) + k
                    recorte_dia[f2.isoformat()] = recorte_dia.get(f2.isoformat(), 0.0) + k
                    puesto += k
                if puesto > 0:
                    fila["repartido"].append({"fecha": f2.isoformat(), "kcal": round(puesto)})
                    resto -= puesto
            fila["pendiente"] = round(max(0.0, resto))
        informe.append(fila)
    return recortes, informe


def plan_dia(fecha: dt.date, persona: str) -> dict:
    recortes, _ = calcular_recortes(persona)
    fiso = fecha.isoformat()
    evs = [e for e in eventos(persona) if e["fecha"] == fiso]
    fuera = {e["comida"]: e for e in evs if e["tipo"] in ("fuera", "saltada") and e.get("comida")}
    comidas = []
    for m in comidas_base(fecha, persona):
        c = dict(m)
        if m["tipo"] in fuera:
            e = fuera[m["tipo"]]
            c.update(sustituida=e, items_aj=[], recorte=0)
            c["mac"] = [e.get("kcal") or 0, e.get("p") or 0, e.get("h") or 0, e.get("g") or 0] if e["tipo"] == "fuera" else [0, 0, 0, 0]
        else:
            items, quitado = aplicar_recorte(m["items"], recortes.get((fiso, m["tipo"]), 0.0), m["receta"])
            c.update(items_aj=items, recorte=round(quitado), mac=suma(mac(i["f"], i["g"]) for i in items))
        comidas.append(c)
    extras = [e for e in evs if e["tipo"] == "extra"]
    diario = extra_diario(persona)
    m_extra = suma([mac(x["f"], x["g"]) for x in diario] +
                   [[e["kcal"], e.get("p") or 0, e.get("h") or 0, e.get("g") or 0] for e in extras])
    total = suma([c["mac"] for c in comidas] + [m_extra])
    base_total = sum(kcal_items(m["items"]) for m in comidas_base(fecha, persona)) + sum(mac(x["f"], x["g"])[0] for x in diario)
    return {"fecha": fiso, "persona": persona, "comidas": comidas, "extras": extras, "diario": diario,
            "total": total, "base_kcal": base_total}


# --------------------------------------------------------------------------- cocinado
def escala_raciones(personas) -> float:
    """Las recetas están escritas para 2 raciones de adulto: cuánto hay que multiplicar el agua o el caldo."""
    total = sum(perfil(p).get("objetivo_kcal") or REF_KCAL for p in personas)
    return max(0.5, total / (2 * REF_KCAL))


def cocinado(receta: str, items_por_persona: dict):
    """Reparto de lo cocinado en una olla entre los que comen.
    items_por_persona: {persona: items_aj}. Devuelve componentes con g = {persona: gramos cocinados}
    y pct = {persona: % de la olla}."""
    comps = MENU["cocinado"]["recetas"].get(receta)
    if not comps or not items_por_persona:
        return None
    ps = list(items_por_persona)

    def mapa(items):
        d = {}
        for i in items:
            d[i["f"]] = d.get(i["f"], 0) + i["g"]
            if i.get("orig"):  # alimento sustituido: cuenta en el componente del original
                d[i["orig"]] = d.get(i["orig"], 0) + 0
                d.setdefault("_alias", {})[i["orig"]] = i["f"]
        return d

    mapas = {p: mapa(items_por_persona[p]) for p in ps}
    out = []
    for c in comps:
        if "fijo" in c:
            out.append({"c": c["c"], "g": {p: c["fijo"] for p in ps}, "pct": {p: round(100 / len(ps)) for p in ps},
                        "ud": False, "olla": False})
            continue
        fac = dict(MENU["cocinado"]["factores"])
        fac.update(c.get("f", {}))
        nombres_c = list(c["items"])
        for g in mapas.values():
            for orig, nuevo in g.get("_alias", {}).items():
                if orig in nombres_c and nuevo not in nombres_c:
                    nombres_c.append(nuevo)
        w = {p: sum(mapas[p].get(f, 0) * fac.get(f, 1.0) for f in nombres_c) for p in ps}
        agua = c.get("agua", 0) * escala_raciones(ps) * (1 - c.get("evap", 0))
        if agua:
            ref = c.get("reparto")
            base = {p: (mapas[p].get(ref, 0) if ref else sum(mapas[p].get(f, 0) for f in nombres_c)) for p in ps}
            tot = sum(base.values())
            for p in ps:
                w[p] += agua * (base[p] / tot if tot else 1 / len(ps))
        total = sum(w.values())
        if total <= 0:
            continue
        etiqueta = c["c"]
        for g in mapas.values():
            for orig, nuevo in g.get("_alias", {}).items():
                if orig in c["items"]:
                    etiqueta = re.sub(re.escape(nombre_corto(orig)), nombre_corto(nuevo), etiqueta, count=1, flags=re.I)
        etiqueta = etiqueta[:1].upper() + etiqueta[1:]
        out.append({"c": etiqueta, "g": {p: int(5 * round(w[p] / 5)) for p in ps},
                    "pct": {p: round(100 * w[p] / total) for p in ps}, "ud": bool(c.get("ud")),
                    "olla": bool(c.get("olla")), "items": nombres_c})
    return out


# --------------------------------------------------------------------------- compra
CATS = ["Fruta y verdura", "Carne", "Pescado", "Charcutería", "Huevos y lácteos", "Panadería y cereales",
        "Legumbres y conservas", "Despensa", "Suplementos"]


def lista_compra(lunes: dt.date) -> list:
    total: dict = {}
    for d in range(7):
        f = lunes + dt.timedelta(days=d)
        for p in PERSONAS:
            for m in comidas_base(f, p):
                for i in m["items"]:
                    total[i["f"]] = total.get(i["f"], 0) + i["g"]
            for x in extra_diario(p):
                total[x["f"]] = total.get(x["f"], 0) + x["g"]
    cats: dict = {}
    for f, g in total.items():
        cats.setdefault(FOODS[f]["cat"], []).append((f, g))
    return [(c, sorted(cats[c])) for c in CATS + sorted(set(cats) - set(CATS)) if c in cats]
