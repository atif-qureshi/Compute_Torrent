from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
from typing import Optional, List, Dict, Literal
from datetime import datetime
import json
import asyncio
import uuid
import os
import re
import sys
import hashlib
import hmac
import secrets
import urllib.request
from pathlib import Path

_MODULE_ROOT = os.getenv("COMPUTETORRENT_MODULE_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.join(_MODULE_ROOT, "modules"))
from task_slicer import TaskSlicer
from verification import verify_replicas

# Database configuration
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/computetorrent"

try:
    DATABASE_URL = os.getenv("DATABASE_URL", DATABASE_URL)
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    Base = declarative_base()
    DB_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Database connection failed: {e}")
    print("Running in mock mode without database")
    DB_AVAILABLE = False
    Base = None
    SessionLocal = None

# Database Models
if DB_AVAILABLE:
    class Task(Base):
        __tablename__ = "tasks"
        
        id = Column(Integer, primary_key=True)
        task_id = Column(String, unique=True, index=True)
        submitter_id = Column(String)
        model_name = Column(String)
        prompt = Column(String)
        status = Column(String, default="pending")
        chunks = Column(JSON)
        created_at = Column(DateTime, default=datetime.utcnow)
        completed_at = Column(DateTime, nullable=True)
        result = Column(JSON, nullable=True)

    class Seeder(Base):
        __tablename__ = "seeders"
        
        id = Column(Integer, primary_key=True)
        node_id = Column(String, unique=True, index=True)
        tier = Column(Integer)
        profile = Column(JSON)
        status = Column(String, default="offline")
        last_heartbeat = Column(DateTime, default=datetime.utcnow)
        tasks_completed = Column(Integer, default=0)
        credits_earned = Column(Float, default=0.0)

    class SeederCredential(Base):
        __tablename__ = "seeder_credentials"
        id = Column(Integer, primary_key=True)
        node_id = Column(String, unique=True, index=True, nullable=False)
        token_hash = Column(String, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)

    class ChunkResult(Base):
        __tablename__ = "chunk_results"
        
        id = Column(Integer, primary_key=True)
        task_id = Column(String, index=True)
        chunk_id = Column(String)
        seeder_id = Column(String)
        output_hash = Column(String)
        output_ref = Column(String)
        status = Column(String)
        created_at = Column(DateTime, default=datetime.utcnow)

    class CreditLedger(Base):
        __tablename__ = "credit_ledger"
        id = Column(Integer, primary_key=True)
        account_id = Column(String, index=True, nullable=False)
        entry_type = Column(String, nullable=False)
        amount = Column(Float, nullable=False)
        task_id = Column(String, nullable=True, index=True)
        description = Column(String, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)

    # Create tables
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created")
    except Exception as e:
        print(f"⚠️ Table creation warning: {e}")
# Mock storage is also initialized in database mode so request handlers can
# use one shared code path for status and connected provider bookkeeping.
MOCK_TASKS = {}
MOCK_SEEDERS = {}
MOCK_RESULTS = {}

MOCK_CREDIT_LEDGER = []
MOCK_SEEDER_CREDENTIALS = {}

# Pydantic models
class TaskCreate(BaseModel):
    model_name: str
    prompt: Optional[str] = None
    prompts: Optional[List[str]] = None
    submitter_id: str = "web-portal"
    max_tokens: int = 256
    mode: Literal["WS-RR", "CC-BP"] = "WS-RR"
    min_ram_gb: int = 0
    require_cuda: bool = False

class SeederEnrollment(BaseModel):
    tier: int = 2
    profile: Dict = {}

class TaskResponse(BaseModel):
    task_id: str
    status: str
    created_at: str

class SeederProfile(BaseModel):
    GPU: Optional[str] = None
    VRAM: int = 0
    CUDA: bool = False
    RAM: int = 0

class SeederRegister(BaseModel):
    node_id: str
    tier: int
    profile: SeederProfile

def load_model_registry():
    """Read an operator-managed manifest; model files are provisioned out of band."""
    manifest_path = os.getenv("COMPUTETORRENT_MODEL_MANIFEST", os.path.join(os.path.dirname(__file__), "models.json"))
    try:
        with open(manifest_path, encoding="utf-8") as manifest:
            models = json.load(manifest)
        return {name: info for name, info in models.items()
                if re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name)
                and isinstance(info, dict)
                and isinstance(info.get("file"), str)
                and re.fullmatch(r"[A-Za-z0-9._-]{1,120}\.gguf", info["file"])
                and isinstance(info.get("sha256"), str)
                and re.fullmatch(r"[a-fA-F0-9]{64}", info["sha256"])
                and isinstance(info.get("magnet_uri"), str)
                and (not info.get("adapter_file") or (isinstance(info.get("adapter_file"), str)
                     and re.fullmatch(r"[A-Za-z0-9._-]{1,120}\.gguf", info["adapter_file"])
                     and isinstance(info.get("adapter_sha256"), str)
                     and re.fullmatch(r"[a-fA-F0-9]{64}", info["adapter_sha256"])))
                and isinstance(info.get("canaries", []), list)
                and all(isinstance(item, dict) and isinstance(item.get("id"), str)
                        and isinstance(item.get("prompt"), str) and item["prompt"].strip()
                        and isinstance(item.get("expected_output_sha256"), str)
                        and re.fullmatch(r"[a-fA-F0-9]{64}", item["expected_output_sha256"])
                        for item in info.get("canaries", [])) }
    except (OSError, ValueError, TypeError):
        return {}

MODEL_REGISTRY = load_model_registry()

