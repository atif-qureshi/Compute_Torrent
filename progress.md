# ComputeTorrent MVP - Development Progress

**Last Updated:** 2026-10-10 19:39

> Historical checklist from the initial build plan. Its phase percentages and unchecked items are not a live source-status report; use [docs/IMPLEMENTATION-STATUS.md](docs/IMPLEMENTATION-STATUS.md) for the current implemented-versus-future boundary.

## Overview

This document tracks development progress across all 11 build phases and 7 milestones of the ComputeTorrent MVP.

---

## Build Phases Progress

### Phase 0: Foundations ⏳ IN PROGRESS
**Target:** Docker stack + Mock server + Contracts frozen  
**Status:** 50% Complete

- [x] Docker compose configuration exists
- [x] .env template created
- [x] PostgreSQL 18 service defined
- [x] Init scripts created
- [ ] **ACTION REQUIRED:** Start Docker Desktop
- [ ] Verify: `docker compose up -d db` gives healthy PostgreSQL
- [ ] Create mock coordination server
- [ ] Verify: Mock server accepts register messages
- [ ] Document: Freeze docs/CONTRACTS.md

**Module:** docker/, docs/CONTRACTS.md, mock-server/

---

### Phase 1: Hardware Profiling ⏸️ NOT STARTED
**Target:** Detect GPU, VRAM, CUDA, RAM, CPU → Assign Tier  
**Milestone:** M1 (Seeder demo with mock)

- [ ] Create module 08.01 structure
- [ ] Implement GPU detection (nvidia-smi, pynvml)
- [ ] Implement VRAM detection
- [ ] Implement CUDA availability check
- [ ] Implement RAM and CPU detection
- [ ] Implement tier assignment logic (Tier-1: VRAM ≥ 8GB)
- [ ] Build Node_Profile JSON object
- [ ] Test on GPU system
- [ ] Test on non-GPU system
- [ ] Create progress.md in 08-provider-node/01-hardware-profiling/

**Module:** 08-provider-node/01-hardware-profiling/  
**Requirements:** Requirement 1 (HP-1 to HP-5)

---

### Phase 2: Docker Sandbox ⏸️ NOT STARTED
**Target:** Isolated container execution with resource limits  
**Milestone:** M1 (Seeder demo with mock)

- [ ] Create module 08.03 structure
- [ ] Implement container creation logic
- [ ] Implement resource limits (CPU, memory, GPU)
- [ ] Implement network isolation (deny all except task I/O)
- [ ] Implement volume mounting (task workspace only)
- [ ] Implement container destruction
- [ ] Test with dummy script
- [ ] Security test: Docker escape attempts
- [ ] Security test: Host filesystem access attempts
- [ ] Create progress.md in 08-provider-node/03-docker-sandbox/

**Module:** 08-provider-node/03-docker-sandbox/  
**Requirements:** Requirement 2 (DS-1 to DS-6, APP-6)

---

### Phase 3: Networking Client ⏸️ NOT STARTED
**Target:** WebSocket connection, register, heartbeat, message handling  
**Milestone:** M1 (Seeder demo with mock)

- [ ] Create module 08.02 structure
- [ ] Implement WebSocket client connection
- [ ] Implement register message sending
- [ ] Implement heartbeat mechanism
- [ ] Implement message listener (task_assign, verdict_notice, cancel)
- [ ] Implement status_update sending
- [ ] Implement result_submit sending
- [ ] Implement reconnection logic
- [ ] Implement STUN/WebRTC upgrade (optional for M1)
- [ ] Test against mock server
- [ ] Test reconnection scenarios
- [ ] Create progress.md in 08-provider-node/02-networking-client/

**Module:** 08-provider-node/02-networking-client/  
**Requirements:** Requirement 3 (NC-1 to NC-6)

---

### Phase 4: WebTorrent Sync ⏸️ NOT STARTED
**Target:** Join swarm, download chunks, verify hashes, leave  
**Milestone:** M2 (One real task)

- [ ] Create module 08.04 structure (Node.js helper)
- [ ] Create module 07 structure (server-side swarm service)
- [ ] Implement swarm join logic
- [ ] Implement chunk download with SHA-1 verification
- [ ] Implement resume capability
- [ ] Implement swarm leave logic
- [ ] Implement server-side swarm creation
- [ ] Implement server-side seeding
- [ ] Test with test swarm
- [ ] Test resume after interruption
- [ ] Create progress.md in 08-provider-node/04-webtorrent-sync/
- [ ] Create progress.md in 07-network-layer/

**Modules:** 08-provider-node/04-webtorrent-sync/, 07-network-layer/  
**Requirements:** Requirement 4 (WT-1 to WT-5), Requirement 15

---

