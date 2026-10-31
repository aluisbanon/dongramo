#!/bin/bash
# Bot de Telegram y avisos programados de Don Gramo (opcional). macOS (launchd) y Linux (systemd --user).
#
#   bot/install.sh token            guarda el token del bot (te lo pide; de @BotFather)
#   bot/install.sh chat CHAT_ID     guarda el id del grupo o chat privado
#   bot/install.sh ids              muestra chats y usuarios que han escrito al bot (con el puente parado)
#   bot/install.sh activar          pone en marcha el puente y los avisos (diario y del domingo)
#   bot/install.sh parar            los detiene
#   bot/install.sh estado           ¿están en marcha? últimas líneas del log
#   bot/install.sh probar           muestra el aviso de hoy sin enviarlo
#
# Datos y secretos: $DON_GRAMO_HOME (por defecto ~/.don-gramo). Nada de esto sale de tu máquina,
# salvo los mensajes a Telegram.
set -euo pipefail
BOT="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(cd "$BOT/../skills/don-gramo" && pwd)"
DGHOME="${DON_GRAMO_HOME:-$HOME/.don-gramo}"
SECRETS="$DGHOME/state/secrets.env"
export DON_GRAMO_HOME="$DGHOME"
mkdir -p "$DGHOME/state" "$DGHOME/logs"
PY="$(command -v python3)"

hora() {  # hora de un aviso en config.json (HH:MM) -> "H M"
  "$PY" -I -c "import json,sys,os;c=json.load(open(os.path.join(os.environ['DON_GRAMO_HOME'],'config.json'))) if os.path.exists(os.path.join(os.environ['DON_GRAMO_HOME'],'config.json')) else {};h=c.get('telegram',{}).get('$1','$2');print(int(h[:2]),int(h[3:5]))"
}

rellenar() {  # plantilla -> destino, con rutas y hora
  local H M; read -r H M <<<"${3:-0 0}"
  sed -e "s#__SKILL__#$SKILL#g" -e "s#__HOME__#$HOME#g" -e "s#__DGHOME__#$DGHOME#g" \
      -e "s#__H__#$H#g" -e "s#__MI__#$M#g" -e "s#__M__#$(printf %02d "$M")#g" "$1" > "$2"
}

# Guarda un secreto en state/secrets.env (chmod 600), que funciona sin sesión gráfica y en Linux,
# y además en el Keychain de macOS si se puede.
guardar() {
  touch "$SECRETS"; chmod 600 "$SECRETS"
  grep -v "^$1=" "$SECRETS" > "$SECRETS.tmp" || true
  echo "$1=$2" >> "$SECRETS.tmp"; mv "$SECRETS.tmp" "$SECRETS"; chmod 600 "$SECRETS"
  if [ "$(uname)" = Darwin ] && security add-generic-password -U -a "$USER" -s "$1" -w "$2" 2>/dev/null; then
    echo "Guardado $1 en $SECRETS y en el Keychain."
  else
    echo "Guardado $1 en $SECRETS."
  fi
}

case "${1:-}" in
  token)
    read -r -s -p "Token del bot (de @BotFather): " T; echo
    guardar don-gramo-telegram-bot "$T" ;;
  chat)
    [ -n "${2:-}" ] || { echo "Uso: bot/install.sh chat -100XXXXXXXXXX (grupo) o tu id (chat privado)"; exit 1; }
    guardar don-gramo-telegram-chat "$2" ;;
  ids)
    "$PY" "$SKILL/scripts/setup_ids.py" ;;
  activar|cargar)
    [ -f "$DGHOME/config.json" ] || { echo "Primero configura el hogar (en Claude Code: /don-gramo:configurar)."; exit 1; }
    if [ "$(uname)" = Darwin ]; then
      LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
      rellenar "$BOT/launchd/telegram.plist.tpl" "$LA/com.dongramo.telegram.plist"
      rellenar "$BOT/launchd/diario.plist.tpl" "$LA/com.dongramo.diario.plist" "$(hora aviso_diario 07:30)"
      rellenar "$BOT/launchd/semanal.plist.tpl" "$LA/com.dongramo.semanal.plist" "$(hora aviso_semanal 10:00)"
      for L in telegram diario semanal; do
        launchctl unload "$LA/com.dongramo.$L.plist" 2>/dev/null || true
        launchctl load "$LA/com.dongramo.$L.plist"
      done
      launchctl list | grep com.dongramo || true
    else
      U="$HOME/.config/systemd/user"; mkdir -p "$U"
      rellenar "$BOT/systemd/don-gramo-telegram.service.tpl" "$U/don-gramo-telegram.service"
      for n in diario semanal; do rellenar "$BOT/systemd/don-gramo-$n.service.tpl" "$U/don-gramo-$n.service"; done
      rellenar "$BOT/systemd/don-gramo-diario.timer.tpl" "$U/don-gramo-diario.timer" "$(hora aviso_diario 07:30)"
      rellenar "$BOT/systemd/don-gramo-semanal.timer.tpl" "$U/don-gramo-semanal.timer" "$(hora aviso_semanal 10:00)"
      systemctl --user daemon-reload
      systemctl --user enable --now don-gramo-telegram.service don-gramo-diario.timer don-gramo-semanal.timer
      echo "Para que siga funcionando sin sesión abierta: sudo loginctl enable-linger $USER"
    fi ;;
  parar)
    if [ "$(uname)" = Darwin ]; then
      for L in telegram diario semanal; do launchctl unload "$HOME/Library/LaunchAgents/com.dongramo.$L.plist" 2>/dev/null || true; done
    else
      systemctl --user disable --now don-gramo-telegram.service don-gramo-diario.timer don-gramo-semanal.timer 2>/dev/null || true
    fi
    echo "Procesos parados." ;;
  estado)
    if [ "$(uname)" = Darwin ]; then
      launchctl list | grep com.dongramo || echo "No hay procesos cargados."
    else
      systemctl --user --no-pager status don-gramo-telegram.service don-gramo-diario.timer don-gramo-semanal.timer | head -30 || true
    fi
    tail -n 15 "$DGHOME/logs/$(date +%F).log" 2>/dev/null || true ;;
  probar)
    "$PY" "$SKILL/scripts/aviso.py" --diario --imprimir ;;
  *)
    sed -n '2,12p' "$0" ;;
esac
