import subprocess
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
        if not self.pynvml_available:
            return None, 0, False, 0
        try:
            count = self.pynvml.nvmlDeviceGetCount()
            if count == 0:
                return None, 0, False, 0
            best_gpu, max_vram = None, 0
            for i in range(count):
                handle = self.pynvml.nvmlDeviceGetHandleByIndex(i)
                name = self.pynvml.nvmlDeviceGetName(handle)
                mem = self.pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_gb = mem.total // (1024 ** 3)
                if vram_gb > max_vram:
                    max_vram, best_gpu = vram_gb, name
            return best_gpu, max_vram, True, count
        except:
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
            summary = f"GPU: {p.GPU}, {p.VRAM}GB VRAM -> Tier {tier}"
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

