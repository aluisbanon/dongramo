#!/bin/bash
# Instala la skill de Don Gramo en herramientas compatibles con AgentSkills (la misma skill para todas).
# En Claude Code no hace falta: usa el plugin (/plugin marketplace add ... y /plugin install ...).
#
#   ./instalar.sh codex      [--cookidoo]   copia a ${CODEX_HOME:-~/.codex}/skills/
#   ./instalar.sh openclaw   [--cookidoo] [--agent ID]   usa `openclaw skills install` (por defecto, --global)
#   ./instalar.sh agents     [--cookidoo]   copia a ~/.agents/skills/ (ruta estándar compartida)
#
# --cookidoo añade también la extensión opcional y no oficial de Cookidoo.
# Para actualizar: `git pull` y vuelve a ejecutar el mismo comando. Tus datos (~/.dongramo) no se tocan.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")" && pwd)"
NUCLEO="$RAIZ/plugins/dongramo/skills/dongramo"
EXT="$RAIZ/plugins/dongramo-cookidoo/skills/dongramo-cookidoo"
dg_home() {  # carpeta de datos; si solo existe ~/.don-gramo (nombre de la 1.0) la pasa a ~/.dongramo
  if [ -n "${DONGRAMO_HOME:-}" ]; then echo "$DONGRAMO_HOME"; return; fi
  if [ -n "${DON_GRAMO_HOME:-}" ]; then echo "$DON_GRAMO_HOME"; return; fi
  if [ ! -e "$HOME/.dongramo" ] && [ -d "$HOME/.don-gramo" ] && [ ! -L "$HOME/.don-gramo" ]; then
    mv "$HOME/.don-gramo" "$HOME/.dongramo" && ln -s "$HOME/.dongramo" "$HOME/.don-gramo"
  fi
  echo "$HOME/.dongramo"
}
DATOS="$(dg_home)"

DESTINO="${1:-}"; shift || true
COOKIDOO=0; AGENTE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --cookidoo) COOKIDOO=1 ;;
    --agent) AGENTE="${2:-}"; shift ;;
    *) echo "Opción desconocida: $1"; exit 1 ;;
  esac
  shift
done

command -v python3 >/dev/null || { echo "Necesitas python3 (3.9 o superior)."; exit 1; }

copiar() {  # copiar <origen> <carpeta de skills>
  local destino="$2/$(basename "$1")"
  local antigua="$2/$(basename "$1" | sed 's/^dongramo/don-gramo/')"  # nombre de la 1.0
  mkdir -p "$2"
  if [ -d "$antigua" ] && [ "$antigua" != "$destino" ]; then rm -rf "$antigua"; echo "🧹 Quitada la copia con el nombre antiguo: $antigua"; fi
  rm -rf "$destino"
  cp -R "$1" "$destino"
  find "$destino" -name __pycache__ -prune -exec rm -rf {} +
  echo "✅ $(basename "$1") → $destino"
}

case "$DESTINO" in
  codex)
    SK="${CODEX_HOME:-$HOME/.codex}/skills"
    copiar "$NUCLEO" "$SK"
    [ "$COOKIDOO" = 1 ] && copiar "$EXT" "$SK"
    mkdir -p "$DATOS"
    cat <<EOF

Codex solo deja escribir dentro del proyecto. Para que Don Gramo pueda guardar tus datos en $DATOS:
  · en cada uso:      codex --add-dir "$DATOS"
  · o para siempre, añade a ${CODEX_HOME:-$HOME/.codex}/config.toml:
      [sandbox_workspace_write]
      writable_roots = ["$DATOS"]
Después, pídeselo con naturalidad: «configura Don Gramo para mi familia».
EOF
    ;;
  openclaw)
    command -v openclaw >/dev/null || { echo "No encuentro el comando openclaw."; exit 1; }
    AMBITO=(--global); [ -n "$AGENTE" ] && AMBITO=(--agent "$AGENTE")
    openclaw skills install "$NUCLEO" "${AMBITO[@]}"
    [ "$COOKIDOO" = 1 ] && openclaw skills install "$EXT" "${AMBITO[@]}"
    echo
    echo "Listo. Comprueba con: openclaw skills info dongramo"
    echo "Si OpenClaw pide aprobar cada comando, permite python3 …/dongramo/scripts/dieta.py."
    echo "Si tenías instalada la skill con el nombre antiguo (don-gramo), quítala de OpenClaw para no tener dos."
    ;;
  agents)
    copiar "$NUCLEO" "$HOME/.agents/skills"
    [ "$COOKIDOO" = 1 ] && copiar "$EXT" "$HOME/.agents/skills"
    ;;
  *)
    sed -n '2,12p' "$0"; exit 1 ;;
esac
