# Printbuddy Deployment Guide

This guide covers a clean Docker Compose deployment of Printbuddy. The default setup is optimized for Linux hosts where host networking is available.

## Requirements

- Linux server or VM with Docker Engine and Docker Compose v2
- Network access from the Docker host to your printers
- Recommended: static IP address or DHCP reservation for the Docker host
- Optional: Tailscale on the host if you want Printbuddy to request certificates for virtual printers

## Quick start

```bash
git clone -b dev https://github.com/vmhomelab/Printbuddy.git
cd Printbuddy
cp .env.example .env
docker compose up -d --build
```

Open Printbuddy:

```text
http://<docker-host-ip>:8000
```

Check container state:

```bash
docker compose ps
docker compose logs -f printbuddy
```

## Recommended Linux deployment

The provided `docker-compose.yml` uses:

- service name: `printbuddy`
- container name: `printbuddy`
- image: `docker.io/vmhomelabde/printbuddy:dev`
- data volume: `printbuddy_data` mounted at `/app/data`
- log volume: `printbuddy_logs` mounted at `/app/logs`
- `network_mode: host` for printer discovery, camera streaming, MQTT/FTP, and virtual printer ports

Start or update the stack:

```bash
docker compose pull
docker compose up -d
```

When testing local source changes from `dev`:

```bash
git pull
docker compose up -d --build
```

## Environment variables

Create `.env` from `.env.example` and adjust the values you need:

```env
TZ=Europe/Berlin
PUID=1000
PGID=1000
PORT=8000
```

Useful options:

- `TZ`: timezone used by the container.
- `PUID` / `PGID`: host UID/GID used for files written into mounted volumes. Run `id -u` and `id -g` on the host.
- `PORT`: web UI/API port. With `network_mode: host`, Printbuddy listens directly on this host port.
- `DISCOVERY_EXTRA_SUBNETS`: optional comma-separated CIDRs shown in Add Printer → subnet scan (Bambu and Moonraker/Klipper), for printer VLANs reachable by routing but not present as a local host NIC (e.g. `10.0.0.0/24`). Requires `network_mode: host` and a working route from the Docker host.
- `DISCOVERY_MOONRAKER_PORTS`: optional comma-separated ports for Moonraker subnet scan (default `7125,80`). Port `80` covers CosmOS / Fluidd reverse-proxies. Hits still require Moonraker/Klipper-shaped `server/info` JSON — bare 401/403 auth walls on unrelated services are ignored.
- `DATABASE_URL`: optional PostgreSQL connection string. If unset, Printbuddy uses SQLite in `/app/data`.
- `MFA_ENCRYPTION_KEY`: optional managed Fernet key for MFA secrets. If unset, Printbuddy generates one in the data volume.
- `TRUSTED_FRAME_ORIGINS`: comma-separated iframe origins, for example a Home Assistant dashboard origin.

## Docker Desktop / bridge networking

Docker Desktop on Windows/macOS does not support Linux-style host networking. For those systems:

1. Comment out `network_mode: host` in `docker-compose.yml`.
2. Uncomment the `ports:` block.
3. Add printers manually by IP address because automatic discovery may not work across Docker Desktop networking.
4. Set `VIRTUAL_PRINTER_PASV_ADDRESS=<docker-host-ip>` if you use virtual printer FTP passive mode.

Minimum web UI mapping:

```yaml
ports:
  - "${PORT:-8000}:8000"
```

For virtual printer support, keep the full commented port block from `docker-compose.yml`.

## Persistent data and backups

Printbuddy stores runtime state in Docker volumes by default:

```bash
docker volume inspect printbuddy_data
docker volume inspect printbuddy_logs
```

Back up the data volume before major upgrades:

```bash
docker compose stop printbuddy
docker run --rm \
  -v printbuddy_data:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine tar czf /backup/printbuddy-data-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
docker compose start printbuddy
```

Optional external backup target:

```yaml
volumes:
  - /path/to/nas/printbuddy-backups:/app/data/backups
```

## Optional PostgreSQL

SQLite is fine for a homelab deployment. If you prefer PostgreSQL, provide an external database and set:

```env
DATABASE_URL=postgresql+asyncpg://printbuddy:<password>@<db-host>:5432/printbuddy
```

The compose file also includes a commented PostgreSQL service skeleton if you want to run the database beside Printbuddy.

## Optional Tailscale integration

To allow Printbuddy to use the host Tailscale daemon for certificate handling:

1. Install and authenticate Tailscale on the host.
2. Permit the container user to operate Tailscale, for example:

   ```bash
   sudo tailscale set --operator=$(id -un)
   ```

3. Mount the socket in `docker-compose.yml`:

   ```yaml
   volumes:
     - /var/run/tailscale/tailscaled.sock:/var/run/tailscale/tailscaled.sock
   ```

Without this mount, Printbuddy falls back to self-signed certificates.

## Health checks and logs

Health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Container logs:

```bash
docker compose logs -f printbuddy
```

Application logs are stored in `/app/logs` inside the container and in the `printbuddy_logs` volume.

## Updating

For the development branch:

```bash
cd Printbuddy
git checkout dev
git pull
docker compose up -d --build
```

When GHCR images are available, update without a local build:

```bash
docker compose pull
docker compose up -d
```

## Rollback

If a new build fails:

```bash
git log --oneline -5
git checkout <known-good-commit>
docker compose up -d --build
```

If data migration was involved, restore the `printbuddy_data` backup taken before the upgrade.

## Troubleshooting

- UI not reachable: check `docker compose ps`, `docker compose logs printbuddy`, and whether port `8000` is already in use.
- Printers not discovered: use Linux host networking, verify the host can reach the printer IP, and add the printer manually by IP if needed.
- Camera or virtual printer issues: verify the required ports are not blocked by the host firewall.
- Permission problems on bind mounts: set `PUID` and `PGID` to the host user that owns the mounted directories.
- HTTPS/self-signed integrations: mount your CA certificates into `/usr/local/share/ca-certificates` and set `USE_SYSTEM_TRUST_STORE=true`.
