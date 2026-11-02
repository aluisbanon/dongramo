#!/usr/bin/env python3
"""Sube la versión de un plugin en todos los sitios a la vez.

    python3 tools/version.py dongramo 1.1.0 "Nuevo menú D y mejoras en la compra"
    python3 tools/version.py dongramo-cookidoo 1.0.1 "Arreglo en la búsqueda"

Cambia plugin.json y su entrada en marketplace.json. Para dongramo (el que marca las publicaciones)
añade además la entrada al principio del CHANGELOG. Después: revisa, haz commit y, para publicar,
`git tag v<versión> && git push --tags`. Solo stdlib.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def guardar(p: Path, datos: dict) -> None:
    p.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 3 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[2]):
        print(__doc__)
        return 1
    plugin, nueva = sys.argv[1], sys.argv[2]
    nota = " ".join(sys.argv[3:]).strip()
    manifiesto = RAIZ / "plugins" / plugin / ".claude-plugin" / "plugin.json"
    if not manifiesto.exists():
        print(f"No existe el plugin {plugin}.")
        return 1
    m = json.loads(manifiesto.read_text(encoding="utf-8"))
    antes = m.get("version")
    if tuple(map(int, nueva.split("."))) <= tuple(map(int, (antes or "0.0.0").split("."))):
        print(f"La versión nueva ({nueva}) tiene que ser mayor que la actual ({antes}).")
        return 1
    m["version"] = nueva
    guardar(manifiesto, m)
    cat_p = RAIZ / ".claude-plugin" / "marketplace.json"
    cat = json.loads(cat_p.read_text(encoding="utf-8"))
    for e in cat["plugins"]:
        if e["name"] == plugin:
            e["version"] = nueva
    guardar(cat_p, cat)
    if plugin == "dongramo":
        ch = RAIZ / "CHANGELOG.md"
        texto = ch.read_text(encoding="utf-8")
        entrada = f"## {nueva} · {dt.date.today().isoformat()}\n\n- {nota or 'Describe aquí los cambios.'}\n\n"
        i = texto.find("\n## ")
        texto = texto[:i + 1] + entrada + texto[i + 1:] if i >= 0 else texto + "\n" + entrada
        ch.write_text(texto, encoding="utf-8")
    print(f"✅ {plugin}: {antes} → {nueva}" + (" (CHANGELOG actualizado)" if plugin == "dongramo" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
