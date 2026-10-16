"""Local Petals job control. Provider credentials remain in the existing API."""
import asyncio
import json
import math
import os
import re
import sqlite3
import time
import urllib.request
import uuid
from pathlib import Path
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictStr

CATALOG = {
    "bigscience/bloom-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOM 560M"},
    "bigscience/bloomz-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOMZ 560M · instructions"},
}


def parse_manifest(content, format):
    if not isinstance(content, str) or len(content.encode()) > 65536:
        raise ValueError("Upload a JSON/XML manifest smaller than 64 KiB")
    if format == "xml":
        if re.search(r"<!|<\?", content.replace('<?xml version="1.0"?>', ''), re.I):
            raise ValueError("XML declarations, DTDs and entities are not supported")
        root = ElementTree.fromstring(content)
        if root.tag != "inference" or root.attrib:
            raise ValueError("XML root must be <inference> without attributes")
        value = {}
        for child in root:
            if child.tag in value or child.attrib or len(child):
                raise ValueError("Use unique, flat XML fields without attributes")
            value[child.tag] = child.text or ""
        for key in ("max_new_tokens", "min_peers"):
            if key in value:
                value[key] = int(value[key])
    elif format == "json":
        def unique(pairs):
            result = {}
            for key, val in pairs:
                if key in result:
                    raise ValueError(f"Duplicate field: {key}")
                result[key] = val
            return result
        value = json.loads(content, object_pairs_hook=unique)
    else:
        raise ValueError("Choose json or xml")
    if not isinstance(value, dict) or set(value) - {"model_id", "revision", "prompt", "max_new_tokens", "min_peers"}:
        raise ValueError("Allowed fields: model_id, revision, prompt, max_new_tokens, min_peers")
    if value.get("model_id") not in CATALOG:
        raise ValueError("Small-model MVP supports bigscience/bloom-560m and bigscience/bloomz-560m")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Prompt must contain 1–4000 characters")
    revision = value.get("revision", "main")
    if not isinstance(revision, str) or not re.fullmatch(r"main|[a-f0-9]{40}", revision):
        raise ValueError("Revision must be main or an immutable 40-character commit SHA")
    for name, default, lo, hi in (("max_new_tokens", 32, 1, 128), ("min_peers", 2, 2, 8)):
        val = value.get(name, default)
        if type(val) is not int or not lo <= val <= hi:
            raise ValueError(f"{name} must be an integer from {lo} to {hi}")
        value[name] = val
    return {**value, "revision": revision, "prompt": prompt.strip()}


def resolve_revision(spec):
    url = f"https://huggingface.co/api/models/{spec['model_id']}/revision/{spec['revision']}"
    with urllib.request.urlopen(url, timeout=30) as response:
        metadata = json.load(response)
    sha = metadata.get("sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Model hub returned no immutable revision")
    return {**spec, "revision": sha, **CATALOG[spec["model_id"]]}


def placement(spec, peers):
    """Conservative FP32 BLOOM budget: weights, KV cache and runtime reserve."""
    candidates = []
    for node, info in peers.items():
        profile = info.get("profile", {})
        if info.get("busy") or info.get("state") in {"paused", "offline"} or profile.get("canary_quarantined"):
            continue
        if not profile.get("petals_enabled") or not profile.get("petals_image_ready") or not profile.get("docker_ok"):
            continue
        ram = min(float(profile.get("free_ram_gb", 0)), float(profile.get("memory_limit_gb", 0)))
        cuda = bool(profile.get("petals_cuda_ready"))
        memory = min(ram * 1024, float(profile.get("gpu_free_mib", 0))) if cuda else ram * 1024
        # 12H^2 FP32 parameters + conservative activation/KV allowance per block.
        per_block = math.ceil(12 * spec["hidden_size"] ** 2 * 4 / 2**20) + 24
        cap = max(0, min(spec["layers"] - 1, int((memory * .75 - 768) / per_block)))
        if cap:
            candidates.append({"node_id": node, "capacity": cap, "device": "cuda" if cuda else "cpu", "count": 0})
    candidates.sort(key=lambda x: (-x["capacity"], x["node_id"]))
    candidates = candidates[:8]
    if len(candidates) < spec["min_peers"] or sum(c["capacity"] for c in candidates) < spec["layers"]:
        raise ValueError("Need enough free RAM/VRAM across at least the requested number of opted-in, runtime-ready providers")
    for _ in range(spec["layers"]):
        c = min((c for c in candidates if c["count"] < c["capacity"]), key=lambda c: c["count"] / c["capacity"])
        c["count"] += 1
    plan, start = [], 0
    for c in candidates:
        if c["count"]:
            plan.append({"node_id": c["node_id"], "start": start, "end": start + c["count"], "device": c["device"]})
            start += c["count"]
    return plan


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        for job in self.all():
            if job["status"] not in {"completed", "failed", "cancelled"}:
                job.update(status="failed", error="Coordinator restarted; resubmit to allocate fresh peer sessions")
                self.save(job)

    def db(self):
        return sqlite3.connect(self.path, timeout=15)

    def save(self, job):
        job["updated_at"] = time.time()
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?)", (job["id"], json.dumps(job)))

    def all(self):
        with self.db() as db:
            rows = db.execute("SELECT body FROM jobs ORDER BY rowid DESC LIMIT 100").fetchall()
        return [json.loads(r[0]) for r in rows]

    def get(self, id):
        with self.db() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown distributed job")
        return json.loads(row[0])


