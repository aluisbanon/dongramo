#!/usr/bin/env python3
"""Avisos programados al chat de Telegram, SIN modelo (coste cero).

  aviso.py --diario    menú del día con las cantidades de cada uno (launchd/systemd, 07:30)
  aviso.py --semanal   progreso, resumen, revisión de calorías y menú de la semana siguiente (domingo 10:00)
  aviso.py --diario --imprimir   lo muestra en pantalla sin enviarlo
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SKILL, credenciales, load_config, log, tg_send  # noqa: E402

DIETA = [sys.executable, str(SKILL / "scripts" / "dieta.py")]


def dieta(*args: str) -> str:
    return subprocess.run([*DIETA, *args], capture_output=True, text=True, cwd=str(SKILL), timeout=60).stdout.strip()


def main() -> int:
    if "--semanal" in sys.argv:
        texto = "\n\n".join([
            "☀️ *Domingo de revisión*",
            dieta("progreso"),
            dieta("semana"),
            dieta("revision"),
            "*La semana que viene*\n" + dieta("menu", "--semana", "proxima"),
            "¿Queréis cambiar algo? Decídmelo mencionándome, p. ej. \"cambia el bacalao por merluza\" o "
            "\"el martes no quiero lentejas\". Lista de la compra: `/compra proxima`. "
            "Y mandad el peso de esta semana (vale una captura de la báscula) para afinar la próxima revisión.",
        ])
    else:
        texto = "🍽️ Buenos días. " + dieta("hoy", "--persona", "todos") + "\n\nReparto de lo cocinado: /racion"
    if "--imprimir" in sys.argv:
        print(texto)
        return 0
    token, chat = credenciales(load_config())
    if not token or not chat:
        log("faltan credenciales de Telegram", level="ERROR")
        return 1
    tipo = "semanal" if "--semanal" in sys.argv else "diario"
    if not tg_send(token, chat, texto):
        log(f"aviso {tipo} sin enviar (o incompleto)", level="ERROR")
        return 1
    log(f"aviso {tipo} enviado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
