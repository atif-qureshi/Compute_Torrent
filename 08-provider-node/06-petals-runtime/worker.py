"""Container entrypoint: run fixed assigned Petals blocks and report peer identity."""
from collections import deque
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
from route_selection import prepare_route


def layer_failure(code, lines):
    tail = "".join(lines)[-6000:]
    tail = re.sub(r"\x1b\[[0-9;]*m", "", tail)
    tail = re.sub(r"(?i)Bearer\s+[^\s]+", "Bearer [redacted]", tail)
    tail = re.sub(r"hf_[A-Za-z0-9]+", "[redacted]", tail)
    tail = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[redacted]", tail)
    # Lead with the exception, rather than losing it when the dashboard truncates.
    meaningful = [line.strip() for line in tail.splitlines() if re.match(
        r"^[A-Za-z_.]*(?:Error|Exception):", line.strip())]
    reason = meaningful[-1] if meaningful else (tail.strip().splitlines()[-1] if tail.strip() else "No stderr captured")
    return f"Petals layer exited ({code}): {reason}"[:1400], tail


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
        not re.fullmatch(r"/(?:ip4|dns4)/[A-Za-z0-9.-]+/tcp/[0-9]{4,5}(?:/p2p/[A-Za-z0-9]+)?(?:/p2p-circuit)?(?:/p2p/[A-Za-z0-9]+)?", addr)
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
    relay_handle = None
    cancelled = threading.Event()
    def stop(*_):
        cancelled.set()
        if proc is not None and proc.poll() is None:
            proc.terminate()
    signal.signal(signal.SIGTERM, stop)
    def lease_watchdog():
        while not cancelled.is_set():
            try:
                valid = (time.time() - float(Path("/state/lease").read_text()) < 90
                         and not (relay_handle and relay_handle.failed.is_set()))
            except (OSError, ValueError):
                valid = False
            if not valid:
                stop()
                return
            time.sleep(5)
    threading.Thread(target=lease_watchdog, daemon=True).start()
    try:
        request, relay_handle = prepare_route(request)
        request["bootstrap"] = asyncio.run(reachable_bootstrap(request["bootstrap"]))
        state.update(status="loading", bootstrap=request["bootstrap"], transport=request["transport"],
                     advertise_maddrs=request["advertise_maddrs"])
        Path("/state/request.json").write_text(json.dumps(request))
        save()
        if cancelled.is_set():
            return
        proc = subprocess.Popen([sys.executable, "/app/layer_server.py"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        recent = deque(maxlen=80)
        for line in proc.stdout:
            recent.append(line)
            # Retain the final traceback even after coordinator cleanup removes
            # the Docker container. Bound the on-disk diagnostic to 6000 chars.
            try:
                Path("/state/layer.log").write_text("".join(recent)[-6000:], encoding="utf-8")
            except OSError:
                pass
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
            error, tail = layer_failure(code, recent)
            state.update(status="failed", error=error, log_tail=tail)
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
        if relay_handle:
            relay_handle.stop()
        save()


if __name__ == "__main__":
    main()
