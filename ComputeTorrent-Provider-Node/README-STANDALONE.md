# Standalone desktop provider

This folder is a separate copy of the current Windows provider app and its hardware profiling, WebSocket client, Docker sandbox, and WebTorrent helper modules. It is independent of `08-provider-node/` and can be edited or packaged without changing the numbered source tree.

## Run from source

Install Docker Desktop and Node.js 22 or newer, then install the Python dependencies:

```powershell
python -m pip install -r desktop/requirements.txt
python desktop/main.py
```

On first launch, enter the coordinator WebSocket address and its private enrollment code. For other PCs on a trusted LAN, use the coordinator PC's private IPv4 address, such as `ws://192.168.1.5:8001/ws/seeder`.

## Build the Windows package

Run `desktop/05-desktop-app-shell/build_installer.ps1` in PowerShell on a Windows build machine with Python, Node.js 22+, npm, and network access for build dependencies. It creates `ComputeTorrent-Seeder-Installer.zip` under that subfolder's `dist/`. The provider machine needs Docker Desktop running; the package includes the app and P2P helper, while models download on demand.
