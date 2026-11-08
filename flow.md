Ab hum ComputeTorrent ke development prompt ko proper phase-wise execution plan mein convert karenge, taake Codex poora project ek hi baar modify na kare, balkay har phase ko separately analyze, implement, test aur verify kare.

Is updated prompt mein 4 major priorities hongi:

1. Research-based development: Petals ke dono papers aur Sun et al. ki optimization techniques.
2. P2P connectivity: Local aur global peer connections ko reliable banana, Tailscale ki mandatory dependency eliminate karna.
3. UI/UX improvement: Dashboard aur peer connection application ka professional, modern aur user-friendly interface.
4. Application installation & auto-update system: Testing aur production mein new releases ka download, installation, version management aur automatic update functionality fix karna.

## Complete Master Prompt for Codex

# ComputeTorrent — Complete Research-Based Development, Network Optimization, UI/UX Redesign & Application Update System

## ROLE AND RESPONSIBILITIES

Act as a Senior Software Architect, Distributed Systems Engineer, AI Infrastructure Engineer, UI/UX Designer, and DevOps Engineer.

You are working on **ComputeTorrent**, an existing decentralized P2P distributed LLM inference platform.

Your responsibility is to continue developing, improving, debugging, and optimizing the existing project while preserving its working functionality.

This project is large and involves multiple interconnected systems. Therefore, **you must divide the entire development process into manageable phases and complete them sequentially.**

Do not attempt to implement the entire project in one operation.

---

# PART A — PROJECT CONTEXT

## 1. Existing Project

ComputeTorrent already includes:

- A functional MVP.
- An existing web dashboard.
- Initial distributed computing functionality.
- A peer/volunteer connection application.
- An existing peer communication mechanism.
- Tailscale-based networking used during development.
- An application download, installation, and update mechanism that was previously implemented but is not working correctly.

Analyze the actual codebase to verify the implementation status of each feature.

Do not assume a feature is working just because its code exists.

## 2. Research Foundations

Our development must primarily follow three selected research papers.

### Petals — Two Foundational Papers

Both Petals papers provide the main foundation for ComputeTorrent.

Study their approaches to:

- Distributed Transformer inference.
- Collaborative LLM execution.
- Pipeline-based execution.
- Layer/block distribution.
- Communication between participating peers.
- Routing and intermediate activation transfer.
- Distributed inference management.

### Sun et al. — Optimization Research

Sun et al. is the primary optimization reference.

Study its proposed algorithms and determine how to apply compatible techniques to improve the existing Petals-based architecture.

Focus on:

- Heterogeneous hardware allocation.
- GPU and VRAM availability.
- Computational capability.
- Network-aware placement.
- Layer/block assignment.
- Routing optimization.
- Resource utilization.
- Latency and inference performance.

Clearly identify what was proposed by each paper, what is already implemented, and what still needs improvement.

Do not invent research results or claim that a particular algorithm performs better without evidence.

---

# PART B — DEVELOPMENT EXECUTION RULES

## 3. Mandatory Step-by-Step Workflow

This is a long-term development effort. Follow these rules strictly:

1. Start by analyzing the existing repository.
2. Divide the work into independent development phases.
3. Complete only **one phase at a time**.
4. Break large phases into smaller executable tasks.
5. Inspect existing implementations before modifying them.
6. Reuse and improve working components instead of rewriting unnecessarily.
7. Run relevant tests after each implementation step.
8. Fix issues introduced by the changes before proceeding.
9. Update project documentation after every completed phase.
10. Provide a concise progress report showing completed work, remaining tasks, and blockers.
11. Stop at the end of each major phase and request approval before continuing.
12. Do not deploy to production, publish releases, or perform destructive operations without explicit authorization.

Maintain these project documents:

- `docs/development-roadmap.md`
- `docs/architecture-analysis.md`
- `docs/research-mapping.md`
- `docs/implementation-progress.md`
- `docs/testing-results.md`

Create or update these documents as appropriate for the repository.

Use them to maintain development continuity across separate Codex sessions.

---

# PART C — SEQUENTIAL DEVELOPMENT PHASES

## EMERGENCY SECURITY PHASE — Provider update containment

