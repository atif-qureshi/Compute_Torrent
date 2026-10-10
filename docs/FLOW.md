# End-to-End Flow (requirements document concept, one builder)

This flow follows the **Seeder/Leecher requirements document** (`docs/source/requirements-seeder-and-portal.md`), the Project Concept, and the research proposal. One developer builds every part, so the "black boxes" of the requirements document (coordination server, slicer, verification) are real modules here.

| Torrent idea | ComputeTorrent meaning |
|---|---|
| Leecher | **Requestor**: submits a heavy task through the web portal |
| Seeder | **Provider**: donor PC running the desktop app |
| Swarm | **Per-task private WebTorrent swarm** (that task's requestor side + its assigned seeders only) |
| File pieces | **Chunks** made by task decomposition |
| Finished download | **Reassembled final result** |

## 0. Planes (what is central and what is not)

| Plane | Carried by | Central? |
|---|---|---|
| Control: register, heartbeat, assign, status, result | WebSocket between the seeder app and the **Coordination Server (Tracker/Relay)** | Yes, control only |
| Data: dataset, model and prompt chunks | Per-task private WebTorrent swarm, SHA-1 piece hashing | No |
| Direct upgrade | STUN handshake, WebRTC when possible; otherwise silently stay on the relay | No |
| Logic on the server: decomposition, allocation, verification, reassembly, credits | Coordination Server modules 04, 05, 06, 09 | Yes |
| Records and dashboard | PostgreSQL + Socket.io feed to the portal | Yes |

Wording for the defense about "trackerless": there is **no BitTorrent tracker for data**; swarms are private per task and torn down afterwards. A coordination server exists for **control messages only**. State this openly; the research proposal's "trackerless peer discovery" refers to the data plane.

## A. Happy path (Sara = seeder with RTX 3060, Ali = requestor with 500 prompts)

```
 ALI (Requestor, web portal)            COORDINATION SERVER                  SARA (Seeder app)
 -------------------------------        ------------------------------       ----------------------------------
                                                                            0. Launch: profile hardware, tier,
                                                                               WebSocket register, heartbeat
 1. Submit task (data, kind) --------->
                                        2. Analyse difficulty, slice into
                                           chunks (+hidden canaries),
                                           create per-task swarm, seed it
                                        3. Match chunks to online seeders
                                           by tier, capacity, availability
                                           ----- task_assign (chunks 7, 14) --->
                                                                            4. status: queued -> downloading,
                                                                               join swarm, download, verify hashes
                                                                            5. status: running, fresh Docker
                                                                               container, run 40 prompts
 <-------- live progress (Socket.io) <-------------- status_update ---------
                                                                            6. result_submit, status: completed,
                                                                               leave swarm, destroy container
                                        <------------- result_submit -------
                                        7. Verify (canary, replicas, audit)
                                        8. Reassemble all chunks in order
                                        9. Credits to seeders
 10. Result view and download <---------
                                        ----- verdict_notice (credits) ---->
                                                                            11. Update local stats, credits;
                                                                                back to idle
```

## B. Step-by-step detail

| Step | Actor | Action | State |
|---|---|---|---|
| 0 | Seeder app | Hardware Profiling builds `{GPU, VRAM, CUDA, RAM}`, assigns Tier-1 (VRAM 8 GB or more) or Tier-2; Networking Client registers over WebSocket; heartbeat starts | Seeder = ONLINE/IDLE |
| 1 | Requestor | Portal form: upload dataset/model, pick task kind (MVP implements Inference) | Task = SUBMITTED |
| 2 | Server: Slicer (04) | Difficulty estimate, mode choice, chunks of fitted size, hashes, hidden canary chunks, manifest; per-task swarm created and seeded by the server side | Task = SLICED, PUBLISHED |
| 3 | Server: Allocator (05) | Match chunks to online seeders (tier, memory, availability), add replicas for risky nodes, send `task_assign` | Chunk = ASSIGNED |
| 4 | Seeder: WebTorrent client | Join the private swarm named in the assignment, download model and chunks, verify hashes, resume if interrupted | Seeder reports `downloading` |
| 5 | Seeder: Docker sandbox | Fresh disposable container, CPU/memory/GPU limits, no network, chunk mounted read-only, run inference | Seeder reports `running` |
| 6 | Seeder: Networking Client | Send `result_submit` per chunk and `status_update: completed`; leave swarm; destroy container | Chunk = RETURNED |
| 7 | Server: Verification (06) | Canary check, replica comparison, partial re-run audit | Chunk = VERIFIED or FAILED |
| 8 | Server: Reassembly | Collect verified chunks, check count and order, stitch into final output | Task = REASSEMBLED |
| 9 | Server: Credits (09) | Credit verified work, penalize cheating, send `verdict_notice` | Ledger updated |
| 10 | Portal | Show final result, history | Task = COMPLETED |
| 11 | Seeder app | Local stats and credit balance updated; idle again | Seeder = IDLE |

## C. Failure flows

1. **Connection drops mid-task (NC-6):** seeder tries to resume; if resume fails it marks the task failed locally, re-registers, and the server reassigns the chunk.
2. **Container crash, timeout or limit exceeded (DS-5):** seeder reports `failed` with a reason; no silent retry on the seeder; server reassigns.
3. **Heartbeat lost:** server marks seeder offline, chunk back to PENDING, allocator reassigns (prefer a seeder that already has the chunk).
4. **Verification failure:** result rejected, seeder penalized, chunk re-run elsewhere.
5. **Hash mismatch on download:** discard, re-download from other peers or the server seed.
6. **Docker missing on the seeder (NFR-3):** app shows a clear message and installation guidance, never accepts tasks.
7. **Server restarts:** state rebuilt from PostgreSQL; seeders re-register automatically.
8. **User pauses seeding (APP-4):** seeder stops accepting new tasks; current task finishes or is handed back by the server.

## D. State machines

Task: `SUBMITTED -> SLICED -> PUBLISHED -> DISPATCHED -> VERIFYING -> REASSEMBLED -> COMPLETED` (or `FAILED`, `CANCELLED`).
Chunk: `PENDING -> ASSIGNED -> DOWNLOADING -> RUNNING -> RETURNED -> VERIFIED` (or `FAILED -> PENDING` retry, then task FAILED after max retries).
Seeder-reported states (status_update): `queued | downloading | running | completed | failed`.
Seeder: `OFFLINE -> ONLINE/IDLE -> BUSY -> IDLE`, plus `PAUSED` (user) and `SUSPENDED` (server, after verification abuse).

## E. What the requestor sees

Submitted -> Analysing difficulty -> Sliced into N chunks -> Assigned to M seeders -> Downloading -> Running (per-chunk progress) -> Verifying -> Reassembling -> Final result ready.

## F. Workload types

The pipeline is workload-agnostic. Task kinds in the requirements are Preprocessing, Inference, Training and LoRA. **MVP implements Inference** (batch LLM prompts). Other kinds exist as a field in `task_assign` only; full-scale model training is out of scope per the proposal.
