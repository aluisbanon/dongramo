#!/usr/bin/env python3
"""Puente del grupo (o chat privado) de Telegram de Don Gramo.

Solo actúa si:
  - el mensaje viene del chat configurado (secreto don-gramo-telegram-chat), y
  - lo escribe alguien del hogar (sus user_id en config.json; cada uno se vincula con `/soy <nombre>`), y
  - es un comando (/hoy…), menciona al bot (@usuario_del_bot) o responde a un mensaje del bot.
Con el modo privacidad del bot activado (el de serie), Telegram ya solo le entrega esos mensajes.

Dos capas:
  - Rápida (sin modelo, coste cero): /hoy, /manana, /semana, /ajustes, /racion, /compra,
    /receta, /pesos, /eventos, /borrar, /ayuda, /nuevo...
  - Conversacional (con modelo): cualquier otro texto o foto con mención va a `claude -p`
    con las instrucciones de la skill don-gramo. El modelo interpreta y llama a scripts/dieta.py,
    que hace todas las cuentas y guarda el registro.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (HOME, SECRETS_FILE, SKILL, STATE, ahora, credenciales, load_config, log, resolver_claude,  # noqa: E402
                    ruta_extension, tg_api, tg_download, tg_send)

ROOT = SKILL  # los comandos se lanzan desde la carpeta de la skill: python3 scripts/dieta.py

OFFSET_FILE = STATE / "telegram-offset.json"
SESSION_FILE = STATE / "chat-session.json"
INBOX = STATE / "inbox"
SESSION_TTL_H = 6
LONG_POLL = 25
DIETA = [sys.executable, str(ROOT / "scripts" / "dieta.py")]

AYUDA = """*Don Gramo* — mencionadme (@{bot}) o usad un comando.

*Día a día*
`/hoy` — qué toca y cuánto a cada uno · `/hoy yo` · `/hoy detalle` con todo
`/manana` · `/racion` (reparto de lo cocinado)
`/receta lentejas` — pasos de una receta · `/receta hoy cena` — la de hoy, con cambios y cantidades
`/cookidoo hoy cena` — subir la receta del día a Cookidoo (te la enseña y confirmas con `si`)
`/cookidoo buscar merluza cena jueves` — buscar en el recetario oficial · `/cookidoo elegir 2`
`/borrar` — deshacer algo registrado · `/ajustes` · `/eventos`

*Semana*
`/menu` — platos de esta semana · `/menu proxima`
`/cambios` — cambios de la semana · `/deshacer N`
`/compra` · `/compra proxima` · `/compra nota` (para pegar en tu app de notas)
`/semana` — lo comido esta semana

*Entrenador*
`/progreso` — peso, tendencia y meta
`/pesos` · `/perfil` — objetivos de cada uno
`/revision` — propuesta de calorías · `/aceptar` · `/rechazar`

*Configuración*
`/soy <nombre>` — vincula tu Telegram con tu perfil (una vez) · `/hogar`

