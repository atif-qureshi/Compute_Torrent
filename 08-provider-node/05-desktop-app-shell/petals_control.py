"""Desktop-owned Petals containers. Only local, operator-built runtime images."""
import ipaddress
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

CPU_IMAGE = "computetorrent-petals:local"
CUDA_IMAGE = "computetorrent-petals:cuda-local"


def command(args, timeout=20):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Docker command failed")[-700:])
    return result.stdout.strip()


class PetalsControl:
    def __init__(self, root):
        self.root = Path(root) / "petals"
        self.root.mkdir(parents=True, exist_ok=True)
        self.job_id = None
        self.container = None

    def capabilities(self):
        try:
            command(["docker", "image", "inspect", CPU_IMAGE, "--format", "{{.Id}}"])
            ready = True
        except Exception:
            ready = False
        cuda = False
        try:
            command(["docker", "image", "inspect", CUDA_IMAGE, "--format", "{{.Id}}"])
            cuda = command(["docker", "run", "--rm", "--network", "none", "--gpus", "all", CUDA_IMAGE,
                            "python", "-c", "import torch; print(torch.cuda.is_available())"], timeout=40) == "True"
        except Exception:
            pass
        return {"petals_image_ready": ready, "petals_cuda_ready": cuda}

    def start(self, data, coordinator_url, cpu_limit, memory_gb):
        job_id = data.get("job_id", "")
        spec, stage = data.get("spec", {}), data.get("stage", {})
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid layer job ID")
        if spec.get("model_id") not in {"bigscience/bloom-560m", "bigscience/bloomz-560m"}:
            raise ValueError("Unsupported model")
        if not re.fullmatch(r"[a-f0-9]{40}", spec.get("revision", "")):
            raise ValueError("Model revision must be pinned")
        if stage.get("device") not in {"cpu", "cuda"} or not 0 <= stage.get("start", -1) < stage.get("end", -1) <= 24:
            raise ValueError("Invalid block assignment")
        if data.get("prefix") != "ct-" + job_id:
            raise ValueError("Invalid job namespace")
        if not isinstance(data.get("bootstrap"), list) or not data["bootstrap"]:
            raise ValueError("Missing DHT bootstrap")
        self.stop()
        self.job_id = job_id
        self.container = "ct-layer-" + job_id[:16]
        folder = self.root / job_id
        folder.mkdir(exist_ok=True)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((urlsplit(coordinator_url).hostname, 8001))
            address = route.getsockname()[0]
        # Docker Desktop publishes the host port. Loopback is fine only when
        # all peers use the coordinator's host networking path.
        if ipaddress.ip_address(address).is_loopback:
            address = socket.gethostbyname(socket.gethostname())
        data = {**data, "advertise_host": address}
        (folder / "request.json").write_text(json.dumps(data))
        (folder / "lease").write_text(str(time.time()))
        args = ["docker", "run", "-d", "--rm", "--name", self.container,
                "--label", "computetorrent.role=layer-provider", "--memory", f"{memory_gb}g",
                "--cpus", str(cpu_limit), "--pids-limit", "256", "--security-opt", "no-new-privileges",
                "-e", f"OMP_NUM_THREADS={cpu_limit}", "-p", "31330:31330",
                "--mount", f"type=bind,source={folder.resolve()},target=/state",
                "-v", "computetorrent-petals-cache:/cache"]
        if stage["device"] == "cuda":
            args += ["--gpus", "device=0"]
        args += [CUDA_IMAGE if stage["device"] == "cuda" else CPU_IMAGE, "python", "/app/worker.py"]
        command(args, timeout=60)

    def status(self, renew=True):
        if not self.job_id:
            return {"status": "idle"}
        folder = self.root / self.job_id
        if renew:
            (folder / "lease").write_text(str(time.time()))
        result = {"job_id": self.job_id, "status": "starting"}
        try:
            path = folder / "status.json"
            if path.exists():
                result = json.loads(path.read_text())
            command(["docker", "inspect", self.container, "--format", "{{.State.Running}}"])
        except Exception as exc:
            result.update(status="failed", error=str(exc)[:400])
        return result

    def stop(self, job_id=None):
        if job_id and self.job_id != job_id:
            return
        if self.container:
            try:
                command(["docker", "stop", "--time", "8", self.container], timeout=15)
            except Exception:
                pass
        self.container = self.job_id = None
