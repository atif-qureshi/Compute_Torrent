# Requirements Document: ComputeTorrent MVP

## Introduction

ComputeTorrent is a decentralized peer-to-peer distributed computing system that enables batch LLM inference on idle consumer computers. The system follows a torrent-style Seeder (provider) and Leecher (requestor) model where compute providers donate idle hardware resources to process tasks submitted by requestors. The MVP demonstrates that users can safely contribute compute resources while requestors can reliably distribute and verify work across an untrusted network.

**Scope:** This requirements document covers the complete MVP implementation including all 11 build phases, 7 milestones, and 12 functional modules as defined in the existing project documentation.

**Sources:** Requirements are extracted from:
- `docs/source/requirements-seeder-and-portal.md` (base requirement IDs: HP, NC, DS, WT, APP, WP, NFR)
- `docs/BUILD-ORDER.md` (phase definitions and milestones)
- `docs/FLOW.md` (system flows and state machines)
- Module READMEs (detailed component requirements)
- `docs/CONTRACTS.md` (data shapes and message protocols)

## Glossary

- **Seeder**: Compute provider running the desktop application that donates hardware resources
- **Requestor**: User submitting tasks through the web portal
- **Coordination_Server**: Central control plane managing task lifecycle, verification, and credits
- **Chunk**: Discrete unit of work from task decomposition
- **Swarm**: Per-task private WebTorrent network for data distribution
- **Canary**: Hidden test chunk with known expected output for verification
- **Tier-1**: Hardware capability class with VRAM ≥ 8 GB (eligible for LLM inference)
- **Tier-2**: Hardware capability class with VRAM < 8 GB (eligible for preprocessing)
- **Manifest**: Task metadata including chunk list, hashes, model version, and ordering
- **VSR**: Verification Success Rate (percentage of results passing verification)
- **CG-BP**: Coarse-grained block placement mode (model blocks pipelined across nodes)
- **WS-RR**: Waterfilling-style split with request routing mode (prompts distributed across replicas)

## Requirements

### Requirement 1: Hardware Detection and Profiling

**User Story:** As a compute provider, I want the system to automatically detect my hardware capabilities, so that I am assigned tasks appropriate for my machine without manual configuration.

**Traceability:** Phase 1, Milestone M1, Module 08.01, Original IDs: HP-1 to HP-5

#### Acceptance Criteria

1. WHEN the Seeder_App launches, THE Hardware_Profiler SHALL detect GPU model, VRAM size, CUDA availability, CPU core count, and total RAM
2. THE Hardware_Profiler SHALL build a Node_Profile JSON object with fields: GPU, VRAM, CUDA, RAM, CPU_cores
3. THE Hardware_Profiler SHALL assign capability tier Tier-1 WHEN VRAM is 8 GB or more
4. THE Hardware_Profiler SHALL assign capability tier Tier-2 WHEN VRAM is less than 8 GB
5. WHEN the user triggers a manual refresh, THE Hardware_Profiler SHALL re-detect hardware specifications
6. THE Seeder_App SHALL display detected profile and tier to the user in plain language
7. THE Hardware_Profiler SHALL function correctly on systems without a GPU

### Requirement 2: Isolated Task Execution

**User Story:** As a compute provider, I want all tasks to run in complete isolation from my personal files and system, so that I can contribute resources without security risk.

**Traceability:** Phase 2, Milestone M1, Module 08.03, Original IDs: DS-1 to DS-6, APP-6

#### Acceptance Criteria

1. WHEN a task is assigned, THE Docker_Sandbox SHALL create a fresh disposable container
2. THE Docker_Sandbox SHALL apply hard resource limits for CPU, memory, and GPU access
3. THE Docker_Sandbox SHALL deny all network access except task data download and result upload
4. THE Docker_Sandbox SHALL mount only the task working directory, not the host filesystem
5. WHEN a task completes or fails, THE Docker_Sandbox SHALL destroy the container immediately
6. WHEN a container crashes or exceeds limits, THE Docker_Sandbox SHALL report failure status
7. THE Docker_Sandbox SHALL log lifecycle events locally for debugging
8. THE Seeder_App SHALL never run tasks outside the Docker_Sandbox

