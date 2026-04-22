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
- Stacks that rely on the shared root `.env` have a `.env` symlink pointing to `../.env`, so `docker compose up -d` from inside a stack picks up `TZ`/`PUID`/`PGID`/etc. without any flag juggling.
- Stacks that need their own secrets (e.g. `runner/runner.env`) keep them local and gitignored.
- Shared persistent data stays at the repo root (`appdata/`, `beszel_data/`); stacks reference it via `../appdata/<svc>` bind mounts.
- Host ports are allocated per stack — see the "Ports in use" table below. Pick unused ports for new stacks.

## First-time setup

1. Clone onto the server.
2. `cp .env.example .env` and fill in shared values (timezone, PUID/PGID, PIA creds, etc.).
3. Bring up whichever stacks you want:
   ```bash
   cd home-automation && docker compose up -d
   cd ../infra && docker compose up -d
   cd ../media && docker compose up -d
   ```
4. For `runner/`, see [`runner/README.md`](runner/README.md) — it needs a GitHub PAT and a 1Password service-account token in its own `runner.env`.

## Updating

`containerupdater.sh` walks every stack directory, pulls fresh images, and recreates containers. Run manually or from cron:

```bash
./containerupdater.sh
```

## Adding a new stack

1. `mkdir newstack && cd newstack`
2. Write `docker-compose.yml`. Pick ports not already in use (see table below). Bind to `127.0.0.1` if the service is internal-only.
3. If the stack needs shared env vars: `ln -s ../.env .env`.
   If it needs its own secrets: add `<stack>.env` (gitignored) + an `<stack>.env.example` template.
4. `docker compose up -d`.
5. `containerupdater.sh` picks it up automatically next run.

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
