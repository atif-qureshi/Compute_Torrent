"""Deterministic WS-RR slicer for independent prompt batches."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


MAX_PROMPTS = 500
MAX_PROMPT_CHARS = 20_000


class TaskSlicer:
    """Create ordered prompt work units and replica assignments.

    Inference prompts are independent requests; they are not split mid-text,
    which would change their meaning. Large prompt batches become multiple
    ordered chunks and can be routed independently (WS-RR).
    """

    def __init__(self, max_prompts_per_chunk: int = 1):
        self.max_prompts_per_chunk = max(1, min(int(max_prompts_per_chunk), 32))

    def slice_task(self, task_id: str, prompts: list[str], model_name: str,
                   model_file: str, model_sha256: str, replicas: int = 1,
                   max_tokens: int = 256, seed: int = 42,
                   mode: str = "WS-RR", min_ram_gb: int = 0,
                   require_cuda: bool = False, adapter_file: str | None = None,
                   adapter_sha256: str | None = None) -> dict[str, Any]:
        if not prompts or len(prompts) > MAX_PROMPTS:
            raise ValueError(f"Supply between 1 and {MAX_PROMPTS} prompts")
        if any(not isinstance(p, str) or not p.strip() or len(p) > MAX_PROMPT_CHARS for p in prompts):
            raise ValueError(f"Each prompt must contain 1 to {MAX_PROMPT_CHARS} characters")
        replicas = max(1, min(int(replicas), 3))
        max_tokens = max(1, min(int(max_tokens), 2048))
        if mode not in {"WS-RR", "CC-BP"}:
            raise ValueError("mode must be WS-RR or CC-BP")
        min_ram_gb = max(0, min(int(min_ram_gb), 512))
        chunks = []
        for offset in range(0, len(prompts), self.max_prompts_per_chunk):
            group = prompts[offset:offset + self.max_prompts_per_chunk]
            index = offset // self.max_prompts_per_chunk
            payload = json.dumps(group, ensure_ascii=False, separators=(",", ":"))
            content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            chunks.append({
                    "chunk_id": f"{task_id}-chunk-{index}",
                    "index": index,
                    "prompts": group,
                    "payload_sha256": content_hash,
                    "model_name": model_name,
                    "model_file": model_file,
                    "model_sha256": model_sha256,
                    "adapter_file": adapter_file,
                    "adapter_sha256": adapter_sha256,
                    "mode": mode,
                    "requirements": {"min_ram_gb": min_ram_gb, "require_cuda": bool(require_cuda)},
                    "replicas_required": replicas,
                    "replica_results": [],
                    "providers": [],
                    "max_tokens": max_tokens,
                    "seed": seed,
                    "status": "pending",
                    "assigned_to": None,
                    "output": None,
                    "output_sha256": None,
                })
        return {
            "mode": mode,
            "prompt_count": len(prompts),
            "chunk_count": math.ceil(len(prompts) / self.max_prompts_per_chunk),
            "replicas": replicas,
            "chunks": chunks,
        }


def get_task_slicer() -> TaskSlicer:
    return TaskSlicer()
