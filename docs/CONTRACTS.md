# Shared Contracts

All modules agree on these names and shapes. Change here first, then update modules. Shapes are described in words and tables, not code.

Source of the base messages: `docs/source/requirements-seeder-and-portal.md` section 7. **Base fields are kept exactly**; fields marked *extension* are our additions and are optional for the first demo.

## 1. Vocabulary (fixes earlier name clashes)

| Term | Meaning |
|---|---|
| Seeder / Provider / Worker | donor PC running the desktop app (some older module READMEs still say "worker"; it means the same thing) |
| Requestor / Leecher | person submitting a task through the portal |
| Coordination Server | Tracker/Relay: control plane plus server-side logic (folder `02-orchestrator-api`) |
| **Capability tier** | hardware class: **Tier-1** = VRAM 8 GB or more (LLM inference, LoRA); **Tier-2** = everything else (preprocessing, light work) |
| **Privacy level** | 1 public, 2 sliced so no seeder sees the whole task, 3 trusted seeders only. (Earlier drafts called these "privacy tiers"; renamed to avoid clashing with capability tier.) |

## 2. Core entities

| Entity | Key fields |
|---|---|
| Task | task_id, requester_id, task_kind, model_version_id, adapter_id (optional), privacy_level, mode, status, created_at, completed_at |
| Chunk | chunk_id, task_id, index, kind (REAL or CANARY), payload_hash, status, retry_count |
| Assignment | assignment_id, chunk_id, seeder_id, replica_no, assigned_at, deadline |
| Seeder | seeder_id, gpu, vram_gb, cuda, ram_gb, cpu_cores (extension), capability_tier, docker_ok (extension), availability_score u_j, trust_score, status, last_heartbeat |
| Result | result_id, assignment_id, output_ref, output_hash, p_time, d_time |
| Verdict | verdict_id, result_id, layer (CANARY, SERENE, VERILLM), outcome (PASS, FAIL, SUSPECT), detail |
| CreditEntry | entry_id, seeder_id, task_id, delta, reason |
| ModelVersion | model_version_id, name, weights_hash, torrent_infohash, created_at |
| AdapterVersion | adapter_id, base_model_version_id, lora_hash, torrent_infohash |
| Swarm | swarm_id, task_id, infohash, created_at, torn_down_at |
| Manifest | manifest_id, task_id, chunk list with hashes, model_version_id, adapter_id, canary map (server-private) |

## 3. Seeder <-> Coordination Server messages (WebSocket, JSON)

| type | Direction | Base fields (from requirements) | Extension fields |
|---|---|---|---|
| `register` | seeder -> server | `profile {GPU, VRAM, CUDA, RAM}`, `tier` (1 or 2) | cpu_cores, docker_ok, app_version, node_id, public_key (post-MVP) |
| `heartbeat` | seeder -> server | (not defined in requirements; needed by NC-2) node_id, state (idle, busy, paused) | free_ram, current_task_id |
| `task_assign` | server -> seeder | `task_id`, `chunk_ids`, `swarm_id`, `model_ref`, `task_kind` | chunk_hashes, deadline, model_version_id, adapter_id, privacy_level, decoding settings |
| `status_update` | seeder -> server | `task_id`, `state` (queued, downloading, running, completed, failed) | chunk_id, progress_percent, reason (when failed) |
| `result_submit` | seeder -> server | `task_id`, `chunk_id`, `output_ref` | output_hash, timings (download, run), signature (post-MVP) |
| `verdict_notice` | server -> seeder | (new) task_id, chunk_id, outcome | credits_earned, new_balance (feeds the credits display, APP-3) |
| `cancel` | server -> seeder | (new) task_id, chunk_id | reason |

Small outputs travel inside the WebSocket or by upload to the server; `output_ref` names the result file (for example `result_chunk7.json`). Large payloads use the swarm.

## 4. Portal <-> server

REST: create task, list tasks, get task, get result, credits and history, list model versions.
Socket.io (server -> portal): swarm status, active seeder count for the task, per-chunk progress, task state changes, completion signal (WP-2, WP-3).

## 5. Internal events (server side)

`TASK_CREATED`, `TASK_SLICED`, `SWARM_CREATED`, `CHUNK_ASSIGNED`, `CHUNK_RETURNED`, `CHUNK_VERIFIED`, `CHUNK_FAILED`, `SEEDER_ONLINE`, `SEEDER_LOST`, `TASK_COMPLETED`, `SWARM_TORN_DOWN`, `CREDITS_AWARDED`.

## 6. Rules everyone follows

1. Every payload and output carries a hash; mismatch means discard.
2. Canary membership is known only to the server; never put it in anything sent to seeders.
3. A seeder only ever receives the chunks assigned to it, through that task's private swarm.
4. Timestamps in UTC, IDs are UUIDs (task_id examples such as `abc123` in the requirements are placeholders).
5. Every state change is written to the database before any message goes out.
6. Seeders never run a task outside the Docker sandbox (hard invariant, APP-6).
