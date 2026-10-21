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
from pydantic import BaseModel, StrictStr
from xml.etree import ElementTree

CATALOG = {
    "bigscience/bloom-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOM 560M"},
    "bigscience/bloomz-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOMZ 560M · instructions"},
}


def parse_manifest(content, format="json"):
    if not isinstance(content, str) or len(content.encode()) > 65536:
        raise ValueError("Upload a JSON or XML manifest smaller than 64 KiB")
    if format == "json":
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
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    elif format == "xml":
        if re.search(r"<!DOCTYPE|<!ENTITY", content, re.I):
            raise ValueError("XML DTDs and entities are not supported")
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise ValueError(f"Invalid XML data: {exc}") from exc
        if root.tag != "inference" or root.attrib:
            raise ValueError("XML root must be <inference> without attributes")
        value = {}
        for child in root:
            if child.tag in value or child.attrib or len(child):
                raise ValueError("Use unique, flat XML fields without attributes")
            value[child.tag] = child.text or ""
        for key in ("max_new_tokens", "min_peers", "max_peers"):
            if key in value:
                try:
                    value[key] = int(value[key])
                except ValueError as exc:
                    raise ValueError(f"{key} must be an integer") from exc
        if "benchmark" in value:
            if value["benchmark"].strip().lower() not in {"true", "false"}:
                raise ValueError("benchmark must be true or false")
            value["benchmark"] = value["benchmark"].strip().lower() == "true"
    else:
        raise ValueError("Choose JSON or XML")
    allowed_keys = {"model_id", "revision", "prompt", "max_new_tokens", "min_peers", "max_peers", "benchmark"}
    if not isinstance(value, dict) or set(value) - allowed_keys:
        raise ValueError(f"Allowed fields: {', '.join(sorted(allowed_keys))}")
    model_id = value.get("model_id")
    if model_id not in CATALOG:
        raise ValueError("This Petals pilot supports bigscience/bloom-560m and bigscience/bloomz-560m; other architectures need an implemented runtime adapter")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Prompt must contain 1–4000 characters")
    revision = value.get("revision", "main")
    if not isinstance(revision, str) or not re.fullmatch(r"main|[a-f0-9]{40}", revision):
        raise ValueError("Revision must be main or an immutable 40-character commit SHA")
    for name, default, lo, hi in (("max_new_tokens", 32, 1, 128), ("min_peers", 2, 2, 8), ("max_peers", 8, 2, 8)):
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


def resolve_revision(spec):
    url = f"https://huggingface.co/api/models/{spec['model_id']}/revision/{spec['revision']}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            metadata = json.load(response)
    except Exception as exc:
        raise RuntimeError(f"Could not resolve model revision from Hugging Face: {exc}") from exc
    sha = metadata.get("sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise RuntimeError("Hugging Face returned no immutable model revision")
    return {**spec, "revision": sha, **CATALOG[spec["model_id"]]}



def placement(spec, peers):
    """Allocate only capacity that a current, opted-in provider actually reported."""
    candidates = []
    for node, info in peers.items():
        profile = info.get("profile", {})
        if info.get("busy") or info.get("state") in {"paused", "offline", "busy"} or profile.get("canary_quarantined"):
            continue
        if profile.get("petals_enabled") is not True or profile.get("docker_ok") is not True or profile.get("petals_protocol_version") != 1:
            continue
        try:
            ram = min(float(profile["free_ram_gb"]), float(profile["memory_limit_gb"]))
            disk = float(profile["disk_free_gb"])
        except (KeyError, TypeError, ValueError):
            continue
        if ram < 2 or disk < 4:
            continue
        cuda = bool(profile.get("petals_cuda_ready") and float(profile.get("gpu_free_mib") or 0) >= 2048)
        memory = min(ram * 1024, float(profile.get("gpu_free_mib") or 0)) if cuda else ram * 1024
        per_block = math.ceil(12 * spec["hidden_size"] ** 2 * 4 / 2**20) + 24
        cap = max(0, min(spec["layers"], int((memory * 0.75 - 768) / per_block)))
        if cap:
            candidates.append({"node_id": node, "capacity": cap, "device": "cuda" if cuda else "cpu", "count": 0})
    
    candidates.sort(key=lambda x: (-x["capacity"], x["node_id"]))
    candidates = candidates[:spec.get("max_peers", 8)]
    min_p = spec.get("min_peers", 2)
    if len(candidates) < min_p:
        raise ValueError(f"Need at least {min_p} connected layer provider(s), but found {len(candidates)}")
    
    total_cap = sum(c["capacity"] for c in candidates)
    if total_cap < spec["layers"]:
        raise ValueError(f"Connected providers can host {total_cap} of {spec['layers']} layers; free more RAM or connect another capable PC")
    
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
        providers = []
        for node, info in manager.seeder_info.items():
            if node not in manager.active_seeders:
                continue
            profile = info.get("profile", {})
            reason = None
            if profile.get("petals_protocol_version") != 1:
                reason = "Install the latest provider app and reconnect"
            elif profile.get("petals_enabled") is not True:
                reason = "Enable Share model layers in the provider app"
            elif profile.get("docker_ok") is not True:
                reason = "Start Docker Desktop on this provider"
            elif info.get("busy") or info.get("state") in {"paused", "busy"}:
                reason = "Provider is busy or paused"
            elif float(profile.get("free_ram_gb") or 0) < 2 or float(profile.get("disk_free_gb") or 0) < 4:
                reason = "Needs at least 2 GB free RAM and 4 GB free disk"
            providers.append({"node_id": node, **info, "layer_ready": reason is None, "layer_reason": reason,
                              "runtime_installed": bool(profile.get("petals_image_ready"))})
        return {**state, "providers": providers}

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
            job.update(plan=plan, status="loading", prefix="ct-" + job["id"],
                       stage_status={stage["node_id"]: {"status": "assigning"} for stage in plan})
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
                job["stage_status"][stage["node_id"]] = {"status": "sent"}
                store.save(job)
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
                        job["stage_status"][stage["node_id"]] = p
                        if p.get("error"):
                            raise RuntimeError(f"Provider {stage['node_id']}: {p['error']}")
                        if p.get("peer_id"):
                            job["stage_status"][stage["node_id"]] = {**p, "status": "serving"}
                            ready.append({**stage, "peer_id": p["peer_id"]})
                if len(ready) == len(plan):
                    job["plan"] = ready
                    break
                store.save(job)
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
            placement({**spec, **CATALOG[spec["model_id"]]},
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