### Requirement 3: Network Registration and Communication

**User Story:** As a compute provider, I want to connect to the network automatically and maintain a stable connection, so that I can receive tasks without manual intervention.

**Traceability:** Phase 3, Milestone M1, Module 08.02, Original IDs: NC-1 to NC-6

#### Acceptance Criteria

1. WHEN hardware profiling completes, THE Networking_Client SHALL open a WebSocket connection to the Coordination_Server
2. THE Networking_Client SHALL send a register message containing Node_Profile and capability tier
3. THE Networking_Client SHALL maintain persistent heartbeat messages indicating online/idle status
4. THE Networking_Client SHALL listen for incoming task_assign messages
5. WHEN STUN handshake succeeds, THE Networking_Client SHALL upgrade to direct WebRTC connection
6. WHEN STUN handshake fails, THE Networking_Client SHALL continue routing through the relay without user notification
7. THE Networking_Client SHALL send status_update messages for state transitions: queued, downloading, running, completed, failed
8. WHEN connection drops mid-task, THE Networking_Client SHALL attempt to resume the task
9. WHEN resume fails, THE Networking_Client SHALL mark the task failed locally and re-register

### Requirement 4: Data Synchronization via Swarms

**User Story:** As a compute provider, I want to efficiently download task data through peer-to-peer networks, so that the system scales without central bottlenecks.

**Traceability:** Phase 4, Milestone M2, Modules 08.04 and 07, Original IDs: WT-1 to WT-5

#### Acceptance Criteria

1. WHEN receiving a task_assign message, THE WebTorrent_Client SHALL join the per-task private swarm specified in swarm_id
2. THE WebTorrent_Client SHALL download assigned dataset and model chunks using SHA-1 piece verification
3. WHEN download is interrupted, THE WebTorrent_Client SHALL resume from the last verified piece
4. WHEN task completes, THE WebTorrent_Client SHALL leave the swarm
5. THE WebTorrent_Client SHALL pass downloaded chunk file paths to Docker_Sandbox as mounted volumes
6. THE WebTorrent_Client SHALL never store downloaded chunks outside the task workspace
7. THE Coordination_Server SHALL create per-task private swarms containing only the requestor and assigned seeders
8. THE Coordination_Server SHALL tear down swarms after task completion

### Requirement 5: Seeder Desktop Application

**User Story:** As a compute provider, I want a simple installable application that runs in the background, so that I can contribute resources passively without technical expertise.

**Traceability:** Phase 5, Milestone M1, Module 08.05, Original IDs: APP-1 to APP-6

#### Acceptance Criteria

1. THE Seeder_App SHALL be packaged as a single installable executable for Windows
2. WHEN first launched, THE Seeder_App SHALL display onboarding screen showing detected hardware and tier
3. THE Seeder_App main dashboard SHALL display connection status, current task with progress, tasks completed, and credits earned
4. THE Seeder_App SHALL provide a "Pause Seeding" control to stop accepting new tasks
5. THE Seeder_App SHALL run in system tray without requiring focus
6. WHEN Docker is not available, THE Seeder_App SHALL display clear installation guidance without crashing
7. WHEN idle with no task running, THE Seeder_App SHALL consume minimal system resources

### Requirement 6: Coordination Server Infrastructure

**User Story:** As a system operator, I want a central coordination server managing task lifecycle and seeder registry, so that tasks are reliably assigned and tracked.

**Traceability:** Phase 6, Milestone M2, Module 02

#### Acceptance Criteria

1. THE Coordination_Server SHALL accept WebSocket connections from Seeder_Apps
2. THE Coordination_Server SHALL validate and process register, heartbeat, status_update, and result_submit messages
3. THE Coordination_Server SHALL send task_assign, verdict_notice, and cancel messages to seeders
4. THE Coordination_Server SHALL relay messages between peers when direct connection fails
5. THE Coordination_Server SHALL expose REST API for task creation, retrieval, and result access
6. THE Coordination_Server SHALL expose Socket.io API for real-time progress updates to portal
7. THE Coordination_Server SHALL maintain seeder registry with profiles, tiers, heartbeats, and availability history
8. WHEN heartbeat timeout occurs, THE Coordination_Server SHALL mark seeder offline and reassign chunks
9. THE Coordination_Server SHALL write state changes to database before sending messages
10. THE Coordination_Server SHALL handle duplicate result_submit messages idempotently
11. WHEN the Coordination_Server restarts, THE System SHALL rebuild state from PostgreSQL

