#!/usr/bin/env bash
# Instalador idempotente: deja la config de Claude Code del host apuntando a la copia instalada de este plugin —
# statusLine, hook Stop de sugiere y comando /sugiere. Vuelve a ejecutarlo tras cada actualización del plugin y no
# duplica nada: sustituye sus propias entradas y no toca las de terceros.
#
#   bash install/install.sh [--settings <ruta>]   (por defecto ~/.claude/settings.json)
#
# URLs por host como variables del entorno del instalador (se hornean en los comandos escritos):
#   SUGIERE_URL=https://...   el servicio sugiere fuera del clúster (ej. un Mac sin tailnet); por defecto el svc interno.
#   NEXUS_URL=https://...     el panel de enrutado para el segmento TTL de la barra; sin él, la barra no pinta TTL.
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
settings=~/.claude/settings.json
while [ $# -gt 0 ]; do
  case "$1" in
    --settings) settings="$2"; shift 2 ;;
    *) echo "uso: install.sh [--settings <ruta>]" >&2; exit 2 ;;
  esac
done
command -v jq >/dev/null || { echo "install: hace falta jq" >&2; exit 1; }

# Prefijos de entorno horneados solo si el host los define (así el script usa su default en el clúster).
sl_env=""; [ -n "${NEXUS_URL:-}" ] && sl_env="NEXUS_URL='$NEXUS_URL' "
sg_env=""; [ -n "${SUGIERE_URL:-}" ] && sg_env="SUGIERE_URL='$SUGIERE_URL' "
sl_cmd="${sl_env}bash '$dir/statusline/claude-statusline-panel'"
sg_cmd="${sg_env}node '$dir/console/sugiere-stop.ts' 2>/dev/null || true"

mkdir -p "$(dirname "$settings")" ~/.claude/commands
[ -f "$settings" ] || printf '{}\n' > "$settings"

# statusLine + hook Stop por jq, escritura atómica. Las entradas propias se reconocen por la ruta del plugin y se
# reescriben enteras; cualquier otra entrada ajena (otros hooks, otros matchers) sale intacta.
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
jq --arg sl "$sl_cmd" --arg sg "$sg_cmd" '
  .statusLine = {type: "command", command: $sl}
  | .hooks //= {}
  | .hooks.Stop = ((.hooks.Stop // [])
      | map(.hooks |= map(select(((.command // "") | test("sugiere-stop\\.ts")) | not)))
      | map(select((.hooks // []) | length > 0)))
  | .hooks.Stop += [{matcher: "", hooks: [{type: "command", command: $sg, timeout: 30}]}]
' "$settings" > "$tmp" && mv "$tmp" "$settings" && trap - EXIT

# /sugiere lleva también la URL horneada: fuera del clúster (Cloudblue) el default interno es inalcanzable.
# Con SUGIERE_URL sin definir queda "" → el script usa su default (es falso para ||).
sed -e "s#__PLUGIN_DIR__#$dir#g" -e "s#__SUGIERE_URL__#${SUGIERE_URL:-}#g" "$dir/commands/sugiere.md" > ~/.claude/commands/sugiere.md

echo "instalado en $settings"
echo "  statusLine: $sl_cmd"
echo "  Stop:       $sg_cmd"
echo "  /sugiere:   ~/.claude/commands/sugiere.md (→ $dir)"
