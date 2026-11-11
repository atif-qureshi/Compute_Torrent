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
from typing import Union, Dict, Any
from xml.etree import ElementTree

CATALOG = {
    "bigscience/bloom-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOM 560M · Base completion"},
    "bigscience/bloomz-560m": {"layers": 24, "hidden_size": 1024, "label": "BLOOMZ 560M · Recommended Q&A"},
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0": {"layers": 22, "hidden_size": 2048, "label": "TinyLlama 1.1B Chat · High accuracy"},
}
PETALS_NETWORK_REVISION = 2


def parse_manifest(content, format="json"):
    if isinstance(content, dict):
        value = dict(content)
    elif isinstance(content, str):
        if len(content.encode("utf-8")) > 65536:
            raise ValueError("Upload a JSON or XML manifest smaller than 64 KiB")
        if format == "json":
            try:
                value = json.loads(content)
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
        else:
            raise ValueError("Choose JSON or XML")
    else:
        raise ValueError("Upload a JSON or XML manifest")

    for key in ("max_new_tokens", "min_peers", "max_peers", "layers", "hidden_size"):
        if key in value:
            try:
                value[key] = int(value[key])
            except ValueError as exc:
                raise ValueError(f"{key} must be an integer") from exc
    if "benchmark" in value:
        if isinstance(value["benchmark"], str):
            value["benchmark"] = value["benchmark"].strip().lower() == "true"
        elif not isinstance(value["benchmark"], bool):
            value["benchmark"] = False

    allowed_keys = {"model_id", "revision", "prompt", "max_new_tokens", "min_peers", "max_peers", "benchmark", "layers", "hidden_size", "label", "weights_bytes"}
    if not isinstance(value, dict) or set(value) - allowed_keys:
        raise ValueError(f"Allowed fields: {', '.join(sorted(allowed_keys))}")
    wb = value.pop("weights_bytes", None)
    if wb is not None and (isinstance(wb, bool) or not isinstance(wb, int) or wb <= 0):
        raise ValueError("weights_bytes must be a positive integer")
    model_id = value.get("model_id")
    if not model_id:
        raise ValueError("model_id field is required")
    if model_id not in CATALOG:
        raise ValueError(f"Unsupported pilot model: {model_id}. Supported models: {', '.join(CATALOG)}")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Prompt must contain 1–4000 characters")
    revision = value.get("revision", "main")
    if not isinstance(revision, str) or not re.fullmatch(r"main|[a-f0-9]{40}", revision):
        raise ValueError("Revision must be main or an immutable 40-character commit SHA")
    for name, default, lo, hi in (("max_new_tokens", 32, 1, 128), ("min_peers", 1, 1, 8), ("max_peers", 8, 2, 8)):
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
    url = f"https://huggingface.co/api/models/{spec['model_id']}/revision/{spec['revision']}?blobs=true"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            metadata = json.load(response)
    except Exception as exc:
        raise RuntimeError(f"Could not resolve model revision from Hugging Face: {exc}") from exc
    sha = metadata.get("sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise RuntimeError("Hugging Face returned no immutable model revision")
    siblings = metadata.get("siblings") or []
    st_sizes = [int(s["size"]) for s in siblings if isinstance(s, dict) and str(s.get("rfilename", "")).endswith(".safetensors") and isinstance(s.get("size"), int)]
    bin_sizes = [int(s["size"]) for s in siblings if isinstance(s, dict) and str(s.get("rfilename", "")).endswith(".bin") and isinstance(s.get("size"), int)]
    weights_bytes = sum(st_sizes) if st_sizes else sum(bin_sizes)
    return {**spec, "revision": sha, **CATALOG[spec["model_id"]], "weights_bytes": weights_bytes}



def provider_capacity(spec, info, *, use_native=True):
    """Use the same current capability checks for initial and replacement stages."""
    profile = info.get("profile", {})
    if (info.get("busy") or info.get("state") in {"paused", "offline", "busy"}
            or profile.get("petals_enabled") is not True or profile.get("docker_ok") is not True
            or profile.get("petals_protocol_version") != 1
            or profile.get("petals_network_revision") != PETALS_NETWORK_REVISION):
        return 0, "cpu"
    try:
        values = [float(profile.get(key, 0)) for key in
                  ("free_ram_gb", "memory_limit_gb", "disk_free_gb", "gpu_free_mib")]
        if any(not math.isfinite(v) or v < 0 for v in values):
            return 0, "cpu"
        ram, limit, disk, gpu = values
        ram = min(ram, limit)
        if ram < 0.4 or disk < 2:
            return 0, "cpu"
        cuda = bool(profile.get("petals_cuda_ready") and gpu >= 2048)
        # In Petals, CUDA servers host blocks directly in GPU VRAM.
        # System RAM only needs to be sufficient for buffers and host processes.
        # For CPU servers, blocks are hosted in system RAM.
        memory = gpu if cuda else ram * 1024
        per_block = math.ceil(12 * spec["hidden_size"] ** 2 * 4 / 2**20) + 24
        usable_memory = max(0.0, memory * 0.90 - 128) if cuda else max(0.0, memory * 0.90 - 256)
        cap = max(0, min(spec["layers"], int(usable_memory / per_block)))
        native = native_capacity(spec, info) if use_native else None
        if native and native["device"] == ("cuda" if cuda else "cpu"):
            bytes_per_block = native["block_bytes"] + native["cache_bytes_per_block"]
            current_budget = max(0, memory * 2**20 - native["reserve_bytes"])
            cap = max(0, min(spec["layers"], int(native["capacity_layers"]), int(current_budget / bytes_per_block)))
        return cap, "cuda" if cuda else "cpu"
    except (TypeError, ValueError, OverflowError):
        return 0, "cpu"


def native_capacity(spec, info):
    record = info.get("profile", {}).get("petals_capacity", {})
    if (not isinstance(record, dict) or record.get("model_id") != spec.get("model_id")
            or record.get("revision") != spec.get("revision") or record.get("source") != "petals-native-v1"
            or record.get("dtype") != "float32" or record.get("quant_type") != "none"):
        return None
    try:
        profile = info.get("profile", {})
        expected_device = "cuda" if profile.get("petals_cuda_ready") and float(profile.get("gpu_free_mib", 0)) >= 2048 else "cpu"
        if record.get("device") != expected_device:
            return None
        if not -300 <= time.time() - float(record["measured_at"]) <= 3600:
            return None
        for key in ("block_bytes", "cache_bytes_per_block", "available_bytes", "reserve_bytes", "capacity_layers", "inference_rps"):
            value = float(record[key])
            if not math.isfinite(value) or value < 0:
                return None
        if record["block_bytes"] <= 0 or record["inference_rps"] <= 0:
            return None
        return record
    except (KeyError, TypeError, ValueError):
        return None


def provider_weight(spec, info, cap, device):
    """Uncapped memory capacity for cold starts, not invented GPU speed ratios.

    Native per-block inference_rps is used instead when all candidates have
    matching fresh Petals measurements. Mixing those units is forbidden.
    """
    profile = info.get("profile", {})
    memory = float(profile.get("gpu_free_mib", 0)) if device == "cuda" else min(
        float(profile.get("free_ram_gb", 0)), float(profile.get("memory_limit_gb", 0))) * 1024
    per_block = math.ceil(12 * spec["hidden_size"] ** 2 * 4 / 2**20) + 24
    reserve = 128 if device == "cuda" else 256
    return max(0.1, (memory * .90 - reserve) / per_block)


def replacement_stage(spec, stage, peers, assigned_nodes):
    """Pick only a spare that can host the entire interrupted contiguous range."""
    required = stage["end"] - stage["start"]
    candidates = []
    for node, info in peers.items():
        if node in assigned_nodes:
            continue
        capacity, device = provider_capacity(spec, info)
        if capacity >= required:
            candidates.append((capacity, node, device))
    if not candidates:
        return None
    _, node, device = min(candidates)
    return {**stage, "node_id": node, "device": device}


def baseline_placement(spec, peers):
    """
    Allocate model layers according to Petals capacity-aware load balancing.
    Peers with higher capacity (e.g. GPUs, more VRAM/RAM) receive proportionally
    more layers. Weaker devices receive smaller segments, avoiding equal-split bottlenecks.
    """
    candidates = []
    for node, info in peers.items():
        cap, device = provider_capacity(spec, info)
        if cap > 0:
            weight = provider_weight(spec, info, cap, device)
            candidates.append({
                "node_id": node,
                "capacity": cap,
                "device": device,
                "weight": weight,
                "count": 0
            })

    measured = {c["node_id"]: native_capacity(spec, peers[c["node_id"]]) for c in candidates}
    if candidates and all(measured.values()):
        for c in candidates:
            c["weight"] = measured[c["node_id"]]["inference_rps"]
    # All weights now have the same units: native per-block rate or memory capacity.
    # Sort candidates by capacity weight (most capable peers first)
    candidates.sort(key=lambda x: (-x["weight"], -x["capacity"], x["node_id"]))
    candidates = candidates[:spec.get("max_peers", 8)]
    min_p = spec.get("min_peers", 2)
    if len(candidates) < min_p:
        raise ValueError(f"Need at least {min_p} connected layer provider(s), but found {len(candidates)}")
    
    total_cap = sum(c["capacity"] for c in candidates)
    if total_cap < spec["layers"]:
        raise ValueError(f"Connected providers can host {total_cap} of {spec['layers']} layers; free more RAM or connect another capable PC")
    
    total_layers = spec["layers"]
    num_candidates = len(candidates)

    # 1. Base allocation: every participating candidate gets at least 1 layer
    # if total_layers >= num_candidates
    if total_layers >= num_candidates:
        for c in candidates:
            c["count"] = 1
        remaining = total_layers - num_candidates
    else:
        remaining = total_layers

    # 2. Distribute remaining layers proportionally according to capacity weight:
    # Each step selects the candidate whose current allocation is furthest below
    # its capacity-weighted fair share (arg min count / weight), subject to physical capacity cap.
    for _ in range(remaining):
        eligible = [c for c in candidates if c["count"] < c["capacity"]]
        if not eligible:
            raise ValueError(f"Provider memory limits prevent allocating all {total_layers} layers")
        c = min(eligible, key=lambda c: (c["count"] / c["weight"], -c["capacity"]))
        c["count"] += 1
    
    # 3. Create contiguous pipeline stages [start, end)
    plan, start = [], 0
    for c in candidates:
        if c["count"] > 0:
            plan.append({
                "node_id": c["node_id"],
                "start": start,
                "end": start + c["count"],
                "device": c["device"],
                "capacity_layers": c["capacity"],
                "allocation_weight": round(c["weight"], 4),
                "allocation_basis": "native_inference_rps" if candidates and all(measured.values()) else "estimated_memory_capacity"
            })
            start += c["count"]

    return plan


def placement(spec, peers, *, calibration=None, policy=None, diagnostics=None):
    """Auto uses Sun only with valid native and activation-path measurements."""
    from sun_runtime import sun_plan, CalibrationUnavailable
    from sun_optimizer import Infeasible
    policy = policy or os.getenv('COMPUTETORRENT_PLANNER', 'auto')
    if policy not in {'auto', 'baseline', 'sun'}:
        raise ValueError('COMPUTETORRENT_PLANNER must be auto, baseline or sun')
    note = diagnostics if diagnostics is not None else {}
    if policy != 'baseline' and calibration is not None:
        try:
            try:
                baseline = baseline_placement(spec, peers)
            except ValueError:
                baseline = None
            plan, evidence = sun_plan(spec, peers, provider_capacity, native_capacity, calibration,
                                      baseline_plan=baseline)
            note.update(evidence, predicted_plan_valid=True, requested_policy=policy)
            if (policy == 'auto' and baseline is not None
                    and evidence['estimated_per_token_seconds'] >= evidence['baseline_estimated_per_token_seconds']):
                note.update(algorithm='baseline',candidate_algorithm=evidence['algorithm'],
                            fallback_reason='Sun candidate does not improve the baseline under the same measured cost model')
                return baseline
            return plan
        except (CalibrationUnavailable, Infeasible) as error:
            if policy == 'sun':
                raise ValueError('Sun planner prerequisites: ' + str(error)) from error
            note.update(algorithm='baseline',fallback_reason=str(error),requested_policy=policy)
    elif policy == 'sun':
        raise ValueError('Sun planner requires measured activation calibration')
    else:
        note.update(algorithm='baseline',requested_policy=policy)
    return baseline_placement(spec, peers)


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS optimizer_calibration (key TEXT PRIMARY KEY, body TEXT NOT NULL)")
        for job in self.all():
            if job["status"] not in {"completed", "failed", "cancelled"}:
                job.update(status="failed", error="Coordinator restarted; resubmit to allocate fresh peer sessions")
                self.save(job)

    def db(self):
        return sqlite3.connect(self.path, timeout=15)

    def save(self, job):
        self.settle_stages(job)
        job["updated_at"] = time.time()
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?)", (job["id"], json.dumps(job)))

    def all(self):
        with self.db() as db:
            rows = db.execute("SELECT body FROM jobs ORDER BY rowid DESC LIMIT 100").fetchall()
        return [self.settle_stages(json.loads(r[0])) for r in rows]

    def calibrations(self):
        with self.db() as db:
            return {key: json.loads(body) for key,body in db.execute('SELECT key,body FROM optimizer_calibration')}

    def save_calibrations(self, records):
        with self.db() as db:
            db.executemany('INSERT OR REPLACE INTO optimizer_calibration VALUES (?, ?)',
                           [(key,json.dumps(value)) for key,value in records.items()])
            # Bound persisted measurement history; old evidence is not routing input.
            for key,body in db.execute('SELECT key,body FROM optimizer_calibration').fetchall():
                if time.time()-json.loads(body).get('measured_at',0)>86400:
                    db.execute('DELETE FROM optimizer_calibration WHERE key=?',(key,))

    @staticmethod
    def settle_stages(job):
        if job.get("status") in {"failed", "cancelled"}:
            for state in job.get("stage_status", {}).values():
                if state.get("status") not in {"failed", "stopped", "completed"}:
                    state.update(last_status=state.get("status"), status="stopped")
        return job

    def get(self, id):
        with self.db() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown distributed job")
        return self.settle_stages(json.loads(row[0]))


