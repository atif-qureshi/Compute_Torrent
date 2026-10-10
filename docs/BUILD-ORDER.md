# Build Order (one developer)

> Historical build plan from the initial requirements. It records the intended order, not live completion status. Use [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) for what works now and which research layers remain future work.

You build every part, so the order matters more than speed. Rule: **a working seeder demo against a mock server comes first**, then the real server, then research features. Sizes: S = a few days, M = 1 to 2 weeks, L = 2 to 4 weeks (rough, for one person). The proposal's Gantt (about 250 project days) is the upper bound; plan to stop at milestone M4 if time runs short.

## Phase 0 — Foundations (S)
- Repo, branches, `docker/` stack: `docker compose up -d db` gives a healthy PostgreSQL 18.
- Freeze docs/CONTRACTS.md (the four base messages plus heartbeat).
- Build the **mock server**: a tiny fake coordination server that accepts `register`, sends a fake `task_assign`, prints `status_update` and `result_submit`.
- **Done when:** the mock server runs and a script can talk to it.

## Phase 1 — Hardware profiling (S) : HP-1 to HP-5
- Module 08.01, testable alone.
- **Done when:** correct profile and tier on a GPU PC and on a PC without a GPU.

## Phase 2 — Docker sandbox (M) : DS-1 to DS-6, APP-6
- Module 08.03: dummy script, then limits, no network, mount layout, destroy, escape tests.
- **Done when:** an isolated run leaves nothing behind and escape attempts fail.

## Phase 3 — Networking client (M) : NC-1 to NC-6
- Module 08.02 against the mock server, including reconnect.
- **Done when:** node shows Online, receives a fake task, reports all states, survives mock restarts.

## Phase 4 — WebTorrent sync (M) : WT-1 to WT-5
- Module 08.04 with a test swarm (a script acting as the server-side seeder), plus module 07's first steps.
- **Done when:** download, resume, hash check, leave, cleanup all work.

## Phase 5 — Seeder app shell (M) : APP-2 to APP-5
- Module 08.05: onboarding, dashboard, tray, pause, Docker-missing screen, all wired to the mock server.
- **MILESTONE M1 — Seeder demo with mock server:** the requirements' acceptance criteria 1 to 6 pass.

## Phase 6 — Real coordination server, single chunk (M)
- Modules 02, 03, 10 (minimal): replace the mock, real registry, one task = one chunk, real small model on CPU or GPU.
- Swarm creation by the server (module 07 server side), `result_submit` stored, result shown by API.
- **MILESTONE M2 — One real task end to end.**

## Phase 7 — Slicing, allocation, reassembly (L)
- Modules 04, 05 (basic), reassembly in 02: many chunks across several seeders, correct ordered output equal to single-node output.
- **MILESTONE M3 — Distributed run:** 3 seeders, one reassembled result.

## Phase 8 — Verification (L)
- Module 06: canary first, then replica comparison, then partial re-run audit.
- **MILESTONE M4 — Trusted results:** a deliberately cheating seeder is caught.

## Phase 9 — Credits and portal (L) : WP-1 to WP-5, APP-3 credits
- Modules 09 and 01 with Socket.io live view, history, credits shown in the seeder app via `verdict_notice`.
- **MILESTONE M5 — Usable product.**

## Phase 10 — Churn and robustness (M)
- Module 05 churn part: availability score, replication for risky seeders, reassignment, recovery time.
- **MILESTONE M6 — Resilient:** killing a seeder mid-run still completes the task.

## Phase 11 — Evaluation, packaging, writing (L) : APP-1
- Modules 11 and 12: single node vs 1, 2, 4, N seeders, repeats, statistics; PyInstaller package; clean-PC install test; report and demo script.
- **MILESTONE M7 — Measured and packaged.**

## Milestones summary
| M | Name | Proof |
|---|---|---|
| M1 | Seeder demo with mock | requirements acceptance 1 to 6 |
| M2 | One real task | real model output through the real server |
| M3 | Distributed run | 3 seeders, one reassembled output |
| M4 | Trusted results | cheater caught |
| M5 | Usable product | portal live view + credits |
| M6 | Resilient | survives seeder loss |
| M7 | Measured and packaged | benchmark dataset + installer |

## If time runs short, cut in this order
1. Trackerless libp2p file-transfer protocol and relay fallback, 2. full VeriLLM and robust canary architecture, 3. stronger multi-user/privacy enforcement, 4. installer polish, 5. portal improvements. Existing WebTorrent transfer, narrow output-hash canaries, replica checks and output-transcript receipts are MVP implementations with limits; do not represent the future protocols as complete. See [implementation status](IMPLEMENTATION-STATUS.md).

## Working habits for a solo builder
- Keep the mock server forever; it makes seeder-side testing independent of the real server.
- Finish each phase's acceptance check before starting the next; do not open three modules at once.
- Commit docs changes to CONTRACTS.md first, then code.
