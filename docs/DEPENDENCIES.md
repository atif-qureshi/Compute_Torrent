# Dependencies

Reading note: dependencies below use the requirements-document flow (docs/FLOW.md). "02 Orchestrator" = the Coordination Server (Tracker/Relay plus server-side logic). Control messages go over WebSocket through 02; chunk and model data move through per-task swarms (07). Module 08 is split into five sub-modules (08.01 profiling, 08.02 networking client, 08.03 sandbox, 08.04 WebTorrent sync, 08.05 app shell); internal order is 01 -> 03 -> 02 -> 04 -> 05.

## 1. Module-to-module (who needs whom)

| Module | Needs (hard) | Needs (soft) | Used by |
|---|---|---|---|
| 03 Database | none | none | 02, 05, 06, 09, 10, 11 |
| 10 Model versioning | 03 | 07 | 02, 04, 08 |
| 02 Orchestrator | 03 | all others plugged in | 01, 08 |
| 07 Network layer | none (standalone) | 10 | 04, 08 |
| 08 Provider node | 02 (contracts), 07 | 10 | 05, 06 |
| 04 Slicer/scheduler | 02, 03, 10 | 05 | 05, 06 |
| 05 Allocator | 03, 04, 08 (profiles) | 09 (trust/priority) | 02 |
| 06 Verification | 03, 04 (canary chunks) | 08 | 09 |
| 09 Credits | 03, 06 | none | 05, 01 |
| 01 Portal | 02 | 09 | requester |
| 11 Benchmark | 02, 08, 04 | all | thesis results |
| 12 Testing | everything | none | all |

## 2. Dependency graph (build direction, arrows = "must exist before")

```
03 DB ---> 10 Versioning ---> 04 Slicer ---> 05 Allocator ---> 06 Verification ---> 09 Credits
 |                |              ^                ^                  |
 |                v              |                |                  v
 +--------> 02 Orchestrator <----+     08 Provider node <--- 07 Network        11 Benchmark
                |                                                         ^
                v                                                         |
             01 Portal ---------------------------------------------------+ (consumes results)
```

Critical path: **03 -> 02 -> 07 + 08 -> 04 -> 05 -> 06 -> 09 -> 11**.
Portal (01) can be built in parallel after 02's task API exists.

## 3. Technology dependencies

| Technology | Used by | Why | Fallback if blocked |
|---|---|---|---|
| Python 3.14 | 02, 04, 05, 06, 08, 09, 11 | core engine | 3.12 if a library lacks wheels |
| FastAPI, Uvicorn, Pydantic | 02 | REST + WebSocket | none |
| PostgreSQL 18 | 03 | persistent state | PostgreSQL 16/17 (schema is portable) |
| SQLAlchemy (async), Alembic, asyncpg | 03, 02 | ORM and migrations | none |
| Node.js + WebTorrent | 07 | chunk transfer | local HTTP transfer for first demo only |
| libp2p (Kademlia DHT, Circuit Relay) | 07 | trackerless discovery, NAT | WebTorrent built-in DHT first |
| Socket.io / WebSocket | 01, 02 | live dashboard | polling |
| ngrok | 02, 07 | expose orchestrator for off-LAN demo | same-LAN demo |
| Next.js, React, TypeScript, Tailwind | 01 | portal UI | plain React |
| CustomTkinter, PyInstaller | 08 | desktop client, single exe | CLI worker first |
| Docker Desktop | 08 | inference sandbox | restricted subprocess for dev only |
| psutil | 08 | CPU/RAM profiling | none |
| pynvml (nvidia-ml-py), CUDA | 08 | GPU/VRAM profiling | CPU-only mode |
| ZSTD | 04, 08 | payload compression | none (post-MVP) |
| Small LLM weights (CPU-friendly) | 08, 10, 11 | inference workload | a mock inference engine for pipeline tests |

## 4. External services and assets

- Public datasets only (for example HellaSwag, LAMBADA, GSM8K prompts) for benchmark prompts.
- Model hosting: model weights distributed through the swarm itself after the first seed.
- At least 3 machines (or 3 VMs/containers) for a real multi-node demo; otherwise run multiple worker instances on one PC.

## 5. Dependency risks

| Risk | Impact | Mitigation |
|---|---|---|
| Docker not installed on a worker | worker cannot run safely | profiling step reports it, worker declines tasks |
| NAT blocks peers | swarm splits | start on one LAN, add relay later |
| No GPU in test machines | cannot show GPU numbers | CPU-first MVP, GPU optional |
| libp2p JS/Python interop effort | schedule slip | keep DHT inside the Node p2p service, Python talks to it over a local API |
