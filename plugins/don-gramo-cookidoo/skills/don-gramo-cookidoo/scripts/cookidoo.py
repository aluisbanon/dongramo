#!/usr/bin/env python3
"""Don Gramo · Cookidoo: extensión OPCIONAL y NO OFICIAL del plugin don-gramo.

Sube la receta del día a tu cuenta de Cookidoo (Creadas por mí, privada) con las cantidades de
todos sumadas y los pasos guiados para la Thermomix, la añade a Mi semana y busca recetas del
recetario oficial que cuadren con el plan. Usa la librería comunitaria cookidoo-api, que no es de
Vorwerk ni está respaldada por Vorwerk. Thermomix® y Cookidoo® son marcas registradas de Vorwerk.

  receta  --fecha F --comida T [--subir] [--compra]   vista previa; sube solo con --subir
  buscar  --texto T [--fecha F] [--comida T] [--n 12]
  elegir  --n N [--compra]
  probar                                              comprueba la cuenta

Necesita el plugin don-gramo (el núcleo): usa su motor para los menús, las cantidades y el registro.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from nucleo import cargar  # noqa: E402

cargar()
from common import HOME, ahora, hoy, registrar_plugin  # noqa: E402
from dieta import (ALIMENTOS_EXTRA, CFG, DIAS_ES, FOODS, MENU, PERSONAS, REGISTRO, TIPOS,  # noqa: E402
                   _raciones_txt, anadir_cambio, cantidad, comidas_base, comidas_en_casa, dfmt, escribir_json,
                   fecha_arg, kcal_items, leer_json, lunes_de, mac, nombre, nombre_alimento, nombre_corto,
                   nombres, notas_parciales, olla_comun, pasos_del_dia, prot_items, texto_cocinado, texto_olla, tipo_arg)


# --------------------------------------------------------------------------- subir la receta del día
COOKIDOO_PY = HOME / ".venv-cookidoo" / "bin" / "python"
NO_INSTALADO = ("La conexión con Cookidoo aún no está preparada en esta máquina. Desde la carpeta del plugin "
                "don-gramo-cookidoo: `./install.sh instalar` y `./install.sh cuenta`.")
COOKIDOO_MAPA = REGISTRO.parent / "cookidoo.json"
COOKIDOO_ENVIO = REGISTRO.parent / "cookidoo_envio.json"


def _ingrediente_ck(fid, g):
    q = cantidad(fid, g)
    nom = nombre_alimento(fid)
    if q.endswith(("huevo", "huevos")):
        return q
    if q.endswith(("lata", "latas")):
        return f"{q} de {nom}"
    if "(" in q:  # "320 g (2 ud)"
        gramos, ud = q.split(" (", 1)
        return f"{gramos} de {nom} ({ud}"
    return f"{q} de {nom}"


def _cantidad_estructurada(linea):
    """'90 g de cebolla' -> {slot: '90 g', amount: 90, unit: 'g'}; '3 huevos' -> {slot: '3', amount: 3}."""
    m = re.match(r"(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)?\b", linea)
    if not m:
        return None
    d = {"slot": m.group(0).strip(), "amount": float(m.group(1).replace(",", "."))}
    if m.group(2):
        d["unit"] = m.group(2)
    return d


def _claves_alimento(fid):
    largo, corto = nombre_alimento(fid).lower(), nombre_corto(fid)
    claves = {largo, corto}
    primera = corto.split()[0]
    if len(primera) > 3:
        claves.add(primera)
        claves.add(primera + "s")
    return sorted(claves, key=len, reverse=True)


def _trocear_paso(p):
    """Un paso con varias acciones de máquina se parte en una por acción (cada una con su ajuste)."""
    texto, ajs = p["texto"], sorted(p["ajustes"], key=lambda a: p["texto"].find(a["slot"]))
    if len(ajs) <= 1:
        return [p]
    trozos, inicio = [], 0
    for n, a in enumerate(ajs):
        fin = texto.find(a["slot"], inicio) + len(a["slot"])
        if n < len(ajs) - 1:
            punto = texto.find(". ", fin)
            sig = texto.find(ajs[n + 1]["slot"], fin)
            fin = punto + 1 if 0 <= punto < sig else fin
        else:
            fin = len(texto)
        trozo = texto[inicio:fin].strip()
        if trozo:
            trozos.append({"texto": trozo[:1].upper() + trozo[1:], "ajustes": [a]})
        inicio = fin
    return trozos


def _pasos_guiados(pasos, linea_de, en_olla):
    """Al estilo Cookidoo: antes de cada acción, un paso por ingrediente para pesarlo con la báscula."""
    usados, out = set(), []
    candidatos = [fid for fid in linea_de if not en_olla or fid in en_olla]
    for original in pasos:
        for p in _trocear_paso(original):
            texto = p["texto"].lower()
            limite = min((texto.find(a["slot"].lower()) for a in p["ajustes"] if a["slot"].lower() in texto),
                         default=len(texto))
            verbo = "Pesa" if re.search(r"varoma|cestillo|bandeja|recipiente", texto) else "Añade"
            ocupado, hallados = [], []
            for fid in sorted(candidatos, key=lambda x: -max(map(len, _claves_alimento(x)))):
                if fid in usados:
                    continue
                for k in _claves_alimento(fid):
                    m = re.search(r"\b" + re.escape(k) + r"\b", texto)
                    if m and m.start() < limite and not any(m.start() < b and a < m.end() for a, b in ocupado):
                        ocupado.append((m.start(), m.end()))
                        hallados.append((m.start(), fid))
                        break
            for _, fid in sorted(hallados):
                usados.add(fid)
                out.append({"texto": f"{verbo} {linea_de[fid]}.", "ajustes": [], "ingrediente": linea_de[fid]})
            out.append(p)
    return out

def _plato_generico(plato):
    """Quita del nombre los retoques de un día ("sin zanahoria", "+ huevo"): siguen siendo la misma receta."""
    def limpia(m):
        partes = [x for x in m.group(1).split(", ") if not x.startswith(("sin ", "+ "))]
        return f" ({', '.join(partes)})" if partes else ""
    return re.sub(r"\s*\(([^()]*)\)", limpia, plato).strip()


def receta_cookidoo(f, tipo):
    """Receta del día para Cookidoo, con las cantidades de todos los que comen en casa sumadas. Devuelve (datos, error)."""
    from tm_ajustes import ajustes
    casa = comidas_en_casa(f, tipo)
    if not casa:
        return None, f"{tipo} del {dfmt(f)}: nadie come en casa."
    base = next(iter(casa.values()))
    r = MENU["recetas"].get(base.get("receta") or "")
    if not r or not r.get("tm"):
        return None, f"{tipo} del {dfmt(f)} ({base['plato']}) no es una receta de Thermomix."
    if base["receta"] == "natillas":
        return None, "Las natillas se hacen por lotes: súbelas una vez con su receta normal, no por día."
    total = {}
    for c in casa.values():
        for i in c.get("items_aj", []):
            total[i["f"]] = total.get(i["f"], 0) + i["g"]
    pasos = [{"texto": t, "ajustes": ajustes(t)} for t in pasos_del_dia(dict(r, pasos_sin_tm=None), casa.values())]
    en_olla = set()
    for comp in MENU["cocinado"]["recetas"].get(base["receta"]) or []:
        en_olla |= set(comp.get("items", []))
    for c in casa.values():  # alimentos sustituidos cuentan como el original
        en_olla |= {i["f"] for i in c.get("items_aj", []) if i.get("orig") in en_olla or i.get("anadido")}
    segundos = sum(a["time"] for p in pasos for a in p["ajustes"])
    tiempo_total = int(300 * max(1, round((segundos + 600) / 300)))
    consejos = [f"Creada por Don Gramo. Cantidades para {nombres(casa)} del {dfmt(f).lower()}; se actualizan cada vez que la planificáis."]
    if len(casa) > 1:
        for x in olla_comun(casa) or []:
            if "items" in x:
                consejos.append(f"Reparto · {x['c']}: " + ", ".join(f"{nombre(p)} {texto_cocinado(x, p)}" for p in x["g"])
                                + (f" (de la olla: {texto_olla(x)})" if x.get("olla") else ""))
    notas = sorted({n for c in casa.values() for n in c.get("notas", [])})
    if notas:
        consejos.append("Cambios: " + "; ".join(notas) + ".")
    consejos += [n.strip("_") for n in notas_parciales(casa.values())]
    if r.get("nota"):
        consejos.append(r["nota"])
    # Ingredientes (con cantidad estructurada para la báscula) y pasos al estilo Cookidoo:
    # primero los pasos de pesar cada ingrediente, después el paso de la máquina.
    lineas_ing, cantidades = [], []
    for fid, g in total.items():
        if g <= 0:
            continue
        linea = _ingrediente_ck(fid, g) + ("" if not en_olla or fid in en_olla else " (aparte, para acompañar)")
        lineas_ing.append(linea)
        cantidades.append(_cantidad_estructurada(linea))
    pasos = _pasos_guiados(pasos, {fid: lineas_ing[i] for i, fid in enumerate(f2 for f2, g2 in total.items() if g2 > 0)},
                           en_olla)
    plato = _plato_generico(base["plato"])
    nombre_receta = f"{plato} · Don Gramo"
    clave = re.sub(r"\s+", " ", plato.lower()).strip()
    datos = {"clave": clave, "fecha": f.isoformat(), "nombre": nombre_receta[:120],
             "ingredientes": lineas_ing, "cantidades": cantidades,
             "pasos": pasos, "raciones": len(casa), "modelo": CFG["hogar"].get("modelo_thermomix", "TM6"),
             "tiempo_total": tiempo_total, "tiempo_activo": min(900, tiempo_total), "consejos": consejos,
             "calendario": True}
    return datos, None


def _firma(datos):
    """Lo que, si cambia, obliga a actualizar la receta en Cookidoo (sin la fecha)."""
    return json.dumps({k: v for k, v in datos.items() if k not in ("calendario", "fecha", "consejos")},
                      ensure_ascii=False, sort_keys=True)


def _sync(*args):
    import subprocess
    p = subprocess.run([str(COOKIDOO_PY), str(Path(__file__).resolve().parent / "cookidoo_sync.py"), *args],
                       capture_output=True, text=True, timeout=120)
    return json.loads((p.stdout or "").strip().splitlines()[-1])


def cmd_receta(a):
    f = fecha_arg(a.fecha)
    tipo = tipo_arg(a.comida) or ("Comida" if ahora().strftime("%H:%M") < "15:00" and f == hoy() else "Cena")
    datos, error = receta_cookidoo(f, tipo)
    if error:
        return error
    mapa = leer_json(COOKIDOO_MAPA, {})
    previa = mapa.get(datos["clave"])
    firma = _firma(datos)
    igual = bool(previa) and previa.get("firma") == firma
    fecha_nueva = not previa or datos["fecha"] not in previa.get("fechas", [])
    n_guiados = sum(1 for p in datos["pasos"] if p["ajustes"])
    n_pesar = sum(1 for p in datos["pasos"] if p.get("ingrediente"))
    dia = DIAS_ES[f.weekday()].lower()
    if not a.subir:
        lineas = [f"*Para Cookidoo* · {datos['nombre']} ({datos['raciones']} {'ración' if datos['raciones'] == 1 else 'raciones'}, ~{datos['tiempo_total'] // 60} min)",
                  "_Ingredientes (total)_: " + "; ".join(datos["ingredientes"]),
                  f"_Pasos_: {len(datos['pasos'])} — {n_pesar} de pesar con la báscula y {n_guiados} programados en la TM6 (tiempo, temperatura y velocidad)."]
        if igual and not fecha_nueva and not a.compra:
            lineas.append(f"✅ Ya está en Cookidoo tal cual y en Mi semana el {dia}.")
            return "\n".join(lineas)
        if not previa:
            lineas.append(f"Es nueva: irá a *Creadas por mí* (privada) y a *Mi semana* el {dia}.")
        else:
            lineas.append(("Ya la tenéis en Cookidoo: " if igual else "Ya la tenéis en Cookidoo: *actualizo las cantidades* y ")
                          + (f"la añado a *Mi semana* el {dia}." if fecha_nueva else "sigue en Mi semana."))
        if a.compra:
            lineas.append("También añadiré sus ingredientes a la lista de la compra de Cookidoo.")
        comida = tipo.lower() if tipo != "Media mañana" else "media-manana"
        lineas.append(f"\n¿La subo? Responde `/cookidoo {dia} {comida} si`")
        return "\n".join(lineas)
    if not COOKIDOO_PY.exists():
        return NO_INSTALADO
    if igual and not fecha_nueva and not a.compra:
        return f"✅ {datos['nombre']} ya está en Cookidoo tal cual."
    envio = dict(datos, id=(previa or {}).get("id"), compra=bool(a.compra), calendario=fecha_nueva)
    escribir_json(COOKIDOO_ENVIO, envio)
    try:
        res = _sync("subir", str(COOKIDOO_ENVIO))
    except Exception as exc:  # noqa: BLE001
        return f"❌ No he podido hablar con Cookidoo ({type(exc).__name__}). Prueba más tarde o usa `/receta`."
    if not res.get("ok"):
        return f"❌ Cookidoo ha fallado: {res.get('error')}\nMientras tanto tenéis la receta con `/receta`."
    extra = res.get("extra", [])
    fechas = sorted(set((previa or {}).get("fechas", [])) | ({datos["fecha"]} if "calendario" in extra else set()))
    mapa[datos["clave"]] = {"id": res["id"], "firma": firma, "url": res.get("url", ""), "nombre": datos["nombre"],
                            "subida": ahora().isoformat(timespec="seconds"), "fechas": fechas}
    escribir_json(COOKIDOO_MAPA, mapa)
    lineas = [("🔄 Actualizada" if res.get("actualizada") else "✅ Subida") + f" a Cookidoo: *{datos['nombre']}*",
              "Está en *Creadas por mí*" + (f" y en *Mi semana* ({dia})" if "calendario" in extra else "")
              + f". {n_pesar} pasos de pesar y {n_guiados} programados para la TM6."]
    if res.get("nivel") and res["nivel"] != "completo":
        lineas.append(f"⚠️ Cookidoo no aceptó todo el formato guiado; subida en modo «{res['nivel']}».")
    if "compra" in extra:
        lineas.append("Ingredientes añadidos a la lista de la compra de Cookidoo.")
    lineas += [f"⚠️ {x}" for x in extra if "falló" in x]
    return "\n".join(lineas)


# --------------------------------------------------------------------------- recetas oficiales de Cookidoo
COOKIDOO_BUSQUEDA = REGISTRO.parent / "cookidoo_busqueda.json"
PROTEINA_EXTRA = "pechuga de pollo"


def _encaje(nut, objetivo):
    """Raciones para acercarse a las kcal del plato que sustituye; si falta proteína, añade pechuga."""
    kcal0, p0 = objetivo
    extra_g = 0
    for _ in range(3):
        extra_k = mac(PROTEINA_EXTRA, extra_g)[0]
        rac = max(0.5, round((kcal0 - extra_k) / nut["kcal"] * 4) / 4)
        prot = rac * nut["p"] + mac(PROTEINA_EXTRA, extra_g)[1]
        if prot >= 0.8 * p0 or extra_g >= 200:
            break
        falta = 0.9 * p0 - rac * nut["p"]
        extra_g = int(min(200, 10 * round(falta / (FOODS[PROTEINA_EXTRA]["p"] / 100) / 10)))
    kcal = rac * nut["kcal"] + mac(PROTEINA_EXTRA, extra_g)[0]
    return {"raciones": rac, "extra_g": extra_g, "kcal": round(kcal), "p": round(prot),
            "ok": 0.75 * kcal0 <= kcal <= 1.25 * kcal0 and prot >= 0.8 * p0 and rac <= 3}


def cmd_buscar(a):
    f = fecha_arg(a.fecha)
    tipo = tipo_arg(a.comida) or ("Comida" if ahora().strftime("%H:%M") < "15:00" and f == hoy() else "Cena")
    if not COOKIDOO_PY.exists():
        return NO_INSTALADO
    casa = comidas_en_casa(f, tipo) or {p: None for p in PERSONAS}
    objetivo = {p: (kcal_items(c["items"]), prot_items(c["items"]))
                for p in casa for c in comidas_base(f, p) if c["tipo"] == tipo}
    try:
        res = _sync("buscar", a.texto, str(a.n))
    except Exception as exc:  # noqa: BLE001
        return f"❌ No he podido buscar en Cookidoo ({type(exc).__name__})."
    if not res.get("ok"):
        return f"❌ Cookidoo ha fallado: {res.get('error')}"
    opciones = []
    for r in res.get("recetas", []):
        if not r.get("nutricion") or not r["nutricion"].get("kcal"):
            continue
        enc = {p: _encaje(r["nutricion"], objetivo[p]) for p in objetivo}
        opciones.append(dict(r, encaje=enc, ok=all(e["ok"] for e in enc.values())))
    opciones.sort(key=lambda o: (not o["ok"], -o["nutricion"]["p"] / max(o["nutricion"]["kcal"], 1)))
    opciones = opciones[:5]
    escribir_json(COOKIDOO_BUSQUEDA, {"fecha": f.isoformat(), "comida": tipo, "texto": a.texto, "opciones": opciones})
    if not opciones:
        return (f"No encuentro recetas de «{a.texto}» con información nutricional en Cookidoo "
                "(sin ella no puedo cuadrarlas con el plan). Prueba con otras palabras.")
    lineas = [f"*Cookidoo · «{a.texto}»* para la {tipo.lower()} del {dfmt(f).lower()}"]
    for n, o in enumerate(opciones, 1):
        nu = o["nutricion"]
        reparto = " · ".join(f"{nombre(p)} {_raciones_txt(e['raciones'])}" for p, e in o["encaje"].items())
        extra = [f"{nombre(p)} +{e['extra_g']} g de pollo" for p, e in o["encaje"].items() if e["extra_g"]]
        lineas.append(f"\n*{n}. {o['nombre']}* ({o['tiempo'] // 60} min · {round(nu['kcal'])} kcal y P {round(nu['p'])} g por ración)"
                      f"\n   {reparto}" + (f" · para completar proteína: {', '.join(extra)}" if extra else "")
                      + ("" if o["ok"] else "\n   ⚠️ cuadra regular con el plan"))
    lineas.append("\nPara elegir una: `/cookidoo elegir N` (añade `compra` si queréis sus ingredientes en la lista de Cookidoo).")
    return "\n".join(lineas)


def cmd_elegir(a):
    b = leer_json(COOKIDOO_BUSQUEDA, {})
    ops = b.get("opciones", [])
    if not ops:
        return "Primero busca: `/cookidoo buscar merluza cena jueves`."
    if not 1 <= a.n <= len(ops):
        return f"Elige un número del 1 al {len(ops)}."
    o = ops[a.n - 1]
    f, tipo = dt.date.fromisoformat(b["fecha"]), b["comida"]
    nu = o["nutricion"]
    clave = f"{o['nombre'].lower()} (cookidoo)"
    extra = leer_json(ALIMENTOS_EXTRA, {})
    extra[clave] = {"kcal": nu["kcal"], "p": nu["p"], "h": nu["h"], "g": nu["g"], "cat": "Recetas de Cookidoo",
                    "ud": None, "flex": False, "paso": 25, "racion": True, "cookidoo_id": o["id"], "url": o["url"]}
    escribir_json(ALIMENTOS_EXTRA, extra)
    FOODS[clave] = extra[clave]
    enc = o["encaje"]
    items = [{"f": clave, **{p: e["raciones"] * 100 for p, e in enc.items()}}]
    if any(e["extra_g"] for e in enc.values()):
        items.append({"f": PROTEINA_EXTRA, **{p: e["extra_g"] for p, e in enc.items()}})
    anadir_cambio(lunes_de(f), {"tipo": "plato_fijo", "fecha": f.isoformat(), "comida": tipo, "plato": o["nombre"],
                                "receta": None, "origen": f"cookidoo:{o['id']}", "items": items, "nota": "de Cookidoo"})
    total = sum(e["raciones"] for e in enc.values())
    import math
    cocinar = max(1, math.ceil(total - 0.01))
    reparto = ", ".join(f"{nombre(p)} {_raciones_txt(e['raciones'])} (≈ {round(100 * e['raciones'] / total)} %)" for p, e in enc.items())
    lineas = [f"✅ {dfmt(f)} · {tipo}: *{o['nombre']}* (de Cookidoo).",
              f"Cocinad la receta para {cocinar} raciones (en la app se cambian las raciones) y servid: {reparto}."]
    if len(items) > 1:
        lineas.append("Acompañad con pechuga de pollo a la plancha: " +
                      ", ".join(f"{nombre(p)} {e['extra_g']} g" for p, e in enc.items() if e["extra_g"]) + ".")
    if cocinar * 1.0 - total >= 1:
        lineas.append(f"Sobrará algo ({_raciones_txt(cocinar - total)}): para un táper fuera de plan o congelar.")
    try:
        res = _sync("planificar", o["id"], f.isoformat(), *(["compra"] if a.compra else []))
        if res.get("ok"):
            lineas.append("En *Mi semana* de Cookidoo" + (" y sus ingredientes en la lista de la compra de Cookidoo." if "compra" in res.get("extra", []) else "."))
        else:
            lineas.append(f"⚠️ No pude añadirla a Mi semana: {res.get('error')}")
    except Exception as exc:  # noqa: BLE001
        lineas.append(f"⚠️ No pude añadirla a Mi semana ({type(exc).__name__}).")
    lineas.append(o["url"])
    lineas.append("Para volver al plato del menú: `/cambios` y `/deshacer N`.")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Don Gramo · Cookidoo (no oficial)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("receta"); s.add_argument("--fecha"); s.add_argument("--comida")
    s.add_argument("--subir", action="store_true"); s.add_argument("--compra", action="store_true")
    s = sub.add_parser("buscar"); s.add_argument("--texto", required=True); s.add_argument("--fecha")
    s.add_argument("--comida"); s.add_argument("--n", type=int, default=12)
    s = sub.add_parser("elegir"); s.add_argument("--n", type=int, required=True); s.add_argument("--compra", action="store_true")
    sub.add_parser("probar")
    a = ap.parse_args(argv)
    registrar_plugin("don-gramo-cookidoo", AQUI)
    if not PERSONAS:
        print("Aún no hay nadie en el plan de Don Gramo: configúralo primero (/don-gramo:configurar).")
        return 1
    if a.cmd == "receta":
        out = cmd_receta(a)
    elif a.cmd == "buscar":
        out = cmd_buscar(a)
    elif a.cmd == "elegir":
        out = cmd_elegir(a)
    else:
        if not COOKIDOO_PY.exists():
            out = NO_INSTALADO
        else:
            res = _sync("probar")
            out = (f"✅ Cookidoo responde: cuenta {res.get('usuario') or '(sin nombre)'}, "
                   f"{res.get('recetas_propias', 0)} recetas propias.") if res.get("ok") else f"❌ {res.get('error')}"
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
