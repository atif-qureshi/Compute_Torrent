# ComputeTorrent provider desktop app

The Windows Python app connects a volunteer PC to the local coordinator, displays the detected hardware profile, and lets the provider cap CPU/RAM use and pause new assignments.

## Working MVP flow

1. The provider enters a coordinator WebSocket address and the operator's one-time network join code. Use `127.0.0.1` only on the coordinator PC; use its private LAN IP on another computer.
2. The app enrolls the PC and stores its own revocable provider credential under `%LOCALAPPDATA%\ComputeTorrent`. The shared enrollment code is memory-only and is not written into settings.
3. While connected, the app sends heartbeats, receives one assignment at a time, fetches the model/prompt payload over WebTorrent, validates hashes, and runs llama.cpp in a network-isolated Docker container.
4. It returns the result over the coordinator WebSocket, receives the verification verdict, and stores a short local contribution history.
5. Pausing stops new assignments; an already running task can finish. Closing the app closes its connection and stops its local libp2p peer process.

For layer inference on another PC, enter the coordinator's actual private IPv4 address. The app checks TCP 31331 before starting a layer worker and reports a specific firewall/network error if not reachable. It advertises only this PC's LAN address; Docker Desktop's `host.docker.internal` alias is used only when the provider runs on the coordinator PC itself.

For layer inference, install the CPU Petals runtime from the app (or the NVIDIA
runtime on a CUDA machine), then enable **Share model layers**. The app reports
CPU model and core counts, available RAM, display adapters, NVIDIA VRAM when
available, disk capacity, Docker readiness, and resource limits. When the
coordinator assigns a pinned BLOOM/BLOOMZ model and contiguous block range, the
app launches a resource-limited Docker container. Weights download and cache on
the provider PC. Keep the app open and allow private-LAN TCP traffic to the
coordinator on 8001/31331 and each provider on 31330. This path is managed in
the portal's Model Studio page and has separate job history from GGUF tasks.

The libp2p peer joins the LAN discovery/relay overlay for connectivity information. It does not transfer GGUF files; WebTorrent still uses configured tracker signalling. Petals uses a separate private Hivemind DHT to route model activations. Trackerless libp2p GGUF file transfer and full independent VeriLLM verification remain future work. See [implementation status](../../docs/IMPLEMENTATION-STATUS.md).

## Build and install locally

From PowerShell in this directory, run `.\build_installer.ps1`. The build machine needs Python, Node.js 22+, npm, and network access to install build dependencies. The generated archive contains the executable and install/uninstall scripts. Provider PCs need Docker Desktop installed and running; model weights must be supplied by the local network operator.

The local app is not a Windows service, tray app, or auto-updater yet. Closing it stops contributions. Credits shown by the app are demonstration accounting with no monetary value.
