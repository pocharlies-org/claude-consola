---
description: Siguiente mensaje sugerido por el servicio sugiere (el mismo de la píldora de Paseo)
---

Muestra al usuario literalmente lo de abajo, sin añadir ni quitar nada:

!`t=~/.claude/projects/$(pwd | tr / -)/${CLAUDE_CODE_SESSION_ID:-$(ls -t ~/.claude/projects/$(pwd | tr / -)/*.jsonl 2>/dev/null | head -1 | xargs -n1 basename .jsonl 2>/dev/null)}.jsonl; out=$([ -f "$t" ] && printf '{"session_id":"%s","transcript_path":"%s"}' "$(basename "$t" .jsonl)" "$t" | SUGIERE_URL="__SUGIERE_URL__" node __PLUGIN_DIR__/console/sugiere-stop.ts 2>/dev/null | jq -r '.systemMessage // empty'); echo "${out:-Sin sugerencia ahora mismo (el servicio no ve nada que proponer).}"`