### Requirement 7: Task Decomposition and Scheduling

**User Story:** As a system operator, I want tasks automatically sliced into appropriately-sized chunks, so that work is distributed efficiently across heterogeneous hardware.

**Traceability:** Phase 7, Milestone M3, Module 04

#### Acceptance Criteria

1. WHEN a task is submitted, THE Task_Slicer SHALL estimate difficulty based on input size, compute requirements, and memory needs
2. THE Task_Slicer SHALL select execution mode: WS-RR WHEN the model fits in smallest eligible worker memory
3. THE Task_Slicer SHALL select execution mode: CG-BP WHEN workers can jointly hold model blocks
4. THE Task_Slicer SHALL reject tasks with clear reason WHEN no eligible execution mode exists
5. THE Task_Slicer SHALL split input into N chunks sized by worker capacity
6. THE Task_Slicer SHALL assign sequential index to every chunk for ordering
7. THE Task_Slicer SHALL inject canary chunks at random positions
8. THE Task_Slicer SHALL compute hash for each chunk payload
9. THE Task_Slicer SHALL build manifest containing chunk list, hashes, model_version_id, adapter_id, and indices
10. THE Task_Slicer SHALL store private manifest copy including canary markers on server only
11. WHEN reassembling, THE System SHALL verify concatenating chunk outputs in index order equals single-node output

### Requirement 8: Chunk Allocation and Churn Management

**User Story:** As a system operator, I want chunks assigned to reliable available seeders with appropriate hardware, so that tasks complete efficiently despite node churn.

**Traceability:** Phase 7 and Phase 10, Milestones M3 and M6, Module 05

#### Acceptance Criteria

1. THE Allocator SHALL match chunks to online seeders by capability tier
2. THE Allocator SHALL match chunks to online seeders by available memory
3. THE Allocator SHALL match chunks to online seeders by availability score
4. THE Allocator SHALL assign replicas WHEN seeder has low availability score
5. THE Allocator SHALL prefer seeders that already downloaded the chunk WHEN reassigning
6. WHEN seeder is marked offline, THE Allocator SHALL reassign pending chunks to other seeders
7. THE Allocator SHALL track seeder availability history to compute availability score u_j
8. THE Allocator SHALL never assign chunks to seeders lacking required tier or memory
9. WHEN a task completes despite seeder failure, THE System SHALL meet resilience requirements

### Requirement 9: Multi-Layer Verification Without Blockchain

**User Story:** As a requestor, I want results verified for correctness without trusting individual seeders, so that I receive reliable outputs from untrusted hardware.

**Traceability:** Phase 8, Milestone M4, Module 06

#### Acceptance Criteria

1. WHEN creating a task, THE Verification_Engine SHALL generate canary chunks with known expected outputs
2. WHEN a result is returned for a canary chunk, THE Verification_Engine SHALL compare output to expected value
3. WHEN canary output matches expectation, THE Verification_Engine SHALL record pass and increase worker trust score
4. WHEN canary output fails, THE Verification_Engine SHALL flag worker, penalize, and invalidate recent results
5. WHEN risk score is high, THE Verification_Engine SHALL assign r replicas to the same chunk
6. WHEN replicas disagree, THE Verification_Engine SHALL run arbitration via third replica or audit
7. THE Verification_Engine SHALL track pairwise agreement history to detect collusion
8. WHEN collusion is detected, THE Verification_Engine SHALL flag worker pairs and force replicas to non-flagged workers
9. THE Verification_Engine SHALL perform partial re-run audits on random result subsets
10. WHEN audit detects mismatch, THE Verification_Engine SHALL reject result and apply strong penalty
11. THE Coordination_Server SHALL never send canary markers or audit positions to seeders
12. THE System SHALL compute and report Verification Success Rate (VSR) metric
13. WHEN a deliberately cheating seeder submits random text, THE Verification_Engine SHALL catch it in nearly all runs

