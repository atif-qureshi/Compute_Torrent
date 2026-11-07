"""
Simple direct-download update module for ComputeTorrent Provider.

Downloads the installer (.exe) from the coordinator's HTTP API:
  GET /api/provider-update/manifest  → JSON with version, filename, sha256, size
  GET /api/provider-update/download  → raw EXE bytes

Legacy unsigned transport retained for investigation. Download and execution are disabled.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MAX_MANIFEST = 65536               # 64 KB max JSON
MAX_PACKAGE  = 600 * 1024 * 1024   # 600 MB max installer


def restart_environment():
    """Launch an independent frozen app without altering the current process."""
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("_PYI_", "PYI_", "_MEI"))
    }
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return environment


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _http_base(coordinator_ws_url: str) -> str:
    """Convert ws://host:port/... or private IP to http://host:port"""
    url = coordinator_ws_url.strip()
    if not url:
        return "http://127.0.0.1:8001"
    if "://" not in url:
        if ":" in url:
            url = "http://" + url
        else:
            url = f"http://{url}:8001"
    parsed = urlsplit(url)
    scheme = "https" if parsed.scheme in {"wss", "https"} else "http"
    netloc = parsed.netloc or parsed.path
    if "/" in netloc:
        netloc = netloc.split("/")[0]
    return f"{scheme}://{netloc}"


def _version_tuple(v: str):
    """Parse version like '2026.11.03-update3' → (2026, 11, 3, 3)."""
    if not isinstance(v, str):
        return (0,)
    nums = re.findall(r"\d+", v)
    return tuple(int(n) for n in nums) if nums else (0,)


def _open_url(url: str, headers: dict = None, timeout: int = 30):
    req = urllib.request.Request(url, headers={
        "ngrok-skip-browser-warning": "69420",
        "User-Agent": "ComputeTorrent-Provider/1.0",
        **(headers or {}),
    })
    return urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout)


def check_update(coordinator_url: str, current_build: str, force: bool = False):
    """
    Fetch manifest from coordinator and check if a newer version exists.

    Returns:
        (manifest_dict, base_http_url, is_newer: bool)
    """
    base = _http_base(coordinator_url)
    manifest_url = base + "/api/provider-update/manifest"
    try:
        with _open_url(manifest_url) as resp:
            raw = resp.read(MAX_MANIFEST + 1)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Update server returned HTTP {e.code}") from e
    except OSError as e:
        raise RuntimeError(f"Cannot reach update server: {e}") from e

    if len(raw) > MAX_MANIFEST:
        raise ValueError("Update manifest too large")

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid update manifest JSON: {e}") from e

    if not isinstance(manifest, dict):
        raise ValueError("Update manifest must be a JSON object")

    version = manifest.get("version", "")
    filename = manifest.get("filename", "")
    sha256 = manifest.get("sha256", "")
    size = manifest.get("size", 0)

    if not version or not filename or not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise ValueError("Malformed update manifest (missing version/filename/sha256)")
    if not isinstance(size, int) or size <= 0 or size > MAX_PACKAGE:
        raise ValueError("Update manifest has invalid size field")

    is_newer = _version_tuple(version) > _version_tuple(current_build) or force
    return manifest, base, is_newer


