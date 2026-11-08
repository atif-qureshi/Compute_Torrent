# ComputeTorrent implementation progress

Roadmap authority is [flow.md](../flow.md). This tracker uses its task IDs, independently of the historical MVP checklist. “Completed” for Phase 0 means the audit task and its available verification are finished. It does not certify the audited feature.

| Phase | Task ID | Description | Status | Dependencies | Modified files | Validation | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.1 | Inspect repository structure | Completed | — | architecture-analysis.md | Reviewed tracked inventory and previous progress reports | Canonical and alternate trees identified. |
| 0 | 0.2 | Identify component ownership | Completed | 0.1 | architecture-analysis.md | Traced Compose services, entry points and module imports | Dependency diagram recorded. |
| 0 | 0.3 | Audit stack and dependencies | Completed | 0.2 | architecture-analysis.md, testing-results.md | Reviewed dependency manifests, Dockerfiles and installed host versions | Build reproducibility gaps recorded. |
| 0 | 0.4 | Trace inference and results | Completed | 0.3 | architecture-analysis.md, research-mapping.md | Followed both inference call paths and ran provider/network regressions | Runtime completion not verified in this pass. |
| 0 | 0.5 | Audit peer discovery and communications | Completed | 0.4 | architecture-analysis.md, testing-results.md | Inspected provider registration, bootstrap, helper and worker code; 15 unit checks passed | Three transport paths documented separately. |
| 0 | 0.6 | Check Tailscale and actual remote integration | Completed | 0.5 | architecture-analysis.md | Tracked-source search and ngrok/portal address trace | Host VPN configuration outside checkout was not inspected. |
| 0 | 0.7 | Audit installation and update mechanisms | Completed | 0.6 | architecture-analysis.md, testing-results.md | Traced build, download and updater; inspected artifact version, size and digest | TLS, raw EXE download and version drift findings recorded. |
| 0 | 0.8 | Audit dashboard routing and state | Completed | 0.7 | architecture-analysis.md, testing-results.md | Inspected routes, shared navigation, proxy and polling; TypeScript check passed | Browser UX evaluation remains pending. |
| 0 | 0.9 | Identify bugs and limitations | Completed | 0.8 | architecture-analysis.md, development-roadmap.md, testing-results.md | Two parser exceptions reproduced; high-severity findings tied to source | Remediation deferred to approved phases. |
| 0 | 0.10 | Audit tests, environment, builds and deployment | Completed | 0.9 | architecture-analysis.md, testing-results.md, development-roadmap.md | Both Compose configurations validated with appropriate environment selection; daemon unavailable | Live checks remain unverified. |
| 1 | 1.1–1.7 | Analyze papers and map methods | Completed | Phase 0.5 research approval | research-mapping.md, architecture-analysis.md, implementation-progress.md, flow.md | Supplied PDF sections and publication records compared with active source | Phase 2 awaits approval. |

Phase 0 completed on 2026-11-06. Five roadmap documents were created. Existing code, historical progress files, and the supplied roadmap remain as found.

## Emergency provider update security checkpoint

| Phase | Task ID | Description | Status | Dependencies | Modified files | Validation | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Emergency | E.1 | Contain legacy feed and preserve evidence | Completed | User authorization | Coordinator routes, portal, provider build script | Legacy serving removed in source; stopped local containers and artifact fingerprints recorded | Existing binaries and remote infrastructure require separate migration. |
| Emergency | E.2 | Investigate legacy update trust chain | Completed | E.1 | security-update-audit.md | Traced route, client, build and replacement code | No compromise determination from available evidence. |
| Emergency | E.3 | Implement authenticated client and installer handoff | Completed | E.2 | Canonical and legacy desktop shell | Signed metadata, verified HTTPS, channel/version checks, staged digest and replay state | Trust anchors remain unprovisioned pending approved release setup. |
| Emergency | E.4 | Isolated security validation | Completed | E.3 | test_secure_provider_update.py | Mock signer, transfer and process boundary tests | Real Windows wizard and hosted TLS validation remain release gates. |
| Emergency | E.5 | Deploy and migrate existing clients | Pending | Separate deployment and publication approval | — | Not performed | Phase 1 paused pending review. |

Phase 1 paper reading began before the emergency request and was resumed after research approval.

## Phase 0.5 checkpoint