### Phase 5: Seeder App Shell ⏸️ NOT STARTED
**Target:** Desktop UI, onboarding, dashboard, tray, pause control  
**Milestone:** M1 (Seeder demo with mock)

- [ ] Create module 08.05 structure (Python + CustomTkinter)
- [ ] Implement onboarding screen
- [ ] Implement main dashboard UI
- [ ] Implement system tray integration
- [ ] Implement pause/resume control
- [ ] Implement Docker-missing warning screen
- [ ] Wire all modules together (profiling, networking, sandbox, sync)
- [ ] Test complete flow against mock server
- [ ] **MILESTONE M1 COMPLETE:** Seeder demo acceptance criteria pass
- [ ] Create progress.md in 08-provider-node/05-desktop-app-shell/
- [ ] Update master 08-provider-node/progress.md

**Module:** 08-provider-node/05-desktop-app-shell/  
**Requirements:** Requirement 5 (APP-1 to APP-6)

---

### Phase 6: Real Coordination Server ⏸️ NOT STARTED
**Target:** Replace mock with real FastAPI server, PostgreSQL, REST/WebSocket APIs  
**Milestone:** M2 (One real task)

- [ ] Create orchestrator/ folder structure (FastAPI project)
- [ ] Module 02: Implement WebSocket gateway
- [ ] Module 02: Implement seeder registry
- [ ] Module 02: Implement message handlers (register, heartbeat, status_update, result_submit)
- [ ] Module 02: Implement message senders (task_assign, verdict_notice, cancel)
- [ ] Module 02: Implement REST API (create task, get task, get result)
- [ ] Module 02: Implement Socket.io broadcaster for portal
- [ ] Module 03: Create Alembic migrations for database schema
- [ ] Module 03: Implement all entity models (Task, Chunk, Seeder, etc.)
- [ ] Module 10: Implement model version manager
- [ ] Deploy database migrations
- [ ] Test single-chunk task end-to-end
- [ ] Test with real small model (CPU or GPU)
- [ ] **MILESTONE M2 COMPLETE:** One real task produces correct output
- [ ] Create progress.md in 02-orchestrator-api/
- [ ] Create progress.md in 03-database/
- [ ] Create progress.md in 10-model-versioning/

**Modules:** 02-orchestrator-api/, 03-database/, 10-model-versioning/  
**Requirements:** Requirements 6, 12, 14

---

### Phase 7: Slicing, Allocation, Reassembly ⏸️ NOT STARTED
**Target:** Multi-chunk tasks across multiple seeders  
**Milestone:** M3 (Distributed run)

- [ ] Module 04: Implement difficulty analysis
- [ ] Module 04: Implement mode selection (WS-RR, CG-BP)
- [ ] Module 04: Implement chunking logic
- [ ] Module 04: Implement manifest generation
- [ ] Module 04: Implement canary injection
- [ ] Module 05: Implement allocator capability matching
- [ ] Module 05: Implement allocator memory checking
- [ ] Module 05: Implement basic assignment logic
- [ ] Module 02: Implement reassembly logic
- [ ] Test with 3 seeders
- [ ] Verify output equals single-node output
- [ ] **MILESTONE M3 COMPLETE:** Distributed run acceptance criteria pass
- [ ] Create progress.md in 04-task-slicer-scheduler/
- [ ] Create progress.md in 05-allocator-churn/

**Modules:** 04-task-slicer-scheduler/, 05-allocator-churn/, 02-orchestrator-api/  
**Requirements:** Requirements 7, 8 (basic), 10

---

### Phase 8: Verification ⏸️ NOT STARTED
**Target:** Canary traps, replica comparison, partial audit  
**Milestone:** M4 (Trusted results)

- [ ] Module 06: Implement canary generation
- [ ] Module 06: Implement canary checking
- [ ] Module 06: Implement replica assignment logic
- [ ] Module 06: Implement replica comparison (SERENE-lite)
- [ ] Module 06: Implement arbitration for disagreements
- [ ] Module 06: Implement partial re-run audit (VeriLLM-lite)
- [ ] Module 06: Implement collusion detection
- [ ] Module 06: Implement VSR metric calculation
- [ ] Test with honest seeders
- [ ] Test with deliberately cheating seeder
- [ ] **MILESTONE M4 COMPLETE:** Cheater caught, VSR reported
- [ ] Create progress.md in 06-verification-engine/

**Module:** 06-verification-engine/  
**Requirements:** Requirement 9

---

### Phase 9: Credits and Portal ⏸️ NOT STARTED
**Target:** Web portal, live dashboard, credit system  
**Milestone:** M5 (Usable product)

