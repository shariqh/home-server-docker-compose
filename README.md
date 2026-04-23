# home-server-docker-compose

Personal home server stack. Each concern lives in its own directory with an independent `docker-compose.yml`, so any single stack can be brought up, torn down, or updated without touching the others.

## Stacks

| Directory | What it runs |
|---|---|
| `home-automation/` | Home Assistant, Z-Wave JS UI |
| `infra/` | Portainer, autoheal, beszel + beszel-agent (monitoring) |
| `media/` | Plex, Radarr, Sonarr, Lidarr, Jackett, qBittorrent (WireGuard) |
| `runner/` | Self-hosted GitHub Actions runner (builds + deploys app repos) |

## Conventions

- Each stack is a directory containing at minimum `docker-compose.yml`.
- **Non-secrets** (TZ, PUID, PGID, NAME_SERVERS) live in the shared root `.env`. Each stack has a `.env` symlink → `../.env`, so `docker compose up -d` inside a stack picks them up automatically.
- **Secrets** (PIA creds, beszel key, GitHub PAT) live in **1Password** and are referenced from each stack's `secrets.env` (committed — these are `op://` pointers, not values). Resolved at up-time by `op run`.
- One bootstrap secret — `OP_SERVICE_ACCOUNT_TOKEN` — lives plain in `runner/runner.env` (gitignored, chmod 600). It's the credential `op run` needs to authenticate, so it can't be behind an `op://` reference itself.
- Shared persistent data stays at the repo root (`appdata/`, `beszel_data/`); stacks reference it via `../appdata/<svc>` bind mounts.
- Host ports are allocated per stack — see the "Ports in use" table below.

## Where every env var lives

| Class | Examples | Where | Who fills it |
|---|---|---|---|
| Non-secret config | `TZ`, `PUID`, `PGID`, `NAME_SERVERS` | root `.env` (gitignored) | You, once |
| Bootstrap secret | `OP_SERVICE_ACCOUNT_TOKEN` | `runner/runner.env` (gitignored) | You, once |
| Runtime secrets | `BESZEL_AGENT_KEY`, `PIA_USERNAME`, `PIA_PASSWORD`, GitHub PAT, all app secrets | 1Password item `ubi-prod-envs` (or app-specific items); referenced from each stack's `secrets.env` | You fill the 1P item once; `op run` resolves on every `docker compose up` forever |

## First-time setup

