"""Utilidades compartidas. Solo stdlib: debe correr con el python3 del sistema (3.9+).

El código vive en el plugin y los datos de cada hogar en DONGRAMO_HOME (por defecto ~/.dongramo):
    config.json   personas, horario, módulos (Thermomix, Telegram, Cookidoo)
    state/        registro, pesos, perfiles, cambios de menú, secretos
    logs/
Así una actualización del plugin nunca pisa vuestros datos.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
SKILL_DATA = SKILL / "data"
# Nombre antiguo (hasta la 1.0): «don-gramo». Se sigue entendiendo para no perder datos ni secretos.
HOME_ANTIGUO = Path.home() / ".don-gramo"


def resolver_home() -> Path:
    """Carpeta de datos: $DONGRAMO_HOME, $DON_GRAMO_HOME (antigua) o ~/.dongramo.
    Si solo existe ~/.don-gramo, la renombra a ~/.dongramo y deja un enlace con el nombre antiguo
    para que un bot instalado con la versión anterior siga encontrando sus datos."""
    for var in ("DONGRAMO_HOME", "DON_GRAMO_HOME"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser()
    nuevo = Path.home() / ".dongramo"
    if not nuevo.exists() and HOME_ANTIGUO.is_dir() and not HOME_ANTIGUO.is_symlink():
        try:
            HOME_ANTIGUO.rename(nuevo)
            HOME_ANTIGUO.symlink_to(nuevo, target_is_directory=True)
        except OSError:
            return HOME_ANTIGUO if HOME_ANTIGUO.is_dir() else nuevo
    return nuevo


HOME = resolver_home()
CONFIG = HOME / "config.json"
STATE = HOME / "state"
LOGS = HOME / "logs"
SECRETS_FILE = STATE / "secrets.env"

CONFIG_BASE = {
    "zona_horaria": "Europe/Madrid",
    "hogar": {"nombre": "Casa", "thermomix": False, "modelo_thermomix": "TM6"},
    "personas": {},
    "reajuste": {"dias_hacia_delante": 3, "recorte_max_alimento_flexible": 0.5, "aceite_minimo_g": 3,
                 "umbral_kcal": 60},
    "telegram": {"bot_username": "", "secreto_token": "dongramo-telegram-bot",
                 "secreto_chat": "dongramo-telegram-chat", "aviso_diario": "07:30", "aviso_semanal": "10:00"},
    "agent": {"claude_bin": "", "claude_model": ""},
}


def _fusionar(base: dict, encima: dict) -> dict:
    out = dict(base)
    for k, v in encima.items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config() -> dict:
    """config.json del hogar sobre los valores por defecto. Sin configurar: personas vacías."""
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return _fusionar(CONFIG_BASE, json.load(fh))
    except FileNotFoundError:
        return json.loads(json.dumps(CONFIG_BASE))


def save_config(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CONFIG)


# --------------------------------------------------------------------------- extensiones
PLUGINS = HOME / "plugins.json"


def registrar_plugin(nombre: str, scripts: Path) -> None:
    """Apunta dónde están los scripts de un plugin de Don Gramo, para que el núcleo y sus
    extensiones se encuentren aunque Claude Code los instale en carpetas distintas."""
    try:
        reg = json.loads(PLUGINS.read_text(encoding="utf-8")) if PLUGINS.exists() else {}
    except json.JSONDecodeError:
        reg = {}
    antiguos = [k for k in reg if k in ("don-gramo", "don-gramo-cookidoo")]  # nombres de la 1.0
    for k in antiguos:
        reg.pop(k)
    if antiguos or reg.get(nombre) != str(scripts):
        reg[nombre] = str(scripts)
        HOME.mkdir(parents=True, exist_ok=True)
        PLUGINS.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def ruta_extension(nombre: str) -> Path | None:
    """Carpeta de scripts de una extensión (p. ej. dongramo-cookidoo), o None si no está instalada.
    Busca en lo registrado, junto al núcleo en el repositorio (plugins/<nombre>) y en la caché de plugins."""
    from glob import glob
    candidatos = []
    try:
        candidatos.append(Path(json.loads(PLUGINS.read_text(encoding="utf-8")).get(nombre, "")))
    except (OSError, json.JSONDecodeError):
        pass
    corto = nombre.replace("dongramo-", "")
    plugin = SKILL.parent.parent  # plugins/dongramo (repo) o cache/<marketplace>/dongramo/<versión>
    candidatos.append(plugin.parent / nombre / "skills" / nombre / "scripts")
    candidatos.append(SKILL.parent / nombre / "scripts")  # skills sueltas, una junto a otra (OpenClaw, ~/.agents/skills)
    candidatos += [Path(x) for x in sorted(glob(str(plugin.parent.parent / nombre / "*" / "skills" / nombre / "scripts")))]
    for c in candidatos:
        if str(c) not in ("", ".") and (c / f"{corto}.py").exists():
            return c
    return None


def cookidoo_listo() -> bool:
    """La extensión de Cookidoo está y su conexión preparada (./install.sh instalar)."""
    return bool(ruta_extension("dongramo-cookidoo")) and (HOME / ".venv-cookidoo" / "bin" / "python").exists()


def load_menu() -> dict:
    with open(SKILL_DATA / "menu.json", encoding="utf-8") as fh:
        return json.load(fh)


def ahora() -> _dt.datetime:
    """Hora local del hogar aunque el sistema esté en otra zona."""
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo(load_config().get("zona_horaria") or "Europe/Madrid")).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return _dt.datetime.now()


def hoy() -> _dt.date:
    return ahora().date()


def log(msg: str, *, level: str = "INFO") -> None:
    stamp = ahora().isoformat(timespec="seconds")
    line = f"{stamp} [{level}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / f"{hoy().isoformat()}.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def nombres_secreto(service: str) -> list:
    """El nombre pedido y, por compatibilidad, su equivalente con el nombre antiguo o el nuevo."""
    otros = []
    if service.startswith("dongramo-"):
        otros.append("don-gramo-" + service[len("dongramo-"):])
    elif service.startswith("don-gramo-"):
        otros.append("dongramo-" + service[len("don-gramo-"):])
    return [service, *otros]


def secreto(service: str) -> str | None:
    """Secreto con su nombre actual o el antiguo (don-gramo-…), el primero que exista."""
    for nombre in nombres_secreto(service):
        valor = _secreto(nombre)
        if valor:
            return valor
    return None


def _secreto(service: str) -> str | None:
    """Secreto del Keychain de macOS si existe; si no (Linux, sesión sin pantalla), de state/secrets.env (chmod 600)."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                                 capture_output=True, text=True, timeout=15)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if not SECRETS_FILE.exists():
        return None
    if SECRETS_FILE.stat().st_mode & 0o077:
        log(f"{SECRETS_FILE} tiene permisos demasiado abiertos: lo ignoro (chmod 600).", level="ERROR")
        return None
    for linea in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        clave, _, valor = linea.strip().partition("=")
        if clave.strip() == service and valor.strip():
            return valor.strip()
    return None