def create_chunk_swarm(chunk_id: str, prompt: str) -> dict:
    """Persist a prompt payload in shared storage and announce its private swarm."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,140}", chunk_id):
        raise ValueError("Invalid chunk ID")
    root = Path(os.getenv("COMPUTETORRENT_SWARM_DATA", os.path.join(os.path.dirname(__file__), "data"))).resolve()
    relative = Path("swarm_payloads") / chunk_id / "chunk.json"
    destination = (root / relative).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"prompt": prompt}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.write_bytes(raw)
    payload_hash = hashlib.sha256(raw).hexdigest()
    request = urllib.request.Request(
        os.getenv("COMPUTETORRENT_SWARM_URL", "http://127.0.0.1:4001") + "/create-swarm",
        data=json.dumps({"task_id": chunk_id, "files": [relative.as_posix()]}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=45) as response:
        swarm = json.loads(response.read().decode("utf-8"))
    return {"magnet_uri": swarm["magnet_uri"], "payload_sha256": payload_hash}

def teardown_chunk_swarm(chunk_id: str) -> None:
    root = Path(os.getenv("COMPUTETORRENT_SWARM_DATA", os.path.join(os.path.dirname(__file__), "data"))).resolve()
    relative = Path("swarm_payloads") / chunk_id / "chunk.json"
    request = urllib.request.Request(
        os.getenv("COMPUTETORRENT_SWARM_URL", "http://127.0.0.1:4001") + "/teardown-swarm",
        data=json.dumps({"task_id": chunk_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15):
            pass
    except Exception:
        pass
    try:
        (root / relative).resolve().unlink(missing_ok=True)
        (root / relative).parent.rmdir()
    except OSError:
        pass


def queue_hidden_canary(model_name: str, model: dict) -> None:
    """Queue a normal-looking private job with a coordinator-known answer."""
    candidates = model.get("canaries", [])
    if not candidates:
        return
    canary = secrets.choice(candidates)
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    manifest = TaskSlicer().slice_task(
        task_id, [canary["prompt"]], model_name, model["file"], model["sha256"],
        replicas=1, max_tokens=canary.get("max_tokens", 64), seed=canary.get("seed", 42),
        adapter_file=model.get("adapter_file"), adapter_sha256=model.get("adapter_sha256"))
    chunk = manifest["chunks"][0]
    chunk["hidden_canary"] = {"id": canary["id"],
                              "expected_output_sha256": canary["expected_output_sha256"]}
    if DB_AVAILABLE:
        db = get_db()
        try:
            db.add(Task(task_id=task_id, submitter_id="__system_canary__", model_name=model_name,
                        prompt=json.dumps([canary["prompt"]], ensure_ascii=False), status="pending",
                        chunks=manifest["chunks"]))
            db.commit()
        finally:
            db.close()
        return
    MOCK_TASKS[task_id] = {
        "task_id": task_id, "submitter_id": "__system_canary__", "model_name": model_name,
        "model_file": model["file"], "model_sha256": model["sha256"], "mode": "WS-RR",
        "prompt": json.dumps([canary["prompt"]], ensure_ascii=False),
        "chunks": manifest["chunks"], "manifest": {key: value for key, value in manifest.items() if key != "chunks"},
        "status": "pending", "created_at": datetime.utcnow().isoformat(),
    }

# FastAPI app
app = FastAPI(
    title="ComputeTorrent Orchestrator",
    version="1.0.0",
    description="Decentralized P2P LLM Inference Coordination"
)

# CORS - allow web portal
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("COMPUTETORRENT_CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_TOKEN = os.getenv("COMPUTETORRENT_API_TOKEN", "").strip()
SEEDER_ENROLLMENT_TOKEN = os.getenv("COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN", "").strip()

def valid_api_token(value: Optional[str]) -> bool:
    if not API_TOKEN or not value or not value.startswith("Bearer "):
        return False
    return hmac.compare_digest(value[7:].strip(), API_TOKEN)

@app.middleware("http")
async def protect_api(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in {
        "/api/health", "/api/seeders/enroll", "/api/network/bootstrap"
    }:
        if not valid_api_token(request.headers.get("authorization")):
            return JSONResponse({"detail": "A valid bearer token is required"}, status_code=401)
    return await call_next(request)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_seeders: Dict[str, WebSocket] = {}
        self.seeder_info: Dict[str, dict] = {}
        self.round_robin_cursor = 0
    
    async def connect(self, node_id: str, websocket: WebSocket):
        self.active_seeders[node_id] = websocket
        print(f"✅ Seeder connected: {node_id}")
    
    def disconnect(self, node_id: str):
        if node_id in self.active_seeders:
            del self.active_seeders[node_id]
            print(f"❌ Seeder disconnected: {node_id}")
        self.seeder_info.setdefault(node_id, {})["busy"] = False
        self.seeder_info.setdefault(node_id, {})["state"] = "offline"
    
    async def send_to_seeder(self, message: dict, node_id: str):
        if node_id in self.active_seeders:
            try:
                await self.active_seeders[node_id].send_text(json.dumps(message))
                return True
            except Exception:
                return False
        return False
    
    def get_available_seeders(self):
        return list(self.active_seeders.keys())

    def choose_provider(self, candidates: list[str], task: dict) -> Optional[str]:
        requirements = task.get("requirements", {})
        capable = []
        for node_id in candidates:
            profile = self.seeder_info.get(node_id, {}).get("profile", {})
            if profile.get("docker_ok") is False:
                continue
            if profile.get("canary_quarantined"):
                continue
            if requirements.get("require_cuda") and not profile.get("CUDA"):
                continue
            if int(profile.get("RAM", 0) or 0) < int(requirements.get("min_ram_gb", 0) or 0):
                continue
            capable.append(node_id)
        if not capable:
            return None
        if task.get("mode") == "CC-BP":
            def capacity_score(node_id: str) -> float:
                profile = self.seeder_info.get(node_id, {}).get("profile", {})
                return (float(profile.get("free_ram_gb", 0) or 0) * 4
                        + float(profile.get("VRAM", 0) or 0) / 1024 * 3
                        + int(profile.get("cpu_cores", 0) or 0) * 2
                        + (100 - float(profile.get("cpu_load_pct", 100) or 100)) * .15
                        + min(float(profile.get("uptime_seconds", 0) or 0) / 3600, 168) * .03)
            return max(capable, key=capacity_score)
        self.round_robin_cursor += 1
        return capable[(self.round_robin_cursor - 1) % len(capable)]

manager = ConnectionManager()

# Helper functions
def get_db():
    if DB_AVAILABLE:
        db = SessionLocal()
        try:
            return db
        finally:
            pass
    return None

# REST API Endpoints

@app.get("/")
async def root():
    return {
        "service": "ComputeTorrent Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "database": "connected" if DB_AVAILABLE else "mock mode",
        "connected_seeders": len(manager.active_seeders)
    }

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "database": DB_AVAILABLE,
        "seeders_online": len(manager.active_seeders),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/network/bootstrap")
async def network_bootstrap():
    """Return this local coordinator's libp2p relay address for provider enrollment."""
    url = os.getenv("COMPUTETORRENT_SWARM_URL", "http://127.0.0.1:4001").rstrip("/") + "/peer-info"
    try:
        def read_peer_info():
            with urllib.request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        peer_info = await asyncio.to_thread(read_peer_info)
    except Exception as error:
        raise HTTPException(status_code=503, detail="Local libp2p relay is unavailable") from error
    return {"peer_id": peer_info["peer_id"], "multiaddr": peer_info["multiaddr"],
            "protocol": peer_info["protocol"], "relay": peer_info["relay"]}

@app.get("/api/network")
async def network_status():
    """Expose local libp2p relay connectivity to the authenticated portal."""
    url = os.getenv("COMPUTETORRENT_SWARM_URL", "http://127.0.0.1:4001").rstrip("/") + "/network-status"
    try:
        def read_network_status():
            with urllib.request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        return await asyncio.to_thread(read_network_status)
    except Exception:
        return {"status": "unavailable", "connected_peer_count": 0, "connected_peers": []}

@app.get("/api/models")
async def list_models():
    MODEL_REGISTRY.clear()
    MODEL_REGISTRY.update(load_model_registry())
    return [{"name": name, "label": info.get("label", name), "sha256": info["sha256"]}
            for name, info in sorted(MODEL_REGISTRY.items())]

