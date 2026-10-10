import customtkinter as ctk
import asyncio
import threading
import psutil
import subprocess
import websockets
import json
import time
from datetime import datetime
import os
import tempfile
import shutil
import hashlib
import sys
import uuid
import urllib.request
import urllib.error
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from inference_runtime import run_inference

_SYNC_SRC = Path(__file__).resolve().parents[1] / "04-webtorrent-sync" / "src"
sys.path.insert(0, str(_SYNC_SRC))
from webtorrent_client import WebTorrentClient

if getattr(sys, "frozen", False):
    bundle_root = Path(sys._MEIPASS)
    os.environ.setdefault("COMPUTETORRENT_WEBTORRENT_HELPER", str(bundle_root / "webtorrent" / "webtorrent_helper.mjs"))
    os.environ.setdefault("COMPUTETORRENT_LIBP2P_HELPER", str(bundle_root / "webtorrent" / "libp2p_peer.mjs"))
    node_binary = bundle_root / "node.exe"
    if node_binary.is_file():
        os.environ.setdefault("COMPUTETORRENT_NODE", str(node_binary))

def uuid_safe(value):
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")[:48] or "task"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Configuration
DEFAULT_ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "ws://127.0.0.1:8001/ws/seeder")

class ComputeTorrentSeeder(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ComputeTorrent Provider")
        self.geometry("980x820")
        self.minsize(760, 640)
        self.resizable(True, True)
        
        # State
        self.websocket = None
        self.is_connected = False
        self.current_task = None
        self.tasks_completed = 0
        self.credits_earned = 0
        self.app_data = Path(os.getenv("LOCALAPPDATA", tempfile.gettempdir())) / "ComputeTorrent"
        self.app_data.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.app_data / "seeder-settings.json"
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = {}
        had_legacy_join_code = "enrollment_token" in self.settings
        self.settings.pop("enrollment_token", None)
        self.recent_work = list(self.settings.get("recent_work", []))[-20:]
        os.environ.setdefault("COMPUTETORRENT_MODELS_DIR", str(self.app_data / "models"))
        self.sync_client = WebTorrentClient(str(self.app_data))
        self.libp2p_process = None
        self.libp2p_log = None
        self.libp2p_helper = Path(os.getenv("COMPUTETORRENT_LIBP2P_HELPER", str(_SYNC_SRC / "libp2p_peer.mjs"))).resolve()
        self.node_binary = os.getenv("COMPUTETORRENT_NODE", "node")
        self.node_id = self.settings.get("node_id")
        self.access_token = self.settings.get("access_token")
        self.orchestrator_url = self.settings.get("orchestrator_url", DEFAULT_ORCHESTRATOR_URL)
        # The network-wide enrollment code is a one-time secret; keep it in
        # memory only and persist only this provider's revocable credential.
        self.enrollment_token = ""
        self.cpu_limit = int(self.settings.get("cpu_limit", 2))
        self.memory_limit_gb = int(self.settings.get("memory_limit_gb", 8))
        self.paused = False
        self.event_loop = None
        self.shutting_down = False
        
        # Detect hardware
        self.profile = self.detect_hardware()
        if had_legacy_join_code:
            self.save_settings()
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        
        # Show onboarding
        self.show_onboarding()
    
    def detect_hardware(self):
        """Detect system hardware"""
        ram_gb = psutil.virtual_memory().total // (1024 ** 3)
        cpu_cores = psutil.cpu_count() or 1
        
        # GPU detection
        gpu = None
        vram = 0
        cuda = False
        
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(',')
                gpu = parts[0].strip()
                vram = int(float(parts[1].strip()))
                cuda = True
        except:
            pass
        
        # Docker check
        docker_ok = False
        try:
            result = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True, timeout=5)
            docker_ok = result.returncode == 0
        except:
            pass
        
        # Tier determination
        if cuda and vram >= 8192:
            tier = 1  # Tier 1: GPU with 8GB+ VRAM
        else:
            tier = 2  # Tier 2: CPU or low VRAM
        
        return {
            "GPU": gpu,
            "VRAM": vram,
            "CUDA": cuda,
            "RAM": ram_gb,
            "cpu_cores": cpu_cores,
            "docker_ok": docker_ok,
            "tier": tier
        }
    
    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()
    
    def show_onboarding(self):
        self.clear_screen()
        frame = ctk.CTkScrollableFrame(self)
        frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Header
        title = ctk.CTkLabel(frame, text="ComputeTorrent Provider",
                           font=("Arial", 28, "bold"))
        title.pack(pady=20)
        
        subtitle = ctk.CTkLabel(frame, text="🌐 Volunteer-computing node",
                              font=("Arial", 14), text_color="gray")
        subtitle.pack(pady=5)
        
        # Hardware info
        info_title = ctk.CTkLabel(frame, text="📊 Hardware Profile", 
                                font=("Arial", 18, "bold"))
        info_title.pack(pady=(30, 15))
        
        info_text = f"""System Configuration:

💻 CPU: {self.profile['cpu_cores']} cores
🧠 RAM: {self.profile['RAM']} GB
🎮 GPU: {self.profile['GPU'] or 'None (CPU mode)'}
💾 VRAM: {self.profile['VRAM'] / 1024:.1f} GB
🐳 Docker: {'✅ Available' if self.profile['docker_ok'] else '❌ Not Available'}

📊 Capability Tier: {self.profile['tier']}
{'✨ Tier 1 - Eligible for GPU inference tasks' if self.profile['tier'] == 1 else '⚡ Tier 2 - Eligible for CPU inference tasks'}

💰 Verified contribution credits are demo accounting with no cash value.
"""
        
        info_box = ctk.CTkTextbox(frame, height=230, width=750, font=("Courier New", 11))
        info_box.pack(pady=20, padx=20)
        info_box.insert("1.0", info_text)
        info_box.configure(state="disabled")

        connection_card = ctk.CTkFrame(frame)
        connection_card.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(connection_card, text="Network connection", font=("Arial", 15, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(connection_card,
            text="Use the coordinator PC's private LAN address on other computers. Never enter localhost from a different PC.",
            wraplength=790, justify="left", text_color="#aebbd1").pack(anchor="w", padx=12, pady=(0, 5))
        ctk.CTkLabel(connection_card,
            text="Examples: this PC: ws://127.0.0.1:8001/ws/seeder  ·  another PC: ws://192.168.1.5:8001/ws/seeder",
            wraplength=790, justify="left", text_color="#8fa4d4").pack(anchor="w", padx=12, pady=(0, 5))
        self.server_entry = ctk.CTkEntry(connection_card, width=680, placeholder_text="ws://127.0.0.1:8001/ws/seeder")
        self.server_entry.pack(fill="x", padx=12, pady=(4, 8))
        self.server_entry.insert(0, self.orchestrator_url)
        ctk.CTkLabel(connection_card, text="Provider enrollment code from your network operator").pack(anchor="w", padx=12)
        self.enrollment_entry = ctk.CTkEntry(connection_card, width=680, show="•", placeholder_text="One-time network join code")
        self.enrollment_entry.pack(fill="x", padx=12, pady=(4, 8))
        if self.enrollment_token:
            self.enrollment_entry.insert(0, self.enrollment_token)
        ctk.CTkLabel(connection_card,
            text="Ask the operator for the join code from their private .env file. Each enrolled PC receives its own revocable credential.",
            wraplength=790, justify="left", text_color="#aebbd1").pack(anchor="w", padx=12, pady=(0, 6))
        limits = ctk.CTkFrame(connection_card, fg_color="transparent")
        limits.pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(limits, text="Max CPU cores").pack(side="left")
        self.cpu_entry = ctk.CTkEntry(limits, width=75)
        self.cpu_entry.pack(side="left", padx=(8, 24))
        self.cpu_entry.insert(0, str(self.cpu_limit))
        ctk.CTkLabel(limits, text="Max RAM (GB)").pack(side="left")
        self.memory_entry = ctk.CTkEntry(limits, width=75)
        self.memory_entry.pack(side="left", padx=8)
        self.memory_entry.insert(0, str(self.memory_limit_gb))
        self.connection_error = ctk.CTkLabel(connection_card, text="", text_color="#ff7070")
        self.connection_error.pack(anchor="w", padx=12)
        
        if not self.profile['docker_ok']:
            warning = ctk.CTkLabel(frame, 
                text="⚠️ Warning: Docker is required for task execution",
                text_color="orange", font=("Arial", 12, "bold"))
            warning.pack(pady=10)
        
        # Connect button
        connect_btn = ctk.CTkButton(frame, text="🚀 Connect to Network", 
                                   command=self.start_connection,
                                   height=50, font=("Arial", 16, "bold"),
                                   fg_color="#00d4ff", hover_color="#0084ff")
        connect_btn.pack(pady=25)
        
        # Footer
        footer = ctk.CTkLabel(frame, 
            text=f"Node ID: {self.node_id or 'New provider'} • Orchestrator: {self.orchestrator_url}",
            font=("Courier New", 9), text_color="gray")
        footer.pack(pady=10)
    
    def start_connection(self):
        """Start connection to orchestrator"""
        self.orchestrator_url = self.server_entry.get().strip()
        self.enrollment_token = self.enrollment_entry.get().strip()
        parsed = urlsplit(self.orchestrator_url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc or not parsed.path.endswith("/ws/seeder"):
            self.connection_error.configure(text="Enter a valid ws:// or wss:// coordinator URL ending in /ws/seeder")
            return
        if not self.access_token and not self.enrollment_token:
            self.connection_error.configure(text="An enrollment code is required for this computer's first connection")
            return
        try:
            self.cpu_limit = min(max(int(self.cpu_entry.get()), 1), max(1, self.profile["cpu_cores"]))
            self.memory_limit_gb = min(max(int(self.memory_entry.get()), 2), max(2, self.profile["RAM"]))
        except ValueError:
            self.connection_error.configure(text="CPU and RAM limits must be whole numbers")
            return
        self.settings.update({"orchestrator_url": self.orchestrator_url,
                              "cpu_limit": self.cpu_limit, "memory_limit_gb": self.memory_limit_gb})
        self.save_settings()
        self.show_dashboard()
        thread = threading.Thread(target=self.run_websocket, daemon=True)
        thread.start()

    def save_settings(self):
        self.settings.update({"node_id": self.node_id, "access_token": self.access_token,
                              "orchestrator_url": self.orchestrator_url,
                              "cpu_limit": self.cpu_limit, "memory_limit_gb": self.memory_limit_gb,
                              "recent_work": self.recent_work[-20:]})
        self.settings.pop("enrollment_token", None)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def enroll_provider(self):
        parsed = urlsplit(self.orchestrator_url)
        scheme = "https" if parsed.scheme == "wss" else "http"
        enrollment_url = urlunsplit((scheme, parsed.netloc, "/api/seeders/enroll", "", ""))
        payload = json.dumps({"tier": self.profile["tier"], "profile": self.profile}).encode("utf-8")
        request = urllib.request.Request(enrollment_url, data=payload, method="POST", headers={
            "Content-Type": "application/json", "X-Enrollment-Token": self.enrollment_token})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                enrollment = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[-300:]
            raise RuntimeError(f"Provider enrollment failed ({error.code}): {detail}") from error
        self.node_id = enrollment["node_id"]
        self.access_token = enrollment["access_token"]
        self.enrollment_token = ""
        self.save_settings()
    
    def run_websocket(self):
        """Run WebSocket connection"""
        self.start_libp2p_peer()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.event_loop = loop
        loop.run_until_complete(self.connect_to_orchestrator())

    def start_libp2p_peer(self):
        """Join the optional LAN discovery/relay overlay (not the file data plane)."""
        if self.libp2p_process and self.libp2p_process.poll() is None:
            return
        try:
            parsed = urlsplit(self.orchestrator_url)
            hostname = parsed.hostname
            if not hostname:
                raise ValueError("Coordinator URL has no host")
            host_part = f"[{hostname}]" if ":" in hostname else hostname
            scheme = "https" if parsed.scheme == "wss" else "http"
            coordinator_port = f":{parsed.port}" if parsed.port else (":443" if scheme == "https" else ":80")
            peer_info_url = f"{scheme}://{host_part}{coordinator_port}/api/network/bootstrap"
            with urllib.request.urlopen(peer_info_url, timeout=8) as response:
                peer_info = json.loads(response.read().decode("utf-8"))
            bootstrap_address = peer_info.get("multiaddr")
            if not isinstance(bootstrap_address, str) or "/p2p/" not in bootstrap_address:
                raise RuntimeError("Coordinator did not provide a valid libp2p relay address")
            if not self.libp2p_helper.is_file():
                raise FileNotFoundError(f"libp2p helper is missing: {self.libp2p_helper}")
            self.libp2p_log = (self.app_data / "libp2p.log").open("a", encoding="utf-8")
            self.libp2p_process = subprocess.Popen(
                [self.node_binary, str(self.libp2p_helper), "join", bootstrap_address],
                cwd=str(self.libp2p_helper.parent), stdin=subprocess.DEVNULL,
                stdout=self.libp2p_log, stderr=self.libp2p_log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.update_status("Joining libp2p LAN discovery and relay overlay…")
            time.sleep(1.0)
            if self.libp2p_process.poll() is not None:
                raise RuntimeError("libp2p peer exited during startup; see %LOCALAPPDATA%\\ComputeTorrent\\libp2p.log")
            self.update_status("LAN peer overlay connected; files still transfer over WebTorrent")
        except Exception as error:
            self.update_status(f"LAN peer overlay unavailable ({error}); WebTorrent transfer remains active")

    def close_application(self):
        """Stop the background peer before closing the desktop app."""
        if self.shutting_down:
            return
        self.shutting_down = True
        if self.websocket and self.event_loop and self.event_loop.is_running():
            try:
                close_future = asyncio.run_coroutine_threadsafe(self.websocket.close(), self.event_loop)
                close_future.result(timeout=3)
            except Exception:
                pass
        if self.libp2p_process and self.libp2p_process.poll() is None:
            self.libp2p_process.terminate()
            try:
                self.libp2p_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.libp2p_process.kill()
        if self.libp2p_log:
            self.libp2p_log.close()
        try:
            self.destroy()
        except Exception:
            pass
    
    async def connect_to_orchestrator(self):
        """Connect to orchestrator via WebSocket"""
        retry_count = 0
        while not self.shutting_down:
            try:
                self.update_status(f"Connecting to {self.orchestrator_url}...")
                if not self.access_token:
                    self.update_status("Enrolling this computer with the network...")
                    await asyncio.to_thread(self.enroll_provider)

                async with websockets.connect(
                    self.orchestrator_url,
                    extra_headers={"Authorization": f"Bearer {self.access_token}"},
                    open_timeout=30, ping_interval=30, ping_timeout=30,
                ) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    retry_count = 0
                    
                    # Send registration
                    register_msg = {
                        "type": "register",
                        "node_id": self.node_id,
                        "tier": self.profile["tier"],
                        "profile": {
                            "GPU": self.profile["GPU"],
                            "VRAM": self.profile["VRAM"],
                            "CUDA": self.profile["CUDA"],
                            "RAM": self.profile["RAM"],
                            "cpu_cores": self.profile["cpu_cores"],
                            "docker_ok": self.profile["docker_ok"]
                        }
                    }
                    
                    await websocket.send(json.dumps(register_msg))
                    self.update_status("✅ Connected & Registered!")
                    
                    # Start heartbeat
                    heartbeat_task = asyncio.create_task(self.send_heartbeats(websocket))
                    
                    # Message loop
                    try:
                        async for message in websocket:
                            await self.handle_message(message)
                    except websockets.exceptions.ConnectionClosed:
                        self.update_status("❌ Connection lost. Reconnecting...")
                    finally:
                        heartbeat_task.cancel()
                        self.websocket = None
                        self.is_connected = False
                        
            except Exception as e:
                if self.shutting_down:
                    break
                self.update_status(f"Connection issue: {e}")
            retry_count += 1
            delay = min(60, 2 ** min(retry_count, 6))
            if self.shutting_down:
                break
            self.update_status(f"Offline; retrying in {delay}s")
            await asyncio.sleep(delay)
    
    async def send_heartbeats(self, websocket):
        """Send periodic heartbeats"""
        while True:
            try:
                await self.send_heartbeat_once(websocket)
                await asyncio.sleep(10)
            except:
                break

    async def send_heartbeat_once(self, websocket):
        memory = psutil.virtual_memory()
        self.profile["free_ram_gb"] = round(memory.available / (1024 ** 3), 1)
        self.profile["cpu_load_pct"] = round(psutil.cpu_percent(interval=None), 1)
        self.profile["uptime_seconds"] = int(time.time() - psutil.boot_time())
        await websocket.send(json.dumps({
            "type": "heartbeat",
            "node_id": self.node_id,
            "state": "paused" if self.paused else ("busy" if self.current_task else "idle"),
            "profile": self.profile,
        }))
    
    async def handle_message(self, message):
        """Handle incoming messages"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "register_ack":
                self.tasks_completed = int(data.get("tasks_completed", self.tasks_completed))
                self.credits_earned = float(data.get("credits_earned", self.credits_earned))
                self.update_tasks_count(self.tasks_completed)
                self.update_credits(self.credits_earned)
                self.update_status("✅ Registration confirmed!")
            
            elif msg_type == "task_assign":
                if self.paused:
                    await self.send_status("failed", data.get("task_id"), "Provider is paused", data.get("chunk_id"))
                    return
                task_id = data.get("task_id")
                self.current_task = task_id
                self.update_task_info(f"📥 Task assigned: {task_id}")
                await self.execute_task(data)
            
            elif msg_type == "verdict_notice":
                credits = data.get("credits_earned", 0)
                self.credits_earned += credits
                self.update_credits(self.credits_earned)
                if data.get("verdict") == "verified":
                    self.tasks_completed += 1
                    self.update_tasks_count(self.tasks_completed)
                item = {"task_id": data.get("task_id"), "chunk_id": data.get("chunk_id"),
                        "verdict": data.get("verdict"), "credits": credits, "at": datetime.utcnow().isoformat()}
                self.recent_work = [item, *self.recent_work][:20]
                self.save_settings()
                self.update_work_history()
                self.update_task_info(f"{data.get('verdict', 'updated').title()} · {credits} credits")
                
        except Exception as e:
            print(f"Message error: {e}")
    
    async def execute_task(self, task_data):
        """Execute assigned task"""
        task_id = task_data.get("task_id")
        
        try:
            await self.send_status("queued", task_id, chunk_id=task_data.get("chunk_id"))
            self.update_task_info(f"📥 Downloading: {task_id}")
            await self.send_status("downloading", task_id, chunk_id=task_data.get("chunk_id"))
            model_path = Path(os.environ["COMPUTETORRENT_MODELS_DIR"]) / task_data["model_name"] / task_data["model_file"]
            if not model_path.is_file():
                await asyncio.to_thread(self.sync_client.download_from_swarm,
                    task_data.get("model_magnet_uri", ""), f"model-{task_data['model_name']}",
                    str(model_path.parent), task_data.get("model_sha256", ""), task_data["model_file"],
                    lambda progress: self.update_task_info(f"📥 Model download: {progress}"))
            if task_data.get("adapter_file"):
                adapter_path = model_path.parent / task_data["adapter_file"]
                if not adapter_path.is_file():
                    await asyncio.to_thread(self.sync_client.download_from_swarm,
                        task_data.get("model_magnet_uri", ""), f"model-{task_data['model_name']}-adapter",
                        str(model_path.parent), task_data.get("model_sha256", ""), task_data["model_file"],
                        lambda progress: self.update_task_info(f"📥 Model download: {progress}"))
            chunk_path = await asyncio.to_thread(self.sync_client.download_from_swarm,
                task_data.get("swarm_id", ""), task_data.get("chunk_id", task_id),
                str(self.sync_client.workspace / "workspace" / task_data.get("chunk_id", task_id)),
                task_data.get("payload_sha256", ""),
                progress_callback=lambda progress: self.update_task_info(f"📥 Task download: {progress}"))
            payload = json.loads(chunk_path.read_text(encoding="utf-8"))
            task_data["prompt"] = payload["prompt"]
            task_data["cpu_limit"] = self.cpu_limit
            task_data["memory_limit_gb"] = self.memory_limit_gb
            self.update_task_info(f"⚙️ Running: {task_id}")
            await self.send_status("running", task_id, chunk_id=task_data.get("chunk_id"))
            execution = await asyncio.to_thread(
                run_inference,
                task_data,
                workspace_dir=str(self.app_data / "workspace" / "inference"),
            )
            await self.send_result(task_data, execution)
            await self.send_status("completed", task_id, chunk_id=task_data.get("chunk_id"))
            
            self.current_task = None
            self.update_task_info("✅ Task completed! Waiting for next...")
            
        except Exception as e:
            self.update_task_info(f"❌ Task failed: {e}")
            await self.send_status("failed", task_id, str(e), task_data.get("chunk_id"))
        finally:
            if task_data.get("chunk_id"):
                await asyncio.to_thread(self.sync_client.leave_swarm, task_data["chunk_id"])
            self.current_task = None

    async def send_status(self, state, task_id, reason=None, chunk_id=None):
        """Send status update"""
        if self.websocket:
            message = {
                "type": "status_update",
                "task_id": task_id,
                "state": state,
                "chunk_id": chunk_id or f"{task_id}-chunk-0"
            }
            if reason:
                message["reason"] = reason[:500]
            await self.websocket.send(json.dumps(message))
    
    async def send_result(self, task_data, execution):
        """Send result"""
        if self.websocket:
            task_id = task_data.get("task_id")
            await self.websocket.send(json.dumps({
                "type": "result_submit",
                "task_id": task_id,
                "chunk_id": task_data.get("chunk_id"),
                "output_ref": "inline",
                "output_hash": execution["output_hash"],
                "output": execution["output"],
                "metrics": {"run_seconds": execution["run_seconds"], "runtime_image": execution["runtime_image"], "model_sha256": execution["model_sha256"]}
            }))
    
    def show_dashboard(self):
        self.clear_screen()
        frame = ctk.CTkScrollableFrame(self)
        frame.pack(fill="both", expand=True, padx=25, pady=25)
        
        # Title
        title = ctk.CTkLabel(frame, text="🖥️ Provider Dashboard",
                           font=("Arial", 24, "bold"))
        title.pack(pady=15)
        
        # Stats grid
        stats_frame = ctk.CTkFrame(frame)
        stats_frame.pack(fill="x", padx=15, pady=15)
        
        stats_grid = ctk.CTkFrame(stats_frame)
        stats_grid.pack(fill="x", padx=10, pady=10)
        
        # Status
        status_container = ctk.CTkFrame(stats_grid)
        status_container.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)
        
        self.status_label = ctk.CTkLabel(status_container, 
            text="Status: Initializing...", 
            font=("Arial", 14, "bold"))
        self.status_label.pack(pady=10)
        
        # Task info
        task_container = ctk.CTkFrame(stats_grid)
        task_container.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        
        self.task_label = ctk.CTkLabel(task_container, 
            text="Current Task: None", 
            font=("Arial", 12))
        self.task_label.pack(pady=8)
        
        # Metrics
        metrics_left = ctk.CTkFrame(stats_grid)
        metrics_left.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        ctk.CTkLabel(metrics_left, text="Verified Chunks", 
                    font=("Arial", 11, "bold")).pack(pady=5)
        self.count_label = ctk.CTkLabel(metrics_left, text="0", 
                                       font=("Arial", 24, "bold"),
                                       text_color="#00d4ff")
        self.count_label.pack(pady=5)
        
        metrics_right = ctk.CTkFrame(stats_grid)
        metrics_right.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
ctk.CTkLabel(metrics_right, text="Credits Earned",
                    font=("Arial", 11, "bold")).pack(pady=5)
        self.credits_label = ctk.CTkLabel(metrics_right, text="0", 
                                         font=("Arial", 24, "bold"),
                                         text_color="#4caf50")
        self.credits_label.pack(pady=5)

        history_card = ctk.CTkFrame(frame)
        history_card.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(history_card, text="Recent verified contributions", font=("Arial", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        self.history_box = ctk.CTkTextbox(history_card, height=105)
        self.history_box.pack(fill="x", padx=12, pady=(2, 10))
        self.update_work_history()
        
        # Info
        info_text = f"""🔗 Volunteer compute node

Node ID: {self.node_id or 'Enrolling'}
Tier: {self.profile['tier']} ({'GPU' if self.profile['tier'] == 1 else 'CPU'})
Coordinator: {self.orchestrator_url}
Resource limit: {self.cpu_limit} CPU cores / {self.memory_limit_gb} GB RAM
Model cache: {self.app_data / 'models'}

        This seeder will:
✅ Maintain connection with orchestrator
✅ Receive task assignments automatically
✅ Execute tasks in isolated Docker containers
✅ Report verified contribution results
✅ Auto-reconnect if connection drops

Credits are demo accounting only and have no cash value.
"""
        
        info_box = ctk.CTkTextbox(frame, height=200, width=750)
        info_box.pack(pady=15, padx=15)
        info_box.insert("1.0", info_text)
        info_box.configure(state="disabled")
        
        # Controls
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(pady=15)
        
        self.pause_btn = ctk.CTkButton(btn_frame, text="⏸️ Pause contributions", width=190, command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=8)
        
        quit_btn = ctk.CTkButton(btn_frame, text="🚪 Quit", width=140,
                                fg_color="#ff5252", hover_color="#c62828",
                                command=self.close_application)
        quit_btn.pack(side="left", padx=8)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.configure(text="▶️ Resume contributions" if self.paused else "⏸️ Pause contributions")
        self.update_status("Paused; current task will finish" if self.paused and self.current_task else
                           ("Paused; not accepting tasks" if self.paused else "Resuming network contributions"))
        if self.websocket and self.event_loop and self.event_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_heartbeat_once(self.websocket), self.event_loop)
    
    def update_status(self, text):
        if hasattr(self, 'status_label') and not self.shutting_down:
            try:
                self.after(0, lambda: self.status_label.configure(text=f"Status: {text}") if not self.shutting_down else None)
            except RuntimeError:
                pass
    
    def update_task_info(self, text):
        if hasattr(self, 'task_label') and not self.shutting_down:
            try:
                self.after(0, lambda: self.task_label.configure(text=text) if not self.shutting_down else None)
            except RuntimeError:
                pass
    
    def update_tasks_count(self, count):
        if hasattr(self, 'count_label') and not self.shutting_down:
            try:
                self.after(0, lambda: self.count_label.configure(text=str(count)) if not self.shutting_down else None)
            except RuntimeError:
                pass
    
    def update_credits(self, credits):
        if hasattr(self, 'credits_label') and not self.shutting_down:
            try:
                self.after(0, lambda: self.credits_label.configure(text=str(credits)) if not self.shutting_down else None)
            except RuntimeError:
                pass

    def update_work_history(self):
        if not hasattr(self, "history_box"):
            return
        def render():
            self.history_box.configure(state="normal")
            self.history_box.delete("1.0", "end")
            if not self.recent_work:
                self.history_box.insert("1.0", "Your verified contribution history will appear here.")
            else:
                rows = [f"{item.get('verdict', 'pending').upper():8}  {item.get('task_id', '')} / {item.get('chunk_id', '')}  +{item.get('credits', 0)} credits"
                        for item in self.recent_work[:10]]
                self.history_box.insert("1.0", "\n".join(rows))
            self.history_box.configure(state="disabled")
        if not self.shutting_down:
            try:
                self.after(0, render)
            except RuntimeError:
                pass

def main():
    app = ComputeTorrentSeeder()
    app.mainloop()

if __name__ == "__main__":
    main()
