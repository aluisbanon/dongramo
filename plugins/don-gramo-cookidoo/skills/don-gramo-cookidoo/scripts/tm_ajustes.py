"""Extrae ajustes guiados de Thermomix del texto de un paso (stdlib, Python 3.9+).

"cuece 14 min / 100 °C / vel 4"           -> 840 s, 100 °C, vel 4
"tritura 1 min subiendo de vel 5 a vel 10" -> 60 s, vel 10 (progresivo)
"5 min más / Varoma / giro a la izquierda" -> 300 s, Varoma, giro inverso, vel cuchara
"""
from __future__ import annotations

import re

_T = r"\d+(?:[.,]\d+)?\s*(?:min|seg|s)\b(?:\s*\d+\s*(?:seg|s)\b)?(?:\s+más)?"
_TEMP = r"(?:\d+\s*°\s*C|[Vv]aroma)"
_GIRO = r"(?:giro a la izquierda|giro inverso)"
_VEL = r"vel(?:ocidad)?\.?\s*(?:cuchara|\d+(?:[.,]\d)?)"
_SEG = rf"(?:{_T}|{_TEMP}|{_GIRO})"
_NORMAL = re.compile(rf"{_SEG}(?:\s*/\s*{_SEG})*\s*/\s*{_VEL}", re.I)
_SIN_VEL = re.compile(rf"{_T}(?:\s*/\s*(?:{_TEMP}|{_GIRO}))+", re.I)
_PROGRESIVO = re.compile(rf"{_T}[^./;]{{0,40}}?de\s+vel\s*\d+(?:[.,]\d)?\s+a\s+vel\s*\d+(?:[.,]\d)?", re.I)


def _datos(s: str) -> dict:
    d = {"slot": s, "time": 0}
    t = re.search(r"(\d+(?:[.,]\d+)?)\s*min\b", s, re.I)
    sec = re.search(r"(\d+)\s*(?:seg|s)\b", s, re.I)
    if t:
        d["time"] += int(round(float(t.group(1).replace(",", ".")) * 60))
    if sec:
        d["time"] += int(sec.group(1))
    tp = re.search(r"(\d+)\s*°\s*C", s)
    if tp:
        d["temperature"] = tp.group(1)
    elif re.search("varoma", s, re.I):
        d["temperature"] = "varoma"
    if re.search(_GIRO, s, re.I):
        d["direction"] = "CCW"
    vels = re.findall(r"vel(?:ocidad)?\.?\s*(cuchara|\d+(?:[.,]\d)?)", s, re.I)
    if vels:
        v = vels[-1].replace(",", ".")
        d["speed"] = "soft" if v.lower() == "cuchara" else v
    else:
        d["speed"] = "soft" if d.get("direction") else "1"
    return d


def ajustes(texto: str) -> list:
    """Lista de ajustes {slot, time, temperature?, speed, direction?} sin solapes."""
    encontrados = []
    for pat in (_NORMAL, _PROGRESIVO, _SIN_VEL):
        for m in pat.finditer(texto):
            if any(m.start() < b and a < m.end() for a, b in encontrados):
                continue
            encontrados.append((m.start(), m.end()))
    return [_datos(texto[a:b]) for a, b in sorted(encontrados)]
