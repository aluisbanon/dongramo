"""Entrenador: histórico de pesos, tendencia, progreso y revisión semanal de calorías.

Cómo decide (todo determinista, sin modelo):
  - Tendencia: recta de regresión del peso de los últimos 28 días (mín. 3 pesadas en 10+ días).
  - Mantenimiento: arranca con una estimación y se recalibra con lo que coméis según el registro
    y lo que baja el peso de verdad:  mant ≈ ingesta media + (kg perdidos/semana × 1.100).
    1 kg de grasa ≈ 7.700 kcal → 1.100 kcal/día por cada kg/semana.
  - Objetivo de kcal = mantenimiento − ritmo deseado × 1.100, sin bajar del suelo.
  - Cambios de ±150 kcal como máximo por semana, y solo si la diferencia es de 75 kcal o más.
  - Al llegar a la meta propone pasar a mantenimiento.
  - Nunca aplica nada solo: deja una propuesta que se acepta con /aceptar.
"""
from __future__ import annotations

import datetime as dt

from common import STATE, hoy
from plan import (PERSONAS, anadir_jsonl, escribir_json, guardar_perfil, leer_json, leer_jsonl, nombre, perfil,
                  plan_dia)

PESOS = STATE / "pesos.jsonl"
PROPUESTA = STATE / "propuesta.json"
KCAL_POR_KG_SEM = 1100
CHISPAS = "▁▂▃▄▅▆▇█"


