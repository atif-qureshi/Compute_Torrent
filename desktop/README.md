# 08 — Provider desktop application

The Windows provider app lets a volunteer PC enroll with the local coordinator, advertise its hardware profile, accept inference work, execute it in a Docker sandbox, and report the result.

## Current provider flow

Install the packaged app -> review hardware/Docker readiness -> enter the coordinator WebSocket URL and one-time join code -> enroll with a unique provider credential -> heartbeat -> receive an independent prompt assignment -> download the model/chunk over WebTorrent -> verify SHA-256 -> run llama.cpp inside a network-disabled Docker container -> submit result over WebSocket -> receive verification verdict and demo credits.

Use `127.0.0.1` only on the coordinator PC. Other trusted-LAN computers must use the coordinator's private IP. The provider's libp2p peer joins the LAN discovery/relay overlay; model and prompt files still use WebTorrent tracker signalling. Trackerless libp2p file transfer remains future work.

## Submodules

| Folder | Current role |
|---|---|
| `01-hardware-profiling/` | Detect CPU, RAM, NVIDIA GPU/VRAM, CUDA, and Docker readiness. |
| `02-networking-client/` | Provider enrollment, WebSocket heartbeat/messages, and reconnect. |
| `03-docker-sandbox/` | Inference runtime and disposable container isolation. |
| `04-webtorrent-sync/` | WebTorrent file download and SHA-256 validation; also includes the separate libp2p LAN peer helper. |
| `05-desktop-app-shell/` | CustomTkinter onboarding/dashboard, resource caps, pause, local contribution history, PyInstaller packaging. |

## Current limits

- Docker Desktop is a prerequisite; the app does not install it or run as a Windows service/tray app.
- Model weights remain cached under `%LOCALAPPDATA%\ComputeTorrent\models`; per-task prompt/inference workspaces are cleaned after use. Do not describe the provider as leaving no model files on disk.
- The app stores its per-device credential and short contribution history locally. The shared enrollment code is memory-only.
- Credits are demo accounting, not redeemable value.
- Full trackerless libp2p data transfer and full VeriLLM/canary verification are future architecture work.

See [desktop app flow](05-desktop-app-shell/README.md), [network transfer status](../07-network-layer/README.md), and [implementation status](../docs/IMPLEMENTATION-STATUS.md).
