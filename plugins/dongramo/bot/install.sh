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
# Datos y secretos: $DONGRAMO_HOME (por defecto ~/.dongramo). Nada de esto sale de tu máquina,
# salvo los mensajes a Telegram.
set -euo pipefail
BOT="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(cd "$BOT/../skills/dongramo" && pwd)"
dg_home() {  # carpeta de datos; si solo existe ~/.don-gramo (nombre de la 1.0) la pasa a ~/.dongramo
  if [ -n "${DONGRAMO_HOME:-}" ]; then echo "$DONGRAMO_HOME"; return; fi
  if [ -n "${DON_GRAMO_HOME:-}" ]; then echo "$DON_GRAMO_HOME"; return; fi
  if [ ! -e "$HOME/.dongramo" ] && [ -d "$HOME/.don-gramo" ] && [ ! -L "$HOME/.don-gramo" ]; then
    mv "$HOME/.don-gramo" "$HOME/.dongramo" && ln -s "$HOME/.dongramo" "$HOME/.don-gramo"
  fi
  echo "$HOME/.dongramo"
}
DGHOME="$(dg_home)"
SECRETS="$DGHOME/state/secrets.env"
export DONGRAMO_HOME="$DGHOME"
mkdir -p "$DGHOME/state" "$DGHOME/logs"
PY="$(command -v python3)"

hora() {  # hora de un aviso en config.json (HH:MM) -> "H M"
  "$PY" -I -c "import json,sys,os;c=json.load(open(os.path.join(os.environ['DONGRAMO_HOME'],'config.json'))) if os.path.exists(os.path.join(os.environ['DONGRAMO_HOME'],'config.json')) else {};h=c.get('telegram',{}).get('$1','$2');print(int(h[:2]),int(h[3:5]))"
}

quitar_systemd_antiguo() {  # unidades con el nombre de la 1.0 (don-gramo-*)
  local U="$HOME/.config/systemd/user" hay=0 f
  for f in "$U"/don-gramo-*.service "$U"/don-gramo-*.timer; do [ -e "$f" ] && hay=1; done
  [ "$hay" = 1 ] || return 0
  systemctl --user disable --now don-gramo-telegram.service don-gramo-diario.timer don-gramo-semanal.timer 2>/dev/null || true
  rm -f "$U"/don-gramo-*.service "$U"/don-gramo-*.timer
  systemctl --user daemon-reload 2>/dev/null || true
  echo "Quitados los servicios con el nombre antiguo (don-gramo-*)."
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
    guardar dongramo-telegram-bot "$T" ;;
  chat)
    [ -n "${2:-}" ] || { echo "Uso: bot/install.sh chat -100XXXXXXXXXX (grupo) o tu id (chat privado)"; exit 1; }
    guardar dongramo-telegram-chat "$2" ;;
  ids)
    "$PY" "$SKILL/scripts/setup_ids.py" ;;
  activar|cargar)
    [ -f "$DGHOME/config.json" ] || { echo "Primero configura el hogar (en Claude Code: /dongramo:configurar)."; exit 1; }
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
      quitar_systemd_antiguo
      U="$HOME/.config/systemd/user"; mkdir -p "$U"
      rellenar "$BOT/systemd/dongramo-telegram.service.tpl" "$U/dongramo-telegram.service"
      for n in diario semanal; do rellenar "$BOT/systemd/dongramo-$n.service.tpl" "$U/dongramo-$n.service"; done
      rellenar "$BOT/systemd/dongramo-diario.timer.tpl" "$U/dongramo-diario.timer" "$(hora aviso_diario 07:30)"
      rellenar "$BOT/systemd/dongramo-semanal.timer.tpl" "$U/dongramo-semanal.timer" "$(hora aviso_semanal 10:00)"
      systemctl --user daemon-reload
      systemctl --user enable --now dongramo-telegram.service dongramo-diario.timer dongramo-semanal.timer
      echo "Para que siga funcionando sin sesión abierta: sudo loginctl enable-linger $USER"
    fi ;;
  parar)
    if [ "$(uname)" = Darwin ]; then
      for L in telegram diario semanal; do launchctl unload "$HOME/Library/LaunchAgents/com.dongramo.$L.plist" 2>/dev/null || true; done
    else
      systemctl --user disable --now dongramo-telegram.service dongramo-diario.timer dongramo-semanal.timer 2>/dev/null || true
      quitar_systemd_antiguo
    fi
    echo "Procesos parados." ;;
  estado)
    if [ "$(uname)" = Darwin ]; then
      launchctl list | grep com.dongramo || echo "No hay procesos cargados."
    else
      systemctl --user --no-pager status dongramo-telegram.service dongramo-diario.timer dongramo-semanal.timer | head -30 || true
    fi
    tail -n 15 "$DGHOME/logs/$(date +%F).log" 2>/dev/null || true ;;
  probar)
    "$PY" "$SKILL/scripts/aviso.py" --diario --imprimir ;;
  *)
    sed -n '2,12p' "$0" ;;
esac