| Task ID | Status | Evidence and next action |
| --- | --- | --- |
| 0.5.1 Security review | Completed | Client trust checks, actual loopback TLS, signer and replay checks passed within the recorded threat model. |
| 0.5.2 Legacy migration | Plan completed, rollout blocked | Logs and local state reviewed. Remote inventory, retirement and trusted manual migration require approval and operator access. |
| 0.5.3 Windows install | Blocked | Isolated Windows environment unavailable. Run clean install, update and recovery matrix before release. |
| 0.5.4 Release infrastructure | Blocked | Review completed. Host, signing infrastructure, publisher authorization, Authenticode, audit logging and disablement drill pending. |
| 0.5.5 Regression | Partial | 22 tests and isolated API, source UI and type checks passed. Live/browser/device/model checks remain pending. |
| 0.5.6 Documentation | Completed | See [release readiness](provider-release-readiness.md), [audit](security-update-audit.md), and [testing results](testing-results.md). |

Phase 0.5 checkpoint approved for research and development only. Release gates remain independently blocked.

## Phase 1 checkpoint

| Task | Status | Evidence |
| --- | --- | --- |
| 1.1 Study Petals papers | Completed | Both supplied papers identified and mapped, including routing, caches, balancing and recovery. |
| 1.2 Analyze Sun et al. | Completed | Offline CG-BPRR and online CG-BP/WS-RR, measurement model, feasibility and assumptions documented. |
| 1.3–1.5 Applicability, comparison and gaps | Completed | Traced active placement, provider telemetry, worker startup, DHT, route generation, verification and unused planner helpers. |
| 1.6 Integration strategy | Completed | Later-phase dependency order, one-request experiment, baselines, metrics and failure gates recorded. |
| 1.7 Attribution | Completed | Published methods distinguished from ComputeTorrent engineering proposals. |

This is a documentation and source review checkpoint. Runtime experiments remain pending. No networking implementation, service restart, deployment, release or legacy endpoint reactivation was authorized. Stop here for Phase 2 review.

## Phase 2 checkpoint

| Tasks | Status | Evidence |
| --- | --- | --- |
| 2.1–2.3 Failure analysis, LAN/Internet and NAT | Completed | Source trace of coordinator, discovery, file transfer and Petals. Reported remote incident could not be reproduced. |
| 2.4–2.7 Protocols, native client, relay and trade-offs | Completed | Compared direct TCP, WSS, ICE/STUN/TURN and libp2p relay against actual protocol boundaries. |
| 2.8–2.10 Connection workflow, identity and fallback | Completed | Proposed bounded probes, relay authorization, reconnection and scheduler eligibility. |

See [network design](network-design.md). Four existing Petals network tests passed. The relay prototype and live acceptance matrix remain pending. Phase 3 awaits approval.

## Phase 3 implementation checkpoint

| Tasks | Status | Evidence |
| --- | --- | --- |
| 3.1 Local discovery | Partial | Existing helper confirmation is checked. Automated discovery and multi-device testing pending. |
| 3.2 Registration and identity | Partial | Configured enrollment, origin binding and registration acknowledgment tested. One-use invites and runtime proof-of-possession pending. |
| 3.3–3.5 Global connectivity, NAT and relay | Partial | ngrok control hardening in source and isolated TLS TCP relay fixture. No pinned runtime integration or cross-network validation. |
| 3.6–3.8 Health, reconnect and dashboard | Implemented and isolated tests passed | Lease expiry, duplicate handling, reconnect, and heartbeat age. Live UI/device validation pending. |
| 3.9 Tailscale migration | Pending verification | No tracked mandatory dependency. Replacement onboarding requires device acceptance. |
| 3.10 Inference compatibility | Partial | Existing Petals regressions passed. Direct and relayed live inference remain pending. |

See the [Phase 3 implementation record](phase-3-connectivity.md). Phase 3 is open and Phase 4 has not started.

### Phase 3 continuation

- Pinned Petals and Hivemind compatibility reviewed from the cached image and active source. Direct and custom WSS bootstrap and DHT lookups passed in two isolated runs. The native relay fixture did not announce a circuit.
- One additional regression verified that an unpaired relay closes on lease expiry and denies a late peer. All 26 regression tests passed.
- Offline BLOOM 560M load attempted. The incomplete checkpoint blocked model worker startup, real block discovery and end-to-end inference. Route integration and real network acceptance remain pending.
- [Network architecture and measurements](network-architecture.md) records reproduction, comparison limits and the device test matrix.
- **Partially Validated — Remaining Integration Tests Pending.** Conditional approval permits Phase 4. Keep real multi-peer inference, different ISP, CGNAT, restrictive firewall and reconnection tests open. Global P2P is not production-ready. Retain the Tailscale development fallback and updater and release restrictions.

