"""Run a real two-container, one-PC Model Studio inference and clean up providers.

This validates coordinator dispatch, private DHT routing, generation and local
verification. It does not substitute for a test on two physical LAN machines.
Run from the repository root with the optional Petals gateway running.
"""
import asyncio
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "08-provider-node" / "05-desktop-app-shell"))
from petals_control import PetalsControl

API = "http://127.0.0.1:8001"
WS = "ws://127.0.0.1:8001/ws/seeder"


def secrets_from_env():
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    return values


def call(path, token, body=None, method=None, enrollment=False):
    headers = {"Content-Type": "application/json"}
    headers["X-Enrollment-Token" if enrollment else "Authorization"] = (
        token if enrollment else "Bearer " + token
    )
    request = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"API {path} returned {error.code}: {error.read().decode()[:300]}") from error


class LocalProvider:
    def __init__(self, index, join_code):
        self.index = index
        self.join_code = join_code
        self.control = PetalsControl(ROOT / "runtime" / f"petals-smoke-{index}", host_port=31330 + index * 2)
        self.profile = {"petals_enabled": True, "petals_protocol_version": 1,
                        "petals_image_ready": True, "docker_ok": True,
                        "free_ram_gb": 6, "memory_limit_gb": 4,
                        "disk_free_gb": 10, "RAM": 8, "CPU": 2,
                        "cpu_model": f"Local smoke provider {index}"}
        self.node_id = None
        self.access_token = None
        self.current_job = None
        self.socket = None
        self.task = None
        self.start_task = None

    async def enroll(self):
        result = await asyncio.to_thread(call, "/api/seeders/enroll", self.join_code,
                                         {"tier": 2, "profile": self.profile}, "POST", True)
        self.node_id, self.access_token = result["node_id"], result["access_token"]

    async def heartbeat(self):
        while self.socket:
            if self.current_job:
                state = await asyncio.to_thread(self.control.status)
                if state.get("job_id") != self.current_job:
                    state = {"job_id": self.current_job, "status": "accepted"}
            else:
                state = {"status": "idle"}
            self.profile["petals"] = state
            await self.socket.send(json.dumps({"type": "heartbeat", "node_id": self.node_id,
                                               "state": "busy" if self.current_job else "idle",
                                               "profile": self.profile}))
            await asyncio.sleep(3)

    async def start_layers(self, message):
        try:
            await asyncio.to_thread(self.control.start, message, WS, 1, 4)
        except Exception as exc:
            self.profile["petals"] = {"job_id": self.current_job, "status": "failed", "error": str(exc)[:450]}
            print(f"Provider {self.index} start failed: {str(exc)[:200]}", flush=True)

    async def run(self):
        async with websockets.connect(WS, extra_headers={"Authorization": "Bearer " + self.access_token},
                                      open_timeout=30, ping_interval=30) as socket:
            self.socket = socket
            await socket.send(json.dumps({"type": "register", "node_id": self.node_id,
                                          "tier": 2, "profile": self.profile}))
            acknowledgement = json.loads(await socket.recv())
            if acknowledgement.get("type") != "register_ack":
                raise RuntimeError("Provider registration was not acknowledged")
            print(f"Provider {self.index} connected", flush=True)
            heartbeat = asyncio.create_task(self.heartbeat())
            try:
                async for raw in socket:
                    message = json.loads(raw)
                    if message.get("type") == "petals_start":
                        self.current_job = message["job_id"]
                        print(f"Provider {self.index} assigned layers {message['stage']['start']}–{message['stage']['end'] - 1}", flush=True)
                        self.start_task = asyncio.create_task(self.start_layers(message))
                    elif message.get("type") == "petals_stop":
                        self.control.stop(message.get("job_id"))
                        self.current_job = None
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                self.socket = None

    async def close(self, api_token):
        self.control.stop()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.node_id:
            try:
                await asyncio.to_thread(call, f"/api/seeders/{self.node_id}/credential", api_token,
                                        None, "DELETE")
            except Exception as exc:
                print(f"Could not revoke temporary provider {self.index}: {exc}", flush=True)


async def main():
    values = secrets_from_env()
    api_token = values["COMPUTETORRENT_API_TOKEN"]
    providers = [LocalProvider(0, values["COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN"]),
                 LocalProvider(1, values["COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN"])]
    job_id = None
    try:
        status = await asyncio.to_thread(call, "/api/distributed/status", api_token)
        if status["status"] != "ready":
            raise RuntimeError("Petals gateway is not ready")
        for provider in providers:
            await provider.enroll()
            provider.task = asyncio.create_task(provider.run())
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            status = await asyncio.to_thread(call, "/api/distributed/status", api_token)
            if sum(p.get("layer_ready", False) for p in status["providers"]) >= 2:
                break
            await asyncio.sleep(2)
        else:
            raise RuntimeError("Temporary providers did not become ready")
        recipe = {"model_id": "bigscience/bloom-560m", "revision": "main",
                  "prompt": "Hello", "max_new_tokens": 2, "min_peers": 2,
                  "max_peers": 2, "benchmark": False}
        job = await asyncio.to_thread(call, "/api/distributed/jobs", api_token,
                                      {"format": "json", "content": json.dumps(recipe)}, "POST")
        job_id = job["id"]
        print("Submitted real two-provider inference", flush=True)
        deadline = time.monotonic() + 1800
        previous = None
        while time.monotonic() < deadline:
            job = await asyncio.to_thread(call, "/api/distributed/jobs/" + job_id, api_token)
            if job["status"] != previous:
                previous = job["status"]
                print("Job status:", previous, flush=True)
                for node, stage in (job.get("stage_status") or {}).items():
                    print("  peer", node[-8:], stage.get("status"), flush=True)
            if job["status"] in {"completed", "failed", "cancelled"}:
                if job["status"] != "completed":
                    raise RuntimeError(job.get("error") or job["status"])
                receipt = job.get("receipt") or {}
                if not (receipt.get("verification", {}).get("passed") and receipt.get("canary", {}).get("passed")):
                    raise RuntimeError("Job completed without passing boundary and canary checks")
                print("Real inference, boundary replay, and canary completed", flush=True)
                print("Generated tokens:", job["metrics"]["generated_tokens"], flush=True)
                return
            await asyncio.sleep(5)
        raise TimeoutError("Two-provider inference exceeded the thirty-minute deadline")
    finally:
        if job_id:
            try:
                await asyncio.to_thread(call, "/api/distributed/jobs/" + job_id, api_token, None, "DELETE")
            except Exception:
                pass
        for provider in providers:
            await provider.close(api_token)


if __name__ == "__main__":
    asyncio.run(main())