### Requirement 10: Result Reassembly

**User Story:** As a requestor, I want verified chunks automatically reassembled into complete results, so that I receive usable output without manual processing.

**Traceability:** Phase 7, Milestone M3, Module 02 (reassembly logic)

#### Acceptance Criteria

1. THE Reassembler SHALL collect all verified chunks for a task
2. THE Reassembler SHALL verify chunk count matches manifest
3. THE Reassembler SHALL order chunks by sequential index from manifest
4. THE Reassembler SHALL concatenate chunk outputs in correct order
5. THE Reassembler SHALL mark task status as REASSEMBLED when complete
6. THE Reassembler SHALL make final output available via API for requestor download

### Requirement 11: Credit System and Incentives

**User Story:** As a compute provider, I want to earn credits for verified work, so that my contributions are recognized and potentially rewarded.

**Traceability:** Phase 9, Milestone M5, Module 09

#### Acceptance Criteria

1. WHEN a chunk result passes verification, THE Credit_System SHALL award credits to the seeder
2. WHEN a chunk result fails verification, THE Credit_System SHALL apply penalty to the seeder
3. THE Credit_System SHALL store credit entries with seeder_id, task_id, delta, and reason
4. THE Coordination_Server SHALL send verdict_notice messages containing credits_earned and new_balance
5. THE Seeder_App SHALL display updated credit balance after receiving verdict_notice
6. THE Credit_System SHALL compute trust_score based on verification history
7. THE Credit_System SHALL use trust_score to influence future task allocation priority

### Requirement 12: Model and Adapter Versioning

**User Story:** As a system operator, I want model and adapter versions tracked and distributed via torrents, so that all seeders run identical model configurations.

**Traceability:** Phase 6, Milestone M2, Module 10

#### Acceptance Criteria

1. THE Model_Version_Manager SHALL store model version records with name, weights_hash, and torrent_infohash
2. THE Model_Version_Manager SHALL store adapter version records with base_model_version_id, lora_hash, and torrent_infohash
3. WHEN creating a task, THE System SHALL specify model_version_id in the manifest
4. WHEN creating a task with adapter, THE System SHALL specify adapter_id in the manifest
5. THE System SHALL ensure all seeders for a task use the same model_version_id
6. THE System SHALL distribute model weights and adapters via WebTorrent using stored infohash

### Requirement 13: Requestor Web Portal

**User Story:** As a requestor, I want a web interface to submit tasks and view results, so that I can use the system without installing software.

**Traceability:** Phase 9, Milestone M5, Module 01, Original IDs: WP-1 to WP-5

#### Acceptance Criteria

1. THE Web_Portal SHALL provide task submission form accepting dataset upload, model selection, and task type
2. THE Web_Portal SHALL display live dashboard showing swarm status, active seeder count, and per-chunk progress
3. THE Web_Portal SHALL receive real-time updates via Socket.io connection to Coordination_Server
4. WHEN task is completed, THE Web_Portal SHALL display final result with download option
5. THE Web_Portal SHALL provide history view listing past tasks and outcomes
6. THE Web_Portal SHALL provide credits view showing credit balance and transaction history

### Requirement 14: Database Schema and Persistence

**User Story:** As a system operator, I want all state persisted in a database, so that the system survives restarts and maintains history.

**Traceability:** Phase 6, Milestone M2, Module 03

#### Acceptance Criteria

1. THE Database SHALL store Task entities with fields: task_id, requester_id, task_kind, model_version_id, adapter_id, privacy_level, mode, status, created_at, completed_at
2. THE Database SHALL store Chunk entities with fields: chunk_id, task_id, index, kind, payload_hash, status, retry_count
3. THE Database SHALL store Assignment entities with fields: assignment_id, chunk_id, seeder_id, replica_no, assigned_at, deadline
4. THE Database SHALL store Seeder entities with fields: seeder_id, gpu, vram_gb, cuda, ram_gb, cpu_cores, capability_tier, docker_ok, availability_score, trust_score, status, last_heartbeat
5. THE Database SHALL store Result entities with fields: result_id, assignment_id, output_ref, output_hash, p_time, d_time
6. THE Database SHALL store Verdict entities with fields: verdict_id, result_id, layer, outcome, detail
7. THE Database SHALL store CreditEntry entities with fields: entry_id, seeder_id, task_id, delta, reason
8. THE Database SHALL store ModelVersion entities with fields: model_version_id, name, weights_hash, torrent_infohash, created_at
9. THE Database SHALL store AdapterVersion entities with fields: adapter_id, base_model_version_id, lora_hash, torrent_infohash
10. THE Database SHALL store Swarm entities with fields: swarm_id, task_id, infohash, created_at, torn_down_at
11. THE Database SHALL store Manifest entities with fields: manifest_id, task_id, chunk_list, model_version_id, adapter_id, canary_map

