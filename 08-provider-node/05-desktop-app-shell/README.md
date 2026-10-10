# ComputeTorrent provider desktop app

The Windows Python app connects a volunteer PC to the local coordinator, displays the detected hardware profile, and lets the provider cap CPU/RAM use and pause new assignments.

## Working MVP flow

1. The provider enters a coordinator WebSocket address and the operator's one-time network join code. Use `127.0.0.1` only on the coordinator PC; use its private LAN IP on another computer.
2. The app enrolls the PC and stores its own revocable provider credential under `%LOCALAPPDATA%\ComputeTorrent`. The shared enrollment code is memory-only and is not written into settings.
3. While connected, the app sends heartbeats, receives one assignment at a time, fetches the model/prompt payload over WebTorrent, validates hashes, and runs llama.cpp in a network-isolated Docker container.
4. It returns the result over the coordinator WebSocket, receives the verification verdict, and stores a short local contribution history.
5. Pausing stops new assignments; an already running task can finish. Closing the app closes its connection and stops its local libp2p peer process.

The libp2p peer joins the LAN discovery/relay overlay for connectivity information. It does not transfer files; WebTorrent still uses configured tracker signalling. Full trackerless libp2p file transfer and the full VeriLLM/canary architecture remain future work. See [implementation status](../../docs/IMPLEMENTATION-STATUS.md).

## Build and install locally

From PowerShell in this directory, run `.\build_installer.ps1`. The build machine needs Python, Node.js 22+, npm, and network access to install build dependencies. The generated archive contains the executable and install/uninstall scripts. Provider PCs need Docker Desktop installed and running; model weights must be supplied by the local network operator.

The local app is not a Windows service, tray app, or auto-updater yet. Closing it stops contributions. Credits shown by the app are demonstration accounting with no monetary value.