Para todo lo demás, escribid mencionándome:
"@{bot} hoy he comido fuera: menú del día con paella y flan"
"@{bot} cambia el pollo por ternera esta semana"
"@{bot} el jueves no quiero alubias, ¿qué me propones?"
"@{bot} mi objetivo ahora es 78 kg"
o mandad la captura de la báscula con "@{bot} mi peso de hoy".
Tarda 1–2 min cuando tiene que pensar."""


# --------------------------------------------------------------------------- estado
def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except json.JSONDecodeError:
        return default


def leer_offset() -> int:
    return int((_json(OFFSET_FILE, {}) or {}).get("offset", 0))


def guardar_offset(v: int) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": v}), encoding="utf-8")


def sesion_vigente() -> str | None:
    import datetime as dt
    d = _json(SESSION_FILE) or {}
    if not d.get("session_id"):
        return None
    try:
        if (ahora() - dt.datetime.fromisoformat(d["ts"])).total_seconds() > SESSION_TTL_H * 3600:
            return None
    except Exception:  # noqa: BLE001
        return None
    return d["session_id"]


def guardar_sesion(sid: str | None) -> None:
    if sid:
        STATE.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps({"session_id": sid, "ts": ahora().isoformat(timespec="seconds")}),
                                encoding="utf-8")


def olvidar_sesion() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


# --------------------------------------------------------------------------- capa rápida
def dieta(*args: str) -> str:
    p = subprocess.run([*DIETA, *args], capture_output=True, text=True, cwd=str(ROOT), timeout=150)
    return (p.stdout or "").strip() or f"Error: {(p.stderr or '')[-400:]}"


def cookidoo(*args: str) -> str:
    """Extensión don-gramo-cookidoo, si está instalada."""
    ext = ruta_extension("don-gramo-cookidoo")
    if not ext:
        return ("Cookidoo es una extensión aparte que no está instalada. Mientras tanto: `/receta hoy cena`.")
    p = subprocess.run([sys.executable, str(ext / "cookidoo.py"), *args], capture_output=True, text=True,
                       cwd=str(ext.parent), timeout=150)
    return (p.stdout or "").strip() or f"Error: {(p.stderr or '')[-400:]}"


COMANDOS = {"hoy", "manana", "mañana", "racion", "ración", "semana", "ajustes", "eventos", "borrar",
            "pesos", "receta", "compra", "ayuda", "help", "start", "nuevo", "menu", "menú", "cambios",
            "deshacer", "progreso", "perfil", "revision", "revisión", "aceptar", "rechazar", "cookidoo",
            "soy", "hogar"}


def semana_de(args: list[str]) -> list[str]:
    return ["--semana", "proxima"] if any(x.lower().startswith(("prox", "próx", "sig")) for x in args) else []


def comando(texto: str, bot: str) -> tuple[str, list[str]] | None:
    """'/hoy@bot marta' -> ('hoy', ['marta']). None si no es un comando conocido."""
    t = texto.strip()
    if not t.startswith("/"):
        return None
    partes = t[1:].split()
    nombre = partes[0].split("@")[0].lower()
    if "@" in partes[0] and bot and partes[0].split("@", 1)[1].lower() != bot.lower():
        return None  # comando dirigido a otro bot
    if nombre not in COMANDOS:
        return None
    return nombre, partes[1:]


def persona_de(argumento: list[str], remitente: str) -> str:
    args = [x.lower() for x in argumento if x.lower() not in ("detalle", "completo", "todo")]
    if not args:
        return "ambos"
    a = args[0]
    if a in ("yo", "mio", "mío", "mia", "mía"):
        return remitente
    return a


def detalle(argumento: list[str]) -> list[str]:
    return ["--detalle"] if any(x.lower() in ("detalle", "completo", "todo") for x in argumento) else []


def capa_rapida(nombre: str, args: list[str], remitente: str, bot: str) -> str:
    if nombre in ("ayuda", "help", "start"):
        return AYUDA.format(bot=bot or "bot")
    if nombre == "nuevo":
        olvidar_sesion()
        return "🧹 Conversación reiniciada."
    if nombre == "hoy":
        return dieta("hoy", "--persona", persona_de(args, remitente), *detalle(args))
    if nombre in ("manana", "mañana"):
        return dieta("manana", "--persona", persona_de(args, remitente), *detalle(args))
    if nombre in ("racion", "ración"):
        return dieta("racion")
    if nombre == "semana":
        return dieta("semana")
    if nombre == "ajustes":
        return dieta("ajustes")
    if nombre == "eventos":
        return dieta("eventos")
    if nombre == "borrar":
        return dieta("borrar", *args[:1])
    if nombre == "pesos":
        return dieta("pesos")
    if nombre == "receta":
        return dieta("receta", *args) if args else dieta("receta", "?")
    if nombre == "compra":
        if any(x.lower() in ("nota", "notas", "iphone", "copiar") for x in args):
            return dieta("compra", "--nota", *semana_de(args))
        sufijo = " proxima" if semana_de(args) else ""
        return dieta("compra", *semana_de(args)) + f"\n\n📲 Para Notas del iPhone: `/compra nota{sufijo}`"
    if nombre == "cookidoo":
        dias = {"hoy", "mañana", "manana", "lunes", "martes", "miercoles", "miércoles", "jueves", "viernes",
                "sabado", "sábado", "domingo"}
        comidas = {"comida": "Comida", "cena": "Cena", "desayuno": "Desayuno", "merienda": "Merienda"}
        a = [x.lower() for x in args]
        if a and a[0] in ("buscar", "busca"):
            resto = [x for x in a[1:] if x not in dias and x not in comidas and x not in ("para", "el", "la", "de", "del")]
            if not resto:
                return "Dime qué buscar: `/cookidoo buscar merluza cena jueves`"
            cmd = ["buscar", "--texto", " ".join(resto)]
            dia = next((x for x in a if x in dias), None)
            tipo = next((comidas[x] for x in a if x in comidas), None)
            return cookidoo(*cmd, *(["--fecha", dia] if dia else []), *(["--comida", tipo] if tipo else []))
        if a and a[0] in ("elegir", "elijo", "usar"):
            n = next((x for x in a if x.isdigit()), None)
            if not n:
                return "Dime el número: `/cookidoo elegir 2`"
            return cookidoo("elegir", "--n", n, *(["--compra"] if any(x.startswith("compra") for x in a) else []))
        cmd = ["receta"]
        dia = next((x for x in a if x in dias), None)
        if dia:
            cmd += ["--fecha", dia]
        tipo = next((comidas[x] for x in a if x in comidas), None)
        if tipo:
            cmd += ["--comida", tipo]
        if any(x in ("si", "sí", "subir", "vale", "ok") for x in a):
            cmd.append("--subir")
        if any(x.startswith("compra") for x in a):
            cmd.append("--compra")
        return cookidoo(*cmd)
    if nombre in ("menu", "menú"):
        return dieta("menu", *semana_de(args))
    if nombre == "cambios":
        return dieta("cambios", *semana_de(args))
    if nombre == "deshacer":
        return dieta("deshacer", *[x for x in args if x.isdigit()][:1], *semana_de(args))
    if nombre == "progreso":
        return dieta("progreso")
    if nombre == "perfil":
        return dieta("perfil")
    if nombre in ("revision", "revisión"):
        return dieta("revision")
    if nombre == "aceptar":
        p = [x for x in args if x.lower() not in ("todo", "ambos")]
        return dieta("aceptar", *(["--persona", persona_de(p, remitente)] if p else []))
    if nombre == "rechazar":
        return dieta("rechazar")
    if nombre == "hogar":
        return dieta("personas")
    return "Comando desconocido. Prueba /ayuda."


# --------------------------------------------------------------------------- capa con modelo
PROMPT = """Eres Don Gramo, el entrenador y asistente de dieta del chat de Telegram de {hogar} ({personas}).
Sigue las instrucciones de la skill don-gramo que tienes en el prompt de sistema.

