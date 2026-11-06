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
