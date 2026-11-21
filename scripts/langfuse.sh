#!/usr/bin/env bash
# Turn Langfuse tracing on or off: sets LANGFUSE_ENABLED in .env AND starts/stops the Langfuse containers.
#   scripts/langfuse.sh on | off | status      (add --prod to use compose.prod.yaml instead of compose.dev.yaml)
set -euo pipefail
cd "$(dirname "$0")/.."
ACTION="${1:-status}"; MODE=dev; [ "${2:-}" = "--prod" ] && MODE=prod
C=(docker compose -f compose.yaml -f "compose.$MODE.yaml" -f compose.langfuse.yaml)
touch .env
setenv() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
case "$ACTION" in
  on)
    scripts/setup-langfuse.sh >/dev/null            # adds missing keys/secrets, never overwrites
    sed -i 's/^# \(LANGFUSE_\(PUBLIC_KEY\|SECRET_KEY\|HOST\)=\)/\1/' .env
    setenv LANGFUSE_ENABLED true
    "${C[@]}" up -d langfuse-web langfuse-worker langfuse-db langfuse-clickhouse langfuse-redis
    "${C[@]}" up -d --force-recreate --no-deps api worker
    echo "Langfuse is ON. UI: http://localhost:3100" ;;
  off)
    setenv LANGFUSE_ENABLED false
    # stop the containers by name (the Langfuse compose file needs its keys, which may be absent)
    docker ps -q --filter "label=com.docker.compose.service" --format '{{.ID}} {{.Label "com.docker.compose.service"}}' | awk '$2 ~ /^langfuse-/ {print $1}' | xargs -r docker stop >/dev/null
    docker compose -f compose.yaml -f "compose.$MODE.yaml" up -d --force-recreate --no-deps api worker
    echo "Langfuse is OFF (containers stopped, data kept; 'docker compose ... down -v' would delete it)." ;;
  status) grep "^LANGFUSE_ENABLED=" .env || echo "LANGFUSE_ENABLED not set (off)"; docker ps --format '{{.Names}}' | grep langfuse || echo "no langfuse containers running" ;;
  *) echo "usage: $0 on|off|status [--prod]"; exit 2 ;;
esac
