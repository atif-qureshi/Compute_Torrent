# ComputeTorrent — Volunteer Computing MVP

Decentralized P2P distributed computing on idle consumer computers, using a torrent-style **Seeder (provider) and Leecher (requestor)** model. The MVP workload is batch LLM inference.

This repository started as a planning blueprint and now includes an executable MVP implementation for LLM inference, WebTorrent transfer, distributed prompt slicing and replica verification, credits/history, and Windows seeder packaging. See [IMPLEMENTATION-SETUP.md](IMPLEMENTATION-SETUP.md) for the deploy and operator workflow. Research and roadmap modules may still be planning-only; the implementation guide records current scope and operational limits.

## Where the ideas come from

| Source | Used for |
|---|---|
| `docs/source/requirements-seeder-and-portal.md` | the flow and the seeder app, portal and message contracts (requirement IDs HP, NC, DS, WT, APP, WP, NFR) |
| Project Concept (leecher/seeder, decomposition, reassembly, fault tolerance, credits) | the overall model |
| Research proposal | verification layers, credits, versioning, evaluation method, scope exclusions |

Builder: **one developer builds everything**, so the parts the requirements document treats as another owner's black boxes (coordination server, slicer, verification) are real modules here.

## 1. What the MVP must prove

*A user installs the Seeder app, the app detects hardware, connects to the network, receives a task, runs it inside an isolated Docker container, and returns a result without risking the user's files. Then, many seeders do this together: a requestor submits a task, it is sliced, spread over per-task private swarms, verified without blockchain, reassembled into one result, providers earn credits, and we measure speedup against a single node.*

## 2. MVP scope cut

| Priority | Included |
|---|---|
| MUST | Seeder desktop app (profiling, networking client, Docker sandbox, WebTorrent sync, app shell), coordination server with registry, one scheduling mode, slicer and reassembly, canary verification, replica comparison (SERENE-lite), credits, model version manifest, benchmark harness (1, 2, 4 seeders), portal (basic) |
| SHOULD | Second scheduling mode, VeriLLM-lite audit, churn-aware allocator with availability score, STUN/WebRTC upgrade, live Socket.io dashboard polish |
| LATER | libp2p DHT and Circuit Relay, privacy levels beyond a label, ZSTD tuning, microbatching, requestor-side desktop app, real GPU scale tests |
| OUT OF SCOPE | Blockchain, crypto, real money, TEE, full-scale training, non-NVIDIA GPUs, data centers |

CPU-first: a small model on CPU proves the pipeline; GPU and Tier-1 paths are detected at runtime.

## 3. Folder map (one README per functionality)

| # | Folder | Functionality |
|---|---|---|
| 01 | `01-submitter-portal/` | Requestor web portal: task form, live dashboard, results, history |
| 02 | `02-orchestrator-api/` | **Coordination Server** (Tracker/Relay + logic): WebSocket gateway, lifecycle, registry |
| 03 | `03-database/` | PostgreSQL schema, migrations, data ownership |
| 04 | `04-task-slicer-scheduler/` | Difficulty analysis, mode selector, chunking, manifests |
| 05 | `05-allocator-churn/` | Tier, memory and churn-aware allocation, reassignment |
| 06 | `06-verification-engine/` | Canary Trap, SERENE-lite, VeriLLM-lite |
| 07 | `07-network-layer/` | Per-task private WebTorrent swarms, connectivity, teardown |
| 08 | `08-provider-node/` | **Seeder desktop app** (index README plus five sub-modules below) |
| 08.01 | `08-provider-node/01-hardware-profiling/` | GPU, VRAM, CUDA, RAM detection, capability tier (HP) |
| 08.02 | `08-provider-node/02-networking-client/` | WebSocket register, heartbeat, messages, reconnect (NC) |
| 08.03 | `08-provider-node/03-docker-sandbox/` | Fresh disposable container per task (DS) |
| 08.04 | `08-provider-node/04-webtorrent-sync/` | Join swarm, download, verify, resume, leave (WT) |
| 08.05 | `08-provider-node/05-desktop-app-shell/` | UI, onboarding, tray, pause, installer (APP) |
| 09 | `09-incentives-credits/` | BOINC-style credits, trust, priority |
| 10 | `10-model-versioning/` | Model, adapter, benchmark version tracking |
| 11 | `11-evaluation-benchmark/` | Single-node vs P2P experiments and metrics |
| 12 | `12-testing-validation/` | Test strategy, fault injection, demo acceptance |

Cross-cutting docs:
- `docs/FLOW.md` — end-to-end flow (Sara and Ali example), failure flows, state machines
- `docs/APPLICATIONS.md` — the applications you build and how they connect
- `docs/CONTRACTS.md` — messages and data shapes shared by all modules
- `docs/REQUIREMENTS-TRACEABILITY.md` — every requirement ID mapped to a module and phase
- `docs/DEPENDENCIES.md` — module and technology dependency maps
- `docs/BUILD-ORDER.md` — solo build plan, milestones, cut order
- `docs/RISKS-AND-DECISIONS.md` — decisions taken, new risks, open questions, proposal inconsistencies
- `docs/source/requirements-seeder-and-portal.md` — the original requirements document
- `docker/README.md` — local Docker stack: PostgreSQL 18 now, server image ready for when its code exists

## 4. Suggested repository layout (when you start coding)

```
computetorrent/
  portal/            (Next.js + TypeScript)                  -> 01
  server/            (FastAPI coordination server)           -> 02, 04, 05, 06, 09, 10
  swarm/             (Node.js WebTorrent swarm service)      -> 07
  db/                (Alembic migrations)                    -> 03
  seeder-app/        (Python + CustomTkinter)                -> 08.01, 08.02, 08.05
    sandbox/         (Docker runner and image)               -> 08.03
    sync-helper/     (Node.js WebTorrent helper)              -> 08.04
  mock-server/       (fake server for early seeder work)     -> docs/BUILD-ORDER.md phase 0
  bench/             (experiment harness)                    -> 11
  tests/                                                     -> 12
  docker/            (compose, env, db init, server image)   -> 03, 02
  docs/
```

Note: the Dockerfile in `docker/orchestrator/` expects the server code under `orchestrator/`; if you use the folder name `server/` above, change the paths in that Dockerfile and in `docker-compose.yml`.

## 5. Reading order

1. `docs/FLOW.md` to see the whole system running
2. `docs/APPLICATIONS.md` to see what you are building
3. `docs/CONTRACTS.md` to fix the shared language
4. `docs/BUILD-ORDER.md` and `docs/DEPENDENCIES.md` to plan the work
5. `docs/REQUIREMENTS-TRACEABILITY.md` when checking requirement coverage
6. Module READMEs when you start each module