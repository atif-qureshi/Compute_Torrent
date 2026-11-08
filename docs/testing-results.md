# ComputeTorrent testing results

## Phase 0 baseline, 2026-11-06

Audit of checkout `0f0d02d` on Windows with Python 3.10.11 and host Node v24.17.0. No runtime or build source was changed in the phase.

| Check | Result | Scope |
| --- | --- | --- |
| `python 11-evaluation-benchmark/test_petals_provider.py -v` | 11 passed | Provider bootstrap address handling, runtime identity/digest and mocked Docker lifecycle. |
| `python 12-testing-validation/test_petals_network.py -v` | 4 passed | Injected bootstrap handshake/error handling, revision gating and failed stage settlement. |
| `docker compose -f docker-compose.local.yml config --quiet` and `config --services` | Passed | Canonical configuration resolves postgres, swarm, orchestrator, petals and portal. No daemon is required for parsing. |
| `docker compose --env-file .env -f docker/docker-compose.yml config --quiet` | Passed with obsolete `version` warning | Alternate configuration resolves with explicit environment-file selection. The plain alternate command failed to resolve required variables from the root. |
| Portal `node node_modules/typescript/bin/tsc --noEmit --incremental false` | Passed | Existing dependencies; static type check, no Next production build or browser test. |
| `node --check` for swarm, relay and provider libp2p helper | Passed | Three JavaScript entry points parse. |
| Python AST parsing | 16 files parsed | Top-level coordinator, desktop shell and Petals runtime Python entry points. |
| Direct parser probes | Two existing failures reproduced | JSON null token count and nonempty list model ID raise `TypeError`; HTTP response was not exercised. |
| Local update artifact inspection | Payload size and SHA-256 match the local feed; release labels diverge | Feed `2026.11.03-update3`; local Inno Setup ProductVersion and source build ID `2026.11.01-update2`. No executable launched. |
| Docker service status | Blocked by missing Docker Desktop Linux engine pipe | No container startup attempted in the audit. |

The unit checks do not run real inference or connect external devices. Live bootstrap, worker and end-to-end scripts exist under `11-evaluation-benchmark/` and were not run in this audit. Future checks need Docker and applicable model/runtime dependencies, plus real provider devices for a cross-PC claim. Windows clean install, update/restart and rollback were not exercised. Earlier project reports remain historical evidence only.

## Phase 0.5 secure updater validation, 2026-11-06

| Check | Result | Scope |
| --- | --- | --- |
| Existing updater, provider and Petals network suites | 22 passed (7 + 11 + 4) | Includes signed manifest rejection, replay, mocked launch, settings fixture, bootstrap and lifecycle checks. |
| Loopback HTTPS fixture | Passed | Disposable certificate and loopback-only listener. Rejected untrusted certificate and hostname mismatch. Accepted the explicitly trusted fixture and refused HTTPS-to-HTTP redirect. |
| Offline signer round trip | Passed | Temporary encrypted key outside checkout, inert installer bytes, signed testing manifest verified, older sequence rejected across SQLite connections, repository key path rejected before prompting. No publication. |
| Coordinator in-process ASGI check | Passed | Mock database, temporary job directory, health, seeders/stats, distributed catalog, enrollment and WebSocket registration. Legacy GET 410 and POST 405 on both endpoints. No live server, production credential or model execution. |
| Portal TypeScript and canonical Compose configuration | Passed | Static checks. Browser rendering and running portal download route were not exercised. |
| Desktop module and notification callbacks | Passed | Source import, numeric version ordering, mocked widgets for available update and missing trust configuration. No desktop GUI or installer launched. |
| Docker/ngrok and log review | Observed only | All five services exited. Local ngrok process and saved tunnel missing, inspector gave no HTTP response. Retained logs contain 15 download and 53 manifest HTTP 200 responses. Remote reachability and client completion remain unverified. |
| Clean install, legacy upgrade, signed install, interruption, restart, settings and recovery | Blocked | No isolated Windows installation environment was available. The production host's Windows session was not used as a test VM. |
| Hosted release security and end-to-end regressions | Blocked | No approved release host, publisher identities, or live-service startup authorization. No real dashboard session, remote P2P or Petals execution. |

## Phase 3 relay continuation, 2026-11-06

