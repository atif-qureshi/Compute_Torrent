"""Authenticated local Petals DHT and bounded inference-process supervisor."""
import hmac
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.getenv("PETALS_JOB_DIR", "/jobs"))
ROOT.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ["COMPUTETORRENT_API_TOKEN"]
LOCK = threading.Lock()
process = None
active_id = None
bootstrap = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        global process, active_id
        if not TOKEN or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + TOKEN):
            return self.reply(401, {"detail": "Authentication required"})
        try:
            if self.command == "GET" and self.path == "/health":
                return self.reply(200, {"status": "ready", "bootstrap": bootstrap})
            if self.command == "GET" and self.path.startswith("/jobs/"):
                id = self.path.split("/")[-1]
                if not re.fullmatch(r"[a-f0-9]{32}", id):
                    return self.reply(400, {"detail": "Invalid job ID"})
                output = ROOT / (id + ".result.json")
                if output.exists():
                    return self.reply(200, json.loads(output.read_text()))
                with LOCK:
                    if id == active_id and process and process.poll() is None:
                        progress = ROOT / (id + ".progress.json")
                        return self.reply(200, json.loads(progress.read_text()) if progress.exists() else {"status": "running"})
                return self.reply(200, {"status": "failed", "error": "Runtime exited or restarted before producing a result; see gateway job log"})
            length = int(self.headers.get("Content-Length", 0))
            if self.command != "POST" or not 0 < length <= 131072:
                return self.reply(400, {"detail": "Invalid request"})
            data = json.loads(self.rfile.read(length))
            if self.path == "/cancel":
                with LOCK:
                    if active_id == data.get("id") and process and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                return self.reply(200, {"status": "stopped"})
            if self.path != "/jobs" or not re.fullmatch(r"[a-f0-9]{32}", data.get("id", "")):
                return self.reply(400, {"detail": "Invalid job"})
            with LOCK:
                if process and process.poll() is None:
                    return self.reply(409, {"detail": "Gateway is busy"})
                active_id = data["id"]
                data["bootstrap"] = bootstrap
                request = ROOT / (active_id + ".request.json")
                request.write_text(json.dumps(data))
                with (ROOT / (active_id + ".log")).open("w") as log:
                    process = subprocess.Popen([sys.executable, "/app/generate_job.py", str(request)], stdout=log, stderr=log)
            return self.reply(202, {"status": "running"})
        except Exception as exc:
            return self.reply(500, {"detail": str(exc)[:500]})


def main():
    global bootstrap
    import hivemind
    host = os.environ["PETALS_ADVERTISE_HOST"]
    if not re.fullmatch(r"[0-9.]+", host):
        raise ValueError("PETALS_ADVERTISE_HOST must be the coordinator's LAN IPv4 address")
    dht = hivemind.DHT(initial_peers=[], host_maddrs=["/ip4/0.0.0.0/tcp/31331"],
                       announce_maddrs=[f"/ip4/{host}/tcp/31331"], start=True)
    bootstrap = [str(a) for a in dht.get_visible_maddrs()]
    try:
        ThreadingHTTPServer(("0.0.0.0", 8002), Handler).serve_forever()
    finally:
        if process and process.poll() is None:
            process.terminate()
        dht.shutdown()


if __name__ == "__main__":
    main()
