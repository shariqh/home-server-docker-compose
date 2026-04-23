#!/bin/bash
# Bring up every stack in the repo. Safe to run multiple times —
# docker compose will only (re)create containers when config changed.
# Each stack is wrapped with `op run` if it has a secrets.env; plain
# docker compose otherwise. A stack that fails to come up logs a
# warning and the loop moves on.

set -uo pipefail

cd "$(dirname "$0")"

# Bootstrap OP_SERVICE_ACCOUNT_TOKEN so `op run` can authenticate.
if [ -f runner/runner.env ]; then
    set -a
    # shellcheck disable=SC1091
    . runner/runner.env
    set +a
fi

# Delegate image builds to buildx bake for faster/parallel builds.
export COMPOSE_BAKE=true

for dir in */; do
    compose="${dir}docker-compose.yml"
    [ -f "$compose" ] || continue

    echo "==> Bringing up ${dir%/}"
    (
        cd "$dir"
        if [ -f secrets.env ]; then
            op run --env-file=secrets.env -- docker compose up -d --build
        else
            docker compose up -d --build
        fi
    ) || echo "  failed to bring up ${dir%/}; continuing" >&2
done
