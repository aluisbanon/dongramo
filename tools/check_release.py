#!/usr/bin/env python3
"""Comprobaciones del repositorio antes de publicar (las ejecuta la CI y puedes lanzarlas tú).

    python3 tools/check_release.py                 versiones, cabeceras de skills y privacidad
    python3 tools/check_release.py --base main     además: si cambió un plugin, ¿subió su versión?
    python3 tools/check_release.py --tag v1.2.0    además: ¿la etiqueta coincide con la versión?

Por qué importa la versión: Claude Code decide si hay actualización mirando el campo `version` de
plugin.json. Si cambias código sin subirla, los usuarios se quedan con la copia antigua.
Solo stdlib.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PLUGINS = ("dongramo", "dongramo-cookidoo")
CLAVES_SKILL = {"name", "description", "license", "allowed-tools", "metadata"}  # las que admite Codex
# Ficheros que nunca deben estar en el repositorio (datos de salud, secretos, entornos)
PROHIBIDOS = re.compile(r"(^|/)(state/|logs/|config\.json$|secrets\.env$|.*\.jsonl$|\.venv)")
# Patrones de datos personales o secretos
SOSPECHOSOS = [
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"), "token de bot de Telegram"),
    (re.compile(r"-100\d{8,}"), "id de grupo de Telegram"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo|icloud)\.[a-z]{2,}", re.I), "email personal"),
    (re.compile(r"(api[_-]?key|password|contraseña)\s*[=:]\s*['\"][^'\"\s]{6,}", re.I), "clave o contraseña"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "clave de API"),
]
errores: list[str] = []


def leer(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def versiones() -> dict:
    """{plugin: versión} según plugin.json, comprobando que el catálogo y el CHANGELOG coinciden."""
    out = {}
    catalogo = {p["name"]: p for p in leer(RAIZ / ".claude-plugin" / "marketplace.json")["plugins"]}
    for nombre in PLUGINS:
        v = leer(RAIZ / "plugins" / nombre / ".claude-plugin" / "plugin.json").get("version")
        if not v or not re.fullmatch(r"\d+\.\d+\.\d+", v):
            errores.append(f"{nombre}: versión ausente o no es X.Y.Z en plugin.json ({v!r})")
            continue
        if catalogo.get(nombre, {}).get("version") != v:
            errores.append(f"{nombre}: marketplace.json dice {catalogo.get(nombre, {}).get('version')!r} "
                           f"y plugin.json {v!r}. Usa tools/version.py para cambiarla en todas partes.")
        out[nombre] = v
    cambios = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## (\d+\.\d+\.\d+)", cambios, re.M)
    principal = out.get("dongramo")
    if not m or m.group(1) != principal:
        errores.append(f"CHANGELOG.md: la primera entrada debería ser «## {principal}» (es {m.group(1) if m else 'ninguna'}).")
    return out


def cabeceras() -> None:
    for nombre in PLUGINS:
        skill = RAIZ / "plugins" / nombre / "skills" / nombre / "SKILL.md"
        partes = skill.read_text(encoding="utf-8").split("---")
        if len(partes) < 3:
            errores.append(f"{skill}: sin cabecera YAML")
            continue
        claves = {l.split(":", 1)[0] for l in partes[1].strip().splitlines() if re.match(r"^[a-z-]+:", l)}
        if not {"name", "description"} <= claves:
            errores.append(f"{skill}: faltan name o description")
        if claves - CLAVES_SKILL:
            errores.append(f"{skill}: claves no admitidas por Codex: {sorted(claves - CLAVES_SKILL)} "
                           "(mételas dentro de metadata)")
        if not re.search(rf"^name:\s*{re.escape(nombre)}\s*$", partes[1], re.M):
            errores.append(f"{skill}: name debe ser «{nombre}» (igual que la carpeta)")
        if "python3 scripts/" in skill.read_text(encoding="utf-8"):
            errores.append(f"{skill}: usa python3 {{baseDir}}/scripts/..., no rutas relativas")


def privacidad() -> None:
    ficheros = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=RAIZ,
                              capture_output=True, text=True).stdout.split()
    for f in ficheros:
        if PROHIBIDOS.search(f):
            errores.append(f"{f}: este tipo de fichero no debe estar en el repositorio (datos o secretos)")
            continue
        ruta = RAIZ / f
        if not ruta.is_file() or ruta.suffix in (".png", ".jpg", ".ico") or f == "tools/check_release.py":
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        for patron, que in SOSPECHOSOS:
            if patron.search(texto):
                errores.append(f"{f}: parece contener un {que}")


def subio_version(base: str, actuales: dict) -> None:
    """En un PR: si cambian ficheros de un plugin, su versión tiene que ser mayor que en la base."""
    def tupla(v):
        return tuple(int(x) for x in v.split("."))
    for nombre, v in actuales.items():
        cambiados = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD", "--", f"plugins/{nombre}"],
                                   cwd=RAIZ, capture_output=True, text=True).stdout.split()
        if not cambiados:
            continue
        r = subprocess.run(["git", "show", f"{base}:plugins/{nombre}/.claude-plugin/plugin.json"], cwd=RAIZ,
                           capture_output=True, text=True)
        if r.returncode != 0:
            continue  # plugin nuevo
        antes = json.loads(r.stdout).get("version", "0.0.0")
        if tupla(v) <= tupla(antes):
            errores.append(f"{nombre}: has cambiado {len(cambiados)} fichero(s) pero la versión sigue en {v}. "
                           f"Súbela con: python3 tools/version.py {nombre} <nueva>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="rama o commit con el que comparar (en un PR, la rama principal)")
    ap.add_argument("--tag", help="etiqueta que se va a publicar, p. ej. v1.2.0")
    a = ap.parse_args()
    v = versiones()
    cabeceras()
    privacidad()
    if a.base:
        subio_version(a.base, v)
    if a.tag and a.tag.lstrip("v") != v.get("dongramo"):
        errores.append(f"La etiqueta {a.tag} no coincide con la versión de dongramo ({v.get('dongramo')}).")
    if errores:
        print("❌ Hay que arreglar esto antes de publicar:\n" + "\n".join(f"  - {e}" for e in errores))
        return 1
    print("✅ Todo en orden: " + ", ".join(f"{k} {x}" for k, x in v.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
