import hmac
import secrets
from connection_routes import select_endpoint, candidates as route_candidates, proof as route_proof, register_digest
import customtkinter as ctk
import provider_views as ui
from provider_views import onboarding as render_onboarding, dashboard as render_dashboard, NoticeLabel
import asyncio
import ipaddress
import random
import socket
import ssl
import threading
import psutil
import subprocess
import csv
import websockets
from websockets.legacy.client import Connect
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
from provider_update import check_update, stage_update, restart_with_update
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

def _detect_active_lan_ip():
    virtual_tokens = (
        "vethernet", "wsl", "docker", "hyper-v", "vmware", "virtualbox",
        "loopback", "teredo", "bluetooth", "tailscale", "wireguard",
        "zerotier", "tap", "tun", "npcap", "isatap", "6to4",
    )
    outbound_ip = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            cand = sock.getsockname()[0]
            if cand and not cand.startswith(("127.", "169.254.", "0.")):
                outbound_ip = cand
        finally:
            sock.close()
    except OSError:
        outbound_ip = None

    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    best = None
    for name, entries in addrs.items():
        st = stats.get(name)
        if st is not None and not st.isup:
            continue
        low = name.lower()
        if any(tok in low for tok in virtual_tokens):
            continue
        for addr in entries:
            if getattr(addr, "family", None) != socket.AF_INET:
                continue
            ip = (addr.address or "").strip()
            if not ip or ip.startswith(("127.", "169.254.", "0.")):
                continue
            try:
                ip_obj = ipaddress.ip_address(ip)
            except ValueError:
                continue
            score = 0
            if any(k in low for k in ("wi-fi", "wifi", "wlan", "wireless")):
                score += 100
            if outbound_ip and ip == outbound_ip:
                score += 50
            if ip_obj.is_private:
                score += 20
            cand = (score, ip, name)
            if best is None or cand[0] > best[0]:
                best = cand
    if best is not None:
        return best[1], best[2]
    if outbound_ip:
        return outbound_ip, None
    return None, None


def coordinator_endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"ws", "wss"} or not parsed.hostname or parsed.username is not None
            or parsed.path != "/ws/seeder" or parsed.query or parsed.fragment):
        raise ValueError("Enter a coordinator URL ending in /ws/seeder")
    port = parsed.port
    if port == 0:
        raise ValueError("Coordinator port must be between 1 and 65535.")
    if parsed.scheme == "ws" and parsed.hostname != "localhost":
        private_ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                          "127.0.0.0/8", "::1/128", "fc00::/7")
        try:
            address = ipaddress.ip_address(parsed.hostname)
            allowed = any(address in ipaddress.ip_network(net) for net in private_ranges)
        except ValueError:
            allowed = False
        if not allowed:
            raise ValueError("Remote coordinators require wss://")
    return parsed.scheme, parsed.hostname, port or (443 if parsed.scheme == "wss" else 80)


def normalize_coordinator_address(value):
    """Accept a copied operator address or a simple private LAN IP."""
    value = value.strip()
    if not value:
        raise ValueError("Paste the coordinator address from your operator.")
    if "://" not in value:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            local = urlsplit("ws://" + value)
            if local.path in {"", "/", "/ws/seeder"}:
                try:
                    endpoint = urlunsplit(local._replace(path="/ws/seeder"))
                    coordinator_endpoint(endpoint)
                except ValueError:
                    pass
                else:
                    if local.port is None:
                        endpoint = urlunsplit(local._replace(netloc=f"{local.netloc}:8001", path="/ws/seeder"))
                    return endpoint
            value = "wss://" + value
        else:
            host = f"[{address}]" if address.version == 6 else str(address)
            candidate = f"ws://{host}:8001/ws/seeder"
            try:
                coordinator_endpoint(candidate)
            except ValueError:
                value = "wss://" + host
            else:
                return candidate
    parsed = urlsplit(value)
    scheme = {"https": "wss", "http": "ws"}.get(parsed.scheme, parsed.scheme)
    if parsed.hostname and parsed.hostname != "localhost":
        private_ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                          "127.0.0.0/8", "::1/128", "fc00::/7")
        try:
            address = ipaddress.ip_address(parsed.hostname)
            is_private = any(address in ipaddress.ip_network(net) for net in private_ranges)
        except ValueError:
            is_private = False
        if not is_private and scheme in {"http", "ws"}:
            scheme = "wss"
    if parsed.path in {"", "/"}:
        parsed = parsed._replace(path="/ws/seeder")
    endpoint = urlunsplit(parsed._replace(scheme=scheme))
    coordinator_endpoint(endpoint)
    return endpoint


