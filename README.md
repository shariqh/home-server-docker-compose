# Home Server Docker Compose

A collection of Docker Compose configurations for running a home server with media management, home automation, and monitoring services.

## Quick Start

1. **Set up environment variables**

   Copy the example file and fill in your values:
   ```bash
   cp .env.example .env
   ```

   Required variables:
   - `TZ` - Your timezone (e.g., `America/Los_Angeles`)
   - `PIA_USERNAME` / `PIA_PASSWORD` - VPN credentials for qBittorrent
   - `NAME_SERVERS` - DNS servers (e.g., `1.1.1.1,8.8.8.8`)
   - `BESZEL_AGENT_KEY` - Key for Beszel monitoring agent

2. **Clone the repository**
   ```bash
   git clone https://github.com/shariqh/home-server-docker-compose.git
   cd home-server-docker-compose
   ```

3. **Start the services**
   ```bash
   # Core services (Portainer, Home Assistant, Z-Wave, monitoring)
   docker compose up -d

   # Media services (Plex, *arr stack, qBittorrent)
   docker compose -f media-compose.yml up -d
   ```

## Services

### docker-compose.yml (Core Infrastructure)

| Service | Port | Description |
|---------|------|-------------|
| **Portainer** | 9443 | Docker management UI |
| **Home Assistant** | 8123 | Home automation (host network) |
| **Z-Wave JS UI** | 8091, 3000 | Z-Wave device management |
| **Beszel** | 8090 | Lightweight server monitoring |
| **Autoheal** | - | Auto-restarts unhealthy containers |

### media-compose.yml (Media Stack)

| Service | Port | Description |
|---------|------|-------------|
| **Plex** | 32400 | Media server (host network) |
| **Radarr** | 7878 | Movie management |
| **Sonarr** | 8989 | TV show management |
| **Lidarr** | 8686 | Music management |
| **Jackett** | 9117 | Torrent indexer proxy |
| **qBittorrent** | 8080 | Torrent client with WireGuard VPN |

## Network Configuration

The qBittorrent container uses a VPN with split tunneling. Update `LAN_NETWORK` in `media-compose.yml` to match your local subnet:
```yaml
- LAN_NETWORK=192.168.1.0/24  # Change to match your network
```

## Directory Structure

```
.
├── docker-compose.yml      # Core services
├── media-compose.yml       # Media services
├── .env                    # Environment variables (not in repo)
├── .env.example            # Example environment file
└── appdata/                # Persistent container data
    ├── homeassistant/
    ├── plex/
    ├── radarr/
    ├── sonarr/
    └── ...
```

## Hardware Requirements

- Intel CPU with Quick Sync recommended for Plex transcoding
- Z-Wave USB stick for Z-Wave JS (e.g., Zooz 800 series)
- Sufficient storage for media at `/mnt/media/`

## Updating Containers

Use Portainer to manage updates, or run:
```bash
docker compose pull && docker compose up -d
docker compose -f media-compose.yml pull && docker compose -f media-compose.yml up -d
```
