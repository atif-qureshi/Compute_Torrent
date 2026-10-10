# 02 — Coordination Server (Tracker/Relay + support service)

Folder name `02-orchestrator-api` is kept for continuity; in the requirements document this role is the "Coordination/Tracker Server". Since one person builds everything, it is now a real module, not a black box.

## Purpose
The server side of ComputeTorrent. It talks WebSocket to seeder apps, Socket.io and REST to the portal, runs the server-side logic (decomposition, allocation, verification, reassembly, credits), and stores everything in PostgreSQL. It is control plane only: chunk and model data move through per-task private WebTorrent swarms (module 07).

## Responsibilities
1. **Seeder WebSocket endpoint:** accept `register`, `heartbeat`, `status_update`, `result_submit`; send `task_assign`, `verdict_notice`, `cancel` (contracts in docs/CONTRACTS.md).
2. **Relay role:** when two peers cannot connect directly (STUN/WebRTC upgrade failed), keep messages and small payloads flowing through the server, invisibly to the user (NC-4).
3. **Portal API:** REST for tasks, results, history, credits; Socket.io for live progress.
4. **Task lifecycle** (state machines in docs/FLOW.md section D); calls modules in order: versioning (10) -> slicer (04) -> swarm creation (07) -> allocator (05) -> verification (06) -> reassembly -> credits (09).
5. **Seeder registry:** online seeders, profiles, capability tiers, heartbeats, availability history.
6. **Fault handling:** heartbeat timeouts, chunk reassignment, retry limits, restart recovery.
7. **Auth (MVP-level):** requestor login or API key; seeder identity by generated node id (public-key signatures post-MVP).
8. **Metrics:** store per-chunk download, run, verification times for module 11.

## Internal components (logical)
| Component | Job |
|---|---|
| Seeder gateway | WebSocket sessions, message validation, relay |
| Portal API | REST + Socket.io |
| Task service | lifecycle and state transitions |
| Dispatcher | sends assignments, tracks deadlines |
| Registry | seeder table with heartbeats |
| Verification coordinator | runs 06 for each returned result |
| Reassembler | stitches verified chunk outputs in order |
| Event publisher | feeds Socket.io |

## Dependencies
- Hard: 03 Database, 07 swarm service (to create and tear down swarms).
- Uses: 04, 05, 06, 09, 10 as internal services.
- Consumed by: 01 Portal, 08 Seeder app.
- Tech: FastAPI, Uvicorn, Pydantic, SQLAlchemy async, WebSocket, python-socketio (for the portal), optional ngrok for demos away from the LAN. Runs in the Docker stack under `docker/` (profile `app`).

## Rules
1. State is written to the database before any message goes out.
2. Idempotent handling: a repeated `result_submit` or `heartbeat` never duplicates work.
3. Every external call has a timeout and retry policy.
4. The canary map and audit positions never leave the server.
5. Do not assume anything about seeders beyond the contract (NFR-5 mirrored on the server side).

## Build steps
1. **Mock version first:** a tiny fake server that only speaks the four base messages, so the seeder app can be built and tested alone (see docs/BUILD-ORDER.md phase 0).
2. Real WebSocket gateway with registry and heartbeats.
3. Task create/get plus one-chunk assignment end to end.
4. Plug in slicer, allocator, swarm creation, then verification, reassembly, credits.
5. Socket.io feed for the portal.
6. Failure paths: timeouts, reassignment, restart recovery.

## Acceptance checks
- Seeder connects, shows online in the registry, and survives a server restart by re-registering.
- Duplicate `result_submit` is ignored safely.
- Unknown message types are rejected without crashing the gateway.
- 100 simulated heartbeats do not slow task APIs.

## Out of scope
Multiple coordination servers, high availability, TURN infrastructure beyond the relay role.
