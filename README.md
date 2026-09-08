# Printbuddy

<p align="center">
  <!-- Replace this with your logo path once added to the repository -->
  <img src="frontend/public/img/printbuddy_logo_dark_transparent.png" alt="Printbuddy Logo" width="420">
</p>

<p align="center">
  <strong>One modern self-hosted dashboard for your 3D printer fleet.</strong>
</p>

<p align="center">
  Manage <strong>Bambu Lab</strong>, <strong>Klipper</strong>, and <strong>Prusa</strong> printers from one clean interface.
</p>

<p align="center">
  <a href="https://wiki.printbuddy.tech">📚 Wiki</a>
  ·
  <a href="https://github.com/vmhomelab/Printbuddy/releases/latest">📦 Latest release</a>
  ·
  <a href="https://demo.printbuddy.tech">🚀 Demo</a>

<p align="center">
  Demo login: <code>admin</code> / <code>printbuddy</code>
</p>

<p align="center">
  <a href="#docker-quick-start">Quick Start</a>
  ·
  <a href="#printer-provider-direction">Providers</a>
  ·
  <a href="#home-assistant">Home Assistant</a>
  ·
  <a href="#screenshots">Screenshots</a>
  ·
  <a href="#printbuddy-mascot--stl">Printbuddy STL</a>
  ·
  <a href="#development-setup">Development</a>
</p>

---

