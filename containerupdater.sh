#!/bin/bash
# Walk every stack directory with a docker-compose.yml, pull the latest
# images, and recreate containers. Safe to run on cron. A stack with
# invalid config or a failing pull/up logs a warning and the loop
# continues so one bad stack never blocks the rest.
#
# Stacks that have a secrets.env (op:// references into 1Password) are
# wrapped with `op run` so secrets are resolved at up-time without any
# plaintext ever landing on disk. Stacks without a secrets.env use
# plain docker compose.

set -uo pipefail

cd "$(dirname "$0")"

# Pull OP_SERVICE_ACCOUNT_TOKEN into the script's environment so `op run`
# can authenticate. runner.env is the single place this bootstrap token
# lives — we source it here rather than maintain a duplicate copy.
if [ -f runner/runner.env ]; then
    set -a
    # shellcheck disable=SC1091
    . runner/runner.env
    set +a
fi

for dir in */; do
    compose="${dir}docker-compose.yml"
    [ -f "$compose" ] || continue

    echo "==> Updating ${dir%/}"
    (
        cd "$dir"
        if ! docker compose config --quiet 2>/dev/null; then
            echo "  skipped: invalid or incomplete compose config" >&2
            exit 0
        fi

        # `--pull always` forces docker build to refetch the base image
        # referenced in any local Dockerfile (runner/ uses one). `docker
        # compose pull` on its own only updates `image:` services.
        if [ -f secrets.env ]; then
            op run --env-file=secrets.env -- docker compose pull && \
            op run --env-file=secrets.env -- docker compose up -d --build --pull always
        else
            docker compose pull && docker compose up -d --build --pull always
        fi
    ) || echo "  failed to update ${dir%/}; continuing" >&2
done

# Only drop dangling layers left by this update cycle. Avoid "-a" since
# it would wipe any unused images on the host, including ones outside
# this repo that other workloads or manual pulls rely on.
docker image prune -f
