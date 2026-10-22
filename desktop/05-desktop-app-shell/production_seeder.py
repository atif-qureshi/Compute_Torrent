import customtkinter as ctk
import asyncio
import threading
import psutil
import subprocess
import csv
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
from petals_control import PetalsControl, provider_identity
from hardware_details import details as hardware_details, gpu_telemetry

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
        build = provider_identity()
        self.title(f"ComputeTorrent Provider · {build['petals_provider_build']} · Network v{build['petals_network_revision']}")
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
        self.orchestrator_url = self.settings.get("orchestrator_url")
        if not self.orchestrator_url or self.orchestrator_url == "ws://127.0.0.1:8001/ws/seeder":
            tunnel_file = Path(__file__).resolve().parents[2] / "runtime" / "public_tunnel.json"
            if tunnel_file.is_file():
                try:
                    data = json.loads(tunnel_file.read_text(encoding="utf-8"))
                    if data.get("ws_url"):
                        self.orchestrator_url = data["ws_url"]
                except Exception:
                    pass
        if not self.orchestrator_url:
            self.orchestrator_url = DEFAULT_ORCHESTRATOR_URL
        # The network-wide enrollment code is a one-time secret; keep it in
        # memory only and persist only this provider's revocable credential.
        self.enrollment_token = ""
        self.cpu_limit = int(self.settings.get("cpu_limit", 2))
        self.memory_limit_gb = int(self.settings.get("memory_limit_gb", 8))
        self.paused = False
        self.event_loop = None
        self.shutting_down = False
        self.petals = PetalsControl(self.app_data)
        self.petals_enabled = bool(self.settings.get("petals_enabled", True))
        
        # Instant startup: Fast baseline or cached profile opens window in <0.2 seconds
        self.profile = self.fast_baseline_profile()
        cached = self.settings.get("cached_profile")
        if isinstance(cached, dict):
            self.profile.update(cached)
            self.profile["free_ram_gb"] = round(psutil.virtual_memory().available / (1024 ** 3), 1)
        self.profile.update(provider_identity(), petals_enabled=self.petals_enabled, petals_protocol_version=1,
                            memory_limit_gb=self.memory_limit_gb, cpu_limit=self.cpu_limit)
        if had_legacy_join_code:
            self.save_settings()
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        
        # Show onboarding UI immediately without blocking
        self.show_onboarding()

        # Run deep hardware & Docker scans in background daemon thread
        threading.Thread(target=self._async_background_hardware_scan, daemon=True).start()
    
    def fast_baseline_profile(self):
        """Ultra-fast (sub-millisecond) hardware baseline using psutil without spawning external processes."""
        ram_gb = psutil.virtual_memory().total // (1024 ** 3)
        cpu_cores = psutil.cpu_count() or 1
        try:
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            disk_free = round(disk.free / (1024 ** 3), 1)
            disk_total = round(disk.total / (1024 ** 3), 1)
        except Exception:
            disk_free = 20.0
            disk_total = 100.0
        return {
            "GPU": None,
            "VRAM": 0,
            "CUDA": False,
            "gpu_count": 0,
            "gpu_devices": [],
            "RAM": ram_gb,
            "cpu_cores": cpu_cores,
            "docker_ok": False,
            "tier": 2,
            "cpu_model": f"{cpu_cores} Core Processor",
            "physical_cores": psutil.cpu_count(logical=False) or cpu_cores,
            "free_ram_gb": round(psutil.virtual_memory().available / (1024 ** 3), 1),
            "disk_free_gb": disk_free,
            "disk_total_gb": disk_total,
            "petals_image_ready": False,
            "petals_cuda_ready": False,
        }

    def _async_background_hardware_scan(self):
        """Asynchronously queries deep WMI, Docker, and GPU telemetry without stalling UI launch."""
        try:
            detected = self.detect_hardware()
            details = hardware_details()
            caps = self.petals.capabilities()
            telemetry = gpu_telemetry()
            
            self.profile.update(detected)
            self.profile.update(details)
            self.profile.update(caps)
            self.profile.update(telemetry)
            self.profile.update(provider_identity(), petals_enabled=self.petals_enabled, petals_protocol_version=1,
                                memory_limit_gb=self.memory_limit_gb, cpu_limit=self.cpu_limit)
            
            cacheable = {k: v for k, v in self.profile.items() if k not in ("cpu_load_pct", "free_ram_gb")}
            self.settings["cached_profile"] = cacheable
            self.save_settings()
            
            # Apply updates seamlessly to onboarding UI if still on onboarding screen
            self.after(0, self._apply_profile_update)
        except Exception:
            pass

    def _apply_profile_update(self):
        """Safely updates UI cards after background hardware detection completes."""
        if hasattr(self, "server_entry") and self.server_entry.winfo_exists():
            saved = {
                "orchestrator_url": self.server_entry.get(),
                "enrollment_token": self.enrollment_entry.get() if hasattr(self, "enrollment_entry") and self.enrollment_entry.winfo_exists() else "",
                "cpu_limit": self.cpu_entry.get() if hasattr(self, "cpu_entry") and self.cpu_entry.winfo_exists() else str(self.cpu_limit),
                "memory_limit_gb": self.memory_entry.get() if hasattr(self, "memory_entry") and self.memory_entry.winfo_exists() else str(self.memory_limit_gb),
            }
            self.show_onboarding()
            if hasattr(self, "server_entry") and self.server_entry.winfo_exists():
                for field, value in ((self.server_entry, saved["orchestrator_url"]),
                                     (self.enrollment_entry, saved["enrollment_token"]),
                                     (self.cpu_entry, saved["cpu_limit"]),
                                     (self.memory_entry, saved["memory_limit_gb"])):
                    field.delete(0, "end")
                    field.insert(0, value)
    
    def detect_hardware(self):
        """Detect system hardware"""
        ram_gb = psutil.virtual_memory().total // (1024 ** 3)
        cpu_cores = psutil.cpu_count() or 1

        # NVIDIA's driver reports CUDA-capable devices and dedicated VRAM.
        gpu = None
        vram = 0
        cuda = False
        gpu_count = 0
        gpu_devices = []
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                for row in csv.reader(result.stdout.splitlines()):
                    if len(row) < 2:
                        continue
                    try:
                        memory_mib = int(float(row[1].strip()))
                    except ValueError:
                        memory_mib = 0
                    gpu_devices.append({"name": row[0].strip(), "vram_mib": memory_mib, "vendor": "NVIDIA"})
                cuda = True
        except:
            pass

        # Detect Windows display adapters (AMD, Intel, etc.) so AMD GPUs and multi-GPU setups are fully recognized
        if sys.platform == "win32":
            try:
                command = (
                    "$ErrorActionPreference='Stop'; "
                    "Get-CimInstance Win32_VideoController | "
                    "Where-Object { $_.Name -and $_.Name -notmatch 'Microsoft Basic|Remote Display|Virtual Display' } | "
                    "Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor | ConvertTo-Json -Compress"
                )
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", command],
                    capture_output=True, text=True, timeout=8
                )
                if result.returncode == 0 and result.stdout.strip():
                    items = json.loads(result.stdout)
                    if isinstance(items, dict):
                        items = [items]
                    existing_names = {d["name"].lower() for d in gpu_devices}
                    for item in items:
                        name = (item.get("Name") or "").strip()
                        if not name or any(ex in name.lower() for ex in existing_names):
                            continue
                        vendor = (
                            "AMD" if any(k in name.lower() for k in ["amd", "radeon"]) else
                            "NVIDIA" if any(k in name.lower() for k in ["nvidia", "geforce", "quadro", "rtx"]) else
                            "Intel" if any(k in name.lower() for k in ["intel", "arc", "iris"]) else "Unknown"
                        )
                        raw_ram = item.get("AdapterRAM") or 0
                        ram_mib = int(raw_ram) // (1024 * 1024) if raw_ram else 0
                        gpu_devices.append({
                            "name": name,
                            "vram_mib": ram_mib,
                            "vendor": vendor,
                            "driver": str(item.get("DriverVersion", "")).strip()
                        })
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                pass

        # Linux AMD GPU detection via sysfs
        if not any(d.get("vendor") == "AMD" for d in gpu_devices) and sys.platform.startswith("linux"):
            try:
                import glob
                cards = glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")
                for index, total_path in enumerate(cards):
                    with open(total_path) as f:
                        vram_bytes = int(f.read().strip())
                    vram_mib = vram_bytes // (1024 * 1024)
                    gpu_devices.append({
                        "name": f"AMD Radeon GPU {index}",
                        "vram_mib": vram_mib,
                        "vendor": "AMD"
                    })
            except Exception:
                pass

        gpu_count = len(gpu_devices)
        vram = max((device.get("vram_mib", 0) for device in gpu_devices), default=0)
        names = list(dict.fromkeys(device["name"] for device in gpu_devices))
        gpu = ", ".join(names) if names else None

        # Docker check
        docker_ok = False
        try:
            result = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True, timeout=5)
            docker_ok = result.returncode == 0
        except:
            pass
        
        # Tier determination
        if (cuda or any(d.get("vendor") == "AMD" for d in gpu_devices)) and vram >= 8192:
            tier = 1  # Tier 1: GPU with 8GB+ VRAM
        else:
            tier = 2  # Tier 2: CPU or entry-level GPU
        
        return {
            "GPU": gpu,
            "VRAM": vram,
            "CUDA": cuda,
            "gpu_count": gpu_count,
            "gpu_devices": gpu_devices,
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
        frame = ctk.CTkScrollableFrame(self, fg_color="#080c18")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header Banner
        header_card = ctk.CTkFrame(frame, fg_color="#0f172a", border_width=1, border_color="#1e293b", corner_radius=16)
        header_card.pack(fill="x", padx=10, pady=(5, 15))
        
        title = ctk.CTkLabel(header_card, text="⚡ ComputeTorrent Provider",
                             font=("Arial", 26, "bold"), text_color="#ffffff")
        title.pack(pady=(16, 4))
        
        subtitle = ctk.CTkLabel(header_card, text="🌐 High-Performance Distributed AI Computing Node",
                                font=("Arial", 13), text_color="#38bdf8")
        subtitle.pack(pady=(0, 16))
        
        # Section 1: System Hardware Profile (4 Distinct Modern Cards)
        sec_title = ctk.CTkLabel(frame, text="📊 DETECTED HARDWARE CAPACITIES",
                                 font=("Arial", 12, "bold"), text_color="#818cf8")
        sec_title.pack(anchor="w", padx=12, pady=(10, 8))
        
        hw_grid = ctk.CTkFrame(frame, fg_color="transparent")
        hw_grid.pack(fill="x", padx=6, pady=4)
        hw_grid.grid_columnconfigure((0, 1), weight=1)
        
        # Card 1: CPU (Indigo / Cyan Accent)
        cpu_card = ctk.CTkFrame(hw_grid, fg_color="#131b2e", border_width=1, border_color="#233354", corner_radius=12)
        cpu_card.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(cpu_card, text="💻 PROCESSOR (CPU)", font=("Arial", 11, "bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(12, 2))
        cpu_name = self.profile.get('cpu_model') or f"{self.profile['cpu_cores']} Core Processor"
        ctk.CTkLabel(cpu_card, text=cpu_name[:40], font=("Arial", 14, "bold"), text_color="#f8fafc").pack(anchor="w", padx=14)
        ctk.CTkLabel(cpu_card, text=f"• Logical Cores: {self.profile['cpu_cores']}\n• Physical Cores: {self.profile.get('physical_cores', '—')}\n• CPU Load: {self.profile.get('cpu_load_pct', 0)}%",
                     font=("Courier New", 11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=14, pady=(4, 12))
        
        # Card 2: RAM (Emerald Accent)
        ram_card = ctk.CTkFrame(hw_grid, fg_color="#102322", border_width=1, border_color="#1b453e", corner_radius=12)
        ram_card.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(ram_card, text="🧠 SYSTEM MEMORY (RAM)", font=("Arial", 11, "bold"), text_color="#34d399").pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(ram_card, text=f"{self.profile['RAM']} GB Installed RAM", font=("Arial", 14, "bold"), text_color="#f8fafc").pack(anchor="w", padx=14)
        ctk.CTkLabel(ram_card, text=f"• Free Available: {self.profile.get('free_ram_gb', 0)} GB\n• Disk Free Space: {self.profile.get('disk_free_gb', '—')} GB\n• Allocation Limit: {self.memory_limit_gb} GB Max",
                     font=("Courier New", 11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=14, pady=(4, 12))
        
        # Card 3: GPU (Violet Accent)
        gpu_card = ctk.CTkFrame(hw_grid, fg_color="#1e162f", border_width=1, border_color="#3b275e", corner_radius=12)
        gpu_card.grid(row=1, column=0, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(gpu_card, text="🎮 GRAPHICS & ACCELERATION", font=("Arial", 11, "bold"), text_color="#a78bfa").pack(anchor="w", padx=14, pady=(12, 2))
        gpu_name = self.profile['GPU'] or "Integrated / CPU Only"
        ctk.CTkLabel(gpu_card, text=gpu_name[:40], font=("Arial", 14, "bold"), text_color="#f8fafc").pack(anchor="w", padx=14)
        vram_text = f"{self.profile['VRAM'] / 1024:.1f} GB Dedicated" if self.profile['VRAM'] else "Shared System Memory"
        ctk.CTkLabel(gpu_card, text=f"• Dedicated VRAM: {vram_text}\n• CUDA Ready: {'✅ Yes' if self.profile['CUDA'] else '❌ No (CPU Mode)'}\n• GPU Devices: {self.profile.get('gpu_count', 0)} detected",
                     font=("Courier New", 11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=14, pady=(4, 12))
        
        # Card 4: Docker & Runtime (Amber Accent)
        dock_card = ctk.CTkFrame(hw_grid, fg_color="#241b12", border_width=1, border_color="#4d351b", corner_radius=12)
        dock_card.grid(row=1, column=1, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(dock_card, text="🐳 EXECUTION SANDBOX & TIER", font=("Arial", 11, "bold"), text_color="#fbbf24").pack(anchor="w", padx=14, pady=(12, 2))
        tier_title = f"Tier {self.profile['tier']} · {'GPU Inference' if self.profile['tier'] == 1 else 'CPU Layer Serving'}"
        ctk.CTkLabel(dock_card, text=tier_title, font=("Arial", 14, "bold"), text_color="#f8fafc").pack(anchor="w", padx=14)
        ctk.CTkLabel(dock_card, text=f"• Docker Desktop: {'✅ Available & Active' if self.profile['docker_ok'] else '❌ Not Detected'}\n• Petals CPU Image: {'✅ Installed' if self.profile.get('petals_image_ready') else '⏳ Needs Build'}\n• Protocol Version: v{self.profile.get('petals_protocol_version', 1)}",
                     font=("Courier New", 11), text_color="#94a3b8", justify="left").pack(anchor="w", padx=14, pady=(4, 12))

        # Refresh Hardware Button
        ctk.CTkButton(frame, text="🔄 Re-detect System Hardware", command=self.refresh_hardware_profile,
                      height=32, width=220, fg_color="#1e293b", hover_color="#334155",
                      font=("Arial", 12)).pack(anchor="w", padx=12, pady=(4, 16))

        # Section 2: Network Connection Setup Card
        connection_card = ctk.CTkFrame(frame, fg_color="#0f172a", border_width=1, border_color="#1e293b", corner_radius=16)
        connection_card.pack(fill="x", padx=10, pady=8)
        
        ctk.CTkLabel(connection_card, text="🌐 NETWORK CONFIGURATION", font=("Arial", 12, "bold"), text_color="#818cf8").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(connection_card,
            text="Enter the Coordinator PC's private LAN address (e.g. ws://192.168.100.7:8001/ws/seeder). Do NOT use localhost from another PC.",
            wraplength=760, justify="left", font=("Arial", 11), text_color="#94a3b8").pack(anchor="w", padx=16, pady=(0, 8))
        
        self.server_entry = ctk.CTkEntry(connection_card, height=38, corner_radius=8,
                                         fg_color="#090e1a", border_color="#334155",
                                         font=("Courier New", 12), text_color="#38bdf8",
                                         placeholder_text="ws://192.168.100.7:8001/ws/seeder")
        self.server_entry.pack(fill="x", padx=16, pady=(2, 10))
        self.server_entry.insert(0, self.orchestrator_url)
        
        ctk.CTkLabel(connection_card, text="🔑 One-Time Provider Enrollment Code", font=("Arial", 11, "bold"), text_color="#cbd5e1").pack(anchor="w", padx=16)
        self.enrollment_entry = ctk.CTkEntry(connection_card, height=38, corner_radius=8,
                                             fg_color="#090e1a", border_color="#334155",
                                             show="•", font=("Arial", 12),
                                             placeholder_text="Enter join code (default: local-volunteer-join)")
        self.enrollment_entry.pack(fill="x", padx=16, pady=(2, 6))
        if self.enrollment_token:
            self.enrollment_entry.insert(0, self.enrollment_token)
            
        # Limits and Sliders Grid
        limits = ctk.CTkFrame(connection_card, fg_color="transparent")
        limits.pack(fill="x", padx=16, pady=(6, 10))
        
        ctk.CTkLabel(limits, text="Max CPU Cores:", font=("Arial", 11, "bold")).pack(side="left")
        self.cpu_entry = ctk.CTkEntry(limits, width=70, height=32, corner_radius=6, fg_color="#090e1a", font=("Arial", 12))
        self.cpu_entry.pack(side="left", padx=(8, 24))
        self.cpu_entry.insert(0, str(self.cpu_limit))
        
        ctk.CTkLabel(limits, text="Max RAM (GB):", font=("Arial", 11, "bold")).pack(side="left")
        self.memory_entry = ctk.CTkEntry(limits, width=70, height=32, corner_radius=6, fg_color="#090e1a", font=("Arial", 12))
        self.memory_entry.pack(side="left", padx=8)
        self.memory_entry.insert(0, str(self.memory_limit_gb))
        
        self.connection_error = ctk.CTkLabel(connection_card, text="", text_color="#f43f5e", font=("Arial", 11, "bold"))
        self.connection_error.pack(anchor="w", padx=16)
        
        # Petals Layer Toggle Card
        petals_box = ctk.CTkFrame(connection_card, fg_color="#131b2e", border_width=1, border_color="#20304f", corner_radius=12)
        petals_box.pack(fill="x", padx=16, pady=(6, 14))
        
        self.layer_switch = ctk.CTkSwitch(petals_box, text="Share Model Layers (Petals Distributed LLM Inference)",
                                          progress_color="#10b981", font=("Arial", 13, "bold"), text_color="#f8fafc")
        self.layer_switch.pack(anchor="w", padx=14, pady=(12, 4))
        if self.petals_enabled:
            self.layer_switch.select()
            
        ctk.CTkLabel(petals_box,
            text="When enabled, this node receives and serves model transformer blocks assigned by the coordinator. Weights stream securely into isolated Docker containers.",
            wraplength=720, justify="left", font=("Arial", 11), text_color="#94a3b8").pack(anchor="w", padx=14, pady=(0, 10))
            
        runtime_ctrls = ctk.CTkFrame(petals_box, fg_color="transparent")
        runtime_ctrls.pack(fill="x", padx=14, pady=(0, 10))
        
        ctk.CTkButton(runtime_ctrls, text="📦 Install CPU Runtime Image", command=lambda: self.install_petals_runtime("cpu"),
                      height=32, fg_color="#0369a1", hover_color="#0284c7").pack(side="left", padx=(0, 8))
        if self.profile.get("CUDA"):
            ctk.CTkButton(runtime_ctrls, text="🚀 Install NVIDIA CUDA Runtime", command=lambda: self.install_petals_runtime("cuda"),
                          height=32, fg_color="#7c3aed", hover_color="#9333ea").pack(side="left", padx=8)
                          
        self.runtime_label = ctk.CTkLabel(petals_box,
            text=f"Petals CPU runtime: {'✅ Ready' if self.profile.get('petals_image_ready') else '⏳ Not installed'} · CUDA runtime: {'✅ Ready' if self.profile.get('petals_cuda_ready') else 'N/A'}",
            font=("Arial", 11), text_color="#38bdf8")
        self.runtime_label.pack(anchor="w", padx=14, pady=(0, 10))
        
        if not self.profile['docker_ok']:
            warn_card = ctk.CTkFrame(frame, fg_color="#451a1a", border_width=1, border_color="#7f1d1d", corner_radius=10)
            warn_card.pack(fill="x", padx=10, pady=6)
            ctk.CTkLabel(warn_card, text="⚠️ Warning: Docker Desktop must be running before tasks can execute.",
                         font=("Arial", 12, "bold"), text_color="#fca5a5").pack(padx=12, pady=10)
        
        # Connect Button (Electric Gradient Styling)
        connect_btn = ctk.CTkButton(frame, text="🚀 Connect & Join Compute Network",
                                    command=self.start_connection,
                                    height=52, corner_radius=12,
                                    font=("Arial", 15, "bold"),
                                    fg_color="#6366f1", hover_color="#4f46e5")
        connect_btn.pack(fill="x", padx=10, pady=(15, 8))
        
        # Footer
        footer = ctk.CTkLabel(frame,
            text=f"Node: {self.node_id or 'Unregistered'} • Orchestrator Target: {self.orchestrator_url}",
            font=("Courier New", 10), text_color="#64748b")
        footer.pack(pady=(0, 16))

    def install_petals_runtime(self, device):
        """Build a sandboxed Petals worker image on this volunteer PC."""
        if not self.profile.get("docker_ok"):
            self.runtime_label.configure(text="Start Docker Desktop before installing the runtime")
            return
        def report(message):
            self.after(0, lambda: self.runtime_label.configure(text=message))
        report(f"Preparing {device.upper()} runtime… Docker may download several GB.")
        def build():
            try:
                self.petals.install_runtime(device, progress=report)
                self.profile.update(self.petals.capabilities())
                self.profile.update(provider_identity(), petals_enabled=self.petals_enabled, petals_protocol_version=1,
                                    cpu_limit=self.cpu_limit, memory_limit_gb=self.memory_limit_gb)
                self.after(0, lambda: self.runtime_label.configure(
                    text=f"Petals CPU runtime: {'installed' if self.profile.get('petals_image_ready') else 'not installed'} · CUDA runtime: {'ready' if self.profile.get('petals_cuda_ready') else 'not installed or not available'}"))
                report(f"{device.upper()} Petals runtime is installed. Enable layer sharing and reconnect.")
            except Exception as error:
                report(f"Runtime installation failed: {str(error)[:500]}")
        threading.Thread(target=build, daemon=True).start()

    def refresh_hardware_profile(self):
        """Re-detect system devices before enrollment."""
        saved = {
            "orchestrator_url": self.server_entry.get() if hasattr(self, "server_entry") else self.orchestrator_url,
            "enrollment_token": self.enrollment_entry.get() if hasattr(self, "enrollment_entry") else "",
            "cpu_limit": self.cpu_entry.get() if hasattr(self, "cpu_entry") else str(self.cpu_limit),
            "memory_limit_gb": self.memory_entry.get() if hasattr(self, "memory_entry") else str(self.memory_limit_gb),
        }
        self.profile = self.detect_hardware()
        self.profile.update(hardware_details())
        self.profile.update(self.petals.capabilities())
        self.profile.update(gpu_telemetry())
        self.petals_enabled = bool(self.layer_switch.get())
        self.show_onboarding()
        for field, value in ((self.server_entry, saved["orchestrator_url"]),
                             (self.enrollment_entry, saved["enrollment_token"]),
                             (self.cpu_entry, saved["cpu_limit"]),
                             (self.memory_entry, saved["memory_limit_gb"])):
            field.delete(0, "end")
            field.insert(0, value)
    
    def start_connection(self):
        """Start connection to orchestrator"""
        self.petals_enabled = bool(self.layer_switch.get())
        self.profile.update(provider_identity(), petals_enabled=self.petals_enabled, petals_protocol_version=1,
                            cpu_limit=self.cpu_limit, memory_limit_gb=self.memory_limit_gb)
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
                              "petals_enabled": self.petals_enabled,
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
            "Content-Type": "application/json",
            "X-Enrollment-Token": self.enrollment_token,
            "ngrok-skip-browser-warning": "69420",
            "User-Agent": "ComputeTorrent-Provider/1.0"
        })
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
            req = urllib.request.Request(peer_info_url, headers={
                "ngrok-skip-browser-warning": "69420",
                "User-Agent": "ComputeTorrent-Provider/1.0"
            })
            with urllib.request.urlopen(req, timeout=10) as response:
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
        self.petals.stop()
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

                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "ngrok-skip-browser-warning": "69420",
                    "User-Agent": "ComputeTorrent-Provider/1.0",
                }
                async with websockets.connect(
                    self.orchestrator_url,
                    extra_headers=headers,
                    open_timeout=45,
                    ping_interval=15,
                    ping_timeout=35,
                    close_timeout=15,
                    max_size=100 * 1024 * 1024,
                ) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    retry_count = 0
                    
                    # Send registration
                    register_msg = {
                        "type": "register",
                        "node_id": self.node_id,
                        "tier": self.profile["tier"],
                        "profile": {**self.profile,
                            "GPU": self.profile["GPU"],
                            "VRAM": self.profile["VRAM"],
                            "CUDA": self.profile["CUDA"],
                            "gpu_count": self.profile["gpu_count"],
                            "gpu_devices": self.profile["gpu_devices"],
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
                        self.update_status("🔄 Reconnecting...")
                    finally:
                        heartbeat_task.cancel()
                        self.websocket = None
                        self.is_connected = False
                        
            except Exception as e:
                if self.shutting_down:
                    break
                self.update_status(f"Connection issue: {e}")
            retry_count += 1
            delay = min(10, 1 + retry_count)
            if self.shutting_down:
                break
            self.update_status(f"Reconnecting in {delay}s…")
            await asyncio.sleep(delay)
    
    async def send_heartbeats(self, websocket):
        """Send periodic heartbeats with failure tolerance"""
        while not self.shutting_down and self.websocket == websocket:
            try:
                await self.send_heartbeat_once(websocket)
            except Exception:
                # Do not break loop on transient heartbeat errors
                pass
            await asyncio.sleep(10)

    async def send_heartbeat_once(self, websocket):
        memory = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            self.profile["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
            self.profile["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        except Exception:
            self.profile.setdefault("disk_free_gb", 20.0)
        self.profile["free_ram_gb"] = round(memory.available / (1024 ** 3), 1)
        self.profile["cpu_load_pct"] = round(psutil.cpu_percent(interval=None), 1)
        self.profile["uptime_seconds"] = int(time.time() - psutil.boot_time())
        self.profile.update(provider_identity(), petals_enabled=self.petals_enabled, petals_protocol_version=1,
                            memory_limit_gb=self.memory_limit_gb, cpu_limit=self.cpu_limit)
        
        # Only query GPU telemetry periodically (every 45s) to avoid PowerShell WMI stalls
        now = time.time()
        if now - getattr(self, "_last_gpu_telemetry_time", 0) > 45:
            self._last_gpu_telemetry_time = now
            try:
                self.profile.update(await asyncio.to_thread(gpu_telemetry))
            except Exception:
                pass

        self.profile["petals"] = await asyncio.to_thread(self.petals.status, self.is_connected and not self.paused)
        layer_active = self.profile["petals"].get("status") not in {"idle", "failed", "stopped", "cancelled"}
        if not layer_active and str(self.current_task or "").startswith("Petals:"):
            self.current_task = None
        if hasattr(self, 'layer_label'):
            text = self.profile['petals']
            self.after(0, lambda: self.layer_label.configure(text=f"Layers: {text.get('start', '—')}–{text.get('end', '—')} · {text.get('status', 'idle')}"))
        await websocket.send(json.dumps({
            "type": "heartbeat",
            "node_id": self.node_id,
            "state": "paused" if self.paused else ("busy" if self.current_task or layer_active else "idle"),
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
            
            elif msg_type == "petals_start":
                if self.paused or not self.petals_enabled or self.current_task:
                    error = 'Layer sharing is disabled or provider is busy'
                    if not self.current_task:
                        self.petals.fail_job(data.get('job_id'), error)
                    self.profile['petals'] = {'job_id': data.get('job_id'), 'status': 'failed', 'error': error}
                    await websocket_profile(self)
                    return
                try:
                    job_id = data.get('job_id', 'job')
                    model_id = data.get('spec', {}).get('model_id', 'Model')
                    start_layer = data.get('stage', {}).get('start', 0)
                    end_layer = data.get('stage', {}).get('end', 0)
                    self.current_task = f"Petals: {model_id} (Layers {start_layer}–{end_layer})"
                    self.update_task_info(f"🚀 Task Received: Serving {model_id} (Layers {start_layer}–{end_layer})")
                    self.update_status(f"Serving layers {start_layer}–{end_layer} of {model_id}")
                    if hasattr(self, 'layer_label'):
                        self.after(0, lambda: self.layer_label.configure(text=f"🟢 Active Task: Layers {start_layer}–{end_layer} assigned", text_color="#00d4ff"))
                    await asyncio.to_thread(self.petals.start, data, self.orchestrator_url, self.cpu_limit, self.memory_limit_gb)
                    self.profile.update(await asyncio.to_thread(self.petals.capabilities))
                    self.profile['petals'] = await asyncio.to_thread(self.petals.status)
                    await websocket_profile(self)
                except Exception as error:
                    self.current_task = None
                    self.petals.fail_job(data.get('job_id'), str(error))
                    self.profile['petals'] = self.petals.status(renew=False)
                    self.update_task_info(f"❌ Error starting layer task: {str(error)[:100]}")
                    self.update_status("Error loading layers")
                    await websocket_profile(self)
            elif msg_type == "petals_stop":
                await asyncio.to_thread(self.petals.stop, data.get('job_id'))
                self.profile['petals'] = self.petals.status(renew=False)
                self.current_task = None
                self.update_task_info("✅ Layer serving completed · Ready for next task")
                self.update_status("Online & ready for tasks")
                if hasattr(self, 'layer_label'):
                    self.after(0, lambda: self.layer_label.configure(text="Layer sharing enabled · waiting for assignment", text_color="#7ce4bc"))
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
        frame = ctk.CTkScrollableFrame(self, fg_color="#080c18")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 1. Top Node Banner & Status
        top_banner = ctk.CTkFrame(frame, fg_color="#0f172a", border_width=1, border_color="#1e293b", corner_radius=16)
        top_banner.pack(fill="x", padx=10, pady=(5, 12))
        
        header_row = ctk.CTkFrame(top_banner, fg_color="transparent")
        header_row.pack(fill="x", padx=16, pady=12)
        
        title_box = ctk.CTkFrame(header_row, fg_color="transparent")
        title_box.pack(side="left")
        
        ctk.CTkLabel(title_box, text="⚡ ComputeTorrent Provider Node",
                     font=("Arial", 20, "bold"), text_color="#ffffff").pack(anchor="w")
        ctk.CTkLabel(title_box, text=f"Node ID: {self.node_id or 'Enrolling…'} · Coordinator: {self.orchestrator_url}",
                     font=("Courier New", 11), text_color="#64748b").pack(anchor="w", pady=(2, 0))
                     
        self.status_label = ctk.CTkLabel(header_row, text="Status: Initializing…",
                                         font=("Arial", 13, "bold"), text_color="#38bdf8",
                                         fg_color="#0c192d", corner_radius=20, padx=14, pady=6)
        self.status_label.pack(side="right")
        
        # 2. Hardware Specs 4-Card Strip
        hw_grid = ctk.CTkFrame(frame, fg_color="transparent")
        hw_grid.pack(fill="x", padx=6, pady=4)
        hw_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # CPU Card
        c1 = ctk.CTkFrame(hw_grid, fg_color="#131b2e", border_width=1, border_color="#233354", corner_radius=12)
        c1.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(c1, text="💻 PROCESSOR", font=("Arial", 10, "bold"), text_color="#38bdf8").pack(anchor="w", padx=10, pady=(8, 2))
        cpu_text = self.profile.get('cpu_model') or f"{self.profile['cpu_cores']} Cores"
        ctk.CTkLabel(c1, text=cpu_text[:20], font=("Arial", 12, "bold"), text_color="#f8fafc").pack(anchor="w", padx=10)
        ctk.CTkLabel(c1, text=f"{self.profile['cpu_cores']} Cores · {self.profile.get('cpu_load_pct', 0)}% Load",
                     font=("Arial", 11), text_color="#94a3b8").pack(anchor="w", padx=10, pady=(2, 8))
        
        # RAM Card
        c2 = ctk.CTkFrame(hw_grid, fg_color="#102322", border_width=1, border_color="#1b453e", corner_radius=12)
        c2.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(c2, text="🧠 MEMORY (RAM)", font=("Arial", 10, "bold"), text_color="#34d399").pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(c2, text=f"{self.profile['RAM']} GB Installed", font=("Arial", 12, "bold"), text_color="#f8fafc").pack(anchor="w", padx=10)
        ctk.CTkLabel(c2, text=f"{self.profile.get('free_ram_gb', 0)} GB Free · Max {self.memory_limit_gb} GB",
                     font=("Arial", 11), text_color="#94a3b8").pack(anchor="w", padx=10, pady=(2, 8))
                     
        # GPU Card
        c3 = ctk.CTkFrame(hw_grid, fg_color="#1e162f", border_width=1, border_color="#3b275e", corner_radius=12)
        c3.grid(row=0, column=2, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(c3, text="🎮 ACCELERATION", font=("Arial", 10, "bold"), text_color="#a78bfa").pack(anchor="w", padx=10, pady=(8, 2))
        gpu_short = (self.profile['GPU'] or "CPU Only")[:20]
        ctk.CTkLabel(c3, text=gpu_short, font=("Arial", 12, "bold"), text_color="#f8fafc").pack(anchor="w", padx=10)
        vram_info = f"{self.profile['VRAM'] / 1024:.1f} GB VRAM" if self.profile['VRAM'] else "System Shared"
        ctk.CTkLabel(c3, text=f"{vram_info} · Tier {self.profile['tier']}",
                     font=("Arial", 11), text_color="#94a3b8").pack(anchor="w", padx=10, pady=(2, 8))
                     
        # Sandbox Card
        c4 = ctk.CTkFrame(hw_grid, fg_color="#241b12", border_width=1, border_color="#4d351b", corner_radius=12)
        c4.grid(row=0, column=3, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(c4, text="🐳 RUNTIME", font=("Arial", 10, "bold"), text_color="#fbbf24").pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(c4, text="Docker Isolated", font=("Arial", 12, "bold"), text_color="#f8fafc").pack(anchor="w", padx=10)
        ctk.CTkLabel(c4, text="Petals Protocol v1",
                     font=("Arial", 11), text_color="#94a3b8").pack(anchor="w", padx=10, pady=(2, 8))

        # 3. Active Task Highlight Card (Glowing Cyan / Electric Border)
        task_card = ctk.CTkFrame(frame, fg_color="#0c192d", border_width=2, border_color="#0ea5e9", corner_radius=14)
        task_card.pack(fill="x", padx=10, pady=10)
        
        task_header = ctk.CTkFrame(task_card, fg_color="transparent")
        task_header.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(task_header, text="🎯 ACTIVE INFERENCE TASK", font=("Arial", 11, "bold"), text_color="#38bdf8").pack(side="left")
        self.layer_label = ctk.CTkLabel(task_header,
            text="Layer sharing enabled · waiting for assignment" if self.petals_enabled else "Layer sharing disabled",
            font=("Arial", 12, "bold"), text_color="#34d399")
        self.layer_label.pack(side="right")
        
        self.task_label = ctk.CTkLabel(task_card, text="Current Task: Idle / Waiting for work from coordinator",
                                       font=("Arial", 14, "bold"), text_color="#ffffff", justify="left")
        self.task_label.pack(anchor="w", padx=16, pady=(4, 14))

        # 4. Multi-Colored Metrics Grid (Verified Chunks in Cyan, Credits in Amber)
        stats_grid = ctk.CTkFrame(frame, fg_color="transparent")
        stats_grid.pack(fill="x", padx=6, pady=4)
        stats_grid.grid_columnconfigure((0, 1), weight=1)
        
        # Left Metric Card: Verified Chunks
        m_left = ctk.CTkFrame(stats_grid, fg_color="#0c1a29", border_width=1, border_color="#153654", corner_radius=14)
        m_left.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(m_left, text="⚡ VERIFIED CHUNKS / RUNS", font=("Arial", 11, "bold"), text_color="#38bdf8").pack(anchor="w", padx=16, pady=(12, 2))
        self.count_label = ctk.CTkLabel(m_left, text=str(self.tasks_completed), font=("Arial", 32, "bold"), text_color="#00d4ff")
        self.count_label.pack(anchor="w", padx=16)
        ctk.CTkLabel(m_left, text="Replica consensus approved tasks", font=("Arial", 11), text_color="#64748b").pack(anchor="w", padx=16, pady=(2, 12))
        
        # Right Metric Card: Credits Earned
        m_right = ctk.CTkFrame(stats_grid, fg_color="#21190f", border_width=1, border_color="#4d351b", corner_radius=14)
        m_right.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")
        ctk.CTkLabel(m_right, text="💰 DEMO CREDITS EARNED", font=("Arial", 11, "bold"), text_color="#fbbf24").pack(anchor="w", padx=16, pady=(12, 2))
        self.credits_label = ctk.CTkLabel(m_right, text=str(self.credits_earned), font=("Arial", 32, "bold"), text_color="#f59e0b")
        self.credits_label.pack(anchor="w", padx=16)
        ctk.CTkLabel(m_right, text="Contribution accounting balance", font=("Arial", 11), text_color="#64748b").pack(anchor="w", padx=16, pady=(2, 12))

        # 5. Recent Verified History Card
        history_card = ctk.CTkFrame(frame, fg_color="#0f172a", border_width=1, border_color="#1e293b", corner_radius=14)
        history_card.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(history_card, text="📜 RECENT TASK CONTRIBUTION AUDIT", font=("Arial", 11, "bold"), text_color="#818cf8").pack(anchor="w", padx=16, pady=(12, 4))
        self.history_box = ctk.CTkTextbox(history_card, height=110, corner_radius=8,
                                          fg_color="#090e1a", border_color="#1e293b",
                                          font=("Courier New", 11), text_color="#94a3b8")
        self.history_box.pack(fill="x", padx=16, pady=(2, 14))
        self.update_work_history()

        # 6. Action Buttons Bar
        btn_bar = ctk.CTkFrame(frame, fg_color="transparent")
        btn_bar.pack(fill="x", padx=10, pady=(6, 16))
        
        self.pause_btn = ctk.CTkButton(btn_bar, text="⏸️ Pause Contributions",
                                      width=180, height=40, corner_radius=10,
                                      font=("Arial", 12, "bold"),
                                      fg_color="#d97706", hover_color="#b45309",
                                      command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=(0, 8))
        
        copy_id_btn = ctk.CTkButton(btn_bar, text="📋 Copy Node ID",
                                    width=140, height=40, corner_radius=10,
                                    font=("Arial", 12, "bold"),
                                    fg_color="#1e293b", hover_color="#334155",
                                    command=lambda: self.clipboard_clear() or self.clipboard_append(self.node_id or ''))
        copy_id_btn.pack(side="left", padx=8)

        quit_btn = ctk.CTkButton(btn_bar, text="🚪 Disconnect & Quit",
                                 width=160, height=40, corner_radius=10,
                                 font=("Arial", 12, "bold"),
                                 fg_color="#e11d48", hover_color="#be123c",
                                 command=self.close_application)
        quit_btn.pack(side="right", padx=(8, 0))

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.petals.stop()
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

async def websocket_profile(app):
    if app.websocket:
        layer_active = app.profile.get('petals', {}).get('status', 'idle') not in {'idle', 'failed', 'stopped', 'cancelled'}
        state = 'paused' if app.paused else ('busy' if app.current_task or layer_active else 'idle')
        await app.websocket.send(json.dumps({'type': 'heartbeat', 'state': state, 'profile': app.profile}))


def main():
    app = ComputeTorrentSeeder()
    app.mainloop()

if __name__ == "__main__":
    main()