@app.post("/api/seeders/enroll")
async def enroll_seeder(enrollment: SeederEnrollment, request: Request):
    supplied = request.headers.get("x-enrollment-token", "")
    if not SEEDER_ENROLLMENT_TOKEN or not hmac.compare_digest(supplied, SEEDER_ENROLLMENT_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or disabled provider enrollment code")
    node_id = f"seeder-{secrets.token_hex(12)}"
    node_token = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(node_token.encode("utf-8")).hexdigest()
    if DB_AVAILABLE:
        db = get_db()
        try:
            db.add(Seeder(node_id=node_id, tier=enrollment.tier, profile=enrollment.profile,
                          status="offline", last_heartbeat=datetime.utcnow()))
            db.add(SeederCredential(node_id=node_id, token_hash=token_hash))
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=503, detail="Could not provision this provider")
        finally:
            db.close()
    else:
        MOCK_SEEDERS[node_id] = {"node_id": node_id, "tier": enrollment.tier, "profile": enrollment.profile,
                                 "status": "offline", "tasks_completed": 0, "credits_earned": 0.0}
        MOCK_SEEDER_CREDENTIALS[node_id] = token_hash
    return {"node_id": node_id, "access_token": node_token}

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    '''Submit a new inference task'''
    MODEL_REGISTRY.clear()
    MODEL_REGISTRY.update(load_model_registry())
    prompts = task.prompts or ([task.prompt] if task.prompt is not None else [])
    if task.prompts and task.prompt is not None:
        raise HTTPException(status_code=422, detail="Use either prompt or prompts, not both")
    model = MODEL_REGISTRY.get(task.model_name)
    if not model:
        raise HTTPException(status_code=422, detail="Model is not registered or provisioned")
    eligible_seeders = []
    for node_id in manager.active_seeders:
        profile = manager.seeder_info.get(node_id, {}).get("profile", {})
        if profile.get("docker_ok") is False:
            continue
        if profile.get("canary_quarantined"):
            continue
        if task.require_cuda and not profile.get("CUDA"):
            continue
        if profile.get("RAM", 0) < task.min_ram_gb:
            continue
        eligible_seeders.append(node_id)
    if (task.require_cuda or task.min_ram_gb) and not eligible_seeders:
        raise HTTPException(status_code=409, detail="No connected provider currently meets the requested hardware requirements")
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    try:
        manifest = TaskSlicer().slice_task(task_id, prompts, task.model_name,
                                           model["file"], model["sha256"], replicas=max(1, min(3, len(eligible_seeders))),
                                           max_tokens=task.max_tokens, mode=task.mode,
                                           min_ram_gb=task.min_ram_gb, require_cuda=task.require_cuda,
                                           adapter_file=model.get("adapter_file"),
                                           adapter_sha256=model.get("adapter_sha256"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    
    if DB_AVAILABLE:
        db = get_db()
        try:
            entries = db.query(CreditLedger).filter(CreditLedger.account_id == task.submitter_id).all()
            balance = sum(entry.amount for entry in entries)
            if not entries:
                db.add(CreditLedger(account_id=task.submitter_id, entry_type="grant", amount=100,
                                    description="Initial demo credit grant"))
                balance = 100
            if balance < 1:
                raise HTTPException(status_code=402, detail="Insufficient credits to submit a task")
            chunks = manifest["chunks"]
            
            db_task = Task(
                task_id=task_id,
                submitter_id=task.submitter_id,
                model_name=task.model_name,
                prompt=json.dumps(prompts, ensure_ascii=False),
                status="pending",
                chunks=chunks
            )
            
            db.add(db_task)
            db.add(CreditLedger(account_id=task.submitter_id, entry_type="task_cost", amount=-1,
                                task_id=task_id, description="Inference task submission"))
            db.commit()
            db.refresh(db_task)
            
            created_at = db_task.created_at.isoformat()
        finally:
            db.close()
    else:
        # Mock storage
        existing = [entry for entry in MOCK_CREDIT_LEDGER if entry["account_id"] == task.submitter_id]
        if not existing:
            MOCK_CREDIT_LEDGER.append({"account_id": task.submitter_id, "entry_type": "grant", "amount": 100,
                                       "task_id": None, "description": "Initial demo credit grant", "created_at": datetime.utcnow().isoformat()})
            existing = [entry for entry in MOCK_CREDIT_LEDGER if entry["account_id"] == task.submitter_id]
        if sum(entry["amount"] for entry in existing) < 1:
            raise HTTPException(status_code=402, detail="Insufficient credits to submit a task")
        MOCK_CREDIT_LEDGER.append({"account_id": task.submitter_id, "entry_type": "task_cost", "amount": -1,
                                   "task_id": task_id, "description": "Inference task submission", "created_at": datetime.utcnow().isoformat()})
        MOCK_TASKS[task_id] = {
            "task_id": task_id,
            "submitter_id": task.submitter_id,
            "model_name": task.model_name,
            "model_file": model["file"],
            "model_sha256": model["sha256"],
            "mode": task.mode,
            "prompt": json.dumps(prompts, ensure_ascii=False),
            "chunks": manifest["chunks"],
            "manifest": {key: value for key, value in manifest.items() if key != "chunks"},
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        created_at = MOCK_TASKS[task_id]["created_at"]
    
    # A randomly selected model canary enters the same scheduler as ordinary
    # work, but is stored under an internal account and filtered from the portal.
    try:
        canary_percent = min(max(int(os.getenv("COMPUTETORRENT_CANARY_PERCENT", "10")), 0), 100)
    except ValueError:
        canary_percent = 10
    if model.get("canaries") and secrets.randbelow(100) < canary_percent:
        try:
            queue_hidden_canary(task.model_name, model)
        except Exception as error:
            print(f"Could not queue hidden canary for {task.model_name}: {error}")

    # Try to allocate immediately
    await allocate_pending_tasks()
    
    return TaskResponse(
        task_id=task_id,
        status="pending",
        created_at=created_at
    )

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    '''Get task details'''
    if DB_AVAILABLE:
        db = get_db()
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if not task or task.submitter_id == "__system_canary__":
                raise HTTPException(status_code=404, detail="Task not found")
            
            return {
                "task_id": task.task_id,
                "status": task.status,
                "model_name": task.model_name,
                "prompt": task.prompt,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "result": task.result,
                "progress": {"completed": sum(c.get("status") == "verified" for c in (task.chunks or [])),
                             "total": len(task.chunks or [])},
                "mode": (task.chunks or [{}])[0].get("mode", "WS-RR"),
                "chunks": [{"chunk_id": c["chunk_id"], "index": c["index"], "status": c["status"],
                            "verification": c.get("verification"), "failure_reason": c.get("failure_reason")}
                           for c in (task.chunks or [])]
            }
        finally:
            db.close()
    else:
        if task_id not in MOCK_TASKS:
            raise HTTPException(status_code=404, detail="Task not found")
        task = MOCK_TASKS[task_id]
        chunks = task.get("chunks", [])
        return {
            "task_id": task["task_id"],
            "status": task.get("status", "pending"),
            "model_name": task.get("model_name"),
            "prompt": task.get("prompt"),
            "created_at": task.get("created_at"),
            "completed_at": task.get("completed_at"),
            "result": task.get("result"),
            "progress": {"completed": sum(c.get("status") == "verified" for c in chunks),
                         "total": len(chunks)},
            "mode": (chunks or [{}])[0].get("mode", task.get("mode", "WS-RR")),
            # Do not return prompts' private canary markers or verifier-only data.
            "chunks": [{"chunk_id": c["chunk_id"], "index": c["index"],
                        "status": c["status"], "verification": c.get("verification"),
                        "failure_reason": c.get("failure_reason")}
                       for c in chunks],
        }

@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 50, submitter_id: Optional[str] = None):
    '''List tasks'''
    limit = min(max(limit, 1), 500)
    if DB_AVAILABLE:
        db = get_db()
        try:
            query = db.query(Task)
            query = query.filter(Task.submitter_id != "__system_canary__")
            if status:
                query = query.filter(Task.status == status)
            if submitter_id:
                query = query.filter(Task.submitter_id == submitter_id)
            tasks = query.order_by(Task.created_at.desc()).limit(limit).all()
            
            return [
                {
                    "task_id": t.task_id,
                    "status": t.status,
                    "model_name": t.model_name,
                    "mode": (t.chunks or [{}])[0].get("mode", "WS-RR"),
                    "created_at": t.created_at.isoformat(),
                    "submitter_id": t.submitter_id
                }
                for t in tasks
            ]
        finally:
            db.close()
    else:
        tasks = list(MOCK_TASKS.values())
        tasks = [t for t in tasks if t.get("submitter_id") != "__system_canary__"]
        if submitter_id:
            tasks = [t for t in tasks if t.get("submitter_id") == submitter_id]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return [{"task_id": t["task_id"], "status": t.get("status", "pending"),
                 "model_name": t.get("model_name"), "mode": t.get("mode", "WS-RR"),
                 "created_at": t.get("created_at"), "submitter_id": t.get("submitter_id")}
                for t in tasks[:limit]]

@app.get("/api/seeders")
async def list_seeders():
    '''List registered seeders'''
    if DB_AVAILABLE:
        db = get_db()
        try:
            seeders = db.query(Seeder).all()
            return [
                {
                    "node_id": s.node_id,
                    "tier": s.tier,
                    "status": s.status,
                    "state": manager.seeder_info.get(s.node_id, {}).get("state", "offline") if s.node_id in manager.active_seeders else "offline",
                    "profile": manager.seeder_info.get(s.node_id, {}).get("profile", s.profile or {}),
                    "tasks_completed": s.tasks_completed,
                    "credits_earned": s.credits_earned,
                    "last_heartbeat": s.last_heartbeat.isoformat()
                }
                for s in seeders
            ]
        finally:
            db.close()
    else:
        return list(MOCK_SEEDERS.values())

@app.delete("/api/seeders/{node_id}/credential")
async def revoke_seeder(node_id: str):
    if DB_AVAILABLE:
        db = get_db()
        try:
            seeder = db.query(Seeder).filter(Seeder.node_id == node_id).first()
            credential = db.query(SeederCredential).filter(SeederCredential.node_id == node_id).first()
            if not seeder or not credential:
                raise HTTPException(status_code=404, detail="Provider credential not found")
            seeder.status = "revoked"
            db.delete(credential)
            db.commit()
        finally:
            db.close()
    else:
        if node_id not in MOCK_SEEDERS or node_id not in MOCK_SEEDER_CREDENTIALS:
            raise HTTPException(status_code=404, detail="Provider credential not found")
        MOCK_SEEDER_CREDENTIALS.pop(node_id, None)
        MOCK_SEEDERS[node_id]["status"] = "revoked"
    connection = manager.active_seeders.get(node_id)
    if connection:
        await connection.close(code=1008, reason="Provider credential revoked by operator")
    return {"node_id": node_id, "status": "revoked"}

@app.get("/api/stats")
async def get_stats():
    '''Get system statistics'''
    if DB_AVAILABLE:
        db = get_db()
        try:
            total_tasks = db.query(Task).count()
            pending = db.query(Task).filter(Task.status == "pending").count()
            completed = db.query(Task).filter(Task.status == "completed").count()
            total_seeders = db.query(Seeder).count()
            online_seeders = len(manager.active_seeders)
            
            return {
                "tasks": {
                    "total": total_tasks,
                    "pending": pending,
                    "completed": completed
                },
                "seeders": {
                    "total": total_seeders,
                    "online": online_seeders
                }
            }
        finally:
            db.close()
    else:
        return {
            "tasks": {
                "total": len(MOCK_TASKS),
                "pending": len([t for t in MOCK_TASKS.values() if t["status"] == "pending"]),
                "completed": len([t for t in MOCK_TASKS.values() if t["status"] == "completed"])
            },
            "seeders": {
                "total": len(MOCK_SEEDERS),
                "online": len(manager.active_seeders)
            }
        }

@app.get("/api/history")
async def task_history(submitter_id: str = "web-portal", limit: int = 100):
    return await list_tasks(limit=min(max(limit, 1), 500), submitter_id=submitter_id)

@app.get("/api/credits")
async def credit_history(submitter_id: str = "web-portal", limit: int = 100):
    if DB_AVAILABLE:
        db = get_db()
        try:
            entries = db.query(CreditLedger).filter(CreditLedger.account_id == submitter_id).order_by(CreditLedger.created_at.desc()).limit(min(max(limit, 1), 500)).all()
            if not entries:
                grant = CreditLedger(account_id=submitter_id, entry_type="grant", amount=100,
                                     description="Initial demo credit grant")
                db.add(grant)
                db.commit()
                entries = [grant]
            balance = sum(row.amount for row in db.query(CreditLedger).filter(CreditLedger.account_id == submitter_id).all())
            return {"account_id": submitter_id, "balance": balance, "entries": [
                {"id": row.id, "entry_type": row.entry_type, "amount": row.amount, "task_id": row.task_id,
                 "description": row.description, "created_at": row.created_at.isoformat()} for row in entries]}
        finally:
            db.close()
    rows = [row for row in MOCK_CREDIT_LEDGER if row["account_id"] == submitter_id]
    if not rows:
        row = {"account_id": submitter_id, "entry_type": "grant", "amount": 100, "task_id": None,
               "description": "Initial demo credit grant", "created_at": datetime.utcnow().isoformat()}
        MOCK_CREDIT_LEDGER.append(row)
        rows = [row]
    return {"account_id": submitter_id, "balance": sum(row["amount"] for row in rows),
            "entries": list(reversed(rows[-min(max(limit, 1), 500):]))}

# WebSocket for seeders
@app.websocket("/ws/seeder")
async def websocket_seeder(websocket: WebSocket):
    '''WebSocket connection for seeder nodes'''
    node_id = None
    
    try:
        await websocket.accept()
        
        # Wait for registration
        register_msg = await websocket.receive_text()
        data = json.loads(register_msg)
        
        if data.get("type") == "register":
            node_id = data.get("node_id")
            tier = data.get("tier")
            profile = data.get("profile")
            supplied_hash = hashlib.sha256((websocket.headers.get("authorization", "")[7:]
                                               if websocket.headers.get("authorization", "").startswith("Bearer ") else "").encode("utf-8")).hexdigest()
            if DB_AVAILABLE:
                db = get_db()
                try:
                    credential = db.query(SeederCredential).filter(SeederCredential.node_id == node_id).first()
                    expected_hash = credential.token_hash if credential else ""
                finally:
                    db.close()
            else:
                expected_hash = MOCK_SEEDER_CREDENTIALS.get(node_id, "")
            if not expected_hash or not hmac.compare_digest(supplied_hash, expected_hash):
                await websocket.close(code=1008, reason="Provider enrollment is invalid or revoked")
                return
            
            # Store seeder info
            tasks_completed = 0
            credits_earned = 0.0
            if DB_AVAILABLE:
                db = get_db()
                try:
                    seeder = db.query(Seeder).filter(Seeder.node_id == node_id).first()
                    if seeder:
                        seeder.status = "online"
                        seeder.last_heartbeat = datetime.utcnow()
                        reported_profile = dict(profile or {})
                        for trust_key in ("canary_failures", "canary_quarantined"):
                            if trust_key in (seeder.profile or {}):
                                reported_profile[trust_key] = seeder.profile[trust_key]
                        profile = reported_profile
                        seeder.profile = profile
                    else:
                        seeder = Seeder(
                            node_id=node_id,
                            tier=tier,
                            profile=profile,
                            status="online"
                        )
                        db.add(seeder)
                    db.commit()
                    tasks_completed = seeder.tasks_completed or 0
                    credits_earned = seeder.credits_earned or 0.0
                finally:
                    db.close()
            else:
                existing_seeder = MOCK_SEEDERS.get(node_id, {})
                reported_profile = dict(profile or {})
                for trust_key in ("canary_failures", "canary_quarantined"):
                    if trust_key in (existing_seeder.get("profile") or {}):
                        reported_profile[trust_key] = existing_seeder["profile"][trust_key]
                profile = reported_profile
                MOCK_SEEDERS[node_id] = {
                    "node_id": node_id,
                    "tier": tier,
                    "profile": profile,
                    "status": "online",
                    "tasks_completed": existing_seeder.get("tasks_completed", 0),
                    "credits_earned": existing_seeder.get("credits_earned", 0.0)
                }
                tasks_completed = MOCK_SEEDERS[node_id]["tasks_completed"]
                credits_earned = MOCK_SEEDERS[node_id]["credits_earned"]
            
            await manager.connect(node_id, websocket)
            manager.seeder_info[node_id] = {"profile": profile or {}, "state": "idle", "busy": False}
            
            # Send ack
            await websocket.send_text(json.dumps({
                "type": "register_ack",
                "node_id": node_id,
                "message": "Registration successful",
                "tasks_completed": tasks_completed,
                "credits_earned": credits_earned
            }))
            
            # Try allocating tasks
            await allocate_pending_tasks()
            
            # Message loop
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                await handle_seeder_message(node_id, data)
                
    except WebSocketDisconnect:
        if node_id:
            manager.disconnect(node_id)
            if DB_AVAILABLE:
                db = get_db()
                try:
                    for task in db.query(Task).filter(Task.status.in_(["pending", "allocated", "running"])).all():
                        changed = False
                        for chunk in task.chunks or []:
                            if chunk.get("assigned_to") == node_id and chunk.get("status") in {"assigned", "running"}:
                                chunk["assigned_to"] = None
                                chunk["providers"] = [provider for provider in chunk.get("providers", []) if provider != node_id]
                                chunk["status"] = "pending" if chunk.get("attempts", 0) < 3 else "failed"
                                chunk["failure_reason"] = "Provider disconnected during execution"
                                changed = True
                        if changed:
                            task.status = "failed" if any(chunk.get("status") == "failed" for chunk in task.chunks) else "pending"
                            task.chunks = task.chunks
                    db.commit()
                    seeder = db.query(Seeder).filter(Seeder.node_id == node_id).first()
                    if seeder:
                        credential = db.query(SeederCredential).filter(SeederCredential.node_id == node_id).first()
                        seeder.status = "offline" if credential else "revoked"
                        db.commit()
                finally:
                    db.close()
            elif node_id in MOCK_SEEDERS:
                MOCK_SEEDERS[node_id]["status"] = "offline"
                for task in MOCK_TASKS.values():
                    if task.get("status") in {"pending", "allocated", "running"}:
                        for chunk in task.get("chunks", []):
                            if chunk.get("assigned_to") == node_id and chunk.get("status") in {"assigned", "running"}:
                                chunk["assigned_to"] = None
                                chunk["providers"] = [provider for provider in chunk.get("providers", []) if provider != node_id]
                                chunk["status"] = "pending" if chunk.get("attempts", 0) < 3 else "failed"
                                chunk["failure_reason"] = "Provider disconnected during execution"
                                task["status"] = "failed" if chunk["status"] == "failed" else "pending"
            await allocate_pending_tasks()

async def handle_seeder_message(node_id: str, data: dict):
    '''Handle messages from seeders'''
    msg_type = data.get("type")
    
    if msg_type == "heartbeat":
        manager.seeder_info.setdefault(node_id, {})["state"] = data.get("state", "online")
        if data.get("profile"):
            incoming_profile = dict(data["profile"])
            previous_profile = manager.seeder_info[node_id].get("profile", {})
            for trust_key in ("canary_failures", "canary_quarantined"):
                if trust_key in previous_profile:
                    incoming_profile[trust_key] = previous_profile[trust_key]
            manager.seeder_info[node_id]["profile"] = incoming_profile
        # Update heartbeat
        if DB_AVAILABLE:
            db = get_db()
            try:
                seeder = db.query(Seeder).filter(Seeder.node_id == node_id).first()
                if seeder:
                    seeder.last_heartbeat = datetime.utcnow()
                    seeder.status = data.get("state", "online")
                    if data.get("profile"):
                        profile = dict(data["profile"])
                        for trust_key in ("canary_failures", "canary_quarantined"):
                            if trust_key in (seeder.profile or {}):
                                profile[trust_key] = seeder.profile[trust_key]
                        seeder.profile = profile
                    db.commit()
            finally:
                db.close()
        elif node_id in MOCK_SEEDERS:
            MOCK_SEEDERS[node_id]["status"] = data.get("state", "online")
        await allocate_pending_tasks()
    
    elif msg_type == "status_update":
        task_id = data.get("task_id")
        state = data.get("state")
        if state not in {"queued", "downloading", "running", "completed", "failed"}:
            return
        cleanup_ids = []
        
        if DB_AVAILABLE:
            db = get_db()
            try:
                task = db.query(Task).filter(Task.task_id == task_id).first()
                if task and task.status not in {"completed", "failed"}:
                    chunk = next((c for c in (task.chunks or []) if c["chunk_id"] == data.get("chunk_id") and c.get("assigned_to") == node_id), None)
                    if chunk and state in {"running", "failed"}:
                        if state == "running":
                            chunk["status"] = "running"
                            task.status = "running"
                        else:
                            chunk["failure_reason"] = str(data.get("reason", "Provider reported failure"))[:500]
                            chunk["providers"] = [provider for provider in chunk.get("providers", []) if provider != node_id]
                            chunk["status"] = "pending" if chunk.get("attempts", 0) < 3 else "failed"
                            chunk["assigned_to"] = None
                            task.chunks = task.chunks
                            unfinished = [c for c in task.chunks if c.get("status") != "verified"]
                            task.status = "failed" if any(c.get("status") == "failed" for c in unfinished) else "pending"
                            if task.status == "failed":
                                task.result = {"error": chunk["failure_reason"]}
                                task.completed_at = datetime.utcnow()
                                cleanup_ids = [c["chunk_id"] for c in task.chunks if c.get("swarm")]
                    db.commit()
                seeder = db.query(Seeder).filter(Seeder.node_id == node_id).first()
                if seeder:
                    seeder.status = "idle" if state in {"completed", "failed"} else "busy"
                    db.commit()
                    if state == "failed":
                        manager.seeder_info.setdefault(node_id, {})["busy"] = False
            finally:
                db.close()
        elif task_id in MOCK_TASKS and MOCK_TASKS[task_id].get("status") not in {"completed", "failed"}:
        task = MOCK_TASKS[task_id]
        if task.get("submitter_id") == "__system_canary__":
            raise HTTPException(status_code=404, detail="Task not found")
            chunk = next((c for c in task["chunks"] if c["chunk_id"] == data.get("chunk_id") and c.get("assigned_to") == node_id), None)
            if chunk and state == "running":
                chunk["status"] = "running"
                task["status"] = "running"
            elif chunk and state == "failed":
                chunk["failure_reason"] = str(data.get("reason", "Provider reported failure"))[:500]
                chunk["providers"] = [provider for provider in chunk.get("providers", []) if provider != node_id]
                chunk["status"] = "pending" if chunk.get("attempts", 0) < 3 else "failed"
                chunk["assigned_to"] = None
                task["status"] = "failed" if chunk["status"] == "failed" else "pending"
                if node_id in MOCK_SEEDERS:
                    MOCK_SEEDERS[node_id]["status"] = "idle"
                if task["status"] == "failed":
                    task["result"] = {"error": chunk["failure_reason"]}
                    task["completed_at"] = datetime.utcnow().isoformat()
                    cleanup_ids = [item["chunk_id"] for item in task["chunks"] if item.get("swarm")]
        if state in {"completed", "failed"}:
            manager.seeder_info.setdefault(node_id, {})["busy"] = False
        for cleanup_id in cleanup_ids:
            await asyncio.to_thread(teardown_chunk_swarm, cleanup_id)
        if state == "failed":
            await allocate_pending_tasks()
    
    elif msg_type == "result_submit":
        task_id = data.get("task_id")
        chunk_id = data.get("chunk_id")
        output = data.get("output")
        output_hash = data.get("output_hash")
        if not task_id or not chunk_id or not isinstance(output, str) or not output_hash:
            return
        if hashlib.sha256(output.encode("utf-8")).hexdigest() != output_hash:
            return
        accepted = False
        canary_rejected = False
        status = "rejected"
        credits = 0
        notices = []
        cleanup_ids = []
        if DB_AVAILABLE:
            db = get_db()
            try:
                task = db.query(Task).filter(Task.task_id == task_id).first()
                if not task or task.status in {"completed", "failed"}:
                    return
                chunks = task.chunks or []
                chunk = next((item for item in chunks if item["chunk_id"] == chunk_id), None)
                if not chunk or chunk.get("assigned_to") != node_id or chunk.get("status") not in {"assigned", "running"}:
                    return
                hidden_canary = chunk.get("hidden_canary")
                if hidden_canary and output_hash != hidden_canary.get("expected_output_sha256"):
                    chunk["status"] = "failed"
                    chunk["failure_reason"] = "Hidden canary result mismatch"
                    task.status = "failed"
                    task.result = {"error": "Internal canary verification failed"}
                    seeder = db.query(Seeder).filter(Seeder.node_id == node_id).first()
                    if seeder:
                        profile = dict(seeder.profile or {})
                        profile["canary_failures"] = int(profile.get("canary_failures", 0)) + 1
                        profile["canary_quarantined"] = profile["canary_failures"] >= 3
                        seeder.profile = profile
                        manager.seeder_info.setdefault(node_id, {}).setdefault("profile", {}).update(profile)
                    task.chunks = chunks
                    cleanup_ids = [item["chunk_id"] for item in chunks if item.get("swarm")]
                    db.add(ChunkResult(task_id=task_id, chunk_id=chunk_id, seeder_id=node_id,
                                       output_hash=output_hash, output_ref="inline", status="canary_failed"))
                    db.commit()
                    canary_rejected = True
                    notices = [node_id]
                if canary_rejected:
                    pass
                else:
                    replica_results = chunk.setdefault("replica_results", [])
                    if any(row.get("seeder_id") == node_id for row in replica_results):
                        return
                    replica_results.append({"output": output, "output_sha256": output_hash,
                                            "seeder_id": node_id,
                                            "canary_passed": bool(hidden_canary),
                                            "canary_id": hidden_canary.get("id") if hidden_canary else None})
                    decision = verify_replicas(replica_results, chunk.get("replicas_required", 1),
                                               task_id=task_id, chunk_id=chunk_id,
                                               model_sha256=chunk.get("model_sha256", ""),
                                               prompt_sha256=chunk.get("payload_sha256", ""))
                    if len(replica_results) < chunk.get("replicas_required", 1):
                        chunk["status"] = "pending"
                        chunk["assigned_to"] = None
                        task.status = "running"
                        status = "pending"
                    elif decision["verified"]:
                        chunk["status"] = "verified"
                        chunk["output"] = decision["output"]
                        chunk["output_sha256"] = decision["winner_hash"]
                        task.status = "running"
                        status = "verified"
                        winning = [row for row in replica_results if row["output_sha256"] == decision["winner_hash"]]
                        credits = max(1, len(decision["output"]) // 100)
                        for row in winning:
                            provider = db.query(Seeder).filter(Seeder.node_id == row["seeder_id"]).first()
                            if provider:
                                provider.credits_earned += credits
                                provider.tasks_completed += 1
                            db.add(CreditLedger(account_id=row["seeder_id"], entry_type="verified_work", amount=credits,
                                                task_id=task_id, description=f"Verified inference chunk {chunk_id}"))
                            notices.append(row["seeder_id"])
                    else:
                        chunk["status"] = "failed"
                        task.status = "failed"
                        task.result = {"error": "Replica outputs disagree; verification failed", "chunk_id": chunk_id}
                        status = "rejected"
                        notices = [row["seeder_id"] for row in replica_results]
                    chunk["verification"] = {"method": "SERENE-lite + VeriLLM-inspired audit",
                                              "canary": {"id": hidden_canary.get("id"), "passed": True} if hidden_canary else None,
                                              **decision}
                    task.chunks = chunks
                    completed_chunks = sorted((c for c in chunks if c["status"] == "verified"), key=lambda c: c["index"])
                    all_done = len(completed_chunks) == len(chunks)
                    if all_done:
                        task.status = "completed"
                        task.completed_at = datetime.utcnow()
                        task.result = {"outputs": [c["output"] for c in completed_chunks],
                                       "text": "\n".join(c["output"] for c in completed_chunks),
                                       "verification": "SERENE-lite replica agreement + VeriLLM-inspired transcript audit",
                                       "chunks": [{"chunk_id": c["chunk_id"], "index": c["index"], "sha256": c["output_sha256"],
                                                   "verification": c.get("verification")} for c in completed_chunks]}
                    if task.status == "failed" or all_done:
                        cleanup_ids = [c["chunk_id"] for c in chunks if c.get("swarm")]
                    db.add(ChunkResult(task_id=task_id, chunk_id=chunk_id, seeder_id=node_id,
                                       output_hash=output_hash, output_ref="inline", status=status))
                    db.commit()
                    accepted = True
            finally:
                db.close()
        else:
            task = MOCK_TASKS.get(task_id)
            if not task or task.get("status") in {"completed", "failed"}:
                return
            chunk = next((item for item in task["chunks"] if item["chunk_id"] == chunk_id), None)
            if not chunk or chunk.get("assigned_to") != node_id or chunk.get("status") not in {"assigned", "running"}:
                return
            hidden_canary = chunk.get("hidden_canary")
            if hidden_canary and output_hash != hidden_canary.get("expected_output_sha256"):
                chunk["status"] = "failed"
                chunk["failure_reason"] = "Hidden canary result mismatch"
                task["status"] = "failed"
                task["result"] = {"error": "Internal canary verification failed"}
                cleanup_ids = [item["chunk_id"] for item in task["chunks"] if item.get("swarm")]
                profile = MOCK_SEEDERS.get(node_id, {}).get("profile", {})
                profile["canary_failures"] = int(profile.get("canary_failures", 0)) + 1
                profile["canary_quarantined"] = profile["canary_failures"] >= 3
                manager.seeder_info.setdefault(node_id, {}).setdefault("profile", {}).update(profile)
                canary_rejected = True
                notices = [node_id]
            else:
                replica_results = chunk.setdefault("replica_results", [])
                if any(row.get("seeder_id") == node_id for row in replica_results):
                    return
                replica_results.append({"output": output, "output_sha256": output_hash, "seeder_id": node_id,
                                        "canary_passed": bool(hidden_canary),
                                        "canary_id": hidden_canary.get("id") if hidden_canary else None})
                decision = verify_replicas(replica_results, chunk.get("replicas_required", 1),
                                           task_id=task_id, chunk_id=chunk_id,
                                           model_sha256=chunk.get("model_sha256", ""),
                                           prompt_sha256=chunk.get("payload_sha256", ""))
                if len(replica_results) < chunk.get("replicas_required", 1):
                    chunk["status"], chunk["assigned_to"] = "pending", None
                    task["status"], status = "running", "pending"
                elif decision["verified"]:
                    chunk["status"], chunk["output"], chunk["output_sha256"] = "verified", decision["output"], decision["winner_hash"]
                    task["status"], status = "running", "verified"
                    credits = max(1, len(decision["output"]) // 100)
                    notices = [row["seeder_id"] for row in replica_results if row["output_sha256"] == decision["winner_hash"]]
                    for provider_id in notices:
                        if provider_id in MOCK_SEEDERS:
                            MOCK_SEEDERS[provider_id]["tasks_completed"] += 1
                            MOCK_SEEDERS[provider_id]["credits_earned"] += credits
                        MOCK_CREDIT_LEDGER.append({"account_id": provider_id, "entry_type": "verified_work", "amount": credits,
                                                   "task_id": task_id, "description": f"Verified inference chunk {chunk_id}",
                                                   "created_at": datetime.utcnow().isoformat()})
                else:
                    chunk["status"], task["status"], status = "failed", "failed", "rejected"
                    task["result"] = {"error": "Replica outputs disagree; verification failed", "chunk_id": chunk_id}
                    notices = [row["seeder_id"] for row in replica_results]
                chunk["verification"] = {"method": "SERENE-lite + VeriLLM-inspired audit",
                                          "canary": {"id": hidden_canary.get("id"), "passed": True} if hidden_canary else None,
                                          **decision}
                completed_chunks = sorted((c for c in task["chunks"] if c["status"] == "verified"), key=lambda c: c["index"])
                all_done = len(completed_chunks) == len(task["chunks"])
                if all_done:
                    task["status"] = "completed"
                    task["completed_at"] = datetime.utcnow().isoformat()
                    task["result"] = {"outputs": [c["output"] for c in completed_chunks],
                                      "text": "\n".join(c["output"] for c in completed_chunks),
                                      "verification": "SERENE-lite replica agreement + VeriLLM-inspired transcript audit"}
                if task["status"] == "failed" or all_done:
                    cleanup_ids = [c["chunk_id"] for c in task["chunks"] if c.get("swarm")]
                if node_id in MOCK_SEEDERS:
                    MOCK_SEEDERS[node_id]["status"] = "idle"
                accepted = True
        if canary_rejected:
            manager.seeder_info.setdefault(node_id, {})["busy"] = False
            for cleanup_id in cleanup_ids:
                await asyncio.to_thread(teardown_chunk_swarm, cleanup_id)
            await manager.send_to_seeder({"type": "verdict_notice", "task_id": task_id,
                "chunk_id": chunk_id, "verdict": "rejected", "credits_earned": 0}, node_id)
            await allocate_pending_tasks()
            return
        manager.seeder_info.setdefault(node_id, {})["busy"] = False
        for provider_id in set(notices or [node_id]):
            await manager.send_to_seeder({"type": "verdict_notice", "task_id": task_id,
                "chunk_id": chunk_id, "verdict": status, "credits_earned": credits if status == "verified" else 0}, provider_id)
        for cleanup_id in cleanup_ids:
            await asyncio.to_thread(teardown_chunk_swarm, cleanup_id)
        await allocate_pending_tasks()

async def allocate_pending_tasks():
    """Persist chunk leases, then dispatch one independent prompt per idle worker."""
    available_seeders = manager.get_available_seeders()
    if not available_seeders:
        return
    idle = [sid for sid in available_seeders if manager.seeder_info.get(sid, {}).get("busy") is not True
            and manager.seeder_info.get(sid, {}).get("state") != "paused"
            and (DB_AVAILABLE or MOCK_SEEDERS.get(sid, {}).get("status") != "busy")]
    if not idle:
        return
    assignments = []
    if DB_AVAILABLE:
        db = get_db()
        try:
            tasks = db.query(Task).filter(Task.status.in_(["pending", "allocated", "running"])).order_by(Task.created_at).all()
            jobs = [(task, chunk) for task in tasks for chunk in (task.chunks or []) if chunk.get("status") == "pending"]
            for task, chunk in jobs:
                eligible = [sid for sid in idle if sid not in chunk.get("providers", [])]
                seeder_id = manager.choose_provider(eligible, chunk)
                if seeder_id is None:
                    continue
                idle.remove(seeder_id)
                try:
                    swarm = chunk.get("swarm") or await asyncio.to_thread(create_chunk_swarm, chunk["chunk_id"], chunk["prompts"][0])
                except Exception as exc:
                    chunk["failure_reason"] = f"Swarm unavailable: {exc}"[:500]
                    continue
                chunk["swarm"] = swarm
                chunk["status"], chunk["assigned_to"] = "assigned", seeder_id
                chunk["attempts"] = chunk.get("attempts", 0) + 1
                if seeder_id not in chunk.setdefault("providers", []):
                    chunk["providers"].append(seeder_id)
                task.chunks = task.chunks
                task.status = "allocated"
                assignments.append((seeder_id, {"type": "task_assign", "task_id": task.task_id,
                    "chunk_id": chunk["chunk_id"], "swarm_id": swarm["magnet_uri"],
                    "payload_sha256": swarm["payload_sha256"], "model_name": task.model_name,
                    "model_file": chunk["model_file"], "model_sha256": chunk["model_sha256"],
                    "adapter_file": chunk.get("adapter_file"), "adapter_sha256": chunk.get("adapter_sha256"),
                    "model_magnet_uri": MODEL_REGISTRY.get(task.model_name, {}).get("magnet_uri"),
                    "docker_image": os.getenv("COMPUTETORRENT_LLAMA_CUDA_IMAGE", "ghcr.io/ggml-org/llama.cpp:full-cuda") if chunk.get("requirements", {}).get("require_cuda") else os.getenv("COMPUTETORRENT_LLAMA_IMAGE", "ghcr.io/ggml-org/llama.cpp:light"),
                    "require_cuda": bool(chunk.get("requirements", {}).get("require_cuda")),
                    "cuda_available": bool((manager.seeder_info.get(seeder_id, {}).get("profile", {})).get("CUDA")),
                    "timeout_seconds": 1800, "max_tokens": chunk["max_tokens"], "seed": chunk["seed"],
                    "index": chunk["index"], "manifest_mode": chunk.get("mode", "WS-RR")}))
            db.commit()
        finally:
            db.close()
    else:
        jobs = [(task, chunk) for task in MOCK_TASKS.values() if task["status"] in {"pending", "allocated", "running"}
                for chunk in task.get("chunks", []) if chunk.get("status") == "pending"]
        for task, chunk in jobs:
            eligible = [sid for sid in idle if sid not in chunk.get("providers", [])]
            seeder_id = manager.choose_provider(eligible, chunk)
            if seeder_id is None:
                continue
            idle.remove(seeder_id)
            try:
                swarm = chunk.get("swarm") or await asyncio.to_thread(create_chunk_swarm, chunk["chunk_id"], chunk["prompts"][0])
            except Exception as exc:
                chunk["failure_reason"] = f"Swarm unavailable: {exc}"[:500]
                continue
            chunk["swarm"] = swarm
            chunk["status"], chunk["assigned_to"] = "assigned", seeder_id
            chunk["attempts"] = chunk.get("attempts", 0) + 1
            if seeder_id not in chunk.setdefault("providers", []):
                chunk["providers"].append(seeder_id)
            task["status"] = "allocated"
            assignments.append((seeder_id, {"type": "task_assign", "task_id": task["task_id"],
                "chunk_id": chunk["chunk_id"], "swarm_id": swarm["magnet_uri"],
                "payload_sha256": swarm["payload_sha256"],
                "model_name": task["model_name"], "model_file": chunk["model_file"],
                "model_sha256": chunk["model_sha256"],
                "adapter_file": chunk.get("adapter_file"), "adapter_sha256": chunk.get("adapter_sha256"),
                "model_magnet_uri": MODEL_REGISTRY.get(task["model_name"], {}).get("magnet_uri"),
                "docker_image": os.getenv("COMPUTETORRENT_LLAMA_CUDA_IMAGE", "ghcr.io/ggml-org/llama.cpp:full-cuda") if chunk.get("requirements", {}).get("require_cuda") else os.getenv("COMPUTETORRENT_LLAMA_IMAGE", "ghcr.io/ggml-org/llama.cpp:light"),
                "require_cuda": bool(chunk.get("requirements", {}).get("require_cuda")),
                "cuda_available": bool((manager.seeder_info.get(seeder_id, {}).get("profile", {})).get("CUDA")),
                "timeout_seconds": 1800, "max_tokens": chunk["max_tokens"], "seed": chunk["seed"],
                "index": chunk["index"], "manifest_mode": chunk.get("mode", "WS-RR")}))
    for seeder_id, assignment in assignments:
        manager.seeder_info.setdefault(seeder_id, {})["busy"] = True
        if seeder_id in MOCK_SEEDERS:
            MOCK_SEEDERS[seeder_id]["status"] = "busy"
        if not await manager.send_to_seeder(assignment, seeder_id):
            manager.seeder_info.setdefault(seeder_id, {})["busy"] = False
            if DB_AVAILABLE:
                db = get_db()
                try:
                    task = db.query(Task).filter(Task.task_id == assignment["task_id"]).first()
                    chunk = next((item for item in (task.chunks or []) if item["chunk_id"] == assignment["chunk_id"]), None) if task else None
                    if chunk and chunk.get("assigned_to") == seeder_id:
                        chunk["assigned_to"] = None
                        chunk["providers"] = [provider for provider in chunk.get("providers", []) if provider != seeder_id]
                        chunk["status"] = "pending"
                        chunk["failure_reason"] = "Provider disconnected before assignment delivery"
                        task.chunks = task.chunks
                        task.status = "pending"
                        db.commit()
                finally:
                    db.close()
            else:
                task = MOCK_TASKS.get(assignment["task_id"])
                chunk = next((item for item in task.get("chunks", []) if item["chunk_id"] == assignment["chunk_id"]), None) if task else None
                if chunk and chunk.get("assigned_to") == seeder_id:
                    chunk["assigned_to"] = None
                    chunk["providers"] = [provider for provider in chunk.get("providers", []) if provider != seeder_id]
                    chunk["status"] = "pending"
                    chunk["failure_reason"] = "Provider disconnected before assignment delivery"
                    task["status"] = "pending"

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting ComputeTorrent Orchestrator...")
    print(f"   Database: {'Connected' if DB_AVAILABLE else 'Mock mode'}")
    print(f"   API will run on: http://localhost:8001")
    print(f"   WebSocket: ws://localhost:8001/ws/seeder")
    uvicorn.run(app, host="0.0.0.0", port=8001)
