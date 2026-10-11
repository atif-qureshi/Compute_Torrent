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

## Petals-style layer execution target

The requested distributed LLM mode is a separate execution type: a model's
transformer blocks are assigned as contiguous layer ranges to multiple peers,
with the ranges sized from each peer's available VRAM or RAM. Generated hidden
states flow through those peers in layer order for each token. It is not the
same as sending different prompts to different computers.

An independent upstream Petals runtime now lives in
[`../08-provider-node/06-petals-runtime/`](../08-provider-node/06-petals-runtime/).
It starts real Petals block servers and a generation client, which use Petals'
own DHT and block-serving protocol. It is not integrated into the portal's
`/api/tasks` or this scheduler; the existing WebSocket `task_assign` path still
runs the full model on one provider. The local capacity planner is a planning
helper only and does not allocate blocks to Petals servers.

The current demo artifact is Qwen2.5 GGUF, which is suitable for the existing
single-provider `llama.cpp` path. Petals needs a Hugging Face Transformer model
supported by its upstream runtime (not the current GGUF). Do not label the GGUF
full-model path as distributed-layer inference. Public-swarm prompts are
processed by other peers; users must not submit secrets or private data to it.

## Canary boundary

Canary probes are not mixed into ordinary task chunks by this slicer. When an operator enables the narrow known-answer canary MVP, the coordinator may queue a separate internal inference task. Its expected output hash is checked privately by the coordinator. Robust canary generation/injection and collusion-resistant verification remain future work; see [verification status](../06-verification-engine/README.md).

## Future work

- Portal task/catalog/gateway integration for the separate Petals runtime.
- Capacity-weighted prompt grouping, adaptive task difficulty, and deadline-aware slicing.
- Retry/re-slice policy with bounded attempts and recovery metrics.
- Full canary protocol integration and evaluation.

This module does not implement distributed training, LoRA training, or splitting a single model across PCs.
