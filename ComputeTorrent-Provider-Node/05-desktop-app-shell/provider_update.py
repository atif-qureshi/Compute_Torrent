"""Operator-hosted provider updates. Credentials and model caches are untouched."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit, urlunsplit


def update_base(websocket_url):
    parsed = urlsplit(websocket_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("Connect to a coordinator before checking for updates")
    scheme = "https" if parsed.scheme == "wss" else "http"
    return urlunsplit((scheme, parsed.netloc, "/api/provider-update", "", ""))


def check_update(websocket_url, current_build):
    base = update_base(websocket_url)
    with urllib.request.urlopen(base + "/manifest", timeout=10) as response:
        manifest = json.loads(response.read(65536).decode("utf-8-sig"))
    version = manifest.get("version", "")
    sha = manifest.get("sha256", "")
    if (manifest.get("filename") != "ComputeTorrent_Seeder.exe" or not version
            or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower())
            or not isinstance(manifest.get("size"), int) or manifest["size"] < 1):
        raise ValueError("Invalid update manifest")
    return (manifest if version > current_build else None), base


def stage_update(base, manifest, data_dir):
    if not getattr(sys, "frozen", False):
        raise RuntimeError("In-app updates require the installed provider executable")
    folder = Path(data_dir) / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    staged = folder / (manifest["sha256"].lower() + ".exe")
    partial = staged.with_suffix(".partial")
    digest = hashlib.sha256()
    count = 0
    request = urllib.request.Request(base + "/download", headers={"Accept": "application/octet-stream"})
    with urllib.request.urlopen(request, timeout=120) as source, partial.open("wb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            digest.update(chunk)
            count += len(chunk)
            if count > manifest["size"]:
                raise ValueError("Update exceeded the declared size")
    if count != manifest["size"] or digest.hexdigest() != manifest["sha256"].lower():
        partial.unlink(missing_ok=True)
        raise ValueError("Downloaded update failed its size or SHA-256 check")
    partial.replace(staged)
    return staged


def restart_with_update(staged, data_dir):
    target = Path(sys.executable).resolve()
    script = Path(data_dir) / "updates" / "install-update.ps1"
    # PowerShell arguments are passed separately, so paths never become code.
    script.write_text('''param([int]$OldPid, [string]$Source, [string]$Destination)
$ErrorActionPreference = 'Stop'
while (Get-Process -Id $OldPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 500 }
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try { Copy-Item -LiteralPath $Source -Destination $Destination -Force; break }
    catch { if ($attempt -eq 29) { throw }; Start-Sleep -Seconds 1 }
}
Start-Process -FilePath $Destination
''', encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                      "-OldPid", str(os.getpid()), "-Source", str(staged), "-Destination", str(target)],
                     creationflags=flags, close_fds=True)
