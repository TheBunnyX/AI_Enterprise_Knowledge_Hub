#!/usr/bin/env bash
# Turn ClamAV virus scanning on or off: sets CLAMAV_ENABLED in .env, starts/stops the clamav container and restarts api + worker.
#   scripts/clamav.sh on | off | status      (add --prod to use compose.prod.yaml instead of compose.dev.yaml)
set -euo pipefail
cd "$(dirname "$0")/.."
ACTION="${1:-status}"; MODE=dev; [ "${2:-}" = "--prod" ] && MODE=prod
C=(docker compose -f compose.yaml -f "compose.$MODE.yaml")
touch .env
setenv() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
case "$ACTION" in
  on)  setenv CLAMAV_ENABLED true; "${C[@]}" up -d --force-recreate api worker clamav; echo "ClamAV is ON (first start downloads signatures; uploads wait until it is ready)." ;;
  off) setenv CLAMAV_ENABLED false; "${C[@]}" up -d --force-recreate api worker; "${C[@]}" rm -sf clamav >/dev/null 2>&1 || true; echo "ClamAV is OFF: container stopped, uploads are not scanned." ;;
  status) grep "^CLAMAV_ENABLED=" .env || echo "CLAMAV_ENABLED not set (on)"; docker ps --format '{{.Names}} {{.Status}}' | grep clamav || echo "no clamav container running" ;;
  *) echo "usage: $0 on|off|status [--prod]"; exit 2 ;;
esac
