# 04 — Task Slicer and Scheduler

The current implementation handles independent prompt inference. It validates a batch, creates one ordered chunk per prompt, hashes the serialized prompt payload, and records the model, output limit, scheduling mode, and hardware requirements in the manifest.

## Available behavior

- Accepts 1–500 prompts, each 1–20,000 characters.
- Creates one prompt per chunk; the provider protocol currently requires this layout.
- Supports `WS-RR` round-robin selection and `CC-BP` capacity-based provider selection.
- Selects eligible online providers using Docker readiness, CUDA, RAM requirements, pause/busy state, and previous replica assignments.
- Requests up to three replicas based on currently connected, hardware-eligible providers.
- Preserves prompt order for result reassembly. If no provider is available, work remains queued.

The submitter chooses the scheduling mode. Automatic difficulty estimation, model-block partitioning, adaptive chunk sizes, task deadlines, and failed-chunk re-slicing are not present.

## Canary boundary

Canary probes are not mixed into ordinary task chunks by this slicer. When an operator enables the narrow known-answer canary MVP, the coordinator may queue a separate internal inference task. Its expected output hash is checked privately by the coordinator. Robust canary generation/injection and collusion-resistant verification remain future work; see [verification status](../06-verification-engine/README.md).

## Future work

- Model-parallel or pipeline splitting across machines.
- Capacity-weighted prompt grouping, adaptive task difficulty, and deadline-aware slicing.
- Retry/re-slice policy with bounded attempts and recovery metrics.
- Full canary protocol integration and evaluation.

This module does not implement distributed training, LoRA training, or splitting a single model across PCs.
