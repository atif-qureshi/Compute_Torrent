"""Authenticated local Petals DHT and bounded inference-process supervisor."""
import asyncio
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
dht = None
relay_broker = None
relay_loop = None


def relay_call(coroutine):
    if relay_loop is None:
        raise RuntimeError("Petals relay is not configured")
    return asyncio.run_coroutine_threadsafe(coroutine, relay_loop).result(timeout=30)


def start_relay(endpoint=None):
    global relay_broker, relay_loop
    from relay_transport import Broker, serve_broker, relay_url
    if endpoint is None:
        endpoint = os.getenv("PETALS_RELAY_PUBLIC_URL", "").strip()
    if not endpoint:
        return
    try:
        endpoint = relay_url(endpoint)
    except Exception:
        return
    if relay_broker is not None:
        return  # Existing routes retain their own origin; never mutate global trust.
    relay_broker = Broker(endpoint)
    relay_loop = asyncio.new_event_loop()
    ready = threading.Event()
    failure = []
    def run():
        asyncio.set_event_loop(relay_loop)
        try:
            relay_loop.run_until_complete(serve_broker(relay_broker))
            ready.set()
            relay_loop.run_forever()
        except Exception as exc:
            failure.append(exc)
            ready.set()
    threading.Thread(target=run, daemon=True).start()
    if not ready.wait(15) or failure:
        raise RuntimeError("Petals relay listener could not start")


