"""Desktop-owned Petals containers. Only local, operator-built runtime images."""
import ipaddress
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

CPU_IMAGE = "computetorrent-petals:local"
CUDA_IMAGE = "computetorrent-petals:cuda-local"
NETWORK_REVISION = 2
PROVIDER_BUILD = "2026.11.08-ui4"
DIGEST_LABEL = "computetorrent.runtime.digest"
RUNTIME_DIR = (Path(__file__).resolve().parents[1] / "06-petals-runtime" if not getattr(sys, "frozen", False)
               else Path(sys._MEIPASS) / "petals-runtime")
if not RUNTIME_DIR.is_dir() and not getattr(sys, "frozen", False):
    # The compatibility desktop tree shares the canonical runtime recipe.
    RUNTIME_DIR = Path(__file__).resolve().parents[2] / "08-provider-node" / "06-petals-runtime"


def provider_identity():
    return {"petals_network_revision": NETWORK_REVISION, "petals_provider_build": PROVIDER_BUILD,
            "petals_relay_protocol": 1, "petals_capacity_protocol": 1}


@lru_cache(maxsize=2)
def runtime_digest(device="cpu"):
    """Identify immutable bundled runtime sources once per application process."""
    if device not in {"cpu", "cuda"}:
        raise ValueError("Choose CPU or CUDA runtime")
    names = ["Dockerfile" if device == "cpu" else "Dockerfile.cuda", "requirements-petals.txt"]
    names += sorted(path.name for path in RUNTIME_DIR.glob("*.py"))
    if "worker.py" not in names:
        raise RuntimeError("Bundled Petals worker is missing; reinstall the latest provider app")
    digest = hashlib.sha256()
    for name in names:
        path = RUNTIME_DIR / name
        if not path.is_file():
            raise RuntimeError("Bundled Petals runtime recipe is missing; reinstall the latest provider app")
        digest.update(name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def command(args, timeout=20):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Docker command failed")[-700:])
    return result.stdout.strip()


class PetalsControl:
    def __init__(self, root, host_port=31330):
        self.root = Path(root) / "petals"
        self.root.mkdir(parents=True, exist_ok=True)
        self.host_port = int(host_port)
        if not 1024 <= self.host_port <= 65535:
            raise ValueError("Petals host port must be between 1024 and 65535")
        self.job_id = None
        self.container = None
        self.phase = "idle"
        self.failure_status = None
        self.assignment = {}
        self._dl_probe = {}
        self.capacity_job_id = None
        self._dl_probe = {}

    def _validated_image_id(self, device):
        expected = runtime_digest(device)
        image = CPU_IMAGE if device == "cpu" else CUDA_IMAGE
        try:
            info = json.loads(command(["docker", "image", "inspect", image, "--format", "{{json .}}"], timeout=3))
            labels = info.get("Config", {}).get("Labels") or {}
            if labels.get(DIGEST_LABEL) == expected and info.get("Id"):
                return info["Id"]
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return None

    def capabilities(self):
        result = {**provider_identity(), "petals_image_ready": False, "petals_cuda_ready": False}
        for device, flag, key in (("cpu", "petals_image_ready", "petals_runtime_digest"),
                                  ("cuda", "petals_cuda_ready", "petals_cuda_runtime_digest")):
            try:
                result[key] = runtime_digest(device)
                result[flag] = bool(self._validated_image_id(device))
            except RuntimeError:
                pass
        return result

    def install_runtime(self, device="cpu", progress=None):
        if device not in {"cpu", "cuda"}:
            raise ValueError("Choose CPU or CUDA runtime")
        dockerfile = RUNTIME_DIR / ("Dockerfile" if device == "cpu" else "Dockerfile.cuda")
        image = CPU_IMAGE if device == "cpu" else CUDA_IMAGE
        if not dockerfile.is_file():
            raise RuntimeError("Bundled Petals runtime recipe is missing; reinstall the latest provider app")
        digest = runtime_digest(device)
        if progress:
            progress(f"Building the {device.upper()} Petals runtime; Docker is downloading dependencies")
        result = subprocess.run(["docker", "build", "--progress=plain", "--label", f"{DIGEST_LABEL}={digest}",
            "-f", str(dockerfile), "-t", image, str(RUNTIME_DIR)],
            capture_output=True, text=True, timeout=3600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "Docker image build failed")[-1200:])
        image_id = self._validated_image_id(device)
        if not image_id:
            raise RuntimeError("Petals runtime build did not produce the expected source revision")
        return image_id

    def measure_capacity(self, data, cpu_limit, memory_gb):
        job_id = data.get("job_id", "")
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid capacity-probe job")
        device = data.get("device", "cpu")
        if device not in {"cpu", "cuda"}:
            raise ValueError("Invalid capacity-probe device")
        image = self._validated_image_id(device) or self.install_runtime(device)
        folder = self.root / job_id
        folder.mkdir(exist_ok=True)
        (folder / "capacity-request.json").write_text(json.dumps({
            "spec": data["spec"], "device": device, "cpu_limit": cpu_limit, "memory_gb": memory_gb}))
        self.capacity_job_id = job_id
        (folder / "capacity-lease").write_text(str(time.time()))
        name = "ct-capacity-" + job_id[:12] + "-" + hashlib.sha256(str(self.root).encode()).hexdigest()[:8]
        args = ["docker", "run", "--rm", "--name", name, "--memory", f"{memory_gb}g",
                "--cpus", str(cpu_limit), "--pids-limit", "256", "--init",
                "--security-opt", "no-new-privileges", "-e", f"OMP_NUM_THREADS={cpu_limit}",
                "--mount", f"type=bind,source={folder.resolve()},target=/state",
                "-v", "computetorrent-petals-cache:/cache"]
        if device == "cuda":
            args += ["--gpus", "device=0"]
        args += ["--entrypoint", "python", image, "/app/capacity_probe.py"]
        try:
            output = command(args, timeout=3600)
            record = next(line[12:] for line in reversed(output.splitlines()) if line.startswith("CT_CAPACITY "))
            return json.loads(record)
        finally:
            self.capacity_job_id = None
            try:
                command(["docker", "rm", "-f", name], timeout=15)
            except Exception:
                pass

    def start(self, data, coordinator_url, cpu_limit, memory_gb):
        job_id = data.get("job_id", "")
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid layer job ID")
        self.stop()
        self.job_id = job_id
        self.phase = "preparing_runtime"
        self.assignment = {key: data.get("stage", {}).get(key) for key in ("start", "end")}
        try:
            self._start(data, coordinator_url, cpu_limit, memory_gb)
        except Exception as exc:
            self.fail_job(job_id, str(exc))
            raise

    def _start(self, data, coordinator_url, cpu_limit, memory_gb):
        job_id = data["job_id"]
        spec, stage = data.get("spec", {}), data.get("stage", {})
        if not spec.get("model_id"):
            raise ValueError("model_id is required")
        if stage.get("device") not in {"cpu", "cuda"} or not 0 <= stage.get("start", -1) < stage.get("end", -1):
            raise ValueError("Invalid block assignment")
        if data.get("prefix") != "ct-" + job_id:
            raise ValueError("Invalid job namespace")
        if not isinstance(data.get("bootstrap"), list) or not data["bootstrap"]:
            raise ValueError("Missing DHT bootstrap")
        node_suffix = hashlib.sha256(stage["node_id"].encode()).hexdigest()[:8]
        self.container = "ct-layer-" + job_id[:10] + "-" + node_suffix
        folder = self.root / job_id
        folder.mkdir(exist_ok=True)
        parsed_coordinator = urlsplit(coordinator_url)
        coordinator_host = parsed_coordinator.hostname
        coordinator_ip = None
        try:
            coordinator_ip = ipaddress.ip_address(socket.gethostbyname(coordinator_host))
        except (OSError, ValueError):
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((coordinator_host, parsed_coordinator.port or (443 if parsed_coordinator.scheme == "wss" else 80)))
            address = route.getsockname()[0]
        same_host = bool(coordinator_ip and (coordinator_ip.is_loopback or str(coordinator_ip) == address))
        # Docker Desktop publishes the host port. Loopback is fine only when
        # all peers use the coordinator's host networking path.
        if ipaddress.ip_address(address).is_loopback:
            advertised_address = None
            if same_host:
                for peer in data.get("bootstrap", []):
                    match = re.match(r"^/ip4/([^/]+)/tcp/", peer)
                    if not match:
                        continue
                    try:
                        candidate = ipaddress.IPv4Address(match.group(1))
                    except ValueError:
                        continue
                    if not (candidate.is_loopback or candidate.is_unspecified or candidate.is_multicast):
                        advertised_address = str(candidate)
                        break
            address = advertised_address or socket.gethostbyname(socket.gethostname())
        bootstrap = []
        # host.docker.internal resolves to the local Windows host from inside
        # Docker Desktop. Add it only on the coordinator PC itself; on a remote
        # volunteer PC it would point back to that volunteer and break DHT join.
        is_lan = False
        if coordinator_ip:
            is_lan = coordinator_ip.is_private or coordinator_ip.is_loopback
        else:
            try:
                resolved = socket.gethostbyname(coordinator_host)
                is_lan = ipaddress.ip_address(resolved).is_private or ipaddress.ip_address(resolved).is_loopback
            except Exception:
                pass

        if not same_host:
            dht_target_ip = None
            for b_peer in data.get("bootstrap", []):
                match = re.search(r"/(?:ip4|dns4)/([^/]+)/tcp/31331", b_peer)
                if match:
                    dht_target_ip = match.group(1)
                    break
            target_to_check = dht_target_ip or (str(coordinator_ip) if coordinator_ip and not coordinator_ip.is_loopback else coordinator_host)
            if target_to_check and is_lan:
                try:
                    with socket.create_connection((target_to_check, 31331), timeout=5):
                        pass
                except OSError as exc:
                    if not data.get("relay"):
                        raise RuntimeError(
                            f"Cannot reach coordinator DHT bootstrap at {target_to_check}:31331. "
                            "Check the LAN firewall or configure the authenticated WSS relay."
                        ) from exc
        for peer in data.get("bootstrap", []):
            if not same_host:
                peer = re.sub(r"^/dns4/host\.docker\.internal(?=/tcp/)", f"/ip4/{coordinator_ip}", peer)
            if same_host and "/tcp/31331" in peer:
                internal_peer = re.sub(r"^/ip4/[^/]+/tcp/31331", "/dns4/host.docker.internal/tcp/31331", peer)
                if internal_peer not in bootstrap:
                    bootstrap.append(internal_peer)
            if peer not in bootstrap:
                bootstrap.append(peer)

        advertise = [f"/ip4/{address}/tcp/{self.host_port}"]
        if same_host:
            advertise.append(f"/dns4/host.docker.internal/tcp/{self.host_port}")
        data = {**data, "bootstrap": bootstrap, "advertise_maddrs": advertise,
                "advertise_host": address, "advertise_port": self.host_port,
                "network_revision": NETWORK_REVISION, "runtime_digest": runtime_digest(stage["device"])}
        (folder / "request.json").write_text(json.dumps(data))
        (folder / "lease").write_text(str(time.time()))
        target_image = self._validated_image_id(stage["device"])
        if not target_image:
            target_image = self.install_runtime(stage["device"])
        self.phase = "starting_container"
        args = ["docker", "run", "-d", "--name", self.container,
                "--label", "computetorrent.role=layer-provider", "--memory", f"{memory_gb}g",
                "--cpus", str(cpu_limit), "--pids-limit", "256", "--shm-size", "1g",
                "--init", "--security-opt", "no-new-privileges",
                "-e", f"OMP_NUM_THREADS={cpu_limit}", "-p", f"{self.host_port}:31330", "--dns", "8.8.8.8", "--dns", "1.1.1.1",
                "--mount", f"type=bind,source={folder.resolve()},target=/state",
                "-v", "computetorrent-petals-cache:/cache"]
        if same_host:
            args += ["--add-host", "host.docker.internal:host-gateway"]
        if stage["device"] == "cuda":
            args += ["--gpus", "device=0"]
        args += [target_image, "python", "/app/worker.py"]
        # Building a first runtime can take an hour; start the worker with a fresh lease.
        (folder / "lease").write_text(str(time.time()))
        command(args, timeout=60)
        self.phase = "loading_model"

    def fail_job(self, job_id, error):
        """Keep launch failures visible until the coordinator acknowledges or retries."""
        self.job_id = job_id
        self.phase = "failed"
        self.failure_status = {"job_id": job_id, "status": "failed", "error": str(error)[:1000], **self.assignment}
        if isinstance(job_id, str) and re.fullmatch(r"[a-f0-9]{32}", job_id):
            try:
                folder = self.root / job_id
                folder.mkdir(exist_ok=True)
                (folder / "status.json").write_text(json.dumps(self.failure_status), encoding="utf-8")
            except OSError:
                pass  # Preserve the original error in heartbeats even if disk writes fail.

    def status(self, renew=True):
        capacity_job = self.capacity_job_id
        if capacity_job:
            if renew:
                (self.root / capacity_job / "capacity-lease").write_text(str(time.time()))
            return {"job_id": capacity_job, "status": "profiling_capacity"}
        if not self.job_id:
            return {"status": "idle"}
        if self.failure_status:
            return dict(self.failure_status)
        folder = self.root / self.job_id
        if renew:
            (folder / "lease").write_text(str(time.time()))
        if self.phase in {"preparing_runtime", "starting_container"}:
            return {"job_id": self.job_id, "status": self.phase, **self.assignment}
        result = {"job_id": self.job_id, "status": "starting"}
        try:
            path = folder / "status.json"
            if path.exists():
                result = json.loads(path.read_text())
            running = command(["docker", "inspect", self.container, "--format", "{{.State.Running}}"])
            if running.lower() != "true":
                if result.get("error") and "inspect provider layer log" not in result["error"]:
                    result["status"] = "failed"
                    return result
                oom = command(["docker", "inspect", self.container, "--format", "{{.State.OOMKilled}}"], timeout=8)
                if oom.lower() == "true":
                    result.update(status="failed", error="Provider Docker memory limit exceeded (OOM). Reduce assigned layers or increase the provider RAM limit.")
                    return result
                tail = command(["docker", "logs", "--tail", "80", self.container], timeout=8)
                (folder / "container.log").write_text(tail[-16000:], encoding="utf-8")
                last = tail.strip().splitlines()[-1] if tail.strip() else "No stderr retained"
                result.update(status="failed", error="Petals layer container stopped: " + last[-1200:])
        except Exception as exc:
            result.update(status="failed", error=result.get("error") or str(exc)[:1000])
            return result
        log_tail = []
        layer_log_file = folder / "layer.log"
        if layer_log_file.is_file():
            try:
                log_tail = [ln[-260:] for ln in layer_log_file.read_text(errors="replace").splitlines() if ln.strip()][-35:]
            except OSError:
                log_tail = []
        status_name = result.get("status")
        if status_name in {"loading", "starting"}:
            weights_bytes = 0
            model_id = None
            req_file = folder / "request.json"
            if req_file.is_file():
                try:
                    req_data = json.loads(req_file.read_text(encoding="utf-8"))
                    spec = req_data.get("spec") or {}
                    model_id = spec.get("model_id")
                    weights_bytes = int(spec.get("weights_bytes") or 0)
                except Exception:
                    pass
            probe = self._dl_probe if isinstance(getattr(self, "_dl_probe", None), dict) and self._dl_probe.get("job_id") == self.job_id else {"job_id": self.job_id, "ts": 0.0, "bytes": 0, "speed_bps": 0}
            now_mono = time.monotonic()
            if model_id and self.container and now_mono - probe.get("ts", 0.0) >= 6.0:
                slug = "models--" + str(model_id).replace("/", "--")
                py_probe = (
                    "import pathlib; "
                    f"s={slug!r}; "
                    "print(sum(f.stat().st_size for r in ('/cache/petals','/cache/huggingface/hub') "
                    "for d in [pathlib.Path(r)/s/'blobs'] if d.is_dir() "
                    "for f in d.iterdir() if f.is_file()))"
                )
                try:
                    out = command(["docker", "exec", self.container, "python", "-c", py_probe], timeout=4)
                    new_bytes = int((out or "0").strip().splitlines()[-1])
                    dt = max(now_mono - probe["ts"], 1.0) if probe.get("ts") else 0.0
                    speed_bps = max(0, int((new_bytes - probe.get("bytes", 0)) / dt)) if dt > 0 and probe.get("ts") else 0
                    probe = {"job_id": self.job_id, "ts": now_mono, "bytes": new_bytes, "speed_bps": speed_bps}
                    self._dl_probe = probe
                except Exception:
                    probe["ts"] = now_mono
                    self._dl_probe = probe
            dl_bytes = int(probe.get("bytes") or 0)
            pct = min(99, max(1, int(dl_bytes * 100 / weights_bytes))) if weights_bytes > 0 and dl_bytes > 0 else (0 if weights_bytes > 0 else None)
            result["progress"] = {
                "phase": status_name,
                "downloaded_bytes": dl_bytes,
                "total_bytes": weights_bytes or None,
                "percent": pct,
                "speed_bps": int(probe.get("speed_bps") or 0),
                "log_tail": log_tail,
                "updated_at": int(time.time()),
            }
        elif log_tail:
            result["progress"] = {
                "phase": status_name,
                "percent": 100 if status_name == "serving" else None,
                "log_tail": log_tail,
                "updated_at": int(time.time()),
            }
        return result

    def stop(self, job_id=None):
        if job_id and self.job_id != job_id:
            return
        if self.container:
            try:
                if self.job_id:
                    log = command(["docker", "logs", "--tail", "80", self.container], timeout=8)
                    (self.root / self.job_id / "container.log").write_text(log[-16000:], encoding="utf-8")
            except Exception:
                pass
            try:
                command(["docker", "rm", "-f", self.container], timeout=15)
            except Exception:
                pass
        self.container = self.job_id = None
        self.phase = "idle"
        self.failure_status = None
        self.assignment = {}
        self._dl_probe = {}
