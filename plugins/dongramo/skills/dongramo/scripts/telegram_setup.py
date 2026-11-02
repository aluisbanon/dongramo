#!/usr/bin/env python3
"""Asistente para enganchar Don Gramo a Telegram, paso a paso (lo usa /dongramo:telegram).

  estado                 qué está hecho y cuál es el siguiente paso
  copiar                 instala/actualiza una copia estable del plugin en ~/.dongramo/app
                         (los servicios apuntan ahí y no se rompen cuando Claude Code actualiza el plugin)
  token [--terminal]     pide el token de @BotFather en una ventana con el texto oculto (macOS)
                         o en la terminal; lo guarda sin que pase por el chat y lo valida
  chat [--id ID]         detecta el grupo (o chat privado) donde escribisteis al bot y lo guarda
  activar                pone en marcha el bot y los avisos, y manda un mensaje de prueba
  prueba                 manda el menú de hoy al chat (sin modelo)
  parar                  detiene el bot y los avisos

Cada paso imprime qué ha pasado y qué toca después. Solo stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (HOME, SECRETS_FILE, SKILL, cookidoo_listo, load_config, resolver_claude, ruta_extension,  # noqa: E402
                    secreto, tg_api, tg_send)

APP = HOME / "app"
PLUGIN = SKILL.parent.parent  # plugins/dongramo (repo) o la caché de Claude Code
COPIA = APP / "dongramo"
COPIA_INSTALL = COPIA / "bot" / "install.sh"
MAC = sys.platform == "darwin"


def cfg_tg() -> dict:
    return load_config()["telegram"]


def guardar_secreto(clave: str, valor: str) -> None:
    """En state/secrets.env (chmod 600) y, en macOS, también en el Llavero."""
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lineas = []
    if SECRETS_FILE.exists():
        lineas = [x for x in SECRETS_FILE.read_text(encoding="utf-8").splitlines() if not x.startswith(clave + "=")]
    lineas.append(f"{clave}={valor}")
    SECRETS_FILE.touch(mode=0o600)
    os.chmod(SECRETS_FILE, 0o600)
    SECRETS_FILE.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    if MAC:
        subprocess.run(["security", "add-generic-password", "-U", "-a", os.environ.get("USER", ""), "-s", clave,
                        "-w", valor], capture_output=True)


def servicios_activos() -> bool:
    if MAC:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
        return "com.dongramo.telegram" in out
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", "dongramo-telegram.service"], capture_output=True, text=True)
    except FileNotFoundError:  # Linux sin systemd (algunos contenedores o WSL)
        return False
    return r.stdout.strip() == "active"


def bot_info(token: str) -> dict | None:
    try:
        r = tg_api(token, "getMe", _timeout=15)
        return r.get("result") if r.get("ok") else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- pasos
def estado() -> str:
    cfg = load_config()
    t = cfg["telegram"]
    token, chat = secreto(t["secreto_token"]), secreto(t["secreto_chat"])
    claude = resolver_claude(cfg)
    pasos = [
        ("Hogar configurado", bool(cfg["personas"]), "Configura antes el hogar: /dongramo:configurar"),
        ("Claude Code disponible para el bot", claude != "claude" or bool(shutil.which("claude")),
         "Instala Claude Code en esta máquina e inicia sesión (lo usa el bot para los mensajes libres)."),
        ("Copia estable del plugin", COPIA_INSTALL.exists(), "python3 scripts/telegram_setup.py copiar"),
        ("Token del bot guardado", bool(token), "Crea el bot con @BotFather y guarda el token: telegram_setup.py token"),
        ("Chat detectado", bool(chat), "Añade el bot al grupo, escribid /ayuda y luego: telegram_setup.py chat"),
        ("Bot en marcha", servicios_activos(), "python3 scripts/telegram_setup.py activar"),
    ]
    lineas = ["*Don Gramo en Telegram*"]
    siguiente = None
    for nombre_paso, ok, como in pasos:
        lineas.append(f"{'✅' if ok else '⬜'} {nombre_paso}")
        if not ok and not siguiente:
            siguiente = como
    if token:
        info = bot_info(token)
        lineas.append(f"Bot: @{info['username']}" if info else "⚠️ El token guardado no funciona: vuelve a guardarlo.")
    sin_vincular = [v["nombre"] for v in cfg["personas"].values() if not v.get("telegram_ids")]
    if chat and sin_vincular:
        lineas.append("Sin vincular todavía: " + ", ".join(sin_vincular) + " (cada uno escribe `/soy <nombre>` en el chat).")
    lineas.append(f"\nSiguiente paso: {siguiente}" if siguiente else "\nTodo listo. 🎉")
    return "\n".join(lineas)


def copiar() -> str:
    if str(SKILL.resolve()).startswith(str(APP.resolve())):
        return "Ya se está ejecutando desde la copia estable."
    if not (PLUGIN / "bot" / "install.sh").exists():
        return ("Esta instalación solo tiene la skill (por ejemplo, en OpenClaw), sin el bot de Telegram propio. "
                "En OpenClaw no hace falta: conecta Telegram con los canales de OpenClaw y la skill ya responde allí.")
    ignorar = shutil.ignore_patterns("__pycache__", "*.pyc", ".git")
    APP.mkdir(parents=True, exist_ok=True)
    nueva = not COPIA.exists()
    shutil.copytree(PLUGIN, COPIA, dirs_exist_ok=True, ignore=ignorar)
    os.chmod(COPIA_INSTALL, 0o755)
    extra = ""
    ext = ruta_extension("dongramo-cookidoo")
    if ext and cookidoo_listo() and not str(ext).startswith(str(APP)):
        shutil.copytree(ext.parent.parent.parent, APP / "dongramo-cookidoo", dirs_exist_ok=True, ignore=ignorar)
        extra = " También la extensión de Cookidoo."
    reinicio = ""
    if servicios_activos():
        subprocess.run([str(COPIA_INSTALL), "activar"], capture_output=True, text=True)
        reinicio = " El bot se ha reiniciado con la versión nueva."
    return (("✅ Copia estable instalada" if nueva else "🔄 Copia estable actualizada") + f" en {COPIA}.{extra}{reinicio}\n"
            "Cuando actualices el plugin, vuelve a ejecutar `/dongramo:telegram` para pasar la versión nueva al bot.")


def token(terminal: bool = False) -> str:
    valor = None
    if MAC and not terminal:
        script = ('display dialog "Pega aquí el token que te ha dado @BotFather (se guarda solo en este ordenador):" '
                  'default answer "" with hidden answer with title "Don Gramo · Telegram" '
                  'buttons {"Cancelar", "Guardar"} default button "Guardar"')
        r = subprocess.run(["osascript", "-e", script, "-e", "text returned of result"], capture_output=True, text=True)
        if r.returncode != 0:
            return "Has cancelado la ventana. Cuando tengas el token, repite este paso."
        valor = r.stdout.strip()
    else:
        if not sys.stdin.isatty():
            return ("Aquí no puedo abrir una ventana. Ejecuta este comando en una terminal de esta máquina y pega el token:\n"
                    f"  python3 {Path(__file__).resolve()} token --terminal")
        import getpass
        valor = getpass.getpass("Token de @BotFather (no se ve al pegarlo): ").strip()
    if not valor or ":" not in valor:
        return "Eso no parece un token de Telegram (tiene la forma 123456789:AA...). Vuelve a intentarlo."
    info = bot_info(valor)
    if not info:
        return "❌ Telegram no reconoce ese token. Cópialo otra vez de @BotFather (sin espacios) y repite."
    guardar_secreto(cfg_tg()["secreto_token"], valor)
    privacidad = ("✅ Modo privacidad activado: en el grupo solo verá comandos y mensajes que le mencionen."
                  if not info.get("can_read_all_group_messages") else
                  "⚠️ El modo privacidad está desactivado: el bot vería todos los mensajes del grupo. Recomendado: "
                  "en @BotFather → /mybots → tu bot → Bot Settings → Group Privacy → Turn on.")
    return (f"✅ Token guardado. Tu bot es *@{info['username']}* ({info.get('first_name', '')}).\n{privacidad}\n\n"
            f"Siguiente: crea un grupo en Telegram con quien vaya a usarlo, añade a @{info['username']} y escribe "
            f"/ayuda en el grupo. Si vives solo, basta con abrir el chat con @{info['username']} y escribirle /ayuda. "
            "Después, dime «hecho».")


def chat(forzar: str | None = None) -> str:
    t = cfg_tg()
    tk = secreto(t["secreto_token"])
    if not tk:
        return "Primero guarda el token (paso anterior)."
    if forzar:
        guardar_secreto(t["secreto_chat"], forzar)
        return f"✅ Chat {forzar} guardado. Siguiente: activar."
    estaba = servicios_activos()
    if estaba:  # el bot en marcha se come los mensajes: lo paro un momento
        parar()
    try:
        r = tg_api(tk, "getUpdates", _timeout=20, timeout=0,
                   allowed_updates=json.dumps(["message", "my_chat_member"]))
    except Exception as exc:  # noqa: BLE001
        if "401" in str(exc):
            return "❌ Telegram no acepta el token guardado. Repite el paso del token con el código de @BotFather."
        return f"❌ No he podido hablar con Telegram ({exc}). ¿Hay conexión a internet?"
    chats = {}
    for u in r.get("result", []):
        m = u.get("message") or u.get("my_chat_member") or {}
        c = m.get("chat") or {}
        if not c:
            continue
        cid = m.get("migrate_to_chat_id") or c["id"]  # grupo convertido en supergrupo: id nuevo
        chats[cid] = {"tipo": c.get("type"), "nombre": c.get("title") or c.get("first_name") or ""}
    grupos = {k: v for k, v in chats.items() if v["tipo"] in ("group", "supergroup")}
    elegibles = grupos or chats
    if not elegibles:
        return ("Todavía no veo ningún mensaje. Comprueba que el bot está en el grupo y escribid /ayuda "
                "(o escríbele por privado). Luego dime «hecho» y lo vuelvo a mirar.")
    if len(elegibles) > 1:
        return ("Veo varios chats; dime cuál es el de Don Gramo:\n"
                + "\n".join(f"- {v['nombre'] or '(sin nombre)'} ({v['tipo']}): `telegram_setup.py chat --id {k}`"
                            for k, v in elegibles.items()))
    cid, info = next(iter(elegibles.items()))
    guardar_secreto(t["secreto_chat"], str(cid))
    return (f"✅ Chat detectado y guardado: *{info['nombre'] or 'chat privado'}* ({info['tipo']}).\n"
            "Siguiente: activar el bot.")


def activar() -> str:
    t = cfg_tg()
    tk, ch = secreto(t["secreto_token"]), secreto(t["secreto_chat"])
    if not tk or not ch:
        return "Faltan pasos: " + ("token" if not tk else "chat") + ". Mira `estado`."
    if not COPIA_INSTALL.exists():
        print(copiar())
    if not MAC and not shutil.which("systemctl"):
        return ("❌ Esta máquina no tiene systemd, así que no puedo dejar el bot arrancado solo. Puedes lanzarlo "
                f"a mano y dejarlo corriendo: `python3 {COPIA}/skills/dongramo/scripts/telegram_bridge.py --daemon`.")
    r = subprocess.run([str(COPIA_INSTALL), "activar"], capture_output=True, text=True)
    if r.returncode != 0:
        return f"❌ No he podido activar los servicios:\n{(r.stderr or r.stdout)[-600:]}"
    personas = load_config()["personas"]
    nombres = ", ".join(v["nombre"] for v in personas.values())
    tg_send(tk, ch, "👋 ¡Hola! Soy *Don Gramo*. Ya estoy conectado a este chat.\n\n"
                    f"Primero, que cada uno se presente: escribid `/soy <vuestro nombre>` ({nombres}).\n"
                    "Después: `/hoy` para ver qué toca, o mencionadme para cualquier cosa. `/ayuda` para ver todo.")
    linger = ""
    if not MAC:
        linger = ("\nEn Linux, para que siga funcionando sin sesión abierta: `sudo loginctl enable-linger "
                  f"{os.environ.get('USER', '$USER')}` (una vez).")
    avisos = f"menú cada día a las {t.get('aviso_diario', '07:30')} y revisión los domingos a las {t.get('aviso_semanal', '10:00')}"
    return (f"✅ Bot en marcha ({avisos}). He mandado un saludo al chat.\n"
            "Último paso: que cada persona escriba `/soy <su nombre>` en el chat. Luego probad `/hoy`." + linger)


def prueba() -> str:
    t = cfg_tg()
    tk, ch = secreto(t["secreto_token"]), secreto(t["secreto_chat"])
    if not tk or not ch:
        return "Faltan el token o el chat."
    aviso = SKILL / "scripts" / "aviso.py"
    r = subprocess.run([sys.executable, str(aviso), "--diario"], capture_output=True, text=True, cwd=str(SKILL))
    return "✅ Menú de hoy enviado al chat." if r.returncode == 0 else f"❌ {r.stdout[-400:]}{r.stderr[-400:]}"


def parar() -> str:
    script = COPIA_INSTALL if COPIA_INSTALL.exists() else PLUGIN / "bot" / "install.sh"
    subprocess.run([str(script), "parar"], capture_output=True, text=True)
    return "Bot y avisos parados."


def main() -> int:
    ap = argparse.ArgumentParser(description="Asistente de Telegram de Don Gramo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("estado", "copiar", "activar", "prueba", "parar"):
        sub.add_parser(n)
    s = sub.add_parser("token"); s.add_argument("--terminal", action="store_true")
    s = sub.add_parser("chat"); s.add_argument("--id")
    a = ap.parse_args()
    out = {"estado": estado, "copiar": copiar, "activar": activar, "prueba": prueba, "parar": parar}.get(a.cmd)
    if a.cmd == "token":
        print(token(a.terminal))
    elif a.cmd == "chat":
        print(chat(a.id))
    else:
        print(out())
    return 0


if __name__ == "__main__":
    sys.exit(main())