This approved exception pauses Phase 1. Retire the legacy update and raw executable download routes, preserve existing release evidence, and require an authenticated release manifest and verified HTTPS transport for any replacement updater. Validate with isolated fixtures. Production deployment, release publication and rollout to volunteers require separate approval. Review the [security update audit](docs/security-update-audit.md) before resuming Phase 1.

## PHASE 0 — Complete Repository Audit

**Objective:** Understand the existing ComputeTorrent architecture before making changes.

### Tasks

0.1. Inspect the complete repository structure.

0.2. Identify frontend, backend, peer application, networking, model execution, and deployment components.

0.3. Analyze the existing technology stack and dependencies.

0.4. Trace the complete inference workflow from dashboard model deployment to peer execution and response delivery.

0.5. Analyze existing peer discovery, connection establishment, and communication.

0.6. Examine the current Tailscale integration.

0.7. Identify the existing peer application installation and update mechanism.

0.8. Inspect dashboard UI structure, reusable components, routing, and state management.

0.9. Identify incomplete features, bugs, security risks, and architectural limitations.

0.10. Review existing tests, build scripts, environment configuration, and deployment procedures.

### Deliverables

- Existing architecture report.
- Component dependency diagram.
- Feature implementation status.
- List of identified issues.
- Prioritized development roadmap.
- Recommended implementation order.

**Completion condition:** The existing system and its main dependencies are documented, and proposed changes are grounded in actual source code.

Do not modify major functionality during this phase.

---

## PHASE 0.5 — Secure updater validation and migration readiness

Review the emergency updater in source, validate the trust chain using isolated fixtures, inventory legacy exposure, and document migration and release gates. The checkpoint can be reviewed with blocked release gates recorded. Production readiness requires separate verification of Windows installation and recovery, HTTPS hosting and publisher access, and legacy retirement and migration. No deployment or distribution is authorized by this phase.

See the [release readiness checklist](docs/provider-release-readiness.md). After checkpoint approval, resume the previously started Phase 1 research mapping. Deployment and publication require separate approval.

---

## PHASE 1 — Research Analysis and Architecture Mapping

**Objective:** Align ComputeTorrent with its research foundations.

### Tasks

1.1. Study both provided Petals research papers.

1.2. Analyze Sun et al.'s optimization methodology.

1.3. Identify which techniques are directly applicable to our current architecture.

1.4. Compare existing ComputeTorrent implementations with the research approaches.

1.5. Identify missing or incorrectly implemented mechanisms.

1.6. Develop an implementation strategy for compatible optimization techniques.

1.7. Separate research-based techniques from our own proposed engineering improvements.

### Deliverables

- Research-to-implementation mapping.
- Algorithm integration plan.
- Proposed architectural adjustments.
- Implementation dependencies and limitations.

**Completion condition:** Every proposed research-based modification has a clear technical justification and identified integration point.

**Checkpoint:** Phase 1 research mapping is complete. See the [research-to-code mapping](docs/research-mapping.md) and [progress tracker](docs/implementation-progress.md). Phase 2 requires separate approval. Phase 0.5 approval covered research and development only. Updater restrictions and the [release gates](docs/provider-release-readiness.md) remain in force.

---

## PHASE 2 — P2P Networking Architecture Redesign

**Objective:** Design reliable local and global connectivity without mandatory manual Tailscale setup.

### Tasks

2.1. Investigate why current peer connections fail.

2.2. Analyze LAN and Internet connectivity separately.

2.3. Identify NAT, CGNAT, firewall, addressing, and routing issues.

2.4. Evaluate WebRTC, ICE, STUN, TURN, WebSockets, and other suitable approaches.

2.5. Examine whether the existing native peer application can handle connectivity automatically.

2.6. Compare direct P2P networking with relay-assisted communication.

2.7. Evaluate bandwidth, connection establishment time, latency, security, and operating costs.

2.8. Design an automatic connection establishment workflow.

2.9. Include authentication, peer identity verification, secure communication, and reconnect handling.

2.10. Design fallback mechanisms for situations where direct connections cannot be established.

### Deliverables

- Proposed networking architecture.
- Connectivity protocol selection.
- NAT traversal strategy.
- Direct/relay fallback strategy.
- Migration plan from Tailscale.
- Security and performance considerations.

**Completion condition:** A technically feasible connectivity architecture is selected and documented.