1. **Install `op` CLI on the host** (Debian/Ubuntu):
   ```bash
   # Start clean so re-runs don't prompt on key overwrite / leave stale list files
   sudo rm -f /usr/share/keyrings/1password-archive-keyring.gpg /etc/apt/sources.list.d/1password.list

   # Import signing key
   curl -fsSL https://downloads.1password.com/linux/keys/1password.asc \
     | sudo gpg --dearmor -o /usr/share/keyrings/1password-archive-keyring.gpg

   # The `deb ...` line MUST be on one physical line — no backslash-newline
   # inside the quotes or apt will reject the file with "Malformed entry".
   echo "deb [arch=amd64 signed-by=/usr/share/keyrings/1password-archive-keyring.gpg] https://downloads.1password.com/linux/debian/amd64 stable main" \
     | sudo tee /etc/apt/sources.list.d/1password.list

   sudo apt update && sudo apt install -y 1password-cli
   op --version   # confirm 2.x
   ```
   (This is the **host** install — needed because `containerupdater.sh` and `op run ... docker compose up -d` both run on the host. The `runner/` container has its own copy of `op` baked in for workflows; that's separate.)

2. **Create the `ubi-prod-envs` item in 1Password** (Private vault) with these fields:
   - `beszel_agent_key`
   - `pia_username`
   - `pia_password`
   - `github_runner_pat`
3. **Create a 1Password service account** scoped to that vault. Copy its `ops_...` token.
4. **Clone onto the server**, then:
   ```bash
   cp .env.example .env
   # edit .env — only non-secrets go here (TZ, PUID, PGID, NAME_SERVERS)

   cp runner/runner.env.example runner/runner.env
   chmod 600 runner/runner.env
   # edit runner/runner.env — fill in REPO_URL, RUNNER_NAME, and the
   # OP_SERVICE_ACCOUNT_TOKEN you copied in step 3
   ```
5. **Bring up the stacks.** Stacks with a `secrets.env` need `op run`; stacks without it (currently just `home-automation`) run plain:
   ```bash
   cd home-automation && docker compose up -d && cd ..
   cd infra && op run --env-file=secrets.env -- docker compose up -d && cd ..
   cd media && op run --env-file=secrets.env -- docker compose up -d && cd ..
   cd runner && op run --env-file=secrets.env -- docker compose up -d --build && cd ..
   ```

## Updating

`containerupdater.sh` walks every stack, detects whether it has a `secrets.env`, wraps with `op run` accordingly, and updates. Run manually or from cron:

```bash
./containerupdater.sh
```

It sources `OP_SERVICE_ACCOUNT_TOKEN` from `runner/runner.env` at the top so cron doesn't need the token in its own environment.

## Adding a new stack

1. `mkdir newstack && cd newstack`
2. Write `docker-compose.yml`. Pick ports not already in use (see table below). Bind to `127.0.0.1` if the service is internal-only.
3. If the stack needs shared non-secrets: `ln -s ../.env .env`.
4. If the stack needs secrets:
   - Add fields for them to the `ubi-prod-envs` 1Password item (or a new dedicated item; just grant the service account access).
   - Create `secrets.env` with `op://` refs (committed — they're just pointers).
5. First bring-up:
   - With secrets: `op run --env-file=secrets.env -- docker compose up -d --build`
   - Without: `docker compose up -d --build`
6. `containerupdater.sh` picks up the new stack automatically next run and wraps with `op run` if `secrets.env` is present.

## Ports in use

| Stack | Port | Service |
|---|---|---|
| home-automation | 8091 | Z-Wave JS UI |
| home-automation | 3000 | Z-Wave JS websocket |
| home-automation | host-mode | Home Assistant (8123 on host) |
| infra | 9443 | Portainer |
| infra | 8090 | Beszel |
| media | host-mode | Plex (32400 on host) |
| media | 7878 | Radarr |
| media | 8989 | Sonarr |
| media | 8686 | Lidarr |
| media | 9117 | Jackett |
| media | 8080 | qBittorrent WebUI |
| media | 6881, 6881/udp | qBittorrent peer |

## Home Assistant & Z-Wave — initial configuration

After `home-automation/` is up:

### Z-Wave JS UI (one-time)

Open `http://<server-ip>:8091`, then:

1. Settings → Z-Wave
2. Set **Serial Port** to `/dev/zwave`
3. GENERATE all empty security keys — **save them somewhere safe**
4. Settings → Home Assistant → enable **WS Server**
5. Save

### Home Assistant integration (one-time)

Open `http://<server-ip>:8123`, then:

1. Settings → Devices & Services → **+ Add Integration** → search **Z-Wave**
2. Server URL: `ws://<server-ip>:3000` (not `ws://zwave-js-ui:3000` — Home Assistant runs in `network_mode: host` and isn't on the compose bridge network, so container DNS won't resolve)
3. Follow prompts

## Historical notes (kept for reference)

### SWAG + DuckDNS (commented out in `home-automation/` / `infra/`)

If you ever need to expose services to the public internet:
- [SWAG starter guide](https://blog.linuxserver.io/2019/04/25/letsencrypt-nginx-starter-guide/#creatingaletsencryptcontainer)
- [SWAG image docs](https://hub.docker.com/r/linuxserver/swag)
- DuckDNS for dynamic DNS on dynamic IPs: <https://www.duckdns.org/>

Currently: nothing in this repo is exposed outbound. Apps use outbound-only patterns (e.g. Telegram long polling, IMAP pull, API calls). Remote SSH happens over Tailscale.