### Requirement 15: Network Layer and Swarm Management

**User Story:** As a system operator, I want per-task private swarms created and torn down automatically, so that data distribution scales peer-to-peer without permanent storage.

**Traceability:** Phase 4 and Phase 6, Milestones M2 and M3, Module 07

#### Acceptance Criteria

1. WHEN a task is sliced, THE Swarm_Service SHALL create a per-task private WebTorrent swarm
2. THE Swarm_Service SHALL generate unique infohash for the swarm
3. THE Swarm_Service SHALL seed task data from the server side
4. THE Swarm_Service SHALL provide swarm_id in task_assign messages
5. WHEN task completes, THE Swarm_Service SHALL tear down the swarm
6. THE Swarm_Service SHALL record swarm creation and teardown timestamps
7. THE Swarm_Service SHALL ensure only assigned seeders and requestor can join the private swarm

### Requirement 16: Testing and Validation Infrastructure

**User Story:** As a developer, I want comprehensive testing infrastructure including fault injection and demo acceptance checks, so that I can verify system correctness and resilience.

**Traceability:** Phase 11, Milestone M7, Module 12

#### Acceptance Criteria

1. THE Test_Suite SHALL include unit tests for all modules
2. THE Test_Suite SHALL include integration tests for end-to-end flows
3. THE Test_Suite SHALL include fault injection tests simulating seeder failures
4. THE Test_Suite SHALL include fault injection tests simulating network failures
5. THE Test_Suite SHALL include fault injection tests simulating cheating seeders
6. THE Test_Suite SHALL verify Docker escape attempts fail
7. THE Test_Suite SHALL verify sandbox isolation prevents host filesystem access
8. THE Test_Suite SHALL verify reassembled output matches single-node output for deterministic tasks

### Requirement 17: Evaluation and Benchmarking

**User Story:** As a researcher, I want benchmark harness measuring speedup and overhead, so that I can evaluate system performance scientifically.

**Traceability:** Phase 11, Milestone M7, Module 11

#### Acceptance Criteria

1. THE Benchmark_Harness SHALL run identical tasks on single node vs 1, 2, 4, N seeders
2. THE Benchmark_Harness SHALL measure total completion time including slicing, distribution, compute, verification, and reassembly
3. THE Benchmark_Harness SHALL compute speedup metric: single-node time / distributed time
4. THE Benchmark_Harness SHALL measure verification overhead as percentage of total time
5. THE Benchmark_Harness SHALL measure network overhead for data distribution
6. THE Benchmark_Harness SHALL repeat experiments multiple times and compute statistics
7. THE Benchmark_Harness SHALL generate report comparing modes (WS-RR vs CG-BP when implemented)
8. THE Benchmark_Harness SHALL measure VSR (Verification Success Rate) across experiments

### Requirement 18: Mock Server for Development

**User Story:** As a developer, I want a mock coordination server for isolated seeder app development, so that I can build and test the seeder independently.

**Traceability:** Phase 0, Module mock-server (development tool)

#### Acceptance Criteria

1. THE Mock_Server SHALL accept WebSocket connections from Seeder_Apps
2. THE Mock_Server SHALL accept register messages and respond with acknowledgment
3. THE Mock_Server SHALL send fake task_assign messages with test data
4. THE Mock_Server SHALL print received status_update messages
5. THE Mock_Server SHALL print received result_submit messages
6. THE Mock_Server SHALL enable seeder app development before real coordination server exists

### Requirement 19: Docker Development Stack