## Phase 4 checkpoint

| Tasks | Status | Evidence |
| --- | --- | --- |
| 4.1–4.4 Source review, startup, onboarding and connect/disconnect | Implemented | Operator address normalization, single connection lifecycle and cancel-to-onboarding tested. |
| 4.5–4.7 Status, resource display and controls | Implemented | Matching coordinator acknowledgment gates Registered. Hidden Windows widgets and active-task controls verified. |
| 4.8–4.10 Recovery, actionable errors and stability | Implemented | Loopback disconnect, reconnection, identity rejection and loss during a busy handler tested. |

[Phase 4 implementation record](phase-4-provider-connection.md) documents the canonical provider changes. Eight focused tests and the 26 existing regressions passed. Real volunteer acceptance remains pending. Phase 5 has not started.

## Local provider restart hotfix, 2026-11-07

Corrected independent PyInstaller restart environment handling in canonical and legacy provider sources; local build identifier is `2026.11.07-hybrid3`. Two focused tests and a disposable frozen parent/child restart probe passed (see testing-results.md). The unsigned updater found in the current checkout is disabled at all public entrypoints pending restoration of the approved signed verifier. Existing release restrictions remain active. No live service was restarted and no production update was published. This hotfix does not advance the roadmap phase or establish full installer-upgrade validation.

## Hybrid networking verification and containment, 2026-11-07

Reviewed the supplied Hybrid LAN and Global P2P requirements against actual control, overlay, transfer and Petals code. Fixed registration's missing import, concurrent socket ownership/late-message/double-close errors, capacity-unsafe recovery and stale inference sessions, unconditional enrollment fallback and automatic revoked-client re-enrollment. Restored canonical legacy updater 410 endpoints, kept client updates disabled, disabled automatic gateway router mapping, explicitly pinned the imported ping dependency, and added a real isolated overlay test. Canonical and legacy provider-shell fixes match.

Evidence: 52 selected tests pass (including 10 production-path recovery checks and one real loopback overlay test). Seven existing signed-updater tests error due to the missing prior verifier implementation; that release gate remains blocked. Actual LAN/WAN Petals inference, automatic authenticated LAN/WAN endpoint selection and production relay integration remain incomplete. See [hybrid audit](hybrid-network-audit.md) and testing-results.md. Phase 3 remains Partially Validated — Remaining Integration Tests Pending. No live service restart, new installer build, publication or Phase 5 work occurred.

## Integrated relay and TinyLlama diagnostics — 2026-11-07

The follow-up integration is now implemented; see [Petals relay integration](petals-relay-integration.md). Gateway-scoped WSS leases carry native Petals TCP/RPC in both directions; worker-side reverse reachability prefers direct LAN and selects WSS fallback. Alternate coordinator endpoints use per-node identity proofs and challenge-based registration without forwarding bearer secrets. Active KV sessions are not migrated.

Offline, network-disabled fixtures with two native worker processes passed both tiny random Llama/GQA and BLOOM generation. The actual production stage-by-stage pipeline, local boundary replay and canary checks completed in both cases, with 31,460 and 37,508 post-startup TCP payload bytes respectively. These are real native integration tests, not physical multiple-PC or CGNAT acceptance. The operator confirmed no second test PC is currently available; those gates remain open.

The reported TinyLlama-1.1B job's failed peer traceback was unavailable. Exact-revision local cache inspection found config only, no complete weight file. This does not establish the other peer's cause. Added retained layer/container logs, exception-first status details and OOM-specific errors. Updater behavior was explicitly placed under operator control and was left untouched after that instruction; do not interpret historical disabled-updater statements as current configuration. The retained legacy-retirement test currently conflicts with that operator configuration and is not silently removed.

No live service restart, public deployment or feed publication was performed by this work. Phase 3 is still Partially Validated — Remaining Integration Tests Pending. Phase 5 has not started.

A local hybrid4 Windows installer was rebuilt with the relay and retained-diagnostics code. Hashes, setup version and embedded runtime source contents were verified. Updater settings/feed remain operator-controlled and unchanged. Manual installation is available for the next authorized test; the existing live stack was not restarted.

## Provider/portal visual alignment — 2026-11-08