keychain = secreto  # nombre antiguo

CANDIDATOS_CLAUDE = ["/opt/homebrew/bin/claude", "/usr/local/bin/claude", "~/.claude/local/claude",
                     "~/.npm-global/bin/claude", "~/.local/bin/claude", "~/.nvm/versions/node/*/bin/claude"]


def resolver_claude(cfg: dict) -> str:
    """Ruta al binario de claude, resistente al PATH recortado de launchd/systemd."""
    from glob import glob
    from shutil import which
    c = (cfg.get("agent") or {}).get("claude_bin") or ""
    if c and os.path.exists(os.path.expanduser(c)):
        return os.path.expanduser(c)
    hallado = which("claude")
    if hallado:
        return hallado
    for patron in CANDIDATOS_CLAUDE:
        for ruta in glob(os.path.expanduser(patron)):
            if os.access(ruta, os.X_OK):
                return ruta
    return "claude"


# --------------------------------------------------------------------------- Telegram
API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 3800


def tg_api(token: str, method: str, _timeout: int = 40, **params):
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=_timeout) as r:
        return json.loads(r.read().decode())


def tg_send(token: str, chat: str, texto: str, reply_to: int | None = None) -> bool:
    """Envía en trozos. Si Telegram rechaza el Markdown, reintenta en texto plano.
    Devuelve False si algún trozo no se pudo enviar."""
    enviado = True
    for i in range(0, len(texto), MAX_LEN):
        trozo = texto[i:i + MAX_LEN]
        extra = {"reply_to_message_id": reply_to} if reply_to and i == 0 else {}
        try:
            try:
                r = tg_api(token, "sendMessage", chat_id=chat, text=trozo, parse_mode="Markdown",
                           disable_web_page_preview="true", **extra)
            except urllib.error.HTTPError as exc:  # el Markdown inválido llega como HTTP 400
                if exc.code != 400:
                    raise
                with exc:
                    r = {"ok": False, "description": exc.read().decode(errors="replace")[:200]}
            if r.get("ok"):
                continue
            log(f"Telegram rechazó el Markdown ({r.get('description')}), reintento en plano", level="WARN")
            r = tg_api(token, "sendMessage", chat_id=chat, text=trozo, disable_web_page_preview="true", **extra)
            if not r.get("ok"):
                raise RuntimeError(r.get("description"))
        except Exception as exc:  # noqa: BLE001
            log(f"no pude enviar a Telegram: {exc!r}", level="ERROR")
            enviado = False
    return enviado


def tg_download(token: str, file_id: str, dest: Path) -> Path | None:
    try:
        info = tg_api(token, "getFile", file_id=file_id)
        path = info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{token}/{path}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as fh:
            fh.write(r.read())
        return dest
    except Exception as exc:  # noqa: BLE001
        log(f"no pude descargar la foto: {exc!r}", level="ERROR")
        return None


def credenciales(cfg: dict) -> tuple[str | None, str | None]:
    t = cfg["telegram"]
    return secreto(t["secreto_token"]), secreto(t["secreto_chat"])