**User Story:** As a developer, I want a Docker Compose stack for local development, so that I can run PostgreSQL and future server components easily.

**Traceability:** Phase 0, Module docker

#### Acceptance Criteria

1. THE Docker_Stack SHALL include PostgreSQL 18 service
2. THE Docker_Stack SHALL include environment variable configuration via .env file
3. THE Docker_Stack SHALL include database initialization scripts
4. THE Docker_Stack SHALL include Dockerfiles for coordination server when code exists
5. WHEN running docker compose up, THE Docker_Stack SHALL provide healthy PostgreSQL instance

### Requirement 20: Progress Tracking System

**User Story:** As a developer, I want progress.md files in each module folder tracking completion status, so that I can monitor development across the 11 phases.

**Traceability:** All phases and milestones

#### Acceptance Criteria

1. THE System SHALL include progress.md file in each of the 12 module folders
2. THE progress.md file SHALL list tasks for the module aligned with BUILD-ORDER.md phases
3. THE progress.md file SHALL use checkbox format for task tracking
4. THE progress.md file SHALL reference milestone completion criteria
5. THE progress.md file SHALL be updated as tasks complete
6. THE System SHALL include master progress.md in project root summarizing all module progress

## Non-Functional Requirements

### Requirement 21: Security and Isolation

**User Story:** As a compute provider, I want absolute guarantee that tasks cannot access my personal files, so that I can contribute resources without risk.

**Traceability:** Original ID: NFR-1

#### Acceptance Criteria

1. THE System SHALL never allow tasks to read, write, or delete anything outside the Docker container workspace
2. THE System SHALL enforce this isolation through Docker container configuration, not application-level checks
3. THE System SHALL treat any security violation as a critical system failure requiring immediate investigation

### Requirement 22: User Experience and Accessibility

**User Story:** As a non-technical user, I want to install and run the seeder app without manual configuration, so that I can contribute without technical expertise.

**Traceability:** Original IDs: NFR-2, NFR-3

#### Acceptance Criteria

1. THE Seeder_App installer SHALL bundle all required dependencies
2. THE Seeder_App SHALL not require manual Docker installation steps
3. WHEN Docker is unavailable, THE Seeder_App SHALL display clear installation guidance rather than crashing
4. THE Seeder_App SHALL use plain language in all user-facing messages
5. THE Seeder_App SHALL not require command-line interaction

### Requirement 23: Resource Efficiency

**User Story:** As a compute provider, I want the app to use minimal resources when idle, so that it runs passively on my personal PC without impacting my work.

**Traceability:** Original ID: NFR-4

#### Acceptance Criteria

1. WHEN idle with no task running, THE Seeder_App SHALL consume less than 100 MB RAM
2. WHEN idle with no task running, THE Seeder_App SHALL consume less than 5% CPU on average
3. THE Seeder_App SHALL not perform background network transfers when paused
4. THE Seeder_App SHALL not perform background disk writes when idle

### Requirement 24: Interface Contracts and Modularity

**User Story:** As a developer, I want clear interface contracts between modules, so that I can build components independently and integrate reliably.

**Traceability:** Original ID: NFR-5

#### Acceptance Criteria

1. THE System SHALL define all message schemas in docs/CONTRACTS.md
2. THE System SHALL define all entity schemas in docs/CONTRACTS.md
3. THE System SHALL validate all messages against defined schemas
4. THE System SHALL reject malformed messages without crashing
5. THE System SHALL version message schemas when changes occur
6. THE System SHALL not hardcode assumptions about other modules' internal implementation

## Milestone Definitions

### Milestone M1: Seeder Demo with Mock Server

**Completion Criteria:**
- Seeder app correctly detects hardware and shows tier
- Seeder app connects to mock server and shows online status
- Seeder app receives fake task, runs dummy script in Docker, returns result
- No files remain on host after task completion
- Seeder app UI shows live status transitions

**Validates Requirements:** 1, 2, 3, 5, 18

### Milestone M2: One Real Task End-to-End

**Completion Criteria:**
- Real coordination server replaces mock server
- Real small model (CPU or GPU) runs through complete pipeline
- Task submission → slicing (1 chunk) → assignment → download → execution → result submission → storage
- Result accessible via API

