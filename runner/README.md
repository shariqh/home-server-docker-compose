# GitHub Actions self-hosted runner

Dockerized runner (`myoung34/github-runner` + 1Password CLI). In the default configuration, it is **repo-scoped** (`RUNNER_SCOPE=repo` + `REPO_URL=<repo>`) and only picks up jobs for that one repo when its workflows declare `runs-on: self-hosted`. See [Serving more than one repo](#serving-more-than-one-repo) below for org-scope or multi-service layouts.

Because the 1Password CLI is baked in, workflows can resolve secrets via `op run --env-file=secrets.env -- <command>` at job time — no plaintext values are ever written to disk. The service-account token stays on this host.

**Trust boundary:** this runner mounts the host Docker socket directly, so workflows get root-equivalent access to the host's Docker daemon. Acceptable for **single-user private repos** where every commit is yours. If you ever point this runner at a public or multi-contributor repo, put a socket proxy (e.g. `tecnativa/docker-socket-proxy`) in front — the `docker-compose.yml` had one originally; was removed after it kept blocking legitimate BuildKit traffic during our builds. History is in git.

> Prerequisites from the root README: `op` CLI installed on the host, the `ubi-prod-envs` item created in 1Password, and a service account token. This README assumes those are done.

## First-time setup

1. **GitHub PAT** with `repo` scope (or fine-grained token scoped to the target repo):
   https://github.com/settings/tokens/new
   Save the `ghp_...` value as the `github_runner_pat` field in your `ubi-prod-envs` 1Password item — it's resolved at container-up time via `secrets.env`.

2. **Populate `runner.env`** (plain, gitignored — only the bootstrap token + runner identity live here):
   ```bash
   cp runner.env.example runner.env
   chmod 600 runner.env
   # fill in REPO_URL, RUNNER_NAME, OP_SERVICE_ACCOUNT_TOKEN
   ```
   `ACCESS_TOKEN` (the GitHub PAT) is **not** in this file — it comes from 1Password via `secrets.env`, which is already committed.

3. **Start**:
   ```bash
   op run --env-file=secrets.env -- docker compose up -d --build
   ```
   At runtime the runner container itself also has `op` CLI baked in (via our Dockerfile), so workflows that check out app repos can `op run` on their own secrets — separate from the host-side `op run` you just ran to bring this container up.

4. **Verify** in GitHub → repo → Settings → Actions → Runners. The runner should appear as **Idle** within ~30 seconds.

## Serving more than one repo

Easiest short-term: duplicate the `runner:` service in `docker-compose.yml`. Each duplicate **must** have its own:
- `container_name` (e.g. `github-runner-<repo>`)
- `env_file` (e.g. `runner-<repo>.env`) with a unique `RUNNER_NAME` and `REPO_URL`
- state volume (e.g. `runner-data-<repo>:/tmp/runner`, plus a matching entry under the top-level `volumes:` block)

Sharing `runner-data` between duplicated services causes runners to clobber each other's work directory — jobs will fail intermittently in ways that are hard to diagnose.

Long-term: move your repos under a GitHub organization, change `RUNNER_SCOPE=org` and point `REPO_URL` at the org URL. One runner serves every repo in the org.

## Updating

```bash
op run --env-file=secrets.env -- docker compose pull
op run --env-file=secrets.env -- docker compose up -d --build --pull always
```

Or just let `../containerupdater.sh` handle it — it wraps with `op run` automatically.

## Troubleshooting

- **Runner shows Offline in GH** → `docker compose logs -f runner`; usually an auth error (bad PAT scope or typo).
- **`op run` fails inside a job with "not signed in"** → confirm `OP_SERVICE_ACCOUNT_TOKEN` made it into the container: `docker compose exec runner env | grep OP_`.
- **Can't reach host Docker** → verify the socket mount is intact inside the runner: `docker compose exec runner ls -l /var/run/docker.sock` and `docker compose exec runner sh -lc 'docker version'`. If docker version fails, the mount isn't landing — check the `volumes:` section of `docker-compose.yml`.