**Checkpoint:** Phase 2 design is complete. See the [network design](docs/network-design.md) for the selected direct and relay paths and their prototype gates. Phase 3 requires approval. Public ingress, provisioning, and releases require separate authorization.

---

## PHASE 3 — Local and Global Connectivity Implementation

**Objective:** Implement the selected networking architecture.

### Tasks

3.1. Implement or improve automatic local peer discovery.

3.2. Implement secure peer registration and identity management.

3.3. Implement global peer connection establishment.

3.4. Integrate the selected NAT traversal mechanisms.

3.5. Add relay fallback where necessary.

3.6. Implement heartbeat and peer health monitoring.

3.7. Implement reconnect and disconnection handling.

3.8. Update dashboard-to-peer communication.

3.9. Remove mandatory Tailscale configuration from the volunteer onboarding workflow once the replacement is verified.

3.10. Maintain compatibility with the existing inference pipeline.

### Test Cases

- Two devices on the same Wi-Fi network.
- Multiple devices on a LAN.
- Devices connected through different Internet providers.
- Devices behind NAT or CGNAT.
- Restrictive firewall environments.
- Temporary network disconnections.
- Peer reconnecting after network recovery.

**Completion condition:** Supported local and global connection scenarios pass tests, and unsupported network conditions are handled gracefully.

**Checkpoint:** Phase 3 is **Partially Validated — Remaining Integration Tests Pending**. Conditional approval permits Phase 4 only. The [network architecture report](docs/network-architecture.md) records isolated Hivemind bootstrap and lookup over custom WSS. Multi-peer inference, separate ISPs, CGNAT, restrictive firewalls, and real reconnection remain open. Global P2P is not production-ready. Retain the operator's Tailscale development fallback and all updater and release restrictions.

---

## PHASE 4 — Peer Connection Application Improvement

**Objective:** Make the existing volunteer application easy to use and reliable.

### Tasks

4.1. Inspect the current peer application.

4.2. Fix existing connection and startup problems.

4.3. Simplify the volunteer onboarding process.

4.4. Implement an intuitive Connect/Disconnect workflow.

4.5. Add clear connection status indicators.

4.6. Display available hardware resources.

4.7. Provide appropriate user controls for resource contribution.

4.8. Implement automatic connection recovery.

4.9. Add meaningful error messages and troubleshooting information.

4.10. Improve application stability and minimize unnecessary resource usage.

### Target User Experience

1. Download ComputeTorrent's peer application.
2. Install and launch it.
3. Sign in or securely link the device.
4. Select Join Network.
5. Automatically connect without manually configuring Tailscale, VPNs, ports, or IP addresses.
6. View connection status and contributed resources.

**Completion condition:** A volunteer can complete the supported onboarding workflow without advanced networking knowledge.

**Checkpoint:** Canonical provider improvements are implemented and passed isolated Windows and loopback checks. See the [Phase 4 implementation record](docs/phase-4-provider-connection.md). The supported workflow uses an operator-provided address and join code. Cross-network and volunteer acceptance remain pending. Stop for review before Phase 5.

---

## PHASE 5 — Peer Application Download, Installation & Auto-Update System

**Objective:** Fix and improve the existing application distribution and update mechanism for testing and production.

**This phase is especially important because an update mechanism already exists but is not working correctly. Do not replace it without first identifying the underlying problems.**

### Tasks

5.1. Inspect the existing download and installation system.

5.2. Trace the complete update workflow from release publishing to client installation.

5.3. Identify why users cannot reliably receive or install updates.

5.4. Verify existing application version detection.

5.5. Check release metadata, download URLs, installer packaging, build artifacts, and application permissions.

5.6. Fix update detection and version comparison.

5.7. Implement reliable update downloads with progress feedback.

5.8. Add download integrity and authenticity verification.

5.9. Implement safe installation/restart procedures appropriate to the actual application framework and operating systems.

5.10. Preserve application configuration and user settings during updates.

5.11. Add failure handling and recovery from interrupted or corrupted downloads.

5.12. Implement rollback or a safe recovery mechanism where technically supported.

5.13. Separate testing/pre-release and production/stable update channels.

5.14. Ensure users receive only updates compatible with their installed application and platform.

5.15. Test clean installation, updating, failed updating, and recovery.

### Desired Update Experience