**Validates Requirements:** 6, 12, 14, 15

### Milestone M3: Distributed Run

**Completion Criteria:**
- Task sliced into multiple chunks
- 3 seeders each receive and complete chunks
- All chunks verified and reassembled
- Final output equals single-node output
- Allocation considers seeder capabilities

**Validates Requirements:** 7, 8, 10

### Milestone M4: Trusted Results

**Completion Criteria:**
- Verification layers L1 (canary) and L2 (replicas) operational
- Deliberately cheating seeder is caught and flagged
- Honest seeders pass verification
- VSR metric computed and reported

**Validates Requirements:** 9

### Milestone M5: Usable Product

**Completion Criteria:**
- Web portal accepts task submissions
- Live dashboard shows real-time progress via Socket.io
- Credits awarded for verified work
- Seeder app displays credit balance
- Result download functional

**Validates Requirements:** 11, 13

### Milestone M6: Resilient

**Completion Criteria:**
- Killing a seeder mid-run results in task completion via reassignment
- Heartbeat timeout triggers chunk reassignment
- System survives coordination server restart
- Availability scoring functional

**Validates Requirements:** 8 (churn aspects)

### Milestone M7: Measured and Packaged

**Completion Criteria:**
- Benchmark harness measures speedup for 1, 2, 4 seeders
- Statistics computed over multiple runs
- Seeder app packaged as installer
- Clean-PC installation test passes
- Verification overhead measured and reported

**Validates Requirements:** 16, 17

## Phase-to-Requirement Mapping

| Phase | Name | Primary Requirements | Milestone |
|---|---|---|---|
| 0 | Foundations | 18, 19 | - |
| 1 | Hardware Profiling | 1 | M1 |
| 2 | Docker Sandbox | 2, 21 | M1 |
| 3 | Networking Client | 3 | M1 |
| 4 | WebTorrent Sync | 4 | M2 |
| 5 | Seeder App Shell | 5, 22, 23 | M1 |
| 6 | Real Coordination Server | 6, 12, 14, 15 | M2 |
| 7 | Slicing, Allocation, Reassembly | 7, 8, 10 | M3 |
| 8 | Verification | 9 | M4 |
| 9 | Credits and Portal | 11, 13 | M5 |
| 10 | Churn and Robustness | 8 (availability scoring) | M6 |
| 11 | Evaluation and Packaging | 16, 17, 20 | M7 |

## Requirements Traceability Matrix

| Original Requirement ID | New Requirement | Module | Status |
|---|---|---|---|
| HP-1 to HP-5 | Requirement 1 | 08.01 | Planned |
| DS-1 to DS-6 | Requirement 2 | 08.03 | Planned |
| NC-1 to NC-6 | Requirement 3 | 08.02 | Planned |
| WT-1 to WT-5 | Requirement 4 | 08.04, 07 | Planned |
| APP-1 to APP-6 | Requirement 5 | 08.05 | Planned |
| WP-1 to WP-5 | Requirement 13 | 01 | Planned |
| NFR-1 | Requirement 21 | System-wide | Planned |
| NFR-2, NFR-3 | Requirement 22 | 08.05 | Planned |
| NFR-4 | Requirement 23 | 08.05 | Planned |
| NFR-5 | Requirement 24 | System-wide | Planned |
| (New - Server) | Requirement 6 | 02 | Planned |
| (New - Slicing) | Requirement 7 | 04 | Planned |
| (New - Allocation) | Requirement 8 | 05 | Planned |
| (New - Verification) | Requirement 9 | 06 | Planned |
| (New - Reassembly) | Requirement 10 | 02 | Planned |
| (New - Credits) | Requirement 11 | 09 | Planned |
| (New - Versioning) | Requirement 12 | 10 | Planned |
| (New - Database) | Requirement 14 | 03 | Planned |
| (New - Network) | Requirement 15 | 07 | Planned |
| (New - Testing) | Requirement 16 | 12 | Planned |
| (New - Benchmark) | Requirement 17 | 11 | Planned |
| (New - Mock) | Requirement 18 | mock-server | Planned |
| (New - Docker) | Requirement 19 | docker | Planned |
| (New - Progress) | Requirement 20 | All modules | Planned |