Implemented the operator-requested native provider redesign in canonical and legacy desktop sources. The provider follows the portal's light neutral/violet design, compact navigation and separated connection, hardware, activity and help views. Existing coordinator-confirmed state and operational callbacks are preserved; updater execution/configuration is unchanged. Eight actual Tk widget tests and 11 existing Phase 4 connection regressions pass, along with Python compilation and scoped whitespace checks. See [provider design record](provider-design.md). This presentation work does not advance the research roadmap or validate physical multi-PC inference. Local candidate packaging is isolated from installed/distributed artifacts.

## Dark mode, original EXE replacement and authorized feed publication — 2026-11-08

Added persisted Light/Dark/System appearance with native tuple-based colors. Theme changes do not reconstruct the form or discard unsaved values. Toolbar, status and notification colors adapt; the updater logic and connection protocol remain unchanged. The build is 2026.11.08-ui1. Nine native widget/theme/layout tests and 11 Phase 4 connection tests passed. Python compilation passed.

The operator explicitly approved publishing the update feed. The canonical and legacy EXEs, installer ZIPs and Inno Setup installer were rebuilt. The original D:\ComputeTorrent\ComputeTorrent_Seeder.exe was backed up and replaced with the matching build. Old artifacts and the prior manifest are retained under runtime/provider-release-backup-2026.11.08-ui1. The feed uses a versioned artifact and an atomic manifest replacement. Its HTTP manifest and full streamed download passed size and SHA-256 verification. Old-build and current-build version detection both passed. The existing portal download API still returns its configured 410 and was not re-enabled.

The actual frozen EXE launched with an isolated profile and exposed its 2026.11.08-ui1 native window. The test instance was closed and the replaced original-location EXE launched. Screenshot capture failed with FrameArrived timeout; activation and a fresh-window retry also failed with window capture timeout. Accordingly, rendered visual acceptance is still blocked by the capture environment; it is not recorded as passed. No multi-PC inference or automated installer installation/rollback was tested in this presentation update.

## Provider navigation hotfix release — 2026-11-08

Fixed ui1 showing Help while Connection was selected. Only the selected page host is now mapped; hidden-page widgets retain unsaved values. A new real Tk visibility test failed against ui1 and passes for ui2. Ten UI and 11 connection tests passed. The 2026.11.08-ui2 EXE was rebuilt and its page-host closure inspected in the final archive. Original-location replacement preserved the settings file byte-for-byte before relaunch. Canonical/legacy EXEs and ZIPs were updated, and the previously authorized update feed now serves ui2; full HTTP download size/SHA-256 were verified. Prior artifacts remain backed up under runtime/provider-release-backup-2026.11.08-ui2. Native screenshot/activation timed out, so screenshot-based acceptance remains unverified.

## Responsive provider overview release — 2026-11-08

2026.11.08-ui3 implements the requested side-by-side overview with three wide-screen columns, two medium-screen columns and a narrow-screen fallback. Eleven native layout/theme/navigation tests and eleven connection tests passed. Reflow preserves the live status widgets and keeps the wide-screen current-assignment text in view; card bounds were checked against the window. Before replacing the app, the release script checked for a current distributed assignment on this provider. Original-location replacement preserved settings byte-for-byte and relaunched the app. Canonical/legacy EXE and release metadata were updated and the previously authorized feed advanced to ui3. No updater or connection algorithm was changed.

## Local provider registration crash — 2026-11-08

Fixed UnboundLocalError for client_host in websocket_seeder when a provider explicitly reports LAN or WAN. Client-address resolution now runs before the reported-mode branch; existing classification and header precedence remain unchanged. The new actual-handler regression reproduced the failure on the prior code and passes for six reported/inferred/missing-client/forwarded-address cases. Thirteen recovery/coordinator tests and eleven provider connection regressions passed.

Rebuilt and recreated only the local orchestrator service after confirming zero active distributed jobs. Health reports healthy; the existing local provider automatically reconnected and appears in the coordinator with a fresh control heartbeat. Fresh logs confirm an accepted LAN WebSocket and successful registration without the reported exception. No provider EXE, updater configuration, or inference execution was changed or tested by this hotfix.

## Two-card header and full-width assignment — 2026-11-08

Per the operator’s revised layout, the overview uses two equal-width cards for connection/resources and a full-width current-assignment panel beneath them. Narrow windows retain a single-column fallback. Live widgets, controls, theme and connection behavior remain unchanged. Eleven native tests (including equal top widths, lower-panel columnspan/position/full width, responsive reflow and retained widgets) and eleven connection regressions pass. Target build is 2026.11.08-ui4.