class Upload(BaseModel):
    content: StrictStr
    format: StrictStr = "json"


def install(app, manager):
    router = APIRouter(prefix="/api/distributed")
    store = Store(Path(os.getenv("COMPUTETORRENT_JOB_DATA", "runtime/distributed")) / "jobs.sqlite3")
    running = {}

    def gateway(path, body=None, timeout=15):
        url = os.getenv("COMPUTETORRENT_PETALS_URL", "http://127.0.0.1:8002").rstrip("/") + path
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + os.getenv("COMPUTETORRENT_API_TOKEN", ""), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)

    @router.get("/catalog")
    async def catalog():
        return [{"model_id": k, **v} for k, v in CATALOG.items()]

    @router.get("/status")
    async def status():
        try:
            state = await asyncio.to_thread(gateway, "/health")
        except Exception:
            state = {"status": "unavailable", "detail": "Start the Petals gateway with the local Compose stack"}
        return {**state, "providers": [{"node_id": n, **i} for n, i in manager.seeder_info.items() if n in manager.active_seeders]}

    @router.get("/jobs")
    async def jobs():
        return store.all()

    @router.get("/jobs/{id}")
    async def job(id: str):
        return store.get(id)

    async def run(job):
        try:
            job.update(status="resolving")
            store.save(job)
            job["spec"] = await asyncio.to_thread(resolve_revision, job["spec"])
            health = await asyncio.to_thread(gateway, "/health")
            if health.get("status") != "ready" or not health.get("bootstrap"):
                raise RuntimeError("Petals DHT gateway is not ready")
            peers = {n: i for n, i in manager.seeder_info.items() if n in manager.active_seeders}
            plan = placement(job["spec"], peers)
            job.update(plan=plan, status="loading", prefix="ct-" + job["id"])
            store.save(job)
            for stage in plan:
                manager.seeder_info[stage["node_id"]]["busy"] = True
                ok = await manager.send_to_seeder({"type": "petals_start", "job_id": job["id"],
                    "spec": job["spec"], "stage": stage, "prefix": job["prefix"],
                    "bootstrap": health["bootstrap"]}, stage["node_id"])
                if not ok:
                    raise RuntimeError("Provider disconnected before layer assignment")
            # Never interpret container startup as model readiness. The gateway
            # checks actual DHT layer coverage before opening inference sessions.
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                ready = []
                for stage in plan:
                    if stage["node_id"] not in manager.active_seeders:
                        raise RuntimeError("A layer provider disconnected; resubmit after reconnecting")
                    p = manager.seeder_info[stage["node_id"]].get("profile", {}).get("petals", {})
                    if p.get("job_id") == job["id"]:
                        if p.get("error"):
                            raise RuntimeError(f"Provider {stage['node_id']}: {p['error']}")
                        if p.get("peer_id"):
                            ready.append({**stage, "peer_id": p["peer_id"]})
                if len(ready) == len(plan):
                    job["plan"] = ready
                    break
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Timed out waiting for provider model downloads/startup (15 minutes)")
            job["status"] = "running"
            store.save(job)
            await asyncio.to_thread(gateway, "/jobs", job)
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                response = await asyncio.to_thread(gateway, "/jobs/" + job["id"])
                if response["status"] in {"completed", "failed"}:
                    job.update(response)
                    break
                job["status"] = response["status"]
                store.save(job)
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Inference exceeded its 30-minute deadline")
        except asyncio.CancelledError:
            job.update(status="cancelled", error="Stopped by operator")
        except Exception as exc:
            job.update(status="failed", error=str(exc)[:1000])
        finally:
            try:
                await asyncio.to_thread(gateway, "/cancel", {"id": job["id"]})
            except Exception:
                pass
            for stage in job.get("plan", []):
                await manager.send_to_seeder({"type": "petals_stop", "job_id": job["id"]}, stage["node_id"])
                manager.seeder_info.get(stage["node_id"], {})["busy"] = False
            store.save(job)
            running.pop(job["id"], None)

    @router.post("/jobs", status_code=202)
    async def submit(upload: Upload):
        if running:
            raise HTTPException(409, "One distributed job at a time is supported by this small-model workspace")
        try:
            spec = parse_manifest(upload.content, upload.format)
            placement({**spec, **CATALOG[spec["model_id"]]},
                      {n: i for n, i in manager.seeder_info.items() if n in manager.active_seeders})
        except (ValueError, ElementTree.ParseError) as exc:
            raise HTTPException(422, str(exc)) from exc
        job = {"id": uuid.uuid4().hex, "spec": spec, "status": "queued", "created_at": time.time()}
        store.save(job)
        running[job["id"]] = asyncio.create_task(run(job))
        return job

    @router.delete("/jobs/{id}")
    async def cancel(id: str):
        job = store.get(id)
        if id in running:
            running[id].cancel()
        return {"id": id, "status": "cancelling" if id in running else job["status"]}

    @app.on_event("shutdown")
    async def shutdown():
        tasks = list(running.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app.include_router(router)