| Check | Result | Scope |
| --- | --- | --- |
| Phase 3, provider, Petals network and updater suites | 26 passed (4 + 11 + 4 + 7) | New unpaired lease test verifies expiry and late-peer denial. A first two-second fixture deadline elapsed during TLS setup, so the rerun used eight seconds to test expiry after admission. |
| Pinned Hivemind direct and WSS DHT | Passed, 2/2 bootstraps each and 10/10 lookups each | Disposable network-disabled container. Identity matched across paths. WSS broker recorded additional TCP bytes after bootstrap. |
| Native relay candidate | Inconclusive | Forced-private peer did not announce a circuit in the 12-second loopback observation. |
| Offline BLOOM 560M | Blocked, runner exit 2 | Metadata present. Both weight filenames absent from resolvable cache. Loader fails before model execution. No inference, real block advertisement or activations asserted. |
| Standalone backend parse | Existing failure | Indentation error near `backend/app/main.py:1004`. Separate from canonical coordinator. |
| Real networks and performance | Pending | See [network architecture](network-architecture.md) for measured bootstrap/lookup times and remaining hardware/network/inference metrics. |

## Phase 4 provider connection

| Check | Result | Scope |
| --- | --- | --- |
| Focused provider connection tests | 8 passed | Real loopback WebSockets plus fixture UI callbacks. Registration, wrong identity, reconnect, connection loss during active handling, cancel, address policy, errors and task guard. |
| Hidden Windows CustomTkinter fixture | Passed | Temporary settings and stubbed background work. Onboarding, Registered gating, hardware values and return to onboarding. |
| Existing regression suites | 26 passed | Phase 3 transport, provider/runtime, Petals network and updater. No service restart. |
| Live volunteer onboarding and Phase 3 acceptance matrix | Pending | No packaged installer or live provider rollout. |

## Provider restart correction, 2026-11-07

- Independent frozen restarts now remove inherited `_PYI_*`, `PYI_*` and `_MEI*` child environment variables and set `PYINSTALLER_RESET_ENVIRONMENT=1`. Parent state is preserved. Both provider source copies match.
- Focused regression suite: 2 tests passed, covering child environment isolation and rejection of legacy unsigned update entrypoints before network access or process launch. Both updater modules compile.
- Disposable PyInstaller 6.22.2 one-file probe successfully started an independent frozen child and wrote its completion marker. The first sandboxed attempt could not extract VCRUNTIME140.dll; the authorized unsandboxed fixture completed. This is not an installer upgrade or full update lifecycle test.
- Security regression observed in the current checkout: unsigned coordinator HTTP updating had replaced the approved signed verifier. Its public check, staging and execution entrypoints now fail closed. Automatic updates remain unavailable until authenticated signed updating is restored and validated. No downloaded update package was executed.
- Real installation, upgrade recovery and live volunteer acceptance remain unverified. Local packaging does not authorize publication or distribution.
- Local installer build completed: `2026.11.07-hybrid3`, Inno Setup 7.1.1, setup 167.66 MiB. Setup ProductVersion matches the build; provider EXE SHA256 matches provider-release.json; legacy setup copy hash matches canonical. Installer was not installed, published or distributed.

## Hybrid networking audit, 2026-11-07

| Suite / check | Result | Scope |
| --- | --- | --- |
| test_hybrid_recovery.py | 10 passed | Actual scheduler endpoint lifecycle with fixture gateway: capacity/device revalidation, delivery failure, setup replacement, no spare, active inference disconnect, same identity/new socket, status telemetry, ownership race and late buffered message. No real model execution. |
| test_hybrid_networking.py | 11 passed | Original mock-based labels, allocation and digest checks. Corrected module import isolation; no real operator DB accessed on final run. These do not establish WAN/CGNAT acceptance. |
| test_phase3_connectivity.py | 4 passed | ASGI enrollment/credentials/takeover/heartbeat/410 and isolated certificate-verified WSS relay byte tests. A missing ipaddress import and old-socket double-close initially failed and were fixed. |
| test_phase4_provider_connection.py | 9 passed | Real loopback provider transport plus UI fixtures; new revoked-credential test verifies no automatic re-enrollment and preserved identity. |
| test_petals_network.py | 4 passed | Bootstrap selection and readiness/capability/state regressions. |
| 11-evaluation-benchmark/test_petals_provider.py | 11 passed | Provider Docker invocation/addressing/runtime-digest fixtures; no real Docker workers. |
| test_provider_restart_environment.py | 2 passed | Independent restart environment and disabled unsigned updater entrypoints. |
| npm test in 07-network-layer | 1 passed | Actual ephemeral provider/coordinator overlay TCP/Noise connection, expected identity and ping. No multicast, no project daemon; sandbox spawn EPERM required authorized unsandboxed fixture rerun. |
| JS module imports, npm dependency checks, Python compile, git diff --check | Passed | Both canonical network modules import; explicit ping dependency resolved. Canonical/legacy provider JS syntax checks pass. |
| Existing test_secure_provider_update.py | 7 errors, release blocker | Current checkout lacks the previously approved signed-updater API (SETUP missing). No tests were skipped or rewritten to claim success; the legacy provider updater is disabled and both canonical coordinator legacy feed routes return 410. Restoration of the signed updater remains separate work. |
| Real separate-PC LAN, separate ISP, CGNAT, roaming, physical power failure and multi-peer inference | Unverified | No live service restarted, public infrastructure provisioned or installer distributed. |