def connection_failure(error):
    """Return a safe volunteer-facing message and whether retry may help."""
    if isinstance(error, urllib.error.HTTPError):
        if error.code in {401, 403}:
            return "Join code rejected. Ask the operator for the current code.", False
        if error.code in {404, 405}:
            return "This address does not offer enrollment. Ask for the coordinator address.", False
        if error.code == 503:
            return "Enrollment is unavailable. Ask the operator to check the coordinator.", False
        if 300 <= error.code < 400:
            return "Coordinator redirected enrollment. Ask for its current address.", False
    if isinstance(error, websockets.exceptions.InvalidStatusCode):
        if error.status_code in {401, 403}:
            return "The coordinator refused the connection. Ask the operator to check access.", False
        if error.status_code in {404, 405}:
            return "This address does not offer provider connections. Ask for the coordinator address.", False
    reason = getattr(error, "reason", error)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "The coordinator certificate could not be verified. Check the address with your operator.", False
    if isinstance(reason, socket.gaierror):
        return "Coordinator name could not be resolved. Check the address and network.", True
    if isinstance(reason, (asyncio.TimeoutError, TimeoutError)):
        return "Coordinator response timed out. Check your network and try again.", True
    if isinstance(reason, OSError):
        return "Cannot reach the coordinator. Check your network and the operator address.", True
    if isinstance(error, ValueError):
        return "Coordinator response or address is invalid. Check the operator address.", False
    return "Connection interrupted. The app will try again.", True


class EnrollmentNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class CoordinatorConnect(Connect):
    def handle_redirect(self, uri):
        raise ValueError("Coordinator WebSocket redirects are disabled")


def uuid_safe(value):
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")[:48] or "task"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Configuration
DEFAULT_ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "ws://127.0.0.1:8001/ws/seeder")
DEFAULT_ENROLLMENT_TOKEN = os.getenv("COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN", "")

