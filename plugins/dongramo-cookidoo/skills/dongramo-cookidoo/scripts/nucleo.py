"""Localiza el plugin dongramo (el núcleo) y pone sus scripts en sys.path.

Orden: $DONGRAMO_NUCLEO, lo que el núcleo registró en ~/.dongramo/plugins.json, el repositorio
(plugins/dongramo junto a esta extensión) y la caché de plugins de Claude Code.
"""
from __future__ import annotations

import json
import os
import sys
from glob import glob
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HOME = Path(os.environ.get("DONGRAMO_HOME") or os.environ.get("DON_GRAMO_HOME")
            or (Path.home() / ".dongramo" if (Path.home() / ".dongramo").exists() or not (Path.home() / ".don-gramo").exists()
                else Path.home() / ".don-gramo")).expanduser()


def ruta() -> Path | None:
    candidatos = []
    for var in ("DONGRAMO_NUCLEO", "DON_GRAMO_NUCLEO"):  # el segundo, nombre de la 1.0
        if os.environ.get(var):
            candidatos.append(Path(os.environ[var]))
    try:
        reg = json.loads((HOME / "plugins.json").read_text(encoding="utf-8"))
        candidatos += [Path(reg.get(k, "")) for k in ("dongramo", "don-gramo")]
    except (OSError, json.JSONDecodeError):
        pass
    plugin = AQUI.parent.parent.parent  # plugins/dongramo-cookidoo (repo) o cache/<marketplace>/dongramo-cookidoo/<versión>
    candidatos.append(plugin.parent / "dongramo" / "skills" / "dongramo" / "scripts")
    candidatos.append(AQUI.parent.parent / "dongramo" / "scripts")  # skills sueltas, una junto a otra (OpenClaw)
    candidatos += [Path(x) for x in sorted(glob(str(plugin.parent.parent / "dongramo" / "*" / "skills" / "dongramo" / "scripts")),
                                           key=os.path.getmtime, reverse=True)]
    for c in candidatos:
        if str(c) not in ("", ".") and (c / "dieta.py").exists():
            return c
    return None


def cargar() -> Path:
    r = ruta()
    if not r:
        print("Esta extensión necesita el plugin dongramo. Instálalo con: /plugin install dongramo@dongramo")
        sys.exit(1)
    sys.path.insert(1, str(r))
    return r
