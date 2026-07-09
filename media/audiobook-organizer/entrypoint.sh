#!/usr/bin/env bash
# Run one organize pass at start, then once per day. Staying alive also
# lets `docker exec -it audiobook-organizer organize --interactive` work.
set -uo pipefail
while true; do
  echo "[entrypoint] $(date) starting daily organize pass"
  organize || echo "[entrypoint] organize pass exited non-zero; continuing" >&2
  echo "[entrypoint] sleeping 24h"
  sleep 86400
done