> [!WARNING]
> **This repository is still under active development**
>
> Printbuddy is not ready for public production use yet. Features may be incomplete, unstable, or subject to breaking changes without notice.
>
> Use it for testing, development, and tinkering only.
>
> You can check the current status of different features in the [projects tab](https://github.com/users/vmhomelab/projects/4/views/1)

---

## What is Printbuddy?

**Printbuddy** is a modern, self-hosted dashboard with a broader goal:

> A single, modern, self-hosted dashboard for managing different 3D printer ecosystems.

Printbuddy uses a provider-based architecture for multiple printer platforms.

Current state:

- Initial fork setup on `dev`
- Bambu Lab support from the original foundation ✅
- Prusa support added via PrusaLink ✅(Prusa Connect not tested)
- Klipper (open fimrware) support being added ⌛ (not officially supported yet)
- Provider architecture in progress ⌛

---

## Features

Current and planned goals include:

- Multi-printer dashboard
- Bambu Lab printer support
- Klipper printer support through Moonraker
- Prusa-compatible environments
- Self-hosted deployment
- Docker-based setup
- Modern web UI

---

## Screenshots

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Printbuddy Dashboard Screenshot" width="800">
</p>
<img width="3230" height="1335" alt="grafik" src="https://github.com/user-attachments/assets/d0aea010-5449-4a47-a860-fd26f5a7b6d9" />

<p align="center">
  <img src="docs/screenshots/printer-detail.png" alt="File Manager of different printers" width="800">
</p>
<img width="708" height="525" alt="grafik" src="https://github.com/user-attachments/assets/a435ea7a-dac7-4c57-98ec-c65eec4467f5" />
<img width="706" height="652" alt="grafik" src="https://github.com/user-attachments/assets/584f786d-7d71-416d-9878-86d45cf8f389" />


<p align="center">
  <img src="docs/screenshots/printer-detail.png" alt="Printer Detail Screenshot" width="800">
</p>
<img width="420" height="576" alt="grafik" align="center" src="https://github.com/user-attachments/assets/730a2060-1032-46cb-bc3f-a341e8a730cb" />


<p align="center">
  <img src="docs/screenshots/printer-detail.png" alt="Klipper-based printer with control options" width="800">
</p>
<img width="960" height="874" alt="grafik" src="https://github.com/user-attachments/assets/c402bcbf-3797-4ad7-b14e-f0ade3bb92d1" />


<p align="center">
  <img src="docs/screenshots/printer-detail.png" alt="Panda Breath Support" width="800">
</p>
<img width="532" height="811" alt="grafik" align="center" src="https://github.com/user-attachments/assets/7c827ed8-cc55-4dcf-acbd-e860bfb60844" />

<p align="center">
  <img src="docs/screenshots/printer-detail.png" alt="Update via the UI" width="800">
</p>
<img width="360" height="663" alt="grafik" src="https://github.com/user-attachments/assets/7bb731b4-c1f3-46c4-a161-56ce976a66ba" />


---

## Printbuddy Mascot / STL

Printbuddy also has its own little mascot.

<p align="center">
  <img width="420" height="500" alt="photo_2026-06-05_21-22-27" src="https://github.com/user-attachments/assets/dc21e98b-5060-44dd-a15d-6d932577495a" />
</p>

### Print your own Printbuddy

Download your Printbuddy here:

- MakerWorld: `https://makerworld.com/de/models/2894134-your-printbuddy#profileId-3234154`
- Printables: `https://www.printables.com/model/1746692-your-printbuddy`

---

## Repository workflow

Development happens on the `dev` branch first.

1. Commit and push work to `dev`.
2. Test from `dev`.
3. Merge approved changes into `main`.
4. Release from `main`.

```text
dev  -> active development
main -> stable releases
```

---

## Docker quick start

For the first test deployment, build directly from the `dev` branch:

```bash
git clone -b dev https://github.com/vmhomelab/Printbuddy.git
cd Printbuddy
docker compose up -d --build
```

Open Printbuddy in your browser:

```text
http://<docker-host-ip>:8000
```

### Linux host networking

On Linux, the compose file uses:

```yaml
network_mode: host
```

This helps with Bambu discovery, camera access, and virtual-printer ports.

### Docker Desktop

On Docker Desktop, remove:

```yaml
network_mode: host
```

Then enable the commented `ports:` block in the compose file instead.

---

## Printer provider direction

Printbuddy introduces a provider boundary so printer-specific integrations can evolve without hard-coding every workflow to Bambu MQTT/FTP.

Planned providers:

| Provider | Description | Status |
|---|---|---|
| `bambu` | Existing Printbuddy / Bambu Lab MQTT + FTP support | Inherited ✅ |
| `klipper` | Moonraker-backed Klipper printer status and control | In progress ⌛ |
| `prusa` | PrusaLink support | Implemented ✅ |
| `elegoo` | CC1 support | In progress ⌛ |

The first implementation step adds the provider and printer metadata to allow printers to be added.

Bambu remains the default provider for backwards compatibility.

---

## Home Assistant

Printbuddy can be used with Home Assistant in two ways:

- **Home Assistant add-on:** run Printbuddy directly inside Home Assistant with Ingress, persistent add-on storage, and LAN printer access through host networking. Repository: [vmhomelab/printbuddy-ha-addon](https://github.com/vmhomelab/printbuddy-ha-addon)
- **Home Assistant custom integration:** connect Home Assistant to an existing Printbuddy instance and expose configured printers as Home Assistant devices and telemetry entities. Repository: [vmhomelab/ha-printbuddy-integration](https://github.com/vmhomelab/ha-printbuddy-integration)

Wiki pages:

- [Printbuddy Home Assistant Add-on](https://github.com/vmhomelab/printbuddy/wiki/Home-Assistant-Add-on)
- [Printbuddy Home Assistant Integration](https://github.com/vmhomelab/printbuddy/wiki/Home-Assistant-Integration)

---

## Development setup

### Backend

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -r requirements-dev.txt

ruff check backend/
ruff format --check backend/

cd backend
../venv/bin/python -m pytest tests/ --tb=short
```

### Frontend

```bash
cd frontend

npm ci
npm run lint
npx tsc --noEmit
npm run test:run
npm run build
```

---

## Project status

Printbuddy is currently focused on:

- Cleaning up the project structure
- Adding provider metadata
- Preparing Klipper and Prusa support
- Keeping existing Bambu functionality working during the transition

---

## Contributing

Contributions are welcome once the project structure becomes more stable.

For now, the best way to contribute is:

1. Open an issue with your idea or bug report.
2. Target pull requests against `dev`.
3. Keep changes focused and easy to review.
4. Test both backend and frontend before opening a pull request.

---

## Attribution and license

Printbuddy keeps the upstream **AGPL-3.0** license.

Historical upstream documentation and changelog entries are retained only where needed for license and release-history context.

---

## Star History

<a href="https://www.star-history.com/?repos=vmhomelab%2Fprintbuddy&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=vmhomelab/printbuddy&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=vmhomelab/printbuddy&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=vmhomelab/printbuddy&type=date&legend=top-left" />
 </picture>
</a>


<p align="center">
  <strong>Printbuddy</strong><br>
  Your tiny helper for keeping the printer chaos under control.
</p>