def num(x, d=1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


# --------------------------------------------------------------------------- pesos
def pesos(persona: str) -> list:
    por_fecha = {}
    for fila in leer_jsonl(STATE / "historico_pesos.jsonl") + leer_jsonl(PESOS):
        if fila.get("persona") == persona and fila.get("kg"):
            por_fecha[fila["fecha"]] = fila  # lo registrado después pisa al histórico
    return [por_fecha[k] for k in sorted(por_fecha)]


def anotar_peso(persona: str, kg: float, fecha: dt.date, grasa=None, visceral=None, musculo=None, fuente="chat") -> dict:
    fila = {"fecha": fecha.isoformat(), "persona": persona, "kg": kg, "grasa": grasa, "visceral": visceral,
            "musculo": musculo, "fuente": fuente}
    anadir_jsonl(PESOS, fila)
    return fila


def tendencia(persona: str, hasta: dt.date | None = None, dias: int = 28) -> dict | None:
    hasta = hasta or hoy()
    serie = [p for p in pesos(persona) if p["fecha"] <= hasta.isoformat()]
    for ventana in (dias, dias + 14):
        desde = (hasta - dt.timedelta(days=ventana)).isoformat()
        pts = [(dt.date.fromisoformat(p["fecha"]), p["kg"]) for p in serie if p["fecha"] >= desde]
        if len(pts) >= 3 and (pts[-1][0] - pts[0][0]).days >= 10:
            break
    else:
        return None
    xs = [(d - hasta).days for d, _ in pts]
    ys = [k for _, k in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    pendiente = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    ajustado = my + pendiente * (0 - mx)
    return {"kg_sem": pendiente * 7, "kg_hoy": ajustado, "n": n, "desde": pts[0][0].isoformat(),
            "ultimo": serie[-1] if serie else None}


def medias_semanales(persona: str, semanas: int = 12) -> list:
    lunes = hoy() - dt.timedelta(days=hoy().weekday())
    out = []
    for s in range(semanas - 1, -1, -1):
        ini = lunes - dt.timedelta(days=7 * s)
        fin = ini + dt.timedelta(days=6)
        kgs = [p["kg"] for p in pesos(persona) if ini.isoformat() <= p["fecha"] <= fin.isoformat()]
        out.append(sum(kgs) / len(kgs) if kgs else None)
    return out


def chispas(valores: list) -> str:
    v = [x for x in valores if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    return "".join("·" if x is None else CHISPAS[0 if hi == lo else round((x - lo) / (hi - lo) * 7)] for x in valores)


def render_progreso(personas=PERSONAS) -> str:
    lineas = ["*Progreso*"]
    for p in personas:
        serie = pesos(p)
        pf = perfil(p)
        if not serie:
            lineas.append(f"\n*{nombre(p)}*: sin pesadas. Manda una captura de la báscula o dime tu peso.")
            continue
        ult, prim = serie[-1], serie[0]
        t = tendencia(p)
        lineas.append(f"\n*{nombre(p)}* · {num(ult['kg'], 2)} kg ({ult['fecha'][8:]}/{ult['fecha'][5:7]})"
                      + (f" · grasa {num(ult['grasa'])} %" if ult.get("grasa") else ""))
        lineas.append(f"Desde el {prim['fecha'][8:]}/{prim['fecha'][5:7]}/{prim['fecha'][2:4]}: "
                      f"{'+' if ult['kg'] - prim['kg'] >= 0 else '−'}{num(abs(ult['kg'] - prim['kg']))} kg")
        if t:
            ritmo = t["kg_sem"]
            estado = "bajando" if ritmo < -0.1 else ("subiendo" if ritmo > 0.1 else "estable")
            lineas.append(f"Tendencia 4 semanas: {'+' if ritmo >= 0 else '−'}{num(abs(ritmo), 2)} kg/semana ({estado})")
        meta = pf.get("meta_kg")
        if meta:
            falta = ult["kg"] - meta
            if falta <= 0:
                lineas.append(f"🎯 Meta de {num(meta)} kg alcanzada.")
            else:
                txt = f"Meta {num(meta)} kg: faltan {num(falta)} kg"
                if t and t["kg_sem"] < -0.05:
                    sem = falta / -t["kg_sem"]
                    fecha = hoy() + dt.timedelta(weeks=sem)
                    txt += f" · a este ritmo, ~{round(sem)} semanas ({fecha.day}/{fecha.month})"
                lineas.append(txt)
        sp = chispas(medias_semanales(p))
        if sp:
            lineas.append(f"Últimas 12 semanas: {sp}")
        if (hoy() - dt.date.fromisoformat(ult["fecha"])).days > 7 and pf.get("modo") != "crecer":
            lineas.append("⚖️ Hace más de una semana de la última pesada.")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- revisión semanal
def ingesta_media(persona: str, dias: int = 14) -> tuple:
    desde = max(dt.date.fromisoformat(perfil(persona).get("desde", hoy().isoformat())), hoy() - dt.timedelta(days=dias))
    totales = []
    d = desde
    while d < hoy():
        totales.append(plan_dia(d, persona)["total"][0])
        d += dt.timedelta(days=1)
    return (sum(totales) / len(totales), len(totales)) if totales else (None, 0)


def evaluar(persona: str) -> dict:
    pf = perfil(persona)
    actual = pf["objetivo_kcal"]
    mant = pf.get("mantenimiento_kcal", actual + 450)
    suelo = pf.get("suelo_kcal", 1200)
    res = {"persona": persona, "actual": actual, "nuevo": actual, "mant": mant, "notas": [], "propone": False}
    if pf.get("modo") == "crecer":
        res["notas"].append("En edad de crecimiento: el plan no busca bajar de peso y no se toca.")
        return res
    serie = pesos(persona)
    if not serie or (hoy() - dt.date.fromisoformat(serie[-1]["fecha"])).days > 10:
        res["notas"].append("No hay pesada en los últimos 10 días: sin datos no cambio nada.")
        return res
    t = tendencia(persona)
    if not t:
        res["notas"].append("Faltan pesadas para ver la tendencia (hacen falta 3 en al menos 10 días).")
        return res
    ritmo_real = -t["kg_sem"]  # positivo = pierde
    res["ritmo_real"] = ritmo_real
    ingesta, ndias = ingesta_media(persona)
    if ingesta and ndias >= 10:
        estimado = ingesta + ritmo_real * KCAL_POR_KG_SEM
        nuevo_mant = 0.5 * mant + 0.5 * estimado
        nuevo_mant = max(mant - 200, min(mant + 200, nuevo_mant))
        res["notas"].append(f"Comiendo ~{round(ingesta)} kcal y perdiendo {num(ritmo_real, 2)} kg/sem, "
                            f"el mantenimiento real ronda las {round(estimado)} kcal.")
        mant = round(nuevo_mant / 10) * 10
        res["mant"] = mant
    else:
        res["notas"].append(f"Aún hay pocos días registrados ({ndias}); uso el mantenimiento estimado de {mant} kcal.")
    meta = pf.get("meta_kg")
    if pf.get("modo") == "mantener" or (meta and t["kg_hoy"] <= meta):
        deseado = mant
        res["modo"] = "mantener"
        if pf.get("modo") != "mantener":
            res["notas"].append(f"🎯 Has llegado a la meta de {num(meta)} kg: propongo pasar a mantenimiento.")
    else:
        ritmo = pf.get("ritmo_kg_sem", 0.4)
        deseado = mant - ritmo * KCAL_POR_KG_SEM
        res["modo"] = "perder"
        if ritmo_real > 1.0:
            deseado = max(deseado, actual + 150)
            res["notas"].append("Estás bajando más de 1 kg/semana: conviene comer algo más para no perder músculo.")
    deseado = max(deseado, suelo)
    cambio = max(-150, min(150, deseado - actual))
    if abs(cambio) >= 75 or res.get("modo") != pf.get("modo", "perder"):
        res["nuevo"] = int(round((actual + cambio) / 10) * 10)
        res["propone"] = res["nuevo"] != actual or res.get("modo") != pf.get("modo", "perder")
    return res


def revision(guardar: bool = True) -> str:
    props = {}
    lineas = ["*Revisión semanal*"]
    for p in PERSONAS:
        r = evaluar(p)
        t = r.get("ritmo_real")
        cab = f"\n*{nombre(p)}*" + (f": {'−' if t >= 0 else '+'}{num(abs(t), 2)} kg/semana" if t is not None else "")
        lineas.append(cab)
        lineas += [f"  {n}" for n in r["notas"]]
        if r["propone"]:
            props[p] = {"objetivo_kcal": r["nuevo"], "mantenimiento_kcal": r["mant"], "modo": r.get("modo", "perder")}
            lineas.append(f"  👉 Propuesta: {r['actual']} → *{r['nuevo']} kcal/día*" +
                          (" (mantenimiento)" if r.get("modo") == "mantener" else ""))
        else:
            lineas.append(f"  ✅ Seguimos con {r['actual']} kcal/día.")
            if r["mant"] != perfil(p).get("mantenimiento_kcal"):
                guardar_perfil(p, {"mantenimiento_kcal": r["mant"]}) if guardar else None
    if props:
        if guardar:
            escribir_json(PROPUESTA, {"fecha": hoy().isoformat(), "propuestas": props})
        quien = " o ".join(f"`/aceptar {p}`" for p in props)
        lineas.append(f"\nPara aplicarlo: `/aceptar` (todo) o {quien}. Para dejarlo igual: `/rechazar`.")
    return "\n".join(lineas)


def aceptar(persona: str | None = None) -> str:
    prop = leer_json(PROPUESTA, {})
    items = prop.get("propuestas", {})
    if not items:
        return "No hay ninguna propuesta pendiente."
    elegidos = [persona] if persona else list(items)
    lineas = []
    for p in elegidos:
        if p not in items:
            lineas.append(f"No hay propuesta para {nombre(p)}.")
            continue
        antes = perfil(p)["objetivo_kcal"]
        guardar_perfil(p, items.pop(p))
        lineas.append(f"✅ {nombre(p)}: {antes} → {perfil(p)['objetivo_kcal']} kcal/día desde hoy. Las cantidades ya están recalculadas.")
    escribir_json(PROPUESTA, {**prop, "propuestas": items})
    return "\n".join(lineas)


def rechazar() -> str:
    escribir_json(PROPUESTA, {})
    return "Vale, seguimos con los objetivos actuales."


def cambiar_objetivo(persona: str, meta=None, ritmo=None, kcal=None, suelo=None, entrenos=None, modo=None,
                     meta_final=None) -> str:
    pf = perfil(persona)
    if (pf.get("modo") == "crecer" or pf.get("edad", 99) < 18) and any(
            v is not None for v in (meta, ritmo, suelo, modo, meta_final)):
        return (f"{nombre(persona)} está en edad de crecimiento: su plan no busca bajar de peso y no lleva meta, "
                "ritmo ni suelo. Cualquier objetivo de peso, con su pediatra.")
    cambios = {k: v for k, v in {"meta_kg": meta, "ritmo_kg_sem": ritmo, "suelo_kcal": suelo,
                                 "entrenos_semana": entrenos, "modo": modo, "meta_final_kg": meta_final}.items() if v is not None}
    lineas = []
    if kcal:
        suelo_ = suelo or perfil(persona).get("suelo_kcal", 1200)
        kcal = max(int(kcal), suelo_)
        cambios["objetivo_kcal"] = kcal
    if cambios:
        guardar_perfil(persona, cambios)
        lineas.append(f"Perfil de {nombre(persona)} actualizado: " + ", ".join(f"{k} = {v}" for k, v in cambios.items()) + ".")
    if not kcal and (meta is not None or ritmo is not None or modo is not None):
        pf = perfil(persona)
        mant = pf.get("mantenimiento_kcal", pf["objetivo_kcal"] + 450)
        deseado = mant if pf.get("modo") in ("mantener", "crecer") else mant - pf.get("ritmo_kg_sem", 0.4) * KCAL_POR_KG_SEM
        deseado = int(round(max(deseado, pf.get("suelo_kcal", 1200)) / 10) * 10)
        cambio = max(-250, min(250, deseado - pf["objetivo_kcal"]))
        if abs(cambio) >= 50:
            nuevo = pf["objetivo_kcal"] + cambio
            prop = leer_json(PROPUESTA, {}) or {"fecha": hoy().isoformat(), "propuestas": {}}
            prop.setdefault("propuestas", {})[persona] = {"objetivo_kcal": nuevo, "mantenimiento_kcal": mant, "modo": pf.get("modo", "perder")}
            escribir_json(PROPUESTA, prop)
            lineas.append(f"👉 Con eso, propongo pasar de {pf['objetivo_kcal']} a *{nuevo} kcal/día*. "
                          f"`/aceptar {persona}` para aplicarlo.")
        else:
            lineas.append(f"Las calorías se quedan en {pf['objetivo_kcal']} kcal/día.")
    return "\n".join(lineas) or "No había nada que cambiar."


def render_perfil(personas=PERSONAS) -> str:
    lineas = []
    for p in personas:
        pf = perfil(p)
        partes = [f"{pf.get('objetivo_kcal', '?')} kcal/día", f"mantenimiento estimado {pf.get('mantenimiento_kcal', '?')} kcal"]
        if pf.get("modo") == "crecer":
            partes.append("modo crecimiento (sin déficit)")
        else:
            if pf.get("meta_kg"):
                partes.append(f"meta {num(pf['meta_kg'])} kg" + (f" (luego {num(pf['meta_final_kg'])})" if pf.get("meta_final_kg") else ""))
            if pf.get("modo", "perder") == "perder":
                partes.append(f"ritmo {num(pf.get('ritmo_kg_sem', 0), 2)} kg/sem")
            partes += [f"modo {pf.get('modo', 'perder')}", f"suelo {pf.get('suelo_kcal')} kcal"]
        if pf.get("entrenos_semana"):
            partes.append(f"entrenos {pf['entrenos_semana']}")
        lineas.append(f"*{nombre(p)}*: " + " · ".join(partes))
    prop = leer_json(PROPUESTA, {}).get("propuestas", {})
    if prop:
        lineas.append("Propuesta pendiente: " + ", ".join(f"{nombre(p)} → {v['objetivo_kcal']} kcal" for p, v in prop.items()))
    return "\n".join(lineas)