class Upload(BaseModel):
    content: Union[str, Dict[str, Any], Any]
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

    stale_stop_sent = {}
    reconcile_task = None

    async def reconcile_stale_sessions():
        sender = getattr(manager, "send_to_seeder", None)
        if not callable(sender):
            return
        now = time.monotonic()
        for node, info in list(manager.seeder_info.items()):
            if node not in manager.active_seeders:
                continue
            profile = info.get("profile", {})
            petals_state = profile.get("petals") if isinstance(profile, dict) else None
            if not isinstance(petals_state, dict):
                continue
            stale_job_id = petals_state.get("job_id")
            petals_status = str(petals_state.get("status") or "").lower()
            if not stale_job_id or stale_job_id in running or petals_status not in {"accepted", "loading", "serving"}:
                continue
            try:
                known = store.get(stale_job_id)
            except Exception:
                known = None
            if not known or known.get("status") not in {"completed", "failed", "cancelled"}:
                continue
            if now - stale_stop_sent.get((node, stale_job_id), 0.0) < 10.0:
                continue
            stale_stop_sent[(node, stale_job_id)] = now
            try:
                await sender({"type": "petals_stop", "job_id": stale_job_id}, node)
            except Exception:
                pass

    @router.get("/status")
    async def status():
        await reconcile_stale_sessions()
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
            if (profile.get("petals_protocol_version") != 1
                    or profile.get("petals_network_revision") != PETALS_NETWORK_REVISION):
                reason = "Install the latest provider app and reconnect"
            elif profile.get("petals_enabled") is not True:
                reason = "Enable Share model layers in the provider app"
            elif profile.get("docker_ok") is not True:
                reason = "Start Docker Desktop on this provider"
            elif info.get("busy") or info.get("state") in {"paused", "busy"}:
                reason = "Provider is busy or paused"
            elif provider_capacity(CATALOG["bigscience/bloom-560m"], info)[0] == 0:
                reason = "No verified layer capacity; refresh RAM, memory limit, disk and GPU telemetry"
            providers.append({"node_id": node, **info, "layer_ready": reason is None, "layer_reason": reason,
                              "runtime_installed": bool(profile.get("petals_image_ready"))})
        return {**state, "providers": providers, "required_network_revision": PETALS_NETWORK_REVISION}

    @router.get("/jobs")
    async def jobs():
        return store.all()

    @router.get("/jobs/{id}")
    async def job(id: str):
        return store.get(id)

    async def profile_capacity(job, peers):
        targets = [n for n, info in peers.items()
                   if info.get("profile", {}).get("petals_capacity_protocol") == 1
                   and provider_capacity(job["spec"], info, use_native=False)[0] > 0][:32]
        if not targets:
            return
        job.update(status="profiling_capacity")
        store.save(job)
        try:
            for node in targets:
                info = manager.seeder_info[node]
                info["capacity_reservation"] = job["id"]
                info.pop("capacity_response", None)
                _, device = provider_capacity(job["spec"], info)
                ok = await manager.send_to_seeder({"type": "petals_capacity", "job_id": job["id"],
                    "spec": {k: job["spec"][k] for k in ("model_id", "revision")}, "device": device}, node)
                if not ok:
                    raise RuntimeError("Provider disconnected before native capacity measurement")
            deadline = time.monotonic() + 3600
            pending = set(targets)
            while pending and time.monotonic() < deadline:
                for node in tuple(pending):
                    if node not in manager.active_seeders:
                        raise RuntimeError("Provider disconnected during native capacity measurement")
                    response = manager.seeder_info[node].get("capacity_response", {})
                    if response.get("job_id") != job["id"]:
                        continue
                    if response.get("error"):
                        raise RuntimeError("Provider capacity measurement failed: " + str(response["error"])[:500])
                    record = native_capacity(job["spec"], manager.seeder_info[node])
                    if record is None:
                        raise RuntimeError("Provider returned invalid or mismatched native capacity data")
                    manager.seeder_info[node].update(state=response.get("state", "idle"), busy=False)
                    pending.remove(node)
                if pending:
                    await asyncio.sleep(1)
            if pending:
                raise RuntimeError("Native capacity probe timed out; check provider runtime/config download")
            job["capacity_measurements"] = {n: native_capacity(job["spec"], manager.seeder_info[n]) for n in targets}
            store.save(job)
        finally:
            for node in targets:
                info = manager.seeder_info.get(node, {})
                if info.get("capacity_reservation") == job["id"]:
                    info.pop("capacity_reservation", None)

    async def run(job):
        assigned_sessions = {}
        reserved_nodes = set()
        relay_leases = {}
        lease_ids = set()
        async def assignment(stage, health):
            message = {"type": "petals_start", "job_id": job["id"],
                "spec": {"model_id": job["spec"]["model_id"], "revision": job["spec"]["revision"]},
                "stage": dict(stage), "prefix": job["prefix"], "bootstrap": health["bootstrap"]}
            policy = os.getenv("COMPUTETORRENT_PETALS_NETWORK_POLICY", "auto")
            if health.get("relay_enabled"):
                if manager.seeder_info[stage["node_id"]].get("profile", {}).get("petals_relay_protocol") != 1:
                    raise RuntimeError("Update the provider app before using hybrid Petals routing")
                lease = await asyncio.to_thread(gateway, "/routes", {"job_id": job["id"], "node_id": stage["node_id"]})
                relay_leases[stage["node_id"]] = lease
                lease_ids.add(lease["id"])
                message.update(relay=lease, network_policy=policy)
            elif policy == "relay":
                raise RuntimeError("Relay-only routing requested, but the gateway relay is disabled")
            return message
        try:
            job.update(status="resolving")
            store.save(job)
            job["spec"] = await asyncio.to_thread(resolve_revision, job["spec"])
            health = await asyncio.to_thread(gateway, "/health")
            if health.get("status") != "ready" or not health.get("bootstrap"):
                raise RuntimeError("Petals DHT gateway is not ready")
            lan_resolver = getattr(app.state, "current_host_lan_state", None)
            if callable(lan_resolver):
                lan_ip = (lan_resolver() or {}).get("lan_ip")
                if lan_ip:
                    health = {
                        **health,
                        "bootstrap": [
                            re.sub(r"^/ip4/[^/]+(?=/tcp/31331/)", f"/ip4/{lan_ip}", str(m))
                            for m in health["bootstrap"]
                        ],
                    }
            peers = {n: i for n, i in manager.seeder_info.items() if n in manager.active_seeders}
            await profile_capacity(job, peers)
            peers = {n: i for n, i in manager.seeder_info.items() if n in manager.active_seeders}
            decision = {}
            plan = placement(job["spec"], peers, calibration=store.calibrations(), diagnostics=decision)
            job['optimizer'] = decision
            job.update(plan=plan, status="loading", prefix="ct-" + job["id"],
                       stage_status={stage["node_id"]: {"status": "assigning"} for stage in plan},
                       metrics={
                           "provider_count": len(plan),
                           "max_new_tokens": int(job["spec"].get("max_new_tokens") or 32),
                           "weights_bytes": int(job["spec"].get("weights_bytes") or 0) or None,
                           "elapsed_seconds": 0.0,
                           "capacity_inference_rps_total": round(sum(float((job.get("capacity_measurements", {}).get(s["node_id"]) or {}).get("inference_rps") or 0) for s in plan), 2) or None,
                       })
            job_wall_started = time.monotonic()
            store.save(job)
            for stage in plan:
                manager.seeder_info[stage["node_id"]]["busy"] = True
            for stage in plan:
                assigned_sessions[stage["node_id"]] = manager.active_seeders.get(stage["node_id"])
                reserved_nodes.add(stage["node_id"])
                manager.seeder_info[stage["node_id"]]["busy"] = True
                message = await assignment(stage, health)
                ok = await manager.send_to_seeder(message, stage["node_id"])
                job["stage_status"][stage["node_id"]] = {"status": "sent" if ok else "delivery_failed"}
                store.save(job)
            # Never interpret container startup as model readiness. The gateway
            # checks actual DHT layer coverage before opening inference sessions.
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline:
                reassigned = False
                ready = []
                for stage in plan:
                    if (stage["node_id"] not in manager.active_seeders
                            or manager.active_seeders[stage["node_id"]] is not assigned_sessions[stage["node_id"]]
                            or job["stage_status"].get(stage["node_id"], {}).get("status") == "delivery_failed"):
                        disconnected_id = stage["node_id"]
                        print(f"[RECOVERY] Layer provider {disconnected_id} disconnected during stage setup. Searching for replacement...")
                        delivery_failed = job["stage_status"].get(disconnected_id, {}).get("status") == "delivery_failed"
                        job["stage_status"][disconnected_id] = {"status": "disconnected"}
                        store.save(job)

                        # Find eligible replacement among active seeders not currently in the plan
                        assigned_nodes = {s["node_id"] for s in plan if s["node_id"] != disconnected_id}
                        replacement = replacement_stage(job["spec"], stage,
                            {n: info for n, info in manager.seeder_info.items()
                             if n in manager.active_seeders},
                            assigned_nodes | ({disconnected_id} if delivery_failed else set()))
                        if replacement:
                            replacement_id = replacement["node_id"]
                            job.setdefault('optimizer', {}).setdefault('execution_deviations', []).append({
                                'reason': 'provider_replaced_before_generation', 'from_node': disconnected_id,
                                'to_node': replacement_id, 'start': stage['start'], 'end': stage['end']})
                            job['optimizer']['predicted_plan_valid'] = False
                            stage.update(replacement)
                            assigned_sessions[replacement_id] = manager.active_seeders[replacement_id]
                            reserved_nodes.add(replacement_id)
                            manager.seeder_info[replacement_id]["busy"] = True
                            job["stage_status"][replacement_id] = {"status": "assigning"}
                            store.save(job)
                            message = await assignment(stage, health)
                            ok = await manager.send_to_seeder(message, replacement_id)
                            if not ok:
                                raise RuntimeError(f"Replacement provider {replacement_id} disconnected during reassignment")
                            job["stage_status"][replacement_id] = {"status": "sent"}
                            store.save(job)
                            reassigned = True
                            break
                        else:
                            raise RuntimeError(f"Layer provider {disconnected_id} disconnected and no alternative provider is available to host layers {stage['start']}-{stage['end']}. Reconnect providers and resubmit.")

                    p = manager.seeder_info[stage["node_id"]].get("profile", {}).get("petals", {})
                    lp = manager.seeder_info[stage["node_id"]].get("layer_progress")
                    if p.get("job_id") == job["id"]:
                        merged_p = {**p, **({"progress": lp} if isinstance(lp, dict) and lp and "progress" not in p else {})}
                        job["stage_status"][stage["node_id"]] = merged_p
                        if merged_p.get("error"):
                            raise RuntimeError(f"Provider {stage['node_id']}: {merged_p['error']}")
                        if merged_p.get("peer_id") and merged_p.get("status") == "serving" and merged_p.get("network_revision") == PETALS_NETWORK_REVISION:
                            job["stage_status"][stage["node_id"]] = {**merged_p, "status": "serving"}
                            transport = merged_p.get("transport", "direct")
                            ready.append({**stage, "peer_id": merged_p["peer_id"], "transport": transport})

                if reassigned:
                    await asyncio.sleep(1)
                    continue

                job.setdefault("metrics", {})["elapsed_seconds"] = round(time.monotonic() - job_wall_started, 1)
                if len(ready) == len(plan):
                    decision = job.get('optimizer', {})
                    for stage in ready:
                        calibrated = decision.get('calibration', {}).get(stage['node_id'])
                        if calibrated and calibrated.get('transport') != stage.get('transport'):
                            decision['predicted_plan_valid'] = False
                            decision.setdefault('execution_deviations', []).append({
                                'reason': 'transport_changed_after_planning', 'node_id': stage['node_id'],
                                'planned_transport': calibrated.get('transport'), 'actual_transport': stage.get('transport')})
                    job["plan"] = ready
                    break
                store.save(job)
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Provider model download/startup exceeded 60 minutes. Check provider disk space, Hugging Face connectivity, and model cache; resume by resubmitting after the download has cached.")
            for stage in job["plan"]:
                if stage.get("transport") == "wss":
                    lease = relay_leases.get(stage["node_id"])
                    if not lease:
                        raise RuntimeError("Provider reported an unassigned relay route")
                    proof = await asyncio.to_thread(gateway, "/routes/probe",
                        {"id": lease["id"], "peer_id": stage["peer_id"]})
                    if proof.get("status") != "verified" or proof.get("peer_id") != stage["peer_id"]:
                        raise RuntimeError("Gateway could not verify the relayed worker identity")
            job["status"] = "downloading_model"
            store.save(job)
            await asyncio.to_thread(gateway, "/jobs", job)
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline:
                missing = [stage["node_id"] for stage in job["plan"]
                           if (stage["node_id"] not in manager.active_seeders
                               or manager.active_seeders[stage["node_id"]] is not assigned_sessions[stage["node_id"]])]
                if missing:
                    raise RuntimeError("Layer provider disconnected during inference: " + ", ".join(missing)
                                       + ". Session state cannot migrate safely; resubmit to restart.")
                response = await asyncio.to_thread(gateway, "/jobs/" + job["id"])
                if response["status"] in {"completed", "failed"}:
                    prev_metrics = {k: v for k, v in (job.get("metrics") or {}).items() if k in {"capacity_inference_rps_total", "weights_bytes"}}
                    job.update(response)
                    if isinstance(job.get("metrics"), dict) and prev_metrics:
                        job["metrics"] = {**prev_metrics, **job["metrics"]}
                    if response["status"] == "completed":
                        job.pop("partial_result", None)
                    for st in job.get("plan") or []:
                        nid = st["node_id"]
                        cur_p = manager.seeder_info.get(nid, {}).get("profile", {}).get("petals", {})
                        cur_lp = manager.seeder_info.get(nid, {}).get("layer_progress")
                        if cur_p.get("job_id") == job["id"]:
                            job.setdefault("stage_status", {})[nid] = {**cur_p, **({"progress": cur_lp} if isinstance(cur_lp, dict) and cur_lp and "progress" not in cur_p else {})}
                    if isinstance(response.get("gateway_log_tail"), list):
                        job["gateway_log_tail"] = response["gateway_log_tail"]
                    from sun_runtime import record_calibration
                    try:
                        store.save_calibrations(record_calibration(job,
                            {n:i for n,i in manager.seeder_info.items() if n in manager.active_seeders}, native_capacity, previous_records=store.calibrations()))
                    except Exception as calibration_error:
                        # Optional performance telemetry cannot turn a completed
                        # completed inference into a failed inference.
                        job.setdefault('optimizer', {})['calibration_error'] = str(calibration_error)[:300]
                    break
                job["status"] = response["status"]
                job["progress"] = response.get("progress", 0)
                if response.get("partial_result") is not None:
                    job["partial_result"] = response["partial_result"]
                if isinstance(response.get("gateway_log_tail"), list):
                    job["gateway_log_tail"] = response["gateway_log_tail"]
                live_metrics = {
                    key: response[key]
                    for key in (
                        "downloaded_bytes", "total_bytes", "percent", "speed_bps",
                        "generated_tokens", "max_new_tokens", "model_load_seconds",
                        "distributed_generation_seconds", "throughput_tokens_per_sec",
                        "latency_per_token_ms", "prefill_latency_seconds",
                        "token_confidence_pct", "perplexity", "finite_logits_pct",
                    )
                    if key in response and response[key] is not None
                }
                live_metrics["elapsed_seconds"] = round(time.monotonic() - job_wall_started, 1)
                job.setdefault("metrics", {}).update(live_metrics)
                stage_map = {**job.get("stage_status", {})}
                for st in job.get("plan") or []:
                    nid = st["node_id"]
                    cur_p = manager.seeder_info.get(nid, {}).get("profile", {}).get("petals", {})
                    cur_lp = manager.seeder_info.get(nid, {}).get("layer_progress")
                    if cur_p.get("job_id") == job["id"]:
                        stage_map[nid] = {**cur_p, **({"progress": cur_lp} if isinstance(cur_lp, dict) and cur_lp and "progress" not in cur_p else {})}
                stage_map["coordinator"] = {
                    "status": response.get("status", "running"),
                    **{k: response[k] for k in ("downloaded_bytes", "total_bytes", "percent", "speed_bps", "elapsed_seconds", "generated_tokens", "max_new_tokens") if k in response},
                }
                job["stage_status"] = stage_map
                store.save(job)
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Model download or inference exceeded 60 minutes. Check the coordinator Hugging Face cache and gateway log, then retry after the checkpoint has downloaded.")
        except asyncio.CancelledError:
            job.update(status="cancelled", error="Stopped by operator")
        except Exception as exc:
            job.update(status="failed", error=str(exc)[:1000])
        finally:
            try:
                await asyncio.to_thread(gateway, "/cancel", {"id": job["id"]})
            except Exception:
                pass
            for node in reserved_nodes:
                await manager.send_to_seeder({"type": "petals_stop", "job_id": job["id"]}, node)
                # Do not clear a different connection's subsequent reservation.
                if manager.active_seeders.get(node) is not assigned_sessions.get(node):
                    continue
                manager.seeder_info.get(node, {})["busy"] = False
                profile = manager.seeder_info.get(node, {}).get("profile", {})
                if profile.get("petals", {}).get("job_id") == job["id"]:
                    profile["petals"] = {"status": "idle"}
            for route_id in lease_ids:
                try:
                    await asyncio.to_thread(gateway, "/routes/revoke", {"id": route_id})
                except Exception:
                    pass  # Broker expiry is an independent upper bound.
            store.save(job)
            running.pop(job["id"], None)

    @router.post("/jobs", status_code=202)
    async def submit(upload: Upload):
        await reconcile_stale_sessions()
        if running:
            raise HTTPException(409, "One distributed job at a time is supported by this small-model workspace")
        try:
            spec = parse_manifest(upload.content, upload.format)
            # Recheck fresh telemetry before profiling; a previously exhausted
            # native memory sample must not prevent the next measurement.
            preflight = {n: {**i, "profile": {k: v for k, v in i.get("profile", {}).items()
                                            if k != "petals_capacity"}}
                         for n, i in manager.seeder_info.items() if n in manager.active_seeders}
            baseline_placement({**spec, **CATALOG[spec["model_id"]]}, preflight)
        except ValueError as exc:
            print(f"[SUBMIT_ERROR] 422: {exc}", flush=True)
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

    @app.on_event("startup")
    async def startup_reconciler():
        nonlocal reconcile_task

        async def _reconcile_loop():
            while True:
                try:
                    await reconcile_stale_sessions()
                except Exception:
                    pass
                await asyncio.sleep(5)

        reconcile_task = asyncio.create_task(_reconcile_loop())

    @app.on_event("shutdown")
    async def shutdown():
        if reconcile_task is not None:
            reconcile_task.cancel()
        tasks = list(running.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app.include_router(router)
