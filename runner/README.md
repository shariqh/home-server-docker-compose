# GitHub Actions self-hosted runner

Dockerized runner (`myoung34/github-runner` + 1Password CLI). In the default configuration, it is **repo-scoped** (`RUNNER_SCOPE=repo` + `REPO_URL=<repo>`) and only picks up jobs for that one repo when its workflows declare `runs-on: self-hosted`. See [Serving more than one repo](#serving-more-than-one-repo) below for org-scope or multi-service layouts.

Because the 1Password CLI is baked in, workflows can resolve secrets via `op run --env-file=secrets.env -- <command>` at job time — no plaintext values are ever written to disk. The service-account token stays on this host.

**Trust boundary:** this runner executes jobs from the configured repo with access to a Docker API (via a restricted socket proxy — see `docker-compose.yml`). Only point it at repos whose commits you trust, since a malicious workflow could still start and stop containers on this host.

## First-time setup

1. **GitHub PAT** with `repo` scope (or fine-grained token scoped to the target repo):
   https://github.com/settings/tokens/new

2. **1Password service account** (Settings → Developer → Service Accounts → Create).
   - Grant read-only access to only the vaults the runner needs.
   - Copy the `ops_...` token.

3. **Populate `runner.env`**:
   ```bash
   cp runner.env.example runner.env
   chmod 600 runner.env
   # edit and fill in REPO_URL, ACCESS_TOKEN, OP_SERVICE_ACCOUNT_TOKEN
   ```

4. **Start**:
   ```bash
   docker compose up -d --build
   ```

5. **Verify** in GitHub → repo → Settings → Actions → Runners. The runner should appear as **Idle** within ~30 seconds.

## Serving more than one repo

Easiest short-term: duplicate the `runner:` service in `docker-compose.yml`. Each duplicate **must** have its own:
- `container_name` (e.g. `github-runner-<repo>`)
- `env_file` (e.g. `runner-<repo>.env`) with a unique `RUNNER_NAME` and `REPO_URL`
- state volume (e.g. `runner-data-<repo>:/tmp/runner`, plus a matching entry under the top-level `volumes:` block)

Sharing `runner-data` between duplicated services causes runners to clobber each other's work directory — jobs will fail intermittently in ways that are hard to diagnose.

Long-term: move your repos under a GitHub organization, change `RUNNER_SCOPE=org` and point `REPO_URL` at the org URL. One runner serves every repo in the org.

## Updating

```bash
docker compose pull
docker compose up -d --build
```

## Troubleshooting

- **Runner shows Offline in GH** → `docker compose logs -f runner`; usually an auth error (bad PAT scope or typo).
- **`op run` fails inside a job with "not signed in"** → confirm `OP_SERVICE_ACCOUNT_TOKEN` made it into the container: `docker compose exec runner env | grep OP_`.
- **Can't reach host Docker** → the runner talks to the host socket via the `docker-proxy` service (over `DOCKER_HOST=tcp://docker-proxy:2375`), *not* a direct socket mount. Verify both legs:
  - proxy has the host socket: `docker compose exec docker-proxy ls -l /var/run/docker.sock`
  - runner can reach the proxy: `docker compose exec runner sh -lc 'docker version'`
