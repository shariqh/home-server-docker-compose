#!/bin/bash
# Walk every stack directory with a docker-compose.yml, pull the latest
# images, and recreate containers. Safe to run on cron. A stack with
# invalid config or a failing pull/up logs a warning and the loop
# continues so one bad stack never blocks the rest.

set -uo pipefail

cd "$(dirname "$0")"

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
        # compose pull` on its own only updates `image:` services, so
        # without this flag the runner would keep its stale base layer.
        docker compose pull && docker compose up -d --build --pull always
    ) || echo "  failed to update ${dir%/}; continuing" >&2
done

# Only drop dangling layers left by this update cycle. Avoid "-a" since
# it would wipe any unused images on the host, including ones outside
# this repo that other workloads or manual pulls rely on.
docker image prune -f
