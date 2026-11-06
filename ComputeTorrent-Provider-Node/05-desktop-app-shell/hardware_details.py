"""Compute capacity only: no serial numbers, user files, or account inventory."""
import csv
import json
import os
import platform
import subprocess
import psutil


def details():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    cpu = platform.processor() or platform.machine()
    if os.name == "nt":
        try:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip():
                cpu = result.stdout.strip()
        except Exception:
            pass
    freq = psutil.cpu_freq()
    return {"cpu_model": cpu, "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(), "cpu_frequency_mhz": round(freq.current) if freq else None,
            "os": platform.system(), "os_release": platform.release(), "architecture": platform.machine(),
            "ram_total_gb": round(memory.total / 2**30, 2), "free_ram_gb": round(memory.available / 2**30, 2),
            "disk_total_gb": round(disk.total / 2**30, 1), "disk_free_gb": round(disk.free / 2**30, 1)}


def gpu_telemetry():
    devices = []
    # 1. Try NVIDIA SMI
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,utilization.gpu,driver_version",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0:
            for index, row in enumerate(csv.reader(result.stdout.splitlines())):
                if len(row) == 5:
                    devices.append({"index": index, "name": row[0].strip(), "vram_mib": int(row[1]),
                        "free_mib": int(row[2]), "utilization_pct": int(row[3]), "driver": row[4].strip(), "vendor": "NVIDIA"})
    except Exception:
        pass

    # 2. Try AMD ROCm SMI
    if not devices:
        try:
            rocm_res = subprocess.run(["rocm-smi", "--showmeminfo", "vram", "--showuse", "--showdriverversion", "--json"],
                                      capture_output=True, text=True, timeout=5,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if rocm_res.returncode == 0 and rocm_res.stdout.strip():
                rocm_data = json.loads(rocm_res.stdout)
                for index, (card_key, card_info) in enumerate(rocm_data.items()):
                    total_bytes = int(card_info.get("VRAM Total Memory (B)", 0))
                    used_bytes = int(card_info.get("VRAM Total Used Memory (B)", 0))
                    vram_mib = total_bytes // (1024 * 1024)
                    free_mib = max(0, (total_bytes - used_bytes) // (1024 * 1024))
                    devices.append({"index": index, "name": card_info.get("Card Series", f"AMD GPU {index}"),
                                    "vram_mib": vram_mib, "free_mib": free_mib,
                                    "utilization_pct": int(card_info.get("GPU use (%)", 0)),
                                    "driver": str(card_info.get("Driver version", "")),
                                    "vendor": "AMD"})
        except Exception:
            pass

    # 3. Windows display adapter telemetry (AMD / Intel / NVIDIA) via CIM
    if not devices and os.name == "nt":
        try:
            cmd = (
                "$ErrorActionPreference='Stop'; "
                "Get-CimInstance Win32_VideoController | "
                "Where-Object { $_.Name -and $_.Name -notmatch 'Microsoft Basic|Remote Display|Virtual Display' } | "
                "Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor | ConvertTo-Json -Compress"
            )
            result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                                    capture_output=True, text=True, timeout=8,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0 and result.stdout.strip():
                items = json.loads(result.stdout)
                if isinstance(items, dict):
                    items = [items]
                for index, item in enumerate(items):
                    name = item.get("Name", "").strip()
                    if not name:
                        continue
                    vendor = (
                        "AMD" if any(k in name.lower() for k in ["amd", "radeon"]) else
                        "NVIDIA" if any(k in name.lower() for k in ["nvidia", "geforce", "quadro", "rtx"]) else
                        "Intel" if any(k in name.lower() for k in ["intel", "arc", "iris"]) else "Unknown"
                    )
                    raw_ram = item.get("AdapterRAM") or 0
                    vram_mib = int(raw_ram) // (1024 * 1024) if raw_ram else 0
                    free_mib = int(vram_mib * 0.85) if vram_mib else 0
                    devices.append({
                        "index": index,
                        "name": name,
                        "vram_mib": vram_mib,
                        "free_mib": free_mib,
                        "utilization_pct": 0,
                        "driver": str(item.get("DriverVersion", "")).strip(),
                        "vendor": vendor
                    })
        except Exception:
            pass

    # 4. Linux sysfs for AMDGPU (/sys/class/drm/card*/device/mem_info_vram_*)
    if not devices and os.name == "posix":
        try:
            import glob
            cards = glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")
            for index, total_path in enumerate(cards):
                with open(total_path) as f:
                    vram_bytes = int(f.read().strip())
                used_path = total_path.replace("mem_info_vram_total", "mem_info_vram_used")
                used_bytes = 0
                if os.path.exists(used_path):
                    with open(used_path) as f:
                        used_bytes = int(f.read().strip())
                vram_mib = vram_bytes // (1024 * 1024)
                free_mib = max(0, (vram_bytes - used_bytes) // (1024 * 1024))
                devices.append({
                    "index": index,
                    "name": f"AMD GPU {index}",
                    "vram_mib": vram_mib,
                    "free_mib": free_mib,
                    "utilization_pct": 0,
                    "driver": "amdgpu",
                    "vendor": "AMD"
                })
        except Exception:
            pass

    free_total = max((d["free_mib"] for d in devices), default=0) if devices else 0
    return {"gpu_free_mib": free_total, "gpu_telemetry": devices}

