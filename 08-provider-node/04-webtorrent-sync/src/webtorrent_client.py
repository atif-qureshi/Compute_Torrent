"""Python adapter for the bundled WebTorrent v2 downloader."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
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
        if not isinstance(magnet_uri, str) or not magnet_uri.startswith("magnet:?xt=urn:btih:"):
            raise ValueError("Assignment did not include a valid WebTorrent magnet URI")
        if not task_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in task_id):
            raise ValueError("Invalid task workspace key")
        target = Path(output_dir).resolve()
        if not target.is_relative_to(self.workspace):
            raise ValueError("Download directory must be inside the seeder workspace")
        if Path(expected_filename).name != expected_filename or expected_filename in {".", ".."}:
            raise ValueError("Invalid expected filename")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
            raise ValueError("Expected SHA-256 must be a 64-character hex digest")
        target.mkdir(parents=True, exist_ok=True)
        if not self.helper.is_file():
            raise FileNotFoundError(f"WebTorrent helper is missing: {self.helper}")
        process = subprocess.Popen(
            [self.node, str(self.helper), "download", magnet_uri, str(target)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
        )
        diagnostics = []

        def report_progress():
            if process.stderr is None:
                return
            for line in process.stderr:
                line = line.strip()
                if not line:
                    continue
                diagnostics.append(line)
                del diagnostics[:-40]
                if progress_callback:
                    try:
                        progress_callback(line)
                    except Exception:
                        # A UI callback must not interrupt a verified transfer.
                        pass

        reader = threading.Thread(target=report_progress, name="computetorrent-webtorrent-log", daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=1800)
        except subprocess.TimeoutExpired as exc:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=2)
            raise RuntimeError("WebTorrent download timed out after 30 minutes") from exc
        finally:
            reader.join(timeout=2)
            if process.stderr:
                process.stderr.close()
        if return_code:
            detail = "\n".join(diagnostics)[-1000:]
            raise RuntimeError(detail or "WebTorrent download failed")
        payload_candidate = target / expected_filename
        if payload_candidate.is_symlink():
            raise RuntimeError("Swarm payload must not be a symlink")
        payload = payload_candidate.resolve()
        if not payload.is_relative_to(target) or not payload.is_file():
            raise RuntimeError(f"Swarm did not contain {expected_filename}")
        digest = hashlib.sha256()
        with payload.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest().lower() != expected_hash.lower():
            raise RuntimeError("Downloaded chunk failed SHA-256 verification")
        if expected_filename == "chunk.json":
            json.loads(payload.read_text(encoding="utf-8"))
        return payload

    def leave_swarm(self, task_id: str):
        """The helper shuts down its peer client once the torrent is complete."""
        task_dir = (self.workspace / "workspace" / task_id).resolve()
        if task_dir.is_relative_to(self.workspace) and task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)
