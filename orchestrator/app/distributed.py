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
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Union

CATALOG = {
    "bigscience/bloom-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOM 560M"},
    "bigscience/bloomz-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOMZ 560M · instructions"},
}


def parse_manifest(content, format="json"):
    if isinstance(content, dict):
        value = content
    elif isinstance(content, str):
        if len(content.encode()) > 65536:
            raise ValueError("Upload a JSON manifest smaller than 64 KiB")
        def unique(pairs):
            result = {}
            for key, val in pairs:
                if key in result:
                    raise ValueError(f"Duplicate field: {key}")
                result[key] = val
            return result
        try:
            value = json.loads(content, object_pairs_hook=unique)
        except Exception as exc:
            raise ValueError(f"Invalid JSON data: {exc}")
    else:
        raise ValueError("Upload a JSON manifest smaller than 64 KiB")
    allowed_keys = {"model_id", "revision", "prompt", "max_new_tokens", "min_peers", "max_peers", "benchmark", "layers", "hidden_size"}
    if not isinstance(value, dict) or set(value) - allowed_keys:
        raise ValueError(f"Allowed JSON fields: {', '.join(sorted(allowed_keys))}")
    model_id = str(value.get("model_id", "")).strip()
    if not model_id:
        raise ValueError("model_id is required in JSON")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Prompt must contain 1–4000 characters")
    revision = str(value.get("revision", "main")).strip() or "main"
    for name, default, lo, hi in (("max_new_tokens", 32, 1, 512), ("min_peers", 1, 1, 8), ("max_peers", 8, 1, 8)):
        val = value.get(name, default)
        if type(val) is not int or not lo <= val <= hi:
            raise ValueError(f"{name} must be an integer from {lo} to {hi}")
        value[name] = val
    if value["max_peers"] < value["min_peers"]:
        raise ValueError("max_peers must be at least min_peers")
    if type(value.get("benchmark", False)) is not bool:
        raise ValueError("benchmark must be true or false")
    value["benchmark"] = value.get("benchmark", False)
    return {**value, "model_id": model_id, "revision": revision, "prompt": prompt.strip()}


KNOWN_REVISIONS = {
    ("bigscience/bloom-560m", "main"): "ac2ae5fab2ce3f9f40dc79b5ca9f637430d24971",
    ("bigscience/bloomz-560m", "main"): "a2845d7e13dd12efae154a9f1c63fcc2e0cc4b05",
}


def resolve_revision(spec):
    model_id = spec["model_id"]
    revision = str(spec.get("revision", "main")).strip() or "main"
    meta = CATALOG.get(model_id, {})
    layers = int(spec.get("layers") or meta.get("layers", 24))
    hidden_size = int(spec.get("hidden_size") or meta.get("hidden_size", 1024))
    label = spec.get("label") or meta.get("label", model_id.split("/")[-1])

    known = KNOWN_REVISIONS.get((model_id, revision))
    sha = known or revision
    if not known and re.fullmatch(r"[a-f0-9]{40}", revision):
        sha = revision
    elif not known:
        try:
            url = f"https://huggingface.co/api/models/{model_id}/revision/{revision}"
            with urllib.request.urlopen(url, timeout=5) as response:
                metadata = json.load(response)
            s = metadata.get("sha", "")
            if re.fullmatch(r"[a-f0-9]{40}", s):
                sha = s
        except Exception:
            pass
        if model_id not in CATALOG and "layers" not in spec:
            try:
                cfg_url = f"https://huggingface.co/{model_id}/raw/{sha}/config.json"
                with urllib.request.urlopen(cfg_url, timeout=5) as resp:
                    cfg = json.load(resp)
                    layers = cfg.get("num_hidden_layers", cfg.get("n_layer", cfg.get("num_layers", layers)))
                    hidden_size = cfg.get("hidden_size", cfg.get("d_model", cfg.get("n_embd", hidden_size)))
            except Exception:
                pass
    return {**spec, "revision": sha, "layers": layers, "hidden_size": hidden_size, "label": label}


def placement(spec, peers):
    """Distribute model layers dynamically across connected systems according to their capacities."""
    candidates = []
    for node, info in peers.items():
        profile = info.get("profile", {})
        if info.get("busy") or info.get("state") in {"paused", "offline"} or profile.get("canary_quarantined"):
            continue
        if profile.get("petals_enabled") is False or profile.get("docker_ok") is False:
            continue
        
        # Calculate available memory
        ram = float(profile.get("free_ram_gb") or 0)
        if ram < 1.0:
            ram = max(float(profile.get("RAM") or 4) * 0.6, 2.0)
        if profile.get("memory_limit_gb"):
            try:
                ram = min(ram, float(profile["memory_limit_gb"]))
            except (ValueError, TypeError):
                pass
        
        cuda = bool(profile.get("petals_cuda_ready") or profile.get("CUDA"))
        memory = min(ram * 1024, float(profile.get("gpu_free_mib") or 0)) if (cuda and profile.get("gpu_free_mib")) else ram * 1024
        per_block = math.ceil(12 * spec["hidden_size"] ** 2 * 4 / 2**20) + 24
        cap = max(1, min(spec["layers"], int((memory * 0.85) / per_block)))
        candidates.append({"node_id": node, "capacity": cap, "device": "cuda" if cuda else "cpu", "count": 0})
    
    candidates.sort(key=lambda x: (-x["capacity"], x["node_id"]))
    max_p = spec.get("max_peers", 8)
    candidates = candidates[:max_p]
    min_p = spec.get("min_peers", 1)
    if len(candidates) < min_p:
        raise ValueError(f"Need at least {min_p} connected layer provider(s), but found {len(candidates)}")
    
    # Ensure total candidate capacity covers all layers
    total_cap = sum(c["capacity"] for c in candidates)
    if total_cap < spec["layers"]:
        for c in candidates:
            c["capacity"] = max(c["capacity"], math.ceil(spec["layers"] / len(candidates)))
    
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
    content: Union[str, dict, Any]
    format: str = "json"


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
                    # Raw prompt remains at the coordinator; providers see model metadata only.
                    "spec": {"model_id": job["spec"]["model_id"], "revision": job["spec"]["revision"]},
                    "stage": stage, "prefix": job["prefix"],
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
                profile = manager.seeder_info.get(stage["node_id"], {}).get("profile", {})
                if profile.get("petals", {}).get("job_id") == job["id"]:
                    profile["petals"] = {"status": "idle"}
            store.save(job)
            running.pop(job["id"], None)

    @router.post("/jobs", status_code=202)
    async def submit(upload: Upload):
        if running:
            raise HTTPException(409, "One distributed job at a time is supported by this small-model workspace")
        try:
            spec = parse_manifest(upload.content, upload.format)
            model_meta = CATALOG.get(spec["model_id"], {"layers": spec.get("layers", 24), "hidden_size": spec.get("hidden_size", 1024), "label": spec.get("label", spec["model_id"].split("/")[-1])})
            placement({**spec, **model_meta},
                      {n: i for n, i in manager.seeder_info.items() if n in manager.active_seeders})
        except ValueError as exc:
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