- The application checks for new compatible versions.
- When an update is available, the user receives a clear notification.
- The latest version can be downloaded easily.
- Installation follows a safe and straightforward process.
- User settings and device identity are preserved where possible.
- Failed updates do not leave the application permanently unusable.
- Testing versions and stable production versions are managed separately.

Avoid insecure update methods. Verify signed or otherwise authenticated releases and do not execute untrusted downloaded binaries.

### Deliverables

- Root-cause analysis of the existing issues.
- Fixed download/installation workflow.
- Reliable update detection.
- Testing and production release configuration.
- Update failure and recovery handling.
- Update system documentation and test results.

**Completion condition:** A previously installed supported version can successfully update to a newer authorized release, and expected failure scenarios are tested.

---

## PHASE 6 — Complete Dashboard UI/UX Improvement

**Objective:** Modernize the existing ComputeTorrent dashboard without losing functionality.

### Tasks

6.1. Audit the complete dashboard interface.

6.2. Identify inconsistent styles, navigation problems, confusing workflows, and accessibility issues.

6.3. Develop a consistent professional design system.

6.4. Improve layout, typography, spacing, colors, icons, and reusable components.

6.5. Improve responsiveness across supported screen sizes.

6.6. Redesign the dashboard overview to present useful metrics clearly.

6.7. Improve peer discovery, connectivity, and resource monitoring screens.

6.8. Improve model upload/deployment and inference monitoring interfaces.

6.9. Improve volunteer onboarding and application download/update pages.

6.10. Add appropriate loading, empty, success, warning, and error states.

6.11. Preserve all existing backend integrations and functional workflows.

6.12. Test accessibility, responsiveness, navigation, and UI regressions.

### Desired Design Direction

Create a clean, modern AI infrastructure dashboard with:

- Professional SaaS-style aesthetics.
- Consistent component styling.
- Clear information hierarchy.
- Readable technical metrics.
- Intuitive navigation.
- Useful peer and inference status displays.
- Minimal unnecessary visual complexity.

Adapt the improvements to the existing frontend framework rather than introducing an unnecessary replacement.

**Completion condition:** The dashboard is visually consistent, responsive, accessible, and all previously working critical actions remain functional.

---

## PHASE 7 — Peer Application UI/UX Redesign

**Objective:** Improve the visual design and usability of the volunteer application.

### Tasks

7.1. Review the existing application interface.

7.2. Implement a consistent design aligned with the ComputeTorrent dashboard.

7.3. Improve connection status presentation.

7.4. Add accessible hardware resource information.

7.5. Show contribution and activity status.

7.6. Improve update notifications and download progress UI.

7.7. Add user-friendly onboarding and error handling screens.

7.8. Improve application settings and connection controls.

7.9. Validate that UI changes do not interfere with background computing processes.

**Completion condition:** Volunteers can understand and control their connection and application state without technical assistance.

---

## PHASE 8 — Research-Based Distributed Inference Optimization

**Objective:** Improve the existing Petals-based inference system using compatible techniques from Sun et al.

### Tasks

8.1. Analyze current layer/block allocation and routing.

8.2. Identify hardware profiling and resource reporting limitations.

8.3. Implement necessary improvements to peer capability assessment.

8.4. Integrate the selected Sun et al. optimization techniques.

8.5. Improve layer/block placement decisions.

8.6. Account for GPU/VRAM constraints and computational heterogeneity.

8.7. Incorporate network latency and bandwidth where supported by the selected approach.

8.8. Improve inference routing and intermediate activation transfer.

8.9. Preserve compatibility with the existing model execution pipeline.

8.10. Compare optimized behavior against the baseline implementation.

### Evaluation Metrics

- Inference latency.
- Tokens per second.
- Model completion time.
- Resource utilization.
- Communication overhead.
- Allocation feasibility.
- Optimization overhead.
- Peer heterogeneity handling.

**Completion condition:** The optimized implementation passes functional tests, and benchmark results clearly show its benefits, trade-offs, or limitations.

---

## PHASE 9 — Stability, Security & Recovery

**Objective:** Improve reliability under real-world volunteer network conditions.

### Tasks

9.1. Improve peer monitoring.

9.2. Detect unavailable or disconnected nodes.

9.3. Implement safe task cancellation and recovery.

9.4. Improve error handling throughout the inference pipeline.

