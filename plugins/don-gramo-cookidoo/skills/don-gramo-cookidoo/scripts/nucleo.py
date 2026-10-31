"""Localiza el plugin don-gramo (el núcleo) y pone sus scripts en sys.path.

Orden: $DON_GRAMO_NUCLEO, lo que el núcleo registró en ~/.don-gramo/plugins.json, el repositorio
(plugins/don-gramo junto a esta extensión) y la caché de plugins de Claude Code.
"""
from __future__ import annotations

import json
import os
import sys
from glob import glob
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HOME = Path(os.environ.get("DON_GRAMO_HOME") or Path.home() / ".don-gramo").expanduser()


def ruta() -> Path | None:
    candidatos = []
    if os.environ.get("DON_GRAMO_NUCLEO"):
        candidatos.append(Path(os.environ["DON_GRAMO_NUCLEO"]))
    try:
        candidatos.append(Path(json.loads((HOME / "plugins.json").read_text(encoding="utf-8")).get("don-gramo", "")))
    except (OSError, json.JSONDecodeError):
        pass
    plugin = AQUI.parent.parent.parent  # plugins/don-gramo-cookidoo (repo) o cache/<marketplace>/don-gramo-cookidoo/<versión>
    candidatos.append(plugin.parent / "don-gramo" / "skills" / "don-gramo" / "scripts")
    candidatos.append(AQUI.parent.parent / "don-gramo" / "scripts")  # skills sueltas, una junto a otra (OpenClaw)
    candidatos += [Path(x) for x in sorted(glob(str(plugin.parent.parent / "don-gramo" / "*" / "skills" / "don-gramo" / "scripts")),
                                           key=os.path.getmtime, reverse=True)]
    for c in candidatos:
        if str(c) not in ("", ".") and (c / "dieta.py").exists():
            return c
    return None


def cargar() -> Path:
    r = ruta()
    if not r:
        print("Esta extensión necesita el plugin don-gramo. Instálalo con: /plugin install don-gramo@don-gramo")
        sys.exit(1)
    sys.path.insert(1, str(r))
    return r
