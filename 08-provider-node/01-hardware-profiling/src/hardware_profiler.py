import subprocess
import csv
import json
import sys
import psutil
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class NodeProfile:
    GPU: Optional[str]
    VRAM: int
    CUDA: bool
    RAM: int
    cpu_cores: int
    gpu_count: int
    docker_ok: bool

@dataclass  
class ProfileResult:
    profile: NodeProfile
    tier: int
    summary: str

class HardwareProfiler:
    def __init__(self):
        self.pynvml_available = self._init_nvidia()
    
    def _init_nvidia(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self.pynvml = pynvml
            return True
        except:
            return False
    
    def detect_gpu(self):
        nvidia_devices = []
        if self.pynvml_available:
            try:
                for index in range(self.pynvml.nvmlDeviceGetCount()):
                    handle = self.pynvml.nvmlDeviceGetHandleByIndex(index)
                    name = self.pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode("utf-8", errors="replace")
                    memory = self.pynvml.nvmlDeviceGetMemoryInfo(handle)
                    nvidia_devices.append((str(name), memory.total // (1024 ** 3)))
            except Exception:
                nvidia_devices = []
        if nvidia_devices:
            names = list(dict.fromkeys(name for name, _ in nvidia_devices))
            return ", ".join(names), max(vram for _, vram in nvidia_devices), True, len(nvidia_devices)

        # Use NVIDIA's CLI when pynvml isn't available, then enumerate Windows
        # display adapters to include AMD/Intel GPUs as CPU-inference workers.
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                devices = [(row[0].strip(), int(float(row[1].strip())) // 1024)
                           for row in csv.reader(result.stdout.splitlines()) if len(row) >= 2]
                if devices:
                    names = list(dict.fromkeys(name for name, _ in devices))
                    return ", ".join(names), max(vram for _, vram in devices), True, len(devices)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

        if sys.platform == "win32":
            try:
                command = (
                    "$ErrorActionPreference='Stop'; Get-CimInstance Win32_VideoController | "
                    "Where-Object { $_.Name -and $_.Name -notmatch 'Microsoft Basic|Remote Display|Virtual Display' } | "
                    "Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"
                )
                result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                        capture_output=True, text=True, timeout=8)
                if result.returncode == 0 and result.stdout.strip():
                    names = json.loads(result.stdout)
                    if isinstance(names, str):
                        names = [names]
                    names = list(dict.fromkeys(name.strip() for name in names if isinstance(name, str) and name.strip()))
                    if names:
                        return ", ".join(names), 0, False, len(names)
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                pass
        return None, 0, False, 0
    
    def detect_ram(self):
        return psutil.virtual_memory().total // (1024 ** 3)
    
    def detect_cpu_cores(self):
        c = psutil.cpu_count(logical=False)
        return c if c else psutil.cpu_count(logical=True)
    
    def check_docker(self):
        try:
            r = subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
            return r.returncode == 0
        except:
            return False
    
    def assign_tier(self, vram_gb):
        return 1 if vram_gb >= 8 else 2
    
    def profile(self):
        gpu, vram, cuda, count = self.detect_gpu()
        p = NodeProfile(GPU=gpu, VRAM=vram, CUDA=cuda, RAM=self.detect_ram(),
                       cpu_cores=self.detect_cpu_cores(), gpu_count=count,
                       docker_ok=self.check_docker())
        tier = self.assign_tier(vram)
        if p.GPU:
            vram = f", {p.VRAM}GB NVIDIA VRAM" if p.VRAM else ", VRAM not reported"
            backend = "CUDA available" if p.CUDA else "CPU inference (no CUDA)"
            summary = f"GPU: {p.GPU}{vram} -> {backend}, Tier {tier}"
        else:
            summary = f"No GPU -> Tier {tier} (CPU only)"
        return ProfileResult(p, tier, summary)

def main():
    profiler = HardwareProfiler()
    result = profiler.profile()
    print(result.summary)
    print(f"RAM: {result.profile.RAM}GB, Cores: {result.profile.cpu_cores}")
    print(f"Docker: {result.profile.docker_ok}")

if __name__ == "__main__":
    main()