def stage_update(base: str, manifest: dict, data_dir, progress_callback=None, *, current_build: str = ""):
    """
    Download the installer from the coordinator, verify SHA256, and stage it
    in an updates folder inside data_dir.

    progress_callback(downloaded_bytes, total_bytes) is called periodically.

    Returns:
        (Path to staged .exe, manifest_dict)
    """
    version = manifest.get("version", "unknown")
    filename = manifest.get("filename", "")
    expected_sha256 = manifest.get("sha256", "").lower()
    expected_size = manifest.get("size", 0)

    if not filename or not expected_sha256 or expected_size <= 0:
        raise ValueError("Incomplete manifest — cannot stage update")

    download_url = base.rstrip("/") + "/api/provider-update/download"
    folder = Path(data_dir) / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / f"{filename}.partial"
    staged = folder / filename

    if partial.is_file():
        partial.unlink(missing_ok=True)

    digest = hashlib.sha256()
    downloaded = 0

    try:
        with _open_url(download_url, timeout=180) as source, partial.open("wb") as target:
            while True:
                chunk = source.read(512 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_PACKAGE:
                    raise ValueError("Download exceeded maximum allowed size")
                digest.update(chunk)
                target.write(chunk)
                if progress_callback:
                    try:
                        progress_callback(downloaded, expected_size)
                    except Exception:
                        pass

        if downloaded != expected_size:
            raise ValueError(f"Downloaded {downloaded} bytes but manifest declared {expected_size}")
        actual_sha256 = digest.hexdigest().lower()
        if actual_sha256 != expected_sha256:
            raise ValueError(f"SHA256 mismatch: got {actual_sha256[:16]}… expected {expected_sha256[:16]}…")

        if staged.is_file():
            staged.unlink(missing_ok=True)
        partial.replace(staged)
        return staged, manifest

    except BaseException:
        if partial.is_file():
            partial.unlink(missing_ok=True)
        raise


def restart_with_update(staged, data_dir, *, current_build: str = ""):
    """
    Launch the staged installer/updater and auto-reopen the application.
    - If running as a frozen executable (ComputeTorrent_Seeder.exe), replaces the current
      binary via background PowerShell and relaunches it.
    - If running from source (Run-Provider.bat), updates petals_control.py to the new
      version and automatically restarts Run-Provider.bat.
    """
    path, manifest = staged
    if not path.is_file():
        raise ValueError("Staged update package not found")

    expected_sha256 = manifest.get("sha256", "").lower()
    if not expected_sha256:
        raise ValueError("Cannot verify staged installer — no SHA256 in manifest")

    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(512 * 1024):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_sha256:
        raise ValueError("Staged installer SHA256 mismatch — file may have been corrupted")

    is_frozen = getattr(sys, "frozen", False)
    target = Path(sys.executable).resolve() if is_frozen else None

    updates_dir = Path(data_dir) / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    script = updates_dir / "install-update.ps1"

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # Clean environment without PyInstaller internal variables so that
    # the updater script and any restarted processes start as a fresh master bootloader
    clean_env = restart_environment()

    if is_frozen and target and target.is_file():
        # Running as compiled standalone executable: replace and restart
        dest_dir = str(target.parent)
        script.write_text(f'''param([int]$OldPid, [string]$Source, [string]$Destination, [string]$WorkDir)
$ErrorActionPreference = 'Stop'
while (Get-Process -Id $OldPid -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 400 }}
for ($attempt = 0; $attempt -lt 30; $attempt++) {{
    try {{
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        break
    }} catch {{
        if ($attempt -eq 29) {{ throw }}
        Start-Sleep -Milliseconds 800
    }}
}}
# Clean PyInstaller internal variables so restarted process starts as a clean master bootloader
Remove-Item Env:\_MEIPASS* -ErrorAction SilentlyContinue
Remove-Item Env:\_PYI_* -ErrorAction SilentlyContinue
Remove-Item Env:\PYI_* -ErrorAction SilentlyContinue
$env:PYINSTALLER_RESET_ENVIRONMENT = "1"
[System.Environment]::SetEnvironmentVariable("_MEIPASS2", $null, "Process")
[System.Environment]::SetEnvironmentVariable("_MEIPASS", $null, "Process")
Start-Process -FilePath $Destination -WorkingDirectory $WorkDir
''', encoding="utf-8")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-OldPid", str(os.getpid()), "-Source", str(path.resolve()), "-Destination", str(target),
             "-WorkDir", dest_dir],
            env=clean_env,
            creationflags=flags
        )
    else:
        # Running from source (Run-Provider.bat)
        new_version = manifest.get("version", "")
        root_dir = Path(__file__).resolve().parents[2]

        # 1. Update petals_control.py so the new session is marked as up-to-date
        if new_version:
            for p in [
                root_dir / "desktop" / "05-desktop-app-shell" / "petals_control.py",
                root_dir / "08-provider-node" / "05-desktop-app-shell" / "petals_control.py",
            ]:
                if p.is_file():
                    try:
                        text = p.read_text(encoding="utf-8")
                        text = re.sub(r'PROVIDER_BUILD\s*=\s*"[^"]+"', f'PROVIDER_BUILD = "{new_version}"', text)
                        p.write_text(text, encoding="utf-8")
                    except Exception:
                        pass

        # 2. Relaunch Run-Provider.bat automatically once this process closes
        bat_path = root_dir / "Run-Provider.bat"
        if bat_path.is_file():
            script.write_text(f'''param([int]$OldPid, [string]$BatPath)
$ErrorActionPreference = 'Stop'
while (Get-Process -Id $OldPid -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 500 }}
Remove-Item Env:\_MEIPASS* -ErrorAction SilentlyContinue
Remove-Item Env:\_PYI_* -ErrorAction SilentlyContinue
Remove-Item Env:\PYI_* -ErrorAction SilentlyContinue
$env:PYINSTALLER_RESET_ENVIRONMENT = "1"
[System.Environment]::SetEnvironmentVariable("_MEIPASS2", $null, "Process")
[System.Environment]::SetEnvironmentVariable("_MEIPASS", $null, "Process")
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$BatPath`"" -WorkingDirectory (Split-Path $BatPath)
''', encoding="utf-8")
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                 "-OldPid", str(os.getpid()), "-BatPath", str(bat_path.resolve())],
                env=clean_env,
                creationflags=flags
            )
        else:
            # Fallback: start downloaded exe directly without hiding window
            subprocess.Popen([str(path.resolve())], env=clean_env, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