class ComputeTorrentSeeder(ctk.CTk):
    def __init__(self):
        super().__init__()
        build = provider_identity()
        self.title(f"ComputeTorrent Provider · {build['petals_provider_build']} · Network v{build['petals_network_revision']}")
        self.geometry("1120x850")
        self.minsize(960, 680)
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
        self.settings_lock = threading.Lock()
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = {}
        if not isinstance(self.settings, dict):
            self.settings = {}
        had_legacy_join_code = "enrollment_token" in self.settings
        self.settings.pop("enrollment_token", None)
        recent_work = self.settings.get("recent_work", [])
        self.recent_work = [item for item in recent_work if isinstance(item, dict)][-20:] if isinstance(recent_work, list) else []
        os.environ.setdefault("COMPUTETORRENT_MODELS_DIR", str(self.app_data / "models"))
        self.sync_client = WebTorrentClient(str(self.app_data))
        self.libp2p_process = None
        self.libp2p_log = None
        self.libp2p_helper = Path(os.getenv("COMPUTETORRENT_LIBP2P_HELPER", str(_SYNC_SRC / "libp2p_peer.mjs"))).resolve()
        self.node_binary = os.getenv("COMPUTETORRENT_NODE", "node")
        self.node_id = self.settings.get("node_id")
        self.access_token = self.settings.get("access_token")
        self.orchestrator_url = self.settings.get("orchestrator_url")

        if not self.orchestrator_url:
            self.orchestrator_url = DEFAULT_ORCHESTRATOR_URL
        # The network-wide enrollment code is a one-time secret; keep it in
        # memory only and persist only this provider's revocable credential.
        self.enrollment_token = DEFAULT_ENROLLMENT_TOKEN
        try:
            self.cpu_limit = max(1, int(self.settings.get("cpu_limit", 2)))
            self.memory_limit_gb = max(2, int(self.settings.get("memory_limit_gb", 8)))
        except (TypeError, ValueError, OverflowError):
            self.cpu_limit, self.memory_limit_gb = 2, 8
        self.paused = False
        self.event_loop = None
        self.shutting_down = False
        self.connection_thread = None
        self.connection_task = None
        self.disconnect_requested = threading.Event()
        self.connection_state = "Disconnected"
        self.connection_note = ""
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
        self.available_update = None
        self.after(1500, self.check_for_update)

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
    
    def get_coordinator_url(self):
        if hasattr(self, "server_entry") and self.server_entry.winfo_exists():
            val = self.server_entry.get().strip()
            if val:
                return val
        return getattr(self, "orchestrator_url", "ws://127.0.0.1:8001/ws/seeder")

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

        # ── Top toolbar bar ──────────────────────────────────────────────────
        toolbar = ctk.CTkFrame(self, fg_color=ui.SURFACE, height=52)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        brand_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        brand_frame.pack(side="left", padx=(16, 8))
        ctk.CTkLabel(brand_frame, text="ComputeTorrent", text_color=ui.INK,
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        curr_ver = provider_identity().get("petals_provider_build", "dev")
        ctk.CTkLabel(brand_frame, text=f"v{curr_ver}", text_color=ui.MUTED,
                     font=("Segoe UI", 11)).pack(side="left", padx=(6, 0))

        # Update button (right side)
        self.update_button = ctk.CTkButton(toolbar, text="Check for updates", width=180,
                                            fg_color="#5750d5", hover_color="#4942be",
                                            font=("Segoe UI", 12, "bold"),
                                            command=self.update_clicked)
        self.update_button.pack(side="right", padx=12, pady=8)

        # Status label (centre-left)
        self.update_notice = NoticeLabel(toolbar, text="Checking for updates…", text_color=ui.MUTED,
                                          font=("Segoe UI", 11), wraplength=280, height=42)
        self.update_notice.pack(side="left", padx=16)

        # ── Update progress strip (hidden by default, shown during download) ─
        self._update_banner = ctk.CTkFrame(self, fg_color=ui.BG, height=36)
        # NOT packed yet — shown only when downloading

        self._update_progress_bar = ctk.CTkProgressBar(
            self._update_banner,
            width=460, height=16,
            corner_radius=8,
            fg_color=ui.BORDER,
            progress_color="#6366f1",
            mode="determinate",
        )
        self._update_progress_bar.set(0)
        self._update_progress_bar.pack(side="left", padx=(16, 8), pady=10)

        self._update_progress_label = ctk.CTkLabel(
            self._update_banner, text="0%  —  0.0 / 0.0 MB",
            font=("Courier New", 11), text_color="#5750d5"
        )
        self._update_progress_label.pack(side="left", padx=(0, 16), pady=10)

        # Restore available_update state if already found
        if getattr(self, "available_update", None):
            manifest, base, is_newer = self.available_update
            if is_newer:
                size_mb = round(manifest.get("size", 0) / (1024 * 1024), 1)
                self.update_notice.configure(
                    text=f"Update available: v{manifest.get('version')} ({size_mb} MB) — click to download",
                    text_color=ui.WARNING
                )
                self.update_button.configure(text="Download & install", fg_color="#ea580c", hover_color="#c2410c")
            else:
                self.update_notice.configure(
                    text=f"Up to date — v{manifest.get('version', curr_ver)}",
                    text_color=ui.GREEN
                )
                self.update_button.configure(text="Check for updates", fg_color="#5750d5", hover_color="#4942be")

    def check_for_update(self, manual=False):
        if self.shutting_down:
            return
        target_url = self.get_coordinator_url()
        curr_ver = provider_identity().get("petals_provider_build", "dev")
        if manual:
            self._set_update_ui(text="🔍 Contacting coordinator…", color="#38bdf8", btn_text=None, btn_state="disabled")
        def work():
            try:
                manifest, base, is_newer = check_update(target_url, curr_ver)
                def show():
                    self.available_update = (manifest, base, is_newer)
                    if is_newer:
                        size_mb = round(manifest.get("size", 0) / (1024 * 1024), 1)
                        self._set_update_ui(
                            text=f"🔥 Update v{manifest.get('version')} available — {size_mb} MB — click to install",
                            color="#fbbf24",
                            btn_text="⬇️ Download & Install",
                            btn_color="#ea580c", btn_hover="#c2410c",
                        )
                    else:
                        self._set_update_ui(
                            text=f"✅ Up to date — v{manifest.get('version', curr_ver)}",
                            color="#86efac",
                            btn_text="🔍 Check for Updates",
                        )
                self.after(0, show)
            except Exception as err:
                def show_err(err=str(err)):
                    if manual:
                        self._set_update_ui(text=f"⚠️ Update check failed: {err[:80]}", color="#f87171")
                    else:
                        self._set_update_ui(text="Updates: not available from this coordinator", color="#64748b")
                self.after(0, show_err)
        threading.Thread(target=work, daemon=True).start()
        self.after(30 * 60 * 1000, self.check_for_update)

    def _set_update_ui(self, text=None, color="#94a3b8", btn_text=None,
                       btn_color="#7c3aed", btn_hover="#6d28d9", btn_state="normal"):
        """Thread-safe helper: update the toolbar notice + button in one call."""
        try:
            if text and hasattr(self, "update_notice") and self.update_notice.winfo_exists():
                self.update_notice.configure(text=text, text_color=color)
            if hasattr(self, "update_button") and self.update_button.winfo_exists():
                self.update_button.configure(state=btn_state)
                if btn_text:
                    self.update_button.configure(text=btn_text, fg_color=btn_color, hover_color=btn_hover)
        except Exception:
            pass

    def _show_progress_banner(self):
        """Pack the download progress strip below the toolbar."""
        try:
            if hasattr(self, "_update_banner") and self._update_banner.winfo_exists():
                self._update_banner.pack(fill="x", after=self.winfo_children()[0])
        except Exception:
            pass

    def _hide_progress_banner(self):
        try:
            if hasattr(self, "_update_banner") and self._update_banner.winfo_exists():
                self._update_banner.pack_forget()
        except Exception:
            pass

    def _update_progress(self, downloaded, total):
        """Called from download thread; schedules UI update on main thread."""
        pct = downloaded / total if total else 0
        mb_done = downloaded / 1_048_576
        mb_tot = total / 1_048_576
        def _do():
            try:
                if hasattr(self, "_update_progress_bar") and self._update_progress_bar.winfo_exists():
                    self._update_progress_bar.set(pct)
                if hasattr(self, "_update_progress_label") and self._update_progress_label.winfo_exists():
                    self._update_progress_label.configure(
                        text=f"{int(pct * 100)}%  —  {mb_done:.1f} / {mb_tot:.1f} MB"
                    )
            except Exception:
                pass
        self.after(0, _do)

    def update_clicked(self):
        # If no update found yet — just trigger a fresh check
        if not getattr(self, "available_update", None):
            self.check_for_update(manual=True)
            return

        manifest, base, is_newer = self.available_update
        if not is_newer:
            # Re-check in case something changed
            self.check_for_update(manual=True)
            return

        if self.current_task:
            self._set_update_ui(
                text="⚠️ A task is running — finish it, then click again to update",
                color="#fbbf24", btn_text="⬇️ Download & Install",
            )
            return

        target_url = self.get_coordinator_url()
        curr_ver = provider_identity().get("petals_provider_build", "dev")

        self._set_update_ui(
            text=f"⬇️ Starting download of v{manifest.get('version')}…",
            color="#38bdf8",
            btn_text="⬇️ Downloading…",
            btn_state="disabled",
        )
        self.after(0, self._show_progress_banner)

        def work():
            try:
                # Re-fetch manifest fresh to validate it is still live
                fresh_manifest, fresh_base, still_newer = check_update(target_url, curr_ver)
                if not still_newer:
                    raise ValueError("Update is no longer available from this coordinator")

                staged = stage_update(
                    fresh_base, fresh_manifest, self.app_data,
                    progress_callback=self._update_progress,
                    current_build=curr_ver,
                )

                def on_done():
                    self._hide_progress_banner()
                    self._set_update_ui(
                        text="🎉 Download verified — launching installer now…",
                        color="#a855f7",
                        btn_text="✅ Installing…",
                        btn_state="disabled",
                    )
                    try:
                        restart_with_update(staged, self.app_data, current_build=curr_ver)
                        # Give the installer a moment to launch, then close the app
                        self.after(1500, self.close_application)
                    except Exception as install_err:
                        self._set_update_ui(
                            text=f"❌ Install failed: {install_err}",
                            color="#f87171",
                            btn_text="🔄 Retry",
                        )

                self.after(0, on_done)

            except Exception as error:
                def on_err(msg=str(error)):
                    self._hide_progress_banner()
                    self._set_update_ui(
                        text=f"❌ Update failed: {msg[:100]}",
                        color="#f87171",
                        btn_text="🔄 Retry Download",
                    )
                self.after(0, on_err)

        threading.Thread(target=work, daemon=True).start()
    
    def show_onboarding(self):
        # Background hardware scans must not discard an unsaved sharing choice.
        choice = (bool(self.layer_switch.get()) if hasattr(self, "layer_switch")
                  and self.layer_switch.winfo_exists() else self.petals_enabled)
        render_onboarding(self)
        self.layer_switch.select() if choice else self.layer_switch.deselect()

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
            "enrollment_token": (self.enrollment_entry.get().strip() if hasattr(self, "enrollment_entry") else "") or self.enrollment_token or DEFAULT_ENROLLMENT_TOKEN,
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
        if self.connection_thread is not None or self.shutting_down:
            return
        try:
            target = normalize_coordinator_address(self.server_entry.get())
            endpoint = coordinator_endpoint(target)
        except ValueError as error:
            self.connection_error.configure(text=str(error))
            return
        entered_code = self.enrollment_entry.get().strip() if hasattr(self, "enrollment_entry") else ""
        self.enrollment_token = entered_code or self.enrollment_token or DEFAULT_ENROLLMENT_TOKEN
        try:
            same_coordinator = endpoint == coordinator_endpoint(self.orchestrator_url)
        except ValueError:
            same_coordinator = False
        if (not self.node_id or not self.access_token or not same_coordinator) and not self.enrollment_token:
            self.enrollment_token = DEFAULT_ENROLLMENT_TOKEN
        try:
            self.cpu_limit = min(max(int(self.cpu_entry.get()), 1), max(1, self.profile["cpu_cores"]))
            self.memory_limit_gb = min(max(int(self.memory_entry.get()), 2), max(2, self.profile["RAM"]))
        except ValueError:
            self.connection_error.configure(text="CPU and RAM limits must be whole numbers")
            return
        if not same_coordinator:
            self.access_token = None
            self.node_id = None
        self.petals_enabled = bool(self.layer_switch.get())
        self.profile.update(provider_identity(), petals_enabled=self.petals_enabled, petals_protocol_version=1,
                            cpu_limit=self.cpu_limit, memory_limit_gb=self.memory_limit_gb)
        self.orchestrator_url = target
        self.settings.update({"orchestrator_url": self.orchestrator_url,
                              "cpu_limit": self.cpu_limit, "memory_limit_gb": self.memory_limit_gb})
        self.save_settings()
        self.disconnect_requested.clear()
        self.connection_state = "Connecting"
        self.connection_note = ""
        self.show_dashboard()
        self.connection_thread = threading.Thread(target=self.run_websocket, daemon=True)
        self.connection_thread.start()

    def save_settings(self):
        with self.settings_lock:
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
        token_to_send = (self.enrollment_token.strip() if self.enrollment_token else "") or DEFAULT_ENROLLMENT_TOKEN
        if not token_to_send:
            token_to_send = DEFAULT_ENROLLMENT_TOKEN
        request = urllib.request.Request(enrollment_url, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "X-Enrollment-Token": token_to_send,
                        "User-Agent": "ComputeTorrent-Provider/1.0"
        })
        with urllib.request.build_opener(EnrollmentNoRedirect()).open(request, timeout=15) as response:
            enrollment = json.loads(response.read(65536))
        if not isinstance(enrollment, dict) or not all(
            isinstance(enrollment.get(key), str) and enrollment[key] for key in ("node_id", "access_token")
        ):
            raise ValueError("Invalid enrollment response")
        return enrollment

    def run_websocket(self):
        async def run():
            self.event_loop = asyncio.get_running_loop()
            self.connection_task = asyncio.current_task()
            if not self.disconnect_requested.is_set():
                await self.connect_to_orchestrator()
        try:
            asyncio.run(run())
        except asyncio.CancelledError:
            pass
        finally:
            self.websocket = None
            self.is_connected = False
            self.event_loop = self.connection_task = None
            try:
                self.stop_connection_resources()
            finally:
                self.after(0, self.connection_finished)

    def stop_connection_resources(self):
        try:
            self.petals.stop()
        finally:
            process, self.libp2p_process = self.libp2p_process, None
            try:
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            finally:
                if self.libp2p_log:
                    self.libp2p_log.close()
                    self.libp2p_log = None

    def connection_finished(self):
        self.connection_thread = None
        self.current_task = None
        if self.shutting_down:
            self.destroy()
            return
        self.connection_state = "Disconnected"
        if self.disconnect_requested.is_set():
            self.connection_note = "Disconnected. You can connect again when ready."
        self.show_onboarding()

    def disconnect_provider(self):
        if self.connection_thread is None or self.disconnect_requested.is_set():
            return

        def cancel_if_idle():
            if self.current_task and not self.shutting_down:
                self.update_status("Finish the current task before disconnecting.")
                return
            self.disconnect_requested.set()
            self.set_connection_state("Disconnecting", "Closing this connection.")
            if self.connection_task is not None:
                self.connection_task.cancel()

        loop = self.event_loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(cancel_if_idle)
            except RuntimeError:
                pass
        else:
            cancel_if_idle()

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
                                "User-Agent": "ComputeTorrent-Provider/1.0"
            })
            with urllib.request.urlopen(req, timeout=10) as response:
                peer_info = json.loads(response.read().decode("utf-8"))
            bootstrap_address = peer_info.get("multiaddr")
            if not isinstance(bootstrap_address, str) or "/p2p/" not in bootstrap_address:
                raise RuntimeError("Coordinator did not provide a valid libp2p relay address")
            if not self.libp2p_helper.is_file():
                raise FileNotFoundError(f"libp2p helper is missing: {self.libp2p_helper}")
            log_path = self.app_data / "libp2p.log"
            if self.libp2p_log:
                self.libp2p_log.close()
            self.libp2p_log = log_path.open("a", encoding="utf-8")
            offset = log_path.stat().st_size
            self.libp2p_process = subprocess.Popen(
                [self.node_binary, str(self.libp2p_helper), "join", bootstrap_address],
                cwd=str(self.libp2p_helper.parent), stdin=subprocess.DEVNULL,
                stdout=self.libp2p_log, stderr=self.libp2p_log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.update_status("Joining libp2p LAN discovery and relay overlay…")
            deadline = time.monotonic() + 8
            with log_path.open("rb") as output:
                output.seek(offset)
                while time.monotonic() < deadline and not self.shutting_down:
                    if self.libp2p_process.poll() is not None:
                        raise RuntimeError("libp2p helper exited; see libp2p.log")
                    line = output.readline()
                    if line and b'"type":"libp2p_joined"' in line:
                        mode_str = f" ({self.network_mode})" if hasattr(self, 'network_mode') and self.network_mode else ""
                        self.update_status(f"Connected{mode_str}")
                        return
                    time.sleep(0.1)
            if self.libp2p_process.poll() is None:
                self.libp2p_process.terminate()
            raise RuntimeError("libp2p helper did not confirm bootstrap")
        except Exception as error:
            if not self.is_connected:
                self.update_status(f"Discovery overlay unavailable ({error})")

    def close_application(self):
        if self.shutting_down:
            return
        if self.current_task:
            self.update_status("Finish or cancel the active task before quitting.")
            return
        self.shutting_down = True
        if self.connection_thread is not None:
            self.connection_state = "Disconnecting"
            self.connection_note = "Closing the connection and releasing local resources."
            self.render_connection_state()
            self.disconnect_provider()
        else:
            self.destroy()

    async def connect_to_orchestrator(self):
        """Connect to orchestrator via WebSocket"""
        retry_count = 0
        overlay_task = None
        while not self.shutting_down and not self.disconnect_requested.is_set():
            try:
                coordinator_endpoint(self.orchestrator_url)
                self.set_connection_state("Connecting", "Contacting the coordinator.")
                if not self.node_id or not self.access_token:
                    self.set_connection_state("Enrolling", "Requesting a provider credential.")
                    enrollment = await asyncio.to_thread(self.enroll_provider)
                    if self.disconnect_requested.is_set():
                        return
                    self.node_id = enrollment["node_id"]
                    self.access_token = enrollment["access_token"]
                    self.enrollment_token = ""
                    self.save_settings()

                settings = getattr(self, "settings", {})
                alternatives = (settings.get("coordinator_candidates", [])
                    if settings.get("candidate_origin") == self.orchestrator_url else [])
                connection_url = self.orchestrator_url
                if alternatives:
                    connection_url = await asyncio.to_thread(select_endpoint, self.orchestrator_url,
                        alternatives, self.node_id, self.access_token)
                use_challenge = connection_url != self.orchestrator_url
                headers = {
                    **({} if use_challenge else {"Authorization": f"Bearer {self.access_token}"}),
                                        "User-Agent": "ComputeTorrent-Provider/1.0",
                }
                connect_kwargs = {
                    "open_timeout": 45,
                    "ping_interval": 15,
                    "ping_timeout": 35,
                    "close_timeout": 15,
                    "max_size": 100 * 1024 * 1024,
                }
                async with CoordinatorConnect(
                    connection_url, extra_headers=headers, **connect_kwargs
                ) as websocket:
                    # Send registration
                    parsed_conn = urlsplit(connection_url)
                    conn_host = parsed_conn.hostname or ""
                    is_local = conn_host in {"localhost", "127.0.0.1"}
                    if not is_local:
                        try:
                            addr = ipaddress.ip_address(conn_host)
                            is_local = addr.is_private or addr.is_loopback
                        except ValueError:
                            is_local = False
                    reported_net_mode = "LAN" if is_local else "WAN"
                    self.network_mode = reported_net_mode

                    register_msg = {
                        "type": "register",
                        "network_mode": reported_net_mode,
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
                    
                    if use_challenge:
                        client_nonce = secrets.token_hex(32)
                        await websocket.send(json.dumps({"type": "auth_challenge", "node_id": self.node_id,
                                                         "nonce": client_nonce}))
                        challenge = json.loads(await asyncio.wait_for(websocket.recv(), 15))
                        server_nonce = challenge.get("nonce", "")
                        key_hash = hashlib.sha256(self.access_token.encode()).hexdigest()
                        expected = route_proof(key_hash, "ct-server-v1", client_nonce, server_nonce, self.node_id)
                        if (challenge.get("type") != "auth_challenge" or not isinstance(server_nonce, str)
                                or len(server_nonce) != 64
                                or not hmac.compare_digest(str(challenge.get("proof", "")), expected)):
                            raise ValueError("Alternate endpoint did not prove coordinator identity")
                        register_msg["proof"] = route_proof(key_hash, "ct-register-v1", client_nonce,
                                                           server_nonce, register_digest(register_msg))
                    await websocket.send(json.dumps(register_msg))
                    self.set_connection_state("Registering", "Waiting for coordinator confirmation.")
                    first = await asyncio.wait_for(websocket.recv(), timeout=15)
                    ack = json.loads(first)
                    if (not isinstance(ack, dict) or ack.get("type") != "register_ack"
                            or ack.get("node_id") != self.node_id):
                        raise ValueError("Coordinator did not acknowledge this provider identity")
                    self.active_coordinator_url = connection_url
                    if "coordinator_endpoints" in ack and hasattr(self, "settings"):
                        self.settings.update(coordinator_candidates=route_candidates(ack["coordinator_endpoints"]),
                                             candidate_origin=self.orchestrator_url)
                        self.save_settings()
                    self.websocket = websocket
                    self.is_connected = True
                    retry_count = 0
                    self.set_connection_state("Registered", "The coordinator confirmed this provider.")
                    await self.handle_message(first)
                    if overlay_task is None or overlay_task.done():
                        overlay_task = asyncio.create_task(asyncio.to_thread(self.start_libp2p_peer))
                    
                    # Start heartbeat
                    heartbeat_task = asyncio.create_task(self.send_heartbeats(websocket))
                    close_watch = asyncio.create_task(self.watch_control_close(websocket))
                    
                    # Message loop
                    try:
                        async for message in websocket:
                            await self.handle_message(message)
                    finally:
                        self.websocket = None
                        self.is_connected = False
                        if not self.disconnect_requested.is_set() and not self.shutting_down:
                            self.set_connection_state("Reconnecting", "The coordinator connection closed.")
                        heartbeat_task.cancel()
                        close_watch.cancel()
                        await asyncio.gather(heartbeat_task, close_watch, return_exceptions=True)
                        
            except websockets.exceptions.ConnectionClosed as error:
                if error.rcvd is not None and error.rcvd.code == 1008:
                    # Revocation must not create a new identity using a remembered join code.
                    self.set_connection_state("Error", "Provider access was rejected. Ask the operator to restore access or explicitly enroll again.")
                    return
                else:
                    self.connection_note = "Coordinator connection closed."
            except Exception as error:
                self.connection_note, retryable = connection_failure(error)
                if not retryable:
                    return
            if self.shutting_down or self.disconnect_requested.is_set():
                break
            retry_count += 1
            delay = random.uniform(0.5, 1.0) * min(30, 2 ** min(retry_count, 5))
            self.set_connection_state("Reconnecting", f"{self.connection_note} Retry in {delay:.1f}s.")
            await asyncio.sleep(delay)

    async def watch_control_close(self, websocket):
        # A task handler may still be awaiting local work when the socket closes.
        await websocket.wait_closed()
        if self.websocket is websocket:
            self.is_connected = False
            if not self.disconnect_requested.is_set() and not self.shutting_down:
                self.set_connection_state("Reconnecting", "The coordinator connection closed.")

    async def send_heartbeats(self, websocket):
        """Send periodic heartbeats with failure tolerance"""
        while not self.shutting_down and self.websocket == websocket:
            try:
                await self.send_heartbeat_once(websocket)
                settings = getattr(self, "settings", {})
                if (not self.current_task and settings.get("candidate_origin") == self.orchestrator_url
                        and settings.get("coordinator_candidates")
                        and time.monotonic() >= getattr(self, "_next_route_probe", 0)):
                    self._next_route_probe = time.monotonic() + 60
                    preferred = await asyncio.to_thread(select_endpoint, self.orchestrator_url,
                        settings["coordinator_candidates"], self.node_id, self.access_token)
                    active = getattr(self, "active_coordinator_url", self.orchestrator_url)
                    if urlsplit(preferred).scheme == "ws" and urlsplit(active).scheme == "wss":
                        await websocket.close(code=1000, reason="Verified LAN route available")
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

        self.profile["petals"] = await asyncio.to_thread(self.petals.status, self.is_connected)
        host_lan_ip, host_lan_iface = _detect_active_lan_ip()
        active_url = getattr(self, "active_coordinator_url", self.orchestrator_url)
        coord_host = (urlsplit(active_url).hostname or "").strip().lower()
        local_coordinator = coord_host in {"127.0.0.1", "localhost", "::1"} or bool(host_lan_ip and coord_host == host_lan_ip.lower())
        layer_progress = self.profile["petals"].get("progress") if isinstance(self.profile.get("petals"), dict) else None
        layer_active = self.profile["petals"].get("status") not in {"idle", "failed", "stopped", "cancelled"}
        if not layer_active and str(self.current_task or "").startswith("Petals:"):
            self.current_task = None
        if hasattr(self, 'layer_label'):
            text = self.profile['petals']
            prog_text = f" ({int(layer_progress['percent'])}%)" if isinstance(layer_progress, dict) and layer_progress.get("percent") is not None else ""
            _layer_txt = f"Layers: {text.get('start', '—')}–{text.get('end', '—')} · {text.get('status', 'idle')}{prog_text}"
            self.after(0, lambda t=_layer_txt: self.layer_label.configure(text=t))
        await websocket.send(json.dumps({
            "type": "heartbeat",
            "node_id": self.node_id,
            "state": "paused" if self.paused else ("busy" if self.current_task or layer_active else "idle"),
            "host_lan_ip": host_lan_ip,
            "host_lan_interface": host_lan_iface,
            "local_coordinator": local_coordinator,
            "layer_progress": layer_progress if isinstance(layer_progress, dict) and layer_progress else None,
            "profile": self.profile,
        }))
        if not self.shutting_down:
            self.after(0, self.render_resources)

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
                net_mode = data.get("network_mode", "LAN")
                self.network_mode = net_mode
                self.update_status(f"Connected ({net_mode})")
            
            if msg_type == "petals_capacity":
                if self.current_task or self.paused or not self.petals_enabled:
                    await self.websocket.send(json.dumps({"type": "petals_capacity_result",
                        "job_id": data["job_id"], "error": "Provider is busy, paused or not opted in"}))
                    return
                self.current_task = "Petals capacity: " + data["job_id"][:8]
                self.update_task_info("Measuring native Petals block capacity and compute speed")
                self.update_status("Measuring model capacity")
                try:
                    measurement = await asyncio.to_thread(self.petals.measure_capacity, data,
                                                          self.cpu_limit, self.memory_limit_gb)
                    self.profile["petals_capacity"] = measurement
                    self.current_task = None
                    await self.websocket.send(json.dumps({"type": "petals_capacity_result",
                        "job_id": data["job_id"], "measurement": measurement,
                        "state": "paused" if self.paused else "idle"}))
                except Exception as exc:
                    await self.websocket.send(json.dumps({"type": "petals_capacity_result",
                        "job_id": data["job_id"], "error": str(exc)[-1000:]}))
                finally:
                    self.current_task = None
                return
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
                    await asyncio.to_thread(self.petals.start, data,
                        getattr(self, "active_coordinator_url", self.orchestrator_url), self.cpu_limit, self.memory_limit_gb)
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
                self.update_status("Connected")
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
        render_dashboard(self)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.configure(text="▶️ Resume contributions" if self.paused else "⏸️ Pause contributions")
        self.update_status("Paused; current task will finish" if self.paused and self.current_task else
                           ("Paused; not accepting tasks" if self.paused else "Resuming network contributions"))
        if self.websocket and self.event_loop and self.event_loop.is_running():
            asyncio.run_coroutine_threadsafe(websocket_profile(self), self.event_loop)
    
    def set_connection_state(self, state, detail):
        self.connection_state = state
        self.connection_note = detail
        if not self.shutting_down:
            self.after(0, self.render_connection_state)

    def render_connection_state(self):
        if not hasattr(self, "connection_badge") or not self.connection_badge.winfo_exists():
            return
        registered = self.connection_state == "Registered" and self.is_connected
        state = "Registered" if registered else (
            "Reconnecting" if self.connection_state == "Registered" else self.connection_state
        )
        self.connection_badge.configure(text=state, text_color=ui.GREEN if registered else ui.WARNING)
        self.connection_detail.configure(text=self.connection_note)
        node = self.node_id if registered else "Awaiting confirmation"
        self.node_label.configure(text=f"Node: {node}")

    def render_resources(self):
        if not hasattr(self, "cpu_detail") or not self.cpu_detail.winfo_exists():
            return
        self.cpu_detail.configure(text=f"{self.profile.get('cpu_cores', '—')} cores · Sharing up to {self.cpu_limit}")
        self.memory_detail.configure(text=f"{self.profile.get('free_ram_gb', '—')} GB free · Limit {self.memory_limit_gb} GB")
        vram = self.profile.get("VRAM")
        gpu_memory = f"{vram / 1024:.1f} GB dedicated VRAM" if vram else "No dedicated VRAM reported"
        self.gpu_detail.configure(text=gpu_memory)
        self.docker_detail.configure(text="Docker available" if self.profile.get("docker_ok") else "Docker unavailable")

    def update_status(self, text):
        if hasattr(self, 'status_label') and not self.shutting_down:
            try:
                clean = str(text).strip()
                display_text = clean if clean.lower().startswith("connected") else (clean if clean.lower().startswith("activity:") else f"Activity: {clean}")
                self.after(0, lambda: self.status_label.configure(text=display_text)
                           if not self.shutting_down and self.status_label.winfo_exists() else None)
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
    import multiprocessing
    multiprocessing.freeze_support()
    main()
