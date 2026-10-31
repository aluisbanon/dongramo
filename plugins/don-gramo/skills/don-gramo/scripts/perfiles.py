"""Alta y baja de personas, ajustes del hogar y estimación inicial de calorías.

Estimación (orientativa, se recalibra cada semana con el peso real en coach.py):
  - Adultos: Mifflin-St Jeor × factor de actividad = mantenimiento.
    Perder: mantenimiento − ritmo × 1.100 kcal, con un déficit máximo del 25 % y nunca por debajo del suelo.
    Suelo: el mayor entre 1.200 (mujer) / 1.500 (hombre) y el 85 % del metabolismo basal.
  - Menores de 18: nunca déficit (modo "crecer"); se usa una referencia por edad y la revisión semanal
    no propone bajar. Para cualquier objetivo de peso en menores: pediatra.
  - Embarazo o lactancia: mantenimiento y consulta profesional; sin déficit.
"""
from __future__ import annotations

import re
import unicodedata

from common import STATE, cookidoo_listo, hoy, load_config, save_config

ACTIVIDAD = {"sedentaria": 1.2, "ligera": 1.375, "moderada": 1.55, "alta": 1.725, "muy alta": 1.9}
KCAL_POR_KG_SEM = 1100
# Referencia por edad (kcal/día, actividad moderada) para menores; orientativa.
MENORES = [(3, 1200, 1200), (8, 1500, 1400), (13, 2000, 1800), (17, 2600, 2000)]


