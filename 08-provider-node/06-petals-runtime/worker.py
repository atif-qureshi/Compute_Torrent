"""Container entrypoint: run fixed assigned Petals blocks and report peer identity."""
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path
from bootstrap_probe import reachable_bootstrap


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
    state = {"job_id": request["job_id"], "status": "connecting", "start": stage["start"],
             "end": stage["end"], "network_revision": 2, "bootstrap": request["bootstrap"]}
    def save():
        state["updated_at"] = time.time()
        path = Path("/state/status.tmp")
        path.write_text(json.dumps(state))
        path.replace("/state/status.json")
    save()
    proc = None
    cancelled = threading.Event()
    def stop(*_):
        cancelled.set()
        if proc is not None and proc.poll() is None:
            proc.terminate()
    signal.signal(signal.SIGTERM, stop)
    def lease_watchdog():
        while not cancelled.is_set():
            try:
                valid = time.time() - float(Path("/state/lease").read_text()) < 90
            except (OSError, ValueError):
                valid = False
            if not valid:
                stop()
                return
            time.sleep(5)
    threading.Thread(target=lease_watchdog, daemon=True).start()
    try:
        request["bootstrap"] = asyncio.run(reachable_bootstrap(request["bootstrap"]))
        state.update(status="loading", bootstrap=request["bootstrap"])
        request["advertise_maddrs"] = advertise_maddrs
        Path("/state/request.json").write_text(json.dumps(request))
        save()
        if cancelled.is_set():
            return
        proc = subprocess.Popen([sys.executable, "/app/layer_server.py"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            print(line, end="", flush=True)
            if line.startswith("CT_STATUS "):
                update = json.loads(line[len("CT_STATUS "):])
                state.update({key: update[key] for key in ("status", "peer_id") if key in update})
                save()
            if "Running a server on" in line:
                match = re.search(r"/p2p/([A-Za-z0-9]+)", line)
                if match:
                    state["peer_id"] = match.group(1)
                    state["status"] = "loading"
                    save()
        code = proc.wait()
        if not cancelled.is_set():
            state.update(status="failed", error=f"Petals server exited ({code}); inspect provider layer log")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        state.update(status="failed", error=str(exc)[-1500:])
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if cancelled.is_set():
            state.update(status="stopped", error="Provider lease expired or layer task was stopped")
        cancelled.set()
        save()


if __name__ == "__main__":
    main()
