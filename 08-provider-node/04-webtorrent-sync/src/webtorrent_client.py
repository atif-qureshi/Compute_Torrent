"""Python adapter for the bundled WebTorrent v2 downloader."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional


class WebTorrentClient:
    def __init__(self, workspace_dir: str = "./workspace"):
        self.workspace = Path(workspace_dir).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.helper = Path(os.getenv("COMPUTETORRENT_WEBTORRENT_HELPER", Path(__file__).with_name("webtorrent_helper.mjs"))).resolve()
        self.node = os.getenv("COMPUTETORRENT_NODE", "node")

    def download_from_swarm(self, magnet_uri: str, task_id: str, output_dir: str,
                            expected_hash: str, expected_filename: str = "chunk.json",
                            progress_callback: Optional[Callable] = None) -> Path:
        if not magnet_uri.startswith("magnet:?xt=urn:btih:"):
            raise ValueError("Assignment did not include a valid WebTorrent magnet URI")
        if not task_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in task_id):
            raise ValueError("Invalid task workspace key")
        target = Path(output_dir).resolve()
        if not target.is_relative_to(self.workspace):
            raise ValueError("Download directory must be inside the seeder workspace")
        target.mkdir(parents=True, exist_ok=True)
        if not self.helper.is_file():
            raise FileNotFoundError(f"WebTorrent helper is missing: {self.helper}")
        result = subprocess.run([self.node, str(self.helper), "download", magnet_uri, str(target)],
                                capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "WebTorrent download failed")[-1000:])
        if Path(expected_filename).name != expected_filename:
            raise ValueError("Invalid expected filename")
        payload = target / expected_filename
        if not payload.is_file():
            raise RuntimeError(f"Swarm did not contain {expected_filename}")
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        if digest.lower() != expected_hash.lower():
            raise RuntimeError("Downloaded chunk failed SHA-256 verification")
        if expected_filename == "chunk.json":
            json.loads(payload.read_text(encoding="utf-8"))
        return payload

    def leave_swarm(self, task_id: str):
        """The helper shuts down its peer client once the torrent is complete."""
        task_dir = (self.workspace / "workspace" / task_id).resolve()
        if task_dir.is_relative_to(self.workspace) and task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)
