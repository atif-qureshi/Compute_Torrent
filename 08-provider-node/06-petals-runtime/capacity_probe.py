"""Native Petals block sizing and compute measurement before placement.

Downloads config metadata only. The benchmark uses a fresh random block, not
pretrained weights or user prompts. CPU support is ComputeTorrent engineering;
upstream Petals automatic block-count selection targets GPUs.
"""
import gc
import os
import threading
import json
import math
from pathlib import Path
import time


def measure(request):
    import psutil
    import torch
    from petals.utils.auto_config import AutoDistributedConfig
    from petals.server.block_utils import get_block_size
    from petals.server.throughput import measure_compute_rps
    from petals.utils.convert_block import QuantType
    spec, device = request["spec"], request["device"]
    if device not in {"cpu", "cuda"}:
        raise ValueError("Unsupported capacity-probe device")
    torch.set_num_threads(max(1, int(request["cpu_limit"])))
    config = AutoDistributedConfig.from_pretrained(spec["model_id"], revision=spec["revision"])
    block = get_block_size(config, "memory", dtype=torch.float32, quant_type=QuantType.NONE)
    cache = int(2 * config.hidden_size * 1024 * 4 / config.num_key_value_groups)
    rps = measure_compute_rps(config, torch.device(device), torch.float32,
        quant_type=QuantType.NONE, tensor_parallel_devices=(torch.device(device),),
        n_tokens=1, n_steps=16, inference=True)
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
        available = torch.cuda.mem_get_info()[0]
        reserve = max(256 * 2**20, int(2 * 2**30 / 14336 * config.hidden_size))
    else:
        available = min(psutil.virtual_memory().available, int(request["memory_gb"] * 2**30))
        # psutil alone may report the Docker VM's RAM rather than this cgroup.
        for limit_file, used_file in (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
                                     ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes")):
            try:
                available = min(available, max(0, int(Path(limit_file).read_text()) - int(Path(used_file).read_text())))
            except (OSError, ValueError):
                pass
        reserve = 256 * 2**20
    if not math.isfinite(rps) or rps <= 0:
        raise RuntimeError("Native Petals benchmark returned no usable throughput")
    return dict(model_id=spec["model_id"], revision=spec["revision"], device=device,
        dtype="float32", quant_type="none", block_bytes=block, cache_bytes_per_block=cache,
        available_bytes=available, reserve_bytes=reserve,
        capacity_layers=max(0, min(config.num_hidden_layers, int((available - reserve) // (block + cache)))),
        inference_rps=rps, measured_at=time.time(), source="petals-native-v1")


if __name__ == "__main__":
    def lease_watch():
        while True:
            try:
                valid = time.time() - float(Path("/state/capacity-lease").read_text()) < 90
            except (OSError, ValueError):
                valid = False
            if not valid:
                os._exit(2)
            time.sleep(5)
    threading.Thread(target=lease_watch, daemon=True).start()
    request = json.loads(Path("/state/capacity-request.json").read_text())
    print("CT_CAPACITY " + json.dumps(measure(request)), flush=True)
