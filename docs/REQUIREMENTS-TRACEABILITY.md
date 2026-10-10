# Requirements Traceability

Maps every requirement ID in `docs/source/requirements-seeder-and-portal.md` to the module that covers it. Phases refer to `docs/BUILD-ORDER.md`.

## 1. Seeder side (module 08)

| ID | Summary | Module README | Phase |
|---|---|---|---|
| HP-1 | Detect GPU, VRAM, CUDA, CPU cores, RAM | 08-provider-node/01-hardware-profiling | 1 |
| HP-2 | Node Profile `{GPU, VRAM, CUDA, RAM}` | 08/01-hardware-profiling, docs/CONTRACTS.md | 1 |
| HP-3 | Tier-1 if VRAM at least 8 GB, else Tier-2 | 08/01-hardware-profiling | 1 |
| HP-4 | Re-check on restart or Refresh | 08/01-hardware-profiling | 1 |
| HP-5 | Plain-language profile display | 08/01-hardware-profiling, 08/05-desktop-app-shell | 1, 5 |
| NC-1 | WebSocket register with profile and tier | 08/02-networking-client | 3 |
| NC-2 | Online/idle heartbeat | 08/02-networking-client | 3 |
| NC-3 | Receive task assignments | 08/02-networking-client | 3 |
| NC-4 | STUN, WebRTC upgrade, silent relay fallback | 08/02-networking-client, 07-network-layer | 3, 6 |
| NC-5 | Status updates queued to completed/failed | 08/02-networking-client | 3 |
| NC-6 | Reconnect, resume or fail and re-register | 08/02-networking-client | 3 |
| DS-1 | Fresh container per task | 08/03-docker-sandbox | 2 |
| DS-2 | CPU, memory caps; GPU scoped to task | 08/03-docker-sandbox | 2 |
| DS-3 | No network except chunk and result; no host access | 08/03-docker-sandbox (resolved: no network, chunk mounted) | 2 |
| DS-4 | Destroy container immediately, no leftovers | 08/03-docker-sandbox | 2 |
| DS-5 | Crash/timeout/limit reports `failed` | 08/03-docker-sandbox, 08/02-networking-client | 2, 3 |
| DS-6 | Local lifecycle logs only | 08/03-docker-sandbox, 08/05-desktop-app-shell | 2, 5 |
| WT-1 | Join per-task private swarm | 08/04-webtorrent-sync, 07-network-layer | 4 |
| WT-2 | Download with piece-hash integrity | 08/04-webtorrent-sync | 4 |
| WT-3 | Resume interrupted download | 08/04-webtorrent-sync | 4 |
| WT-4 | Leave swarm after completion | 08/04-webtorrent-sync, 07-network-layer | 4 |
| WT-5 | Chunk mounted into sandbox only | 08/04-webtorrent-sync, 08/03-docker-sandbox | 4, 5 |
| APP-1 | Single installable package (Windows) | 08/05-desktop-app-shell | 11 |
| APP-2 | Onboarding: detect, tier, Start Seeding | 08/05-desktop-app-shell | 5 |
| APP-3 | Dashboard: status, task progress, tasks done, credits | 08/05-desktop-app-shell, 09-incentives-credits | 5, 9 |
| APP-4 | Pause/Stop seeding | 08/05-desktop-app-shell | 5 |
| APP-5 | Background and system tray | 08/05-desktop-app-shell | 5 |
| APP-6 | Sandbox always active | 08/03-docker-sandbox, 08/05-desktop-app-shell | 2, 5 |

## 2. Portal (module 01)

| ID | Summary | Module README | Phase |
|---|---|---|---|
| WP-1 | Task submission form with task types | 01-submitter-portal | 9 |
| WP-2 | Live dashboard via Socket.io | 01-submitter-portal, 02-orchestrator-api | 9 |
| WP-3 | Result view and download | 01-submitter-portal | 9 |
| WP-4 | Credit and history view | 01-submitter-portal, 09-incentives-credits | 9 |
| WP-5 | Secondary priority | docs/BUILD-ORDER.md | 9 |

## 3. Non-functional

| ID | Summary | Where covered |
|---|---|---|
| NFR-1 | Task can never touch host outside its workspace | 08/03-docker-sandbox safety checks, 12-testing-validation |
| NFR-2 | Usable by non-technical users, installer provisions what is needed | 08/05-desktop-app-shell (realistic installer plan), docs/RISKS-AND-DECISIONS.md |
| NFR-3 | Graceful behavior without Docker | 08/05-desktop-app-shell problems screen |
| NFR-4 | Minimal idle usage | 08/05-desktop-app-shell, 08-provider-node |
| NFR-5 | Treat the tracker/relay as a fixed contract | docs/CONTRACTS.md, 08/02-networking-client |

## 4. Beyond the requirements document (added from the proposal and concept)

The requirements document treats these as another owner's area; with one builder they are real modules.

| Capability | Module |
|---|---|
| Coordination, tracker/relay, registry | 02-orchestrator-api |
| Task decomposition and manifests | 04-task-slicer-scheduler |
| Allocation and churn handling | 05-allocator-churn |
| Verification (canary, SERENE-lite, VeriLLM-lite) | 06-verification-engine |
| Reassembly | 02-orchestrator-api (reassembler) |
| Credits and trust | 09-incentives-credits |
| Model and adapter versions | 10-model-versioning |
| Experiments and benchmark dataset | 11-evaluation-benchmark |
| Database | 03-database, `docker/` |

## 5. Acceptance mapping

| Demo acceptance criterion | Verified by |
|---|---|
| Install with no manual steps beyond installer | 08/05 acceptance, 12 |
| Correct hardware and tier | 08/01 acceptance |
| Connects and shows Online | 08/02 acceptance |
| Test task runs isolated and returns result | 08/03 + 08/02 acceptance, 12 scenario 1 |
| No task files remain | 08/03 and 08/04 acceptance |
| Live status idle and busy | 08/05 acceptance |
| (Stretch) portal shows live progress | 01 acceptance |
