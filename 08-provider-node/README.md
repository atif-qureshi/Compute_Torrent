# 08 — Provider (Seeder) Desktop Application

## Purpose
The installable desktop app donors run on their PC. It detects hardware, joins the network, receives a task, runs it safely inside an isolated Docker container, and returns the result, without ever putting the user's files or system at risk.

MVP goal sentence (from the requirements): *a user installs the Seeder app, the app detects hardware, connects, receives a task, runs it in an isolated container, and returns the result.*

## Sub-modules (one README each)
| Folder | Functionality | Requirement IDs |
|---|---|---|
| `01-hardware-profiling/` | detect GPU, VRAM, CUDA, CPU, RAM; assign capability tier | HP-1 to HP-5 |
| `02-networking-client/` | WebSocket register, heartbeat, task messages, STUN/WebRTC, reconnect | NC-1 to NC-6 |
| `03-docker-sandbox/` | fresh disposable container per task, limits, no network, destroy | DS-1 to DS-6 |
| `04-webtorrent-sync/` | join per-task private swarm, download, verify, resume, leave | WT-1 to WT-5 |
| `05-desktop-app-shell/` | UI, onboarding, tray, pause, packaging, Docker-missing flow | APP-1 to APP-6 |

Non-functional requirements NFR-1 to NFR-5 apply to all five (see `docs/REQUIREMENTS-TRACEABILITY.md`).

## How the pieces connect
```
Hardware profiling --> Networking client <==WebSocket==> Coordination server (02)
                            |
                            v
                   Task receiver / dispatcher (app shell)
                      |                      |
                      v                      v
           WebTorrent sync  ---chunk--->  Docker sandbox
          (private task swarm)             (isolated run)
                                              |
                          result via Networking client --> server
```

## Seeder lifecycle
Install -> first run (profile, tier, onboarding) -> "Start Seeding" -> register and heartbeat -> idle -> `task_assign` -> `queued` -> `downloading` (swarm) -> `running` (sandbox) -> `result_submit` -> `completed` -> leave swarm, destroy container, clean workspace -> update local stats -> idle.

## Hard invariants
1. No task ever runs outside the Docker sandbox (APP-6).
2. Nothing from a task survives on the host after it finishes (DS-4, acceptance criteria).
3. The app never reads or writes outside its own working directory on the host (NFR-1).
4. Idle resource use stays minimal (NFR-4).

## Dependencies
- Needs: contracts in docs/CONTRACTS.md, the coordination server (or its mock) from module 02, swarm protocol from 07.
- Tech: Python, psutil, pynvml (nvidia-ml-py), CustomTkinter (or PyQt), Docker Engine plus NVIDIA Container Toolkit (GPU), a bundled Node.js WebTorrent helper, PyInstaller for a single `.exe`.
- Used by: 05 (profiles, tiers), 06 (producer of results), 09 (credits display).

## Build order inside this module (from the requirements)
1. 01 hardware profiling (testable alone)
2. 03 Docker sandbox with a dummy script
3. 02 networking client against the mock server
4. 04 WebTorrent sync with a test swarm
5. 05 app shell wiring everything, then packaging

## Acceptance (module level)
- Install on a clean Windows PC (Docker present) and reach "Online" without manual steps beyond the installer.
- Correct hardware and tier shown in plain language.
- A test task is received, run inside a container, result returned, and no task files remain.
- UI shows live status while idle and while processing.

## Out of scope
Auto-update, non-NVIDIA GPU acceleration, macOS and Linux installers (future work).