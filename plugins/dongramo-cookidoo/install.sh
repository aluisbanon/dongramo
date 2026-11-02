#!/bin/bash
# Don Gramo · Cookidoo (extensión opcional y no oficial).
#
#   ./install.sh instalar   Python 3.12 aparte (con uv) + librería comunitaria cookidoo-api
#   ./install.sh cuenta     guarda tu email y contraseña de Cookidoo (te los pide)
#   ./install.sh probar     comprueba que entra en tu cuenta
#
# Tus credenciales se quedan en tu máquina: Keychain de macOS y/o $DONGRAMO_HOME/state/secrets.env (chmod 600).
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$AQUI/skills/dongramo-cookidoo/scripts"
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
mkdir -p "$DGHOME/state"

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
  instalar)
    UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
    if [ ! -x "$UV" ]; then
      echo "Instalando uv (gestor de Python, en ~/.local/bin)..."
      curl -LsSf https://astral.sh/uv/install.sh | sh
      UV="$HOME/.local/bin/uv"
    fi
    "$UV" venv --python 3.12 "$DGHOME/.venv-cookidoo"
    "$UV" pip install --python "$DGHOME/.venv-cookidoo/bin/python" "cookidoo-api==0.19.0"
    echo "Listo. Ahora: ./install.sh cuenta" ;;
  cuenta)
    read -r -p "Email de Cookidoo: " E
    read -r -s -p "Contraseña de Cookidoo: " P; echo
    guardar cookidoo-email "$E"
    guardar cookidoo-password "$P"
    echo "Ahora: ./install.sh probar" ;;
  probar)
    DONGRAMO_HOME="$DGHOME" python3 "$SCRIPTS/cookidoo.py" probar ;;
  *)
    sed -n '2,9p' "$0" ;;
esac