- [ ] Module 09: Implement credit award calculation
- [ ] Module 09: Implement penalty calculation
- [ ] Module 09: Implement trust score computation
- [ ] Module 09: Implement verdict_notice sending
- [ ] Module 01: Create Next.js portal project structure
- [ ] Module 01: Implement task submission form
- [ ] Module 01: Implement live dashboard (Socket.io)
- [ ] Module 01: Implement results view
- [ ] Module 01: Implement history page
- [ ] Module 01: Implement credits page
- [ ] Update seeder app to display credits
- [ ] Test complete requestor flow
- [ ] **MILESTONE M5 COMPLETE:** Usable product acceptance criteria pass
- [ ] Create progress.md in 09-incentives-credits/
- [ ] Create progress.md in 01-submitter-portal/

**Modules:** 09-incentives-credits/, 01-submitter-portal/  
**Requirements:** Requirements 11, 13

---

### Phase 10: Churn and Robustness ⏸️ NOT STARTED
**Target:** Availability scoring, reassignment, survive seeder loss  
**Milestone:** M6 (Resilient)

- [ ] Module 05: Implement availability history tracking
- [ ] Module 05: Implement availability score u_j calculation
- [ ] Module 05: Implement replica assignment for risky seeders
- [ ] Module 05: Implement heartbeat timeout detection
- [ ] Module 05: Implement chunk reassignment logic
- [ ] Module 05: Prefer seeders with chunk already downloaded
- [ ] Test: Kill seeder mid-task
- [ ] Test: Heartbeat timeout triggers reassignment
- [ ] Test: Server restart recovery
- [ ] **MILESTONE M6 COMPLETE:** Task completes despite seeder loss
- [ ] Update progress.md in 05-allocator-churn/

**Module:** 05-allocator-churn/  
**Requirements:** Requirement 8 (churn aspects)

---

### Phase 11: Evaluation and Packaging ⏸️ NOT STARTED
**Target:** Benchmark harness, PyInstaller packaging, testing  
**Milestone:** M7 (Measured and packaged)

- [ ] Module 11: Create benchmark harness structure
- [ ] Module 11: Implement single-node baseline measurement
- [ ] Module 11: Implement N-seeder distributed measurement
- [ ] Module 11: Implement speedup calculation
- [ ] Module 11: Implement overhead measurement (verification, network)
- [ ] Module 11: Implement statistics computation
- [ ] Module 11: Generate report
- [ ] Module 12: Create comprehensive test suite
- [ ] Module 12: Implement fault injection tests
- [ ] Module 12: Implement security tests (Docker escape)
- [ ] Module 12: Implement integration tests
- [ ] Create PyInstaller spec for seeder app
- [ ] Build Windows installer
- [ ] Test on clean PC
- [ ] Run benchmark experiments (1, 2, 4 seeders)
- [ ] **MILESTONE M7 COMPLETE:** Measured, packaged, report ready
- [ ] Create progress.md in 11-evaluation-benchmark/
- [ ] Create progress.md in 12-testing-validation/

**Modules:** 11-evaluation-benchmark/, 12-testing-validation/  
**Requirements:** Requirements 16, 17, 20

---

## Milestones Status

| Milestone | Target | Status | Completion Date |
|---|---|---|---|
| M1 | Seeder demo with mock | ⏸️ Not Started | - |
| M2 | One real task | ⏸️ Not Started | - |
| M3 | Distributed run (3 seeders) | ⏸️ Not Started | - |
| M4 | Trusted results | ⏸️ Not Started | - |
| M5 | Usable product | ⏸️ Not Started | - |
| M6 | Resilient | ⏸️ Not Started | - |
| M7 | Measured and packaged | ⏸️ Not Started | - |

---

## Current Sprint

**Active Phase:** Phase 0 (Foundations)  
**Next Action:** Start Docker Desktop, then verify PostgreSQL stack

---

## Blockers and Notes

### Current Blockers
1. **Docker Desktop not running** - Required for Phase 0 verification
   - Action: Start Docker Desktop manually
   - Then run: `cd docker && docker compose up -d db`

### Technical Decisions
- Using Python 3.12+ for seeder app (CustomTkinter compatibility)
- Using FastAPI for coordination server (async WebSocket support)
- Using PostgreSQL 18 (latest stable)
- Using Next.js 14+ for portal (App Router)

### Dependencies
- Phase 1-5 can proceed in parallel after Phase 0
- Phase 6 blocks Phase 7-11
- Milestone M1 required before M2
- Each milestone builds on previous milestones

---

## Statistics

- **Total Phases:** 11
- **Completed Phases:** 0
- **In Progress Phases:** 1 (Phase 0)
- **Total Milestones:** 7
- **Completed Milestones:** 0
- **Overall Progress:** ~5%

---

*Generated: 2026-10-10 19:39*