9.5. Secure peer registration and communication.

9.6. Validate permissions and resource access boundaries.

9.7. Prevent unauthorized update downloads or installation.

9.8. Implement appropriate logging and diagnostics.

9.9. Test system behavior under intermittent connectivity and heterogeneous hardware conditions.

9.10. Document remaining reliability limitations.

**Completion condition:** The system behaves predictably during common failures without silently corrupting execution state or exposing unnecessary security risks.

---

## PHASE 10 — Integration Testing and Performance Evaluation

**Objective:** Verify that all improved components work together.

### Tasks

10.1. Execute end-to-end model deployment tests.

10.2. Verify peer registration and resource discovery.

10.3. Verify local and global peer connectivity.

10.4. Test distributed LLM inference across connected devices.

10.5. Validate optimized placement and routing.

10.6. Test peer disconnections and recovery.

10.7. Test dashboard and peer application interactions.

10.8. Test downloading, installing, and updating application releases.

10.9. Evaluate performance using reproducible benchmark configurations.

10.10. Document results, failures, and remaining limitations.

**Completion condition:** Core functionality is verified end-to-end, with documented performance and reliability results.

---

## PHASE 11 — Deployment, Documentation & Release Preparation

**Objective:** Prepare the improved system for controlled testing and future production deployment.

### Tasks

11.1. Review deployment architecture and infrastructure requirements.

11.2. Separate development, testing, and production configuration.

11.3. Verify build and release workflows.

11.4. Validate the peer application update distribution process.

11.5. Prepare installation and user onboarding documentation.

11.6. Prepare developer and architecture documentation.

11.7. Create troubleshooting guidance for connectivity failures.

11.8. Document operational costs and external dependencies.

11.9. Prepare a release readiness checklist.

11.10. Conduct final regression and security checks.

Do not publish releases or deploy to production without approval.

**Completion condition:** The project has reproducible build instructions, documented deployment procedures, and a verified release readiness checklist.

---

# PART D — PROGRESS MANAGEMENT

## 4. Required Progress Tracking

Maintain a persistent task tracker with the following fields:

| Field          | Description                                 |
| -------------- | ------------------------------------------- |
| Phase          | Current development phase                   |
| Task ID        | Unique task identifier                      |
| Description    | Technical work to perform                   |
| Status         | Pending / In Progress / Completed / Blocked |
| Dependencies   | Prerequisite tasks                          |
| Modified Files | Relevant source files                       |
| Validation     | Tests and results                           |
| Notes          | Decisions, issues, and next actions         |

Update the tracker after completing each task.

Do not mark an implementation complete without appropriate validation.

## 5. Required Report After Each Phase

At the end of every phase, provide:

1. Summary of completed work.
2. Files and components modified.
3. Problems identified.
4. Technical decisions and their justification.
5. Tests executed and their results.
6. Known limitations.
7. Remaining tasks.
8. Recommendations for the next phase.

Stop and await approval before beginning the next major phase.

---

# PART E — DEVELOPMENT SAFETY AND QUALITY

## 6. Important Engineering Requirements

- Preserve working functionality.
- Avoid unnecessary dependencies and large rewrites.
- Use the existing architecture wherever practical.
- Maintain code readability and modularity.
- Follow existing repository conventions.
- Prefer small, reviewable changes.
- Add automated tests for important modifications.
- Never expose API keys, authentication tokens, credentials, or release signing keys.
- Avoid downloading and executing unverified binaries.
- Handle network failures gracefully.
- Do not claim tests have passed if they were not executed.
- Clearly distinguish verified functionality from planned functionality.
- Explain any unavoidable technical trade-offs.
- Never silently alter the research objectives or project scope.

---

# PART F — IMMEDIATE EXECUTION INSTRUCTIONS

## 7. What You Must Do First

Begin with **PHASE 0 — Complete Repository Audit**.

Your immediate responsibilities are:

1. Inspect the existing ComputeTorrent repository.
2. Analyze the current frontend, backend, peer application, and network architecture.
3. Identify existing bugs and architectural limitations.
4. Locate and examine the application download, installation, and auto-update implementation.
5. Examine the existing UI and volunteer onboarding workflow.
6. Produce a prioritized development roadmap.
7. Document the findings in the specified project documents.

**Do not start major implementation changes before completing Phase 0.**