52 tests passed across the selected Python and overlay suites; the seven signed-updater errors remain explicitly open. This is not an all-green repository or production-readiness report. See hybrid-network-audit.md for requirements, diagram, changed modules, infrastructure and acceptance gaps. Current source fixes are newer than the locally built hybrid3 installer.

## Integrated Petals WSS follow-up — 2026-11-07

| Check | Result | Boundary |
| --- | --- | --- |
| Integrated relay / identity / route / diagnostics suite | 6 passed | Real TLS/TCP streams, both directions, eight concurrent half-closed streams, replay/auth/TLS/expiry/framing denial, coordinator nonce proof and diagnostics redaction; route selection fixtures. |
| Production recovery scheduler suite | 12 passed | Includes relay lease allocation, expected identity probe before inference, revocation, failure cleanup and invalid relay proof. The deliberately undersized fixture was adjusted to 0.5 GiB to remain undersized under the operator's new capacity formula. |
| Provider connection suite | 10 passed | Actual alternate WebSocket challenge sends no bearer header/token; registration/reconnect and existing controls preserved. |
| Provider runtime/diagnostics suite | 13 passed | Added OOM-specific reporting and log retention before container removal. |
| Original hybrid suite / Petals network | 12 passed / 4 passed | Mock control/capability coverage and native bootstrap/state unit checks, not real WAN acceptance. |
| Tiny random Llama/GQA native integration | Passed, exit 0 | Two native workers, two layers, native generation matches reference; actual production sliced pipeline completed, boundary verification and canary passed; 31,460 post-startup payload bytes over WSS. |
| Tiny random BLOOM native integration | Passed, exit 0 | Same actual pipeline and checks; 37,508 post-startup payload bytes over WSS. Local fixture contains documented block-key aliases, hence reference-loader extra-key warnings. |
| Existing Phase 3 suite | 3 passed, 1 failed | Retained test expects legacy update manifest 410, but the operator explicitly enabled it (observed 404 with no manifest in the isolated fixture). Updater code/assertion were not changed after the instruction not to touch updater behavior. Automatic review rejected the proposed assertion removal; it remains intact. |
| Real TinyLlama-1.1B screenshot failure | Cause not established | Local artifacts are for the other peer; failed peer's original traceback/container not available. Exact local revision has config metadata but no complete weight file. New diagnostics require a fresh run with current runtime. |
| Physical devices / public ingress / CGNAT | Blocked by availability/configuration | Operator confirmed no second PC available. No deployment, ISP/CGNAT or physical power interruption test is claimed. |

Docker fixtures used pinned cached image f66ff872f25b, no external network or published ports, 2 CPUs/5 GiB limits, read-only source/websockets mounts, and randomly initialized tiny local checkpoints. No full pretrained weights were downloaded. Added explicit sequence-manager/DHT cleanup and verified successful fixture process exit. Test evidence is separate from production readiness and full VeriLLM claims. See docs/petals-relay-integration.md for reproduction and architecture.

Local provider packaging completed after verification: build `2026.11.07-hybrid4`, setup ProductVersion matches, 167.67 MiB. EXE SHA256 matches provider-release.json; canonical/legacy setup hashes match. Frozen archive extraction confirms worker.py, relay_transport.py, route_selection.py and generate_job.py exactly match current source. No installer was installed or published, and no update feed/configuration was changed. The operator-selected existing version identifier was preserved.

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


## Sun optimization checkpoint — 2026-11-08

Implemented the operator-requested CG-BPRR/CG-BP, shortest-path/WS-RR, cache admission, request-target tuning, conditional bounds and bounded optional MILP reference kernels. Added a measured single-job coordinator bridge with baseline fallback/dominance gating and real gateway stage timings. See [Sun implementation and evidence](sun-optimization.md) for equation-to-function mapping, research attribution, assumptions, tests and outstanding gates.

58 selected tests passed. Two isolated native Petals fixtures (BLOOM and Llama/GQA) executed unequal 3+1 ranges with successful production generation and existing checks. Synthetic planner costs are not measured speedups. Candidate Docker images built/imported successfully; live containers were not restarted and updater/provider distribution settings were unchanged. The runtime still admits one job and materializes processed ranges only. Persistent replica pools, concurrent online scheduling, real pretrained heterogeneous-peer A/B performance, physical multiple-PC/CGNAT acceptance and production readiness remain unverified. Phase 8 is partially implemented and isolated-validated, not complete.
