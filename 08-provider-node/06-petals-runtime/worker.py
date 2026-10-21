"""Container entrypoint: run fixed assigned Petals blocks and report peer identity."""
import json
import os
import re
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path


def main():
    request = json.loads(Path("/state/request.json").read_text())
    spec, stage = request["spec"], request["stage"]
    if not spec.get("model_id"):
        raise ValueError("model_id is required")
    if not (0 <= stage["start"] < stage["end"]):
        raise ValueError("Invalid block range")
    advertise_port = int(request.get("advertise_port", 31330))
    if not 1024 <= advertise_port <= 65535:
        raise ValueError("Invalid advertised provider port")
    advertise_maddrs = request.get("advertise_maddrs") or [f"/ip4/{request['advertise_host']}/tcp/{advertise_port}"]
    if not isinstance(advertise_maddrs, list) or not advertise_maddrs or any(
        not re.fullmatch(r"/(?:ip4|dns4)/[A-Za-z0-9.-]+/tcp/[0-9]{4,5}", addr)
        for addr in advertise_maddrs
    ):
        raise ValueError("Invalid announced provider addresses")
    state = {"job_id": request["job_id"], "status": "loading", "start": stage["start"], "end": stage["end"]}
    def save():
        state["updated_at"] = time.time()
        path = Path("/state/status.tmp")
        path.write_text(json.dumps(state))
        path.replace("/state/status.json")
    save()
    command = [sys.executable, "-m", "petals.cli.run_server", spec["model_id"],
        "--revision", spec["revision"], "--block_indices", f"{stage['start']}:{stage['end']}",
        "--dht_prefix", request["prefix"], "--device", stage["device"],
        "--torch_dtype", "float32", "--quant_type", "none", "--compression", "NONE",
        "--port", "31330", "--announce_maddrs", *advertise_maddrs,
        "--inference_max_length", "512", "--attn_cache_tokens", "1024", "--num_handlers", "2",
        "--max_disk_space", "8GiB", "--throughput", "auto", "--balance_quality", "0",
        "--initial_peers", *request["bootstrap"]]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    signal.signal(signal.SIGTERM, lambda *_: proc.terminate())
    def lease_watchdog():
        while proc.poll() is None:
            try:
                valid = time.time() - float(Path("/state/lease").read_text()) < 90
            except (OSError, ValueError):
                valid = False
            if not valid:
                proc.terminate()
                return
            time.sleep(5)
    threading.Thread(target=lease_watchdog, daemon=True).start()
    try:
        for line in proc.stdout:
            print(line, end="", flush=True)
            if "Running a server on" in line:
                match = re.search(r"/p2p/([A-Za-z0-9]+)", line)
                if match:
                    state["peer_id"] = match.group(1)
                    state["status"] = "serving"
                    save()
        code = proc.wait()
        state.update(status="stopped", error=f"Petals server exited ({code}); inspect provider layer log")
    finally:
        if proc.poll() is None:
            proc.terminate()
        save()


if __name__ == "__main__":
    main()