async def probe_route(route_id, peer_id):
    from hivemind.p2p import P2P
    route = relay_broker.leases.get(route_id)
    if not route or route["mux"] is None:
        raise ValueError("Provider relay is not connected")
    port = route["listener"].sockets[0].getsockname()[1]
    peer = await P2P.create(initial_peers=[f"/ip4/127.0.0.1/tcp/{port}/p2p/{peer_id}"],
                            no_listen=True, use_relay=False, use_auto_relay=False,
                            auto_nat=False, nat_port_map=False, startup_timeout=15)
    try:
        if not any(str(p.peer_id) == peer_id for p in await peer.list_peers()):
            raise ValueError("Worker runtime identity mismatch")
        return {"status": "verified", "peer_id": peer_id, "route": "wss"}
    finally:
        await peer.shutdown()



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
                alive = dht is not None and dht.is_alive()
                return self.reply(200 if alive else 503, {
                    "status": "ready" if alive else "unavailable", "bootstrap": bootstrap if alive else [],
                    "network_revision": 2,
                    "relay_enabled": bool(relay_broker is not None and relay_loop and relay_loop.is_running()),
                })
            if self.command == "GET" and self.path.startswith("/jobs/"):
                id = self.path.split("/")[-1]
                if not re.fullmatch(r"[a-f0-9]{32}", id):
                    return self.reply(400, {"detail": "Invalid job ID"})
                def tail_job_log(job_id: str, limit: int = 50):
                    log_file = ROOT / (job_id + ".log")
                    if not log_file.is_file():
                        return []
                    try:
                        lines = [ln for ln in log_file.read_text(errors="replace").splitlines() if ln.strip()]
                        return [ln[-280:] for ln in lines[-limit:]]
                    except Exception:
                        return []

                output = ROOT / (id + ".result.json")
                if output.exists():
                    payload = json.loads(output.read_text())
                    if isinstance(payload, dict) and not payload.get("gateway_log_tail"):
                        payload["gateway_log_tail"] = tail_job_log(id)
                    return self.reply(200, payload)
                with LOCK:
                    if id == active_id and process and process.poll() is None:
                        progress = ROOT / (id + ".progress.json")
                        payload = json.loads(progress.read_text()) if progress.exists() else {"status": "running"}
                        if isinstance(payload, dict):
                            payload["gateway_log_tail"] = tail_job_log(id)
                        return self.reply(200, payload)
                return self.reply(200, {"status": "failed", "error": "Runtime exited or restarted before producing a result; see gateway job log", "gateway_log_tail": tail_job_log(id)})
            length = int(self.headers.get("Content-Length", 0))
            if self.command != "POST" or not 0 < length <= 131072:
                return self.reply(400, {"detail": "Invalid request"})
            data = json.loads(self.rfile.read(length))
            if self.path.startswith("/routes"):
                if self.path == "/routes" and re.fullmatch(r"[a-f0-9]{32}", data.get("job_id", "")):
                    pub_url = data.get("public_url") or os.getenv("PETALS_RELAY_PUBLIC_URL", "").strip()
                    if not pub_url:
                        return self.reply(503, {"detail": "No relay origin configured for this assignment"})
                    from relay_transport import relay_url
                    pub_url = relay_url(pub_url)
                    with LOCK:
                        if relay_broker is None:
                            start_relay(pub_url)
                    if relay_broker is None:
                        return self.reply(503, {"detail": "Petals relay is disabled"})
                    node = data.get("node_id", "")
                    if not isinstance(node, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", node):
                        return self.reply(400, {"detail": "Invalid provider identity"})
                    return self.reply(201, relay_call(relay_broker.create(data["job_id"], node, public_url=pub_url)))
                if relay_broker is None:
                    return self.reply(503, {"detail": "Petals relay is disabled"})
                if self.path == "/routes/revoke":
                    relay_call(relay_broker.revoke(data.get("id", "")))
                    return self.reply(200, {"status": "revoked"})
                if self.path == "/routes/probe" and re.fullmatch(r"[A-Za-z0-9]{16,128}", data.get("peer_id", "")):
                    return self.reply(200, relay_call(probe_route(data.get("id"), data["peer_id"])))
                return self.reply(400, {"detail": "Invalid route request"})
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
                # The inference child runs in this container. Connect it to the
                # local DHT listener; Docker Desktop may not hairpin via the
                # coordinator's published LAN address.
                data["bootstrap"] = [re.sub(r"^/ip4/[^/]+/tcp/31331", "/ip4/127.0.0.1/tcp/31331", peer)
                                     for peer in bootstrap]
                request = ROOT / (active_id + ".request.json")
                request.write_text(json.dumps(data))
                (ROOT / (active_id + ".progress.json")).write_text(json.dumps({"status": "downloading_model", "progress": 0}))
                with (ROOT / (active_id + ".log")).open("w") as log:
                    process = subprocess.Popen([sys.executable, "/app/generate_job.py", str(request)], stdout=log, stderr=log)
            return self.reply(202, {"status": "running"})
        except Exception as exc:
            return self.reply(500, {"detail": str(exc)[:500]})


def main():
    global bootstrap, dht
    import hivemind
    host = os.environ["PETALS_ADVERTISE_HOST"]
    is_ipv4 = bool(re.fullmatch(r"[0-9.]+", host))
    is_dns = bool(re.fullmatch(r"[A-Za-z0-9.-]+", host))
    if not (is_ipv4 or is_dns):
        raise ValueError("PETALS_ADVERTISE_HOST must be a valid IPv4 address or hostname")
    proto = "/ip4" if is_ipv4 else "/dns4"
    announce = [f"{proto}/{host}/tcp/31331"]
    # The gateway's own reachability helper must bootstrap without Docker
    # Desktop hairpinning through its published host address.
    if host != "127.0.0.1":
        announce.append("/ip4/127.0.0.1/tcp/31331")
    identity = Path(os.getenv("PETALS_IDENTITY_PATH", "/cache/petals/dht-identity.key"))
    identity.parent.mkdir(parents=True, exist_ok=True)
    dht = hivemind.DHT(initial_peers=[], host_maddrs=["/ip4/0.0.0.0/tcp/31331"],
                       announce_maddrs=announce, identity_path=str(identity),
                       use_auto_relay=True, use_relay=True, auto_nat=True, nat_port_map=False, start=True)
    from petals.server.reachability import ReachabilityProtocol
    reachability = ReachabilityProtocol.attach_to_dht(dht, await_ready=True)
    bootstrap = [str(a) for a in dht.get_visible_maddrs()
                 if host == "127.0.0.1" or not str(a).startswith("/ip4/127.")]
    advertised_bootstrap = announce[0] + "/p2p/" + str(dht.peer_id)
    if advertised_bootstrap not in bootstrap:
        bootstrap.insert(0, advertised_bootstrap)
    start_relay()
    try:
        ThreadingHTTPServer(("0.0.0.0", 8002), Handler).serve_forever()
    finally:
        if process and process.poll() is None:
            process.terminate()
        if relay_broker is not None:
            relay_call(relay_broker.close())
            relay_loop.call_soon_threadsafe(relay_loop.stop)
        dht.shutdown()


if __name__ == "__main__":
    main()