Escribe: *{quien}* ({persona}) · {fecha} {hora} (hora local, {dia}).
Mensaje:
{mensaje}
{foto}
Haz los cálculos SIEMPRE con `python3 {skill}/scripts/dieta.py` (nunca de cabeza) y registra lo que
corresponda antes de responder. Responde breve para Telegram (máx. ~12 líneas), en español,
dirigiéndote a {quien}. Formato: como mucho *negrita*."""

SEGUIMIENTO = """Escribe: *{quien}* ({persona}) · {fecha} {hora}.
{mensaje}
{foto}
(Mismas reglas: cálculos con {skill}/scripts/dieta.py, registra antes de responder, respuesta breve.)"""

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def capa_modelo(cfg: dict, mensaje: str, persona: str, foto: Path | None) -> str:
    claude = resolver_claude(cfg)
    n = ahora()
    datos = {"quien": cfg["personas"][persona]["nombre"], "persona": persona, "fecha": n.date().isoformat(),
             "hora": n.strftime("%H:%M"), "dia": DIAS[n.weekday()], "mensaje": mensaje or "(sin texto)",
             "hogar": cfg["hogar"]["nombre"], "skill": str(SKILL),
             "personas": ", ".join(f"{v['nombre']} = `{k}`" for k, v in cfg["personas"].items()),
             "foto": f"\nHa adjuntado una imagen: {foto}. Léela con Read (si es una captura de una báscula, "
                     f"anota el peso con `dieta.py peso`).\n" if foto else ""}
    # Lectura solo de la skill y de las fotos recibidas: nunca de state/ (secretos, datos de salud).
    # En las reglas de permisos de Claude Code, «//ruta» es una ruta absoluta.
    allowed = (f"Read(/{SKILL}/**),Read(/{INBOX}/**),Bash(python3 {SKILL}/scripts/dieta.py:*),"
               "Bash(python3 scripts/dieta.py:*),Bash(date:*)")
    # Denegar todo state/ bloquearía también state/inbox: se deniegan los ficheros sensibles uno a uno
    # (el resto de state/ ya queda fuera porque no está permitido ni es directorio de trabajo).
    # Además, en construir(): solo Read y Bash, sin heredar los ajustes del usuario (sus reglas «allow»
    # abrirían más lecturas) y sin sus servidores MCP.
    denied = f"Read(/{SECRETS_FILE}),Read(/{HOME}/config.json),Read(/{HOME}/logs/**)"
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8").replace("{baseDir}", str(SKILL))
    ext = ruta_extension("don-gramo-cookidoo")
    if ext:  # extensión de Cookidoo: sus instrucciones y su comando, con la ruta completa
        allowed += f",Read(/{ext.parent}/**),Bash(python3 {ext}/cookidoo.py:*)"
        skill += "\n\n" + (ext.parent / "SKILL.md").read_text(encoding="utf-8").replace("{baseDir}", str(ext.parent))

    def construir(sesion: str | None) -> list[str]:
        prompt = (SEGUIMIENTO if sesion else PROMPT).format(**datos)
        c = [claude, "-p", prompt, "--output-format", "json", "--tools", "Read,Bash",
             "--setting-sources", "project", "--strict-mcp-config", "--allowed-tools", allowed,
             "--disallowed-tools", denied, "--add-dir", str(ROOT), "--add-dir", str(INBOX),
             "--append-system-prompt", skill]
        if sesion:
            c += ["--resume", sesion]
        if cfg["agent"].get("claude_model"):
            c += ["--model", cfg["agent"]["claude_model"]]
        return c

    sesion = sesion_vigente()
    try:
        proc = subprocess.run(construir(sesion), capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    except FileNotFoundError:
        return "No encuentro `claude` desde launchd. Pon la ruta de `which claude` en `agent.claude_bin` de config.json."
    if sesion and proc.returncode != 0:
        log("--resume falló, empiezo conversación nueva", level="WARN")
        olvidar_sesion()
        proc = subprocess.run(construir(None), capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    try:
        salida = json.loads(proc.stdout)
        guardar_sesion(salida.get("session_id"))
        return salida.get("result") or "(sin respuesta)"
    except Exception:  # noqa: BLE001
        return f"El modelo no respondió bien:\n{(proc.stderr or proc.stdout)[-400:]}"


# --------------------------------------------------------------------------- despacho
def vincular(cfg: dict, user_id, args: list[str], actual: str | None) -> str:
    """`/soy marta`: asocia este Telegram a una persona del plan que aún no tenga ninguno."""
    if actual:
        return f"Ya te tengo como {cfg['personas'][actual]['nombre']}."
    if not args:
        return "Dime quién eres: `/soy <nombre>`. En el plan: " + ", ".join(v["nombre"] for v in cfg["personas"].values())
    q = " ".join(args)
    out = dieta("personas")  # valida que hay plan
    candidatos = [k for k, v in cfg["personas"].items()
                  if k == q.lower() or v["nombre"].lower() == q.lower() or k.startswith(q.lower())]
    if len(candidatos) != 1:
        return f"No encuentro a «{q}» en el plan.\n{out}"
    p = candidatos[0]
    if cfg["personas"][p].get("telegram_ids"):
        return f"{cfg['personas'][p]['nombre']} ya tiene un Telegram vinculado. Si es un error, cámbialo en config.json."
    res = dieta("vincular-telegram", "--persona", p, "--id", str(user_id))
    cfg["personas"][p].setdefault("telegram_ids", []).append(str(user_id))
    return f"👋 {res} Ya puedes escribirme."


def remitente(cfg: dict, user_id) -> str | None:
    for clave, p in cfg["personas"].items():
        if str(user_id) in {str(x) for x in p.get("telegram_ids", [])}:
            return clave
    return None


def dirigido_al_bot(msg: dict, bot: str, bot_id: int | None) -> bool:
    if (msg.get("chat") or {}).get("type") == "private":  # en privado todo va al bot, sin mención
        return True
    texto = msg.get("text") or msg.get("caption") or ""
    if texto.strip().startswith("/"):
        primero = texto.strip().split()[0]
        return "@" not in primero or (bool(bot) and primero.split("@", 1)[1].lower() == bot.lower())
    if bot and f"@{bot.lower()}" in texto.lower():
        return True
    rep = msg.get("reply_to_message") or {}
    return bool(rep.get("from", {}).get("is_bot") and (bot_id is None or rep["from"].get("id") == bot_id))


def limpiar(texto: str, bot: str) -> str:
    return re.sub(rf"@{re.escape(bot)}\b", "", texto or "", flags=re.I).strip() if bot else (texto or "").strip()


def atender(cfg: dict, token: str, chat: str, msg: dict, bot: str, bot_id: int | None) -> None:
    if str((msg.get("chat") or {}).get("id")) != str(chat):
        log(f"ignoro chat ajeno {(msg.get('chat') or {}).get('id')}", level="WARN")
        return
    texto0 = (msg.get("text") or "").strip()
    uid = (msg.get("from") or {}).get("id")
    persona = remitente(cfg, uid)
    if comando(texto0, bot) and comando(texto0, bot)[0] == "soy":
        tg_send(token, chat, vincular(cfg, uid, comando(texto0, bot)[1], persona), reply_to=msg.get("message_id"))
        return
    if not persona:
        log(f"ignoro usuario no vinculado {uid}", level="WARN")
        if dirigido_al_bot(msg, bot, bot_id):
            tg_send(token, chat, "No te tengo vinculado todavía: escribe `/soy <tu nombre>` (el del plan).",
                    reply_to=msg.get("message_id"))
        return
    if not dirigido_al_bot(msg, bot, bot_id):
        return
    texto = msg.get("text") or msg.get("caption") or ""
    mid = msg.get("message_id")
    log(f"{persona} -> {texto[:120]!r}{' +foto' if msg.get('photo') else ''}")

    cmd = comando(texto, bot)
    if cmd and not msg.get("photo"):
        respuesta = capa_rapida(cmd[0], cmd[1], persona, bot)
        tg_send(token, chat, respuesta, reply_to=mid)
        return

    foto = None
    doc = msg.get("document") or {}
    if msg.get("photo"):
        mayor = max(msg["photo"], key=lambda p: p.get("file_size", 0))
        foto = tg_download(token, mayor["file_id"], INBOX / f"{ahora():%Y%m%d-%H%M%S}-{persona}.jpg")
    elif str(doc.get("mime_type", "")).startswith("image/"):
        ext = Path(doc.get("file_name") or "foto.jpg").suffix or ".jpg"
        foto = tg_download(token, doc["file_id"], INBOX / f"{ahora():%Y%m%d-%H%M%S}-{persona}{ext}")
    hilo = " (sigo el hilo)" if sesion_vigente() else ""
    tg_send(token, chat, f"⏳ Lo miro{hilo}…", reply_to=mid)
    try:
        respuesta = capa_modelo(cfg, limpiar(texto, bot), persona, foto)
    except Exception as exc:  # noqa: BLE001
        log(f"error con el modelo: {exc!r}", level="ERROR")
        respuesta = f"Se rompió algo: {exc!r}"
    tg_send(token, chat, respuesta, reply_to=mid)


def una_pasada(cfg: dict, token: str, chat: str, bot: str, bot_id: int | None, espera: int = 0) -> int:
    try:
        r = tg_api(token, "getUpdates", _timeout=espera + 15, offset=leer_offset(), timeout=espera,
                   allowed_updates=json.dumps(["message"]))
    except Exception as exc:  # noqa: BLE001
        log(f"getUpdates falló: {exc!r}", level="ERROR")
        return 1
    if not r.get("ok"):
        log(f"getUpdates: {r.get('description')}", level="ERROR")
        return 1
    for upd in r.get("result", []):
        guardar_offset(upd["update_id"] + 1)
        msg = upd.get("message")
        if msg:
            try:
                atender(cfg, token, chat, msg, bot, bot_id)
            except Exception as exc:  # noqa: BLE001
                log(f"error atendiendo: {exc!r}", level="ERROR")
    return 0


def main() -> int:
    cfg = load_config()
    token, chat = credenciales(cfg)
    if not token or not chat:
        log("faltan credenciales de Telegram (Keychain o state/secrets.env)", level="ERROR")
        return 1
    bot, bot_id = cfg["telegram"].get("bot_username") or "", None
    try:
        me = tg_api(token, "getMe")["result"]
        bot, bot_id = me.get("username") or bot, me.get("id")
    except Exception as exc:  # noqa: BLE001
        log(f"getMe falló: {exc!r}", level="WARN")
    if "--daemon" not in sys.argv:
        return una_pasada(cfg, token, chat, bot, bot_id)
    log(f"puente en marcha como @{bot} (long polling)")
    fallos = 0
    while True:
        rc = una_pasada(cfg, token, chat, bot, bot_id, espera=LONG_POLL)
        if rc == 0:
            fallos = 0
            continue
        fallos = min(fallos + 1, 6)
        time.sleep(min(5 * (2 ** (fallos - 1)), 300))


if __name__ == "__main__":
    sys.exit(main())
