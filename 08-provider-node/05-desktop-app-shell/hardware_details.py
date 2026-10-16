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
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,utilization.gpu,driver_version",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        devices = []
        if result.returncode == 0:
            for index, row in enumerate(csv.reader(result.stdout.splitlines())):
                if len(row) == 5:
                    devices.append({"index": index, "name": row[0].strip(), "vram_mib": int(row[1]),
                        "free_mib": int(row[2]), "utilization_pct": int(row[3]), "driver": row[4].strip()})
        return {"gpu_free_mib": devices[0]["free_mib"] if devices else 0, "gpu_telemetry": devices}
    except Exception:
        return {"gpu_free_mib": 0, "gpu_telemetry": []}