After Phase 0, present the findings and implementation plan for review.

The overall objective is to transform ComputeTorrent's existing MVP into a polished, research-backed, reliable distributed LLM inference platform with seamless peer onboarding, optimized resource allocation, professional user interfaces, and a dependable application update system.

**IMPORTANT FINAL RULE: Execute one phase at a time. Within each phase, work task-by-task, validate the results, save progress in project documentation, and stop at the phase checkpoint. Do not attempt to complete all phases in a single Codex session.**

## Codex ke liye recommended execution sequence

Development roadmap — 12 phases

00

Repository audit

Understand existing code

Start here

01

Research mapping

Petals + Sun et al.

Foundation

02

Networking design

Choose connectivity architecture

Architecture

03

P2P implementation

LAN, global, NAT traversal

Critical

04

Peer app improvements

Easy volunteer onboarding

Critical

05

Installer & auto-updates

Fix releases and updates

Critical

06

Dashboard UI/UX

Modernize web interface

Design

07

Peer application UI

Improve desktop experience

Design

08

Inference optimization

Research-based algorithms

Research

09

Security & recovery

Reliable execution

Stability

10

Integration & benchmarks

Test complete platform

Validation

11

Release preparation

Documentation and deployment

Final

## Har phase ke baad Codex ko kya prompt dena hai?

Ye chhota continuation prompt use karna, taake Codex pehle wale kaam ko samjhay aur unnecessary changes na kare.

Continue the ComputeTorrent development project using the master development roadmap.

First, read the existing progress tracker, architecture documentation, research mapping, and previous testing results.

Identify the next approved phase and its pending tasks.

Before modifying any code, inspect the relevant existing implementation.

Complete tasks sequentially, making small and verifiable changes. Run appropriate tests, fix any introduced issues, and update the progress documentation.

Do not repeat completed work or overwrite verified implementations unnecessarily.

At the end of the current phase, provide a detailed completion report and stop for review before proceeding to the next phase.

## Networking audit checkpoint — 2026-11-07

The supplied hybrid networking requirements were audited and concrete control/session/recovery/security regressions corrected; see docs/hybrid-network-audit.md and docs/testing-results.md. 52 selected tests passed; 7 existing signed-updater tests still error because the previous signed implementation is absent. No live services, deployment or provider release was authorized by this audit. Phase 3 stays Partially Validated — Remaining Integration Tests Pending. Automatic LAN/WAN endpoint selection, production Petals relay routing, real multi-peer inference and external-network acceptance remain open; retain the development fallback. This checkpoint does not start Phase 5 or certify production readiness.

## Follow-up integration evidence — 2026-11-07

The selected custom WSS adapter is now integrated with gateway leases, worker routing and coordinator assignments, while preserving native Petals DHT/RPC/TLS. Two isolated native-worker inference runs passed for tiny random BLOOM and Llama/GQA, including the production stage pipeline and local boundary/canary verification. See docs/petals-relay-integration.md. Actual multiple-PC/CGNAT acceptance remains unverified because no second test system is available. Phase 3 stays partially validated. Operator-controlled updater configuration is unchanged by this follow-up; the existing updater assertion failure is recorded explicitly. No new roadmap phase or public deployment was started.


## Sun optimization checkpoint — 2026-11-08

Implemented the operator-requested CG-BPRR/CG-BP, shortest-path/WS-RR, cache admission, request-target tuning, conditional bounds and bounded optional MILP reference kernels. Added a measured single-job coordinator bridge with baseline fallback/dominance gating and real gateway stage timings. See [Sun implementation and evidence](docs/sun-optimization.md) for equation-to-function mapping, research attribution, assumptions, tests and outstanding gates.

58 selected tests passed. Two isolated native Petals fixtures (BLOOM and Llama/GQA) executed unequal 3+1 ranges with successful production generation and existing checks. Synthetic planner costs are not measured speedups. Candidate Docker images built/imported successfully; live containers were not restarted and updater/provider distribution settings were unchanged. The runtime still admits one job and materializes processed ranges only. Persistent replica pools, concurrent online scheduling, real pretrained heterogeneous-peer A/B performance, physical multiple-PC/CGNAT acceptance and production readiness remain unverified. Phase 8 is partially implemented and isolated-validated, not complete.
