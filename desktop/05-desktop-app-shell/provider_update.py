"""Operator-hosted provider updates. Credentials and model caches are untouched."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit, urlunsplit


def update_base(url_or_ws):
    if not url_or_ws:
        url_or_ws = "http://127.0.0.1:8001"
    url_str = str(url_or_ws).strip()
    if not (url_str.startswith("http://") or url_str.startswith("https://") or
            url_str.startswith("ws://") or url_str.startswith("wss://")):
        url_str = "http://" + url_str
    parsed = urlsplit(url_str)
    scheme = "https" if parsed.scheme in {"https", "wss"} else "http"
    netloc = parsed.netloc or parsed.path.split("/")[0]
    return urlunsplit((scheme, netloc, "/api/provider-update", "", ""))


def _create_ssl_context():
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return None


def check_update(websocket_url, current_build, force=False):
    """
    Checks the coordinator for updates.
    Returns: (manifest, base_url, is_newer)
    """
    base = update_base(websocket_url)
    manifest_url = f"{base.rstrip('/')}/manifest"
    req = urllib.request.Request(
        manifest_url,
        headers={
            "User-Agent": "ComputeTorrent-Seeder/1.0",
            "Accept": "application/json",
            "ngrok-skip-browser-warning": "69420",
        }
    )
    
    ctx = _create_ssl_context()
    with urllib.request.urlopen(req, timeout=12, context=ctx) as response:
        manifest = json.loads(response.read(65536).decode("utf-8-sig"))
        
    version = str(manifest.get("version", "")).strip()
    sha = str(manifest.get("sha256", "")).strip().lower()
    
    if (manifest.get("filename") != "ComputeTorrent_Seeder.exe" or not version
            or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)
            or not isinstance(manifest.get("size"), int) or manifest["size"] < 1):
        raise ValueError("Invalid update manifest received from coordinator")
        
    is_newer = bool(version > str(current_build).strip())
    return manifest, base, is_newer


def stage_update(base, manifest, data_dir, progress_callback=None):
    """
    Downloads and verifies the update file into {data_dir}/updates.
    Calls progress_callback(downloaded_bytes, total_bytes) during streaming.
    Works for both packaged executables and Python source environments.
    """
    folder = Path(data_dir) / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    
    sha_short = manifest.get("sha256", "update")[:16].lower()
    staged = folder / f"ComputeTorrent_Seeder_{sha_short}.exe"
    partial = folder / f"ComputeTorrent_Seeder_{sha_short}.partial"
    
    if partial.is_file():
        try:
            partial.unlink(missing_ok=True)
        except Exception:
            pass
            
    digest = hashlib.sha256()
    count = 0
    total_size = int(manifest["size"])
    
    download_url = f"{base.rstrip('/')}/download"
    req = urllib.request.Request(
        download_url,
        headers={
            "User-Agent": "ComputeTorrent-Seeder/1.0",
            "Accept": "application/octet-stream",
            "ngrok-skip-browser-warning": "69420",
        }
    )
    
    ctx = _create_ssl_context()
    with urllib.request.urlopen(req, timeout=300, context=ctx) as source, partial.open("wb") as target:
        chunk_size = 512 * 1024
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            target.write(chunk)
            digest.update(chunk)
            count += len(chunk)
            if progress_callback:
                progress_callback(count, total_size)
            if count > total_size:
                raise ValueError("Update download exceeded declared file size")
                
    if count != total_size or digest.hexdigest().lower() != manifest["sha256"].lower():
        try:
            partial.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError(
            f"Update failed verification (expected SHA-256 {manifest['sha256'][:8]}..., got {digest.hexdigest()[:8]}...)"
        )
        
    if staged.is_file():
        try:
            staged.unlink(missing_ok=True)
        except Exception:
            pass
    partial.replace(staged)
    return staged


def restart_with_update(staged, data_dir):
    """
    Applies the downloaded update and launches the updated client.
    - If running as a frozen binary: Replaces sys.executable and restarts it.
    - If running as a Python script: Copies to standard install location & launches it.
    """
    staged_path = Path(staged).resolve()
    if not staged_path.is_file():
        raise FileNotFoundError(f"Staged update file not found: {staged_path}")

    if getattr(sys, "frozen", False):
        target = Path(sys.executable).resolve()
        script = Path(data_dir) / "updates" / "install-update.ps1"
        script.parent.mkdir(parents=True, exist_ok=True)
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
        subprocess.Popen([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-OldPid", str(os.getpid()), "-Source", str(staged_path), "-Destination", str(target)
        ], creationflags=flags, close_fds=True)
    else:
        # Running via Python source: copy to installation directory & launch
        install_dir = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "ComputeTorrent"
        install_dir.mkdir(parents=True, exist_ok=True)
        installed_exe = install_dir / "ComputeTorrent_Seeder.exe"
        try:
            shutil.copy2(str(staged_path), str(installed_exe))
            launch_target = installed_exe
        except Exception:
            launch_target = staged_path

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"Start-Process -FilePath '{launch_target}'"
        ], creationflags=flags, close_fds=True)
