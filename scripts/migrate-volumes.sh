#!/usr/bin/env bash
# Copy all data of this machine's stack (database, files, search index, app data, backups) to another Docker host,
# streaming over SSH. Run it on the machine that holds the data.
#
#   scripts/migrate-volumes.sh user@192.168.1.12 [REMOTE_PREFIX] [--yes] [--dry-run]
#
# REMOTE_PREFIX is the Compose project name on the target (the part before "_postgres-data" in `docker volume ls`).
# It is detected when exactly one such volume exists. The target stack must be stopped; its volumes are REPLACED.
set -euo pipefail

LOCAL_PREFIX="${LOCAL_PREFIX:-ai-knowledge-hub}"
VOLUMES=(postgres-data seaweed-data qdrant-data api-data backups-data)
COMPOSE_LOCAL=(docker compose -f compose.yaml -f compose.dev.yaml)

TARGET="${1:-}"; shift || true
REMOTE_PREFIX=""; YES=0; DRY=0
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    *) REMOTE_PREFIX="$a" ;;
  esac
done
[ -n "$TARGET" ] || { echo "usage: $0 user@host [REMOTE_PREFIX] [--yes] [--dry-run]"; exit 2; }

run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi; }
remote() { if [ "$DRY" = 1 ]; then echo "+ ssh $TARGET $*"; else ssh -o BatchMode=yes "$TARGET" "$@"; fi; }

if [ -z "$REMOTE_PREFIX" ]; then
  [ "$DRY" = 0 ] || { echo "dry run needs REMOTE_PREFIX"; exit 2; }
  found=$(ssh -o BatchMode=yes "$TARGET" "docker volume ls -q" | grep '_postgres-data$' | sed 's/_postgres-data$//' || true)
  [ "$(printf '%s\n' "$found" | grep -c .)" = 1 ] || { echo "Cannot detect the target project (found: ${found:-none}). Deploy once in Dokploy, then pass REMOTE_PREFIX."; exit 1; }
  REMOTE_PREFIX="$found"
fi
echo "Source volumes : ${LOCAL_PREFIX}_*   (this machine)"
echo "Target volumes : ${REMOTE_PREFIX}_*  on $TARGET"

# the target must not be writing while its volumes are replaced
if [ "$DRY" = 0 ]; then
  for v in "${VOLUMES[@]}"; do
    if [ -n "$(ssh -o BatchMode=yes "$TARGET" "docker ps -q --filter volume=${REMOTE_PREFIX}_$v")" ]; then
      echo "A container on $TARGET still uses ${REMOTE_PREFIX}_$v. Stop the stack in Dokploy first."; exit 1
    fi
  done
fi

if [ "$YES" = 0 ] && [ "$DRY" = 0 ]; then
  echo "This STOPS the local stack and REPLACES the data on $TARGET."
  read -r -p "Type 'yes' to continue: " ans; [ "$ans" = yes ] || { echo "aborted"; exit 1; }
fi

echo "Stopping the local stack (a consistent copy needs it stopped)..."
run "${COMPOSE_LOCAL[@]}" stop

for v in "${VOLUMES[@]}"; do
  echo "Copying $v ..."
  remote "docker volume create ${REMOTE_PREFIX}_$v >/dev/null"
  if [ "$DRY" = 1 ]; then
    echo "+ docker run --rm -v ${LOCAL_PREFIX}_$v:/v:ro alpine tar czf - -C /v . | ssh $TARGET docker run --rm -i -v ${REMOTE_PREFIX}_$v:/v alpine sh -c 'find /v -mindepth 1 -delete; tar xzf - -C /v'"
  else
    docker run --rm -v "${LOCAL_PREFIX}_$v:/v:ro" alpine tar czf - -C /v . \
      | ssh -o BatchMode=yes "$TARGET" "docker run --rm -i -v ${REMOTE_PREFIX}_$v:/v alpine sh -c 'find /v -mindepth 1 -delete; tar xzf - -C /v'"
  fi
done

echo
echo "Done. The local stack stays STOPPED so two copies never diverge."
echo "Now start the stack in Dokploy. Change the demo account passwords right away."
