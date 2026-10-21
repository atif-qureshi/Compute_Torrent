"""Start one real local Petals block and confirm its private DHT announcement.

Run from the repository root after starting the optional Petals gateway.
This is a worker preflight, not a multi-provider inference result.
"""
import argparse
import json
import secrets
import sys
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "08-provider-node" / "05-desktop-app-shell"))
    from petals_control import PetalsControl

    values = {}
    for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    token = values["COMPUTETORRENT_API_TOKEN"]
    request = urllib.request.Request("http://127.0.0.1:8001/api/distributed/status",
                                     headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=30) as response:
        bootstrap = json.load(response)["bootstrap"]
    with urllib.request.urlopen(
        "https://huggingface.co/api/models/bigscience/bloom-560m/revision/main", timeout=30
    ) as response:
        revision = json.load(response)["sha"]
    job_id = secrets.token_hex(16)
    control = PetalsControl(root / "runtime" / "local-layer-smoke", host_port=31330)
    payload = {"job_id": job_id, "spec": {"model_id": "bigscience/bloom-560m", "revision": revision},
               "stage": {"node_id": "local-smoke", "start": 0, "end": 1, "device": "cpu"},
               "prefix": "ct-" + job_id, "bootstrap": bootstrap}
    try:
        control.start(payload, "ws://127.0.0.1:8001/ws/seeder", 2, 4)
        deadline = time.monotonic() + args.timeout
        previous = None
        while time.monotonic() < deadline:
            status = control.status()
            if status.get("status") != previous:
                previous = status.get("status")
                print("Worker status:", previous, flush=True)
            if status.get("peer_id"):
                print("Real worker announced model layer 0 in the private DHT", flush=True)
                return
            if status.get("error"):
                raise RuntimeError(status["error"])
            time.sleep(5)
        raise TimeoutError("Worker did not announce within the deadline")
    finally:
        control.stop()


if __name__ == "__main__":
    main()