def slug(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "persona"


def actividad_arg(s: str | None) -> str:
    s = (s or "ligera").lower().strip()
    for k in ACTIVIDAD:
        if s == k or s.startswith(k[:4]):
            return k
    raise SystemExit(f"actividad desconocida: {s}. Usa una de: {', '.join(ACTIVIDAD)}")


def es_hombre(sexo: str | None) -> bool:
    """h/hombre/varón → True; m/mujer → False."""
    return (sexo or "").lower().strip().startswith(("h", "v"))


def estimar(sexo: str, edad: int, altura_cm: float, peso_kg: float, actividad: str, modo: str = "perder",
            ritmo: float | None = None, embarazo: bool = False) -> dict:
    hombre = es_hombre(sexo)
    notas = []
    if edad < 18:
        _, kh, km = next(x for x in MENORES if edad <= x[0]) if edad <= MENORES[-1][0] else MENORES[-1]
        mant = kh if hombre else km
        mant = int(round(mant * ACTIVIDAD[actividad] / ACTIVIDAD["moderada"] / 50) * 50)
        notas.append("Menor de edad: sin déficit; las cantidades son orientativas. Para objetivos de peso, pediatra.")
        return {"bmr": None, "mantenimiento_kcal": mant, "objetivo_kcal": mant, "suelo_kcal": int(mant * 0.85 // 50 * 50),
                "modo": "crecer", "ritmo_kg_sem": 0.0, "notas": notas}
    bmr = 10 * peso_kg + 6.25 * altura_cm - 5 * edad + (5 if hombre else -161)
    mant = int(round(bmr * ACTIVIDAD[actividad] / 10) * 10)
    suelo = max(1500 if hombre else 1200, int(0.85 * bmr // 50 * 50))
    if embarazo:
        notas.append("Embarazo o lactancia: sin déficit. Consulta con tu matrona o dietista-nutricionista.")
        return {"bmr": round(bmr), "mantenimiento_kcal": mant, "objetivo_kcal": mant, "suelo_kcal": suelo,
                "modo": "mantener", "ritmo_kg_sem": 0.0, "notas": notas}
    if modo == "mantener":
        return {"bmr": round(bmr), "mantenimiento_kcal": mant, "objetivo_kcal": mant, "suelo_kcal": suelo,
                "modo": "mantener", "ritmo_kg_sem": 0.0, "notas": notas}
    ritmo = ritmo if ritmo is not None else round(min(0.6, max(0.25, peso_kg * 0.005)), 2)
    deficit = min(ritmo * KCAL_POR_KG_SEM, 0.25 * mant)
    objetivo = int(round(max(mant - deficit, suelo) / 10) * 10)
    if objetivo == suelo:
        notas.append(f"El objetivo queda en el suelo de seguridad ({suelo} kcal): el ritmo real será algo menor.")
    return {"bmr": round(bmr), "mantenimiento_kcal": mant, "objetivo_kcal": objetivo, "suelo_kcal": suelo,
            "modo": "perder", "ritmo_kg_sem": ritmo, "notas": notas}


def alta(nombre: str, sexo: str, edad: int, altura_cm: float, peso_kg: float, actividad: str | None = None,
         meta_kg: float | None = None, ritmo: float | None = None, modo: str | None = None, kcal: float | None = None,
         embarazo: bool = False, entrenos: str | None = None, telegram_id: str | None = None) -> str:
    cfg = load_config()
    pid = slug(nombre)
    if pid in cfg["personas"]:
        return f"Ya existe «{cfg['personas'][pid]['nombre']}» (id {pid}). Para cambiar objetivos: `objetivo --persona {pid}`."
    act = actividad_arg(actividad)
    modo = modo or ("perder" if meta_kg and meta_kg < peso_kg else "mantener")
    e = estimar(sexo, edad, altura_cm, peso_kg, act, modo, ritmo, embarazo)
    if kcal:
        e["objetivo_kcal"] = max(int(kcal), e["suelo_kcal"])
    pf = {k: e[k] for k in ("mantenimiento_kcal", "objetivo_kcal", "suelo_kcal", "modo", "ritmo_kg_sem")}
    pf.update({"sexo": "h" if es_hombre(sexo) else "m", "edad": edad, "altura_cm": altura_cm,
               "peso_inicial_kg": peso_kg, "actividad": act, "desde": hoy().isoformat()})
    if meta_kg and e["modo"] == "perder":
        pf["meta_kg"] = meta_kg
    if entrenos:
        pf["entrenos_semana"] = entrenos
    cfg["personas"][pid] = {"nombre": nombre.strip(), "telegram_ids": [str(telegram_id)] if telegram_id else [],
                            "extra_diario": [], "perfil": pf}
    save_config(cfg)
    from coach import anotar_peso  # el peso de hoy es la primera pesada
    anotar_peso(pid, peso_kg, hoy(), fuente="alta")
    lineas = [f"✅ {nombre.strip()} ya está en el plan (id `{pid}`).",
              f"Mantenimiento estimado: {e['mantenimiento_kcal']} kcal/día · objetivo: *{pf['objetivo_kcal']} kcal/día* "
              f"· suelo: {e['suelo_kcal']} kcal · modo: {e['modo']}"
              + (f" · ritmo {str(e['ritmo_kg_sem']).replace('.', ',')} kg/semana" if e["modo"] == "perder" else "") + "."]
    lineas += [f"ℹ️ {n}" for n in e["notas"]]
    lineas.append("Es una estimación de partida: cada domingo la revisión la corrige con vuestro peso real.")
    return "\n".join(lineas)


def baja(pid: str) -> str:
    cfg = load_config()
    if pid not in cfg["personas"]:
        return f"No hay nadie con id {pid}."
    nombre = cfg["personas"].pop(pid)["nombre"]
    save_config(cfg)
    return f"{nombre} ya no está en el plan. Su histórico se conserva en state/ por si vuelve."


def hogar(nombre: str | None = None, thermomix: str | None = None, zona: str | None = None,
          modelo: str | None = None) -> str:
    cfg = load_config()
    h = cfg["hogar"]
    si = lambda v: str(v).lower() in ("si", "sí", "s", "true", "1", "yes")  # noqa: E731
    if nombre:
        h["nombre"] = nombre
    if thermomix is not None:
        h["thermomix"] = si(thermomix)
    if modelo:
        h["modelo_thermomix"] = modelo.upper()
    if zona:
        from zoneinfo import ZoneInfo
        ZoneInfo(zona)  # valida
        cfg["zona_horaria"] = zona
    save_config(cfg)
    return render_hogar()


def objetivo_vigente(pid: str, persona: dict):
    """Objetivo de kcal actual: el de state/perfil.json (revisiones aceptadas) o, si no, el del alta."""
    import json
    try:
        cambios = json.loads((STATE / "perfil.json").read_text(encoding="utf-8")).get(pid, {})
    except (OSError, ValueError):
        cambios = {}
    return cambios.get("objetivo_kcal") or persona.get("perfil", {}).get("objetivo_kcal", "?")


def render_hogar() -> str:
    cfg = load_config()
    h = cfg["hogar"]
    ps = cfg["personas"]
    lineas = [f"*{h['nombre']}* · zona horaria {cfg['zona_horaria']}",
              f"Thermomix: {'sí (' + h.get('modelo_thermomix', 'TM6') + ')' if h['thermomix'] else 'no'}"
              + (" · Cookidoo: conectado" if cookidoo_listo() else ""),
              f"Personas ({len(ps)}): " + (", ".join(f"{v['nombre']} (`{k}`, {objetivo_vigente(k, v)} kcal)"
                                                    for k, v in ps.items()) or "ninguna todavía")]
    return "\n".join(lineas)


def extra_diario(pid: str, alimento: str | None, g: float | None, nota: str | None, quitar: bool) -> str:
    from plan import buscar_alimento
    cfg = load_config()
    if pid not in cfg["personas"]:
        return f"No hay nadie con id {pid}."
    lista = cfg["personas"][pid].setdefault("extra_diario", [])
    if quitar:
        cfg["personas"][pid]["extra_diario"] = [x for x in lista if not alimento or alimento.lower() not in x["f"]]
        save_config(cfg)
        return "Quitado de lo que toma cada día."
    fid = buscar_alimento(alimento or "")
    if not fid or not g:
        return "Dime el alimento (de `alimentos`) y los gramos."
    lista.append({"f": fid, "g": g, "nota": nota or fid})
    save_config(cfg)
    return f"Anotado: {cfg['personas'][pid]['nombre']} toma cada día {nota or fid} ({g:g} g). Cuenta en sus calorías."


def vincular_telegram(pid: str, user_id: str) -> str:
    cfg = load_config()
    if pid not in cfg["personas"]:
        return f"No hay nadie con id {pid}."
    ids = cfg["personas"][pid].setdefault("telegram_ids", [])
    if str(user_id) not in ids:
        ids.append(str(user_id))
    save_config(cfg)
    return f"Telegram {user_id} vinculado a {cfg['personas'][pid]['nombre']}."
