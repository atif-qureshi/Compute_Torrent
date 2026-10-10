# 12 — Testing and Validation

## Purpose
Prove each module works, the whole pipeline is correct, and failures are handled.

## Test levels
| Level | Scope | Examples |
|---|---|---|
| Unit | one module's logic | slicer ordering, credit formula, availability score, hash checks |
| Contract | message shapes between modules | ASSIGN/RESULT validation against docs/CONTRACTS.md |
| Integration | two or three modules | orchestrator + worker, slicer + allocator, worker + p2p |
| End-to-end | full flow | submit prompts, get verified ordered results |
| Fault injection | failures | worker kill, packet delay, corrupt chunk, cheating worker |
| Security checks | abuse cases | unauthorized RESULT, canary leak, sandbox escape attempts |
| Usability | demo readiness | install on clean PC, portal walk-through |

## Core scenarios (must pass)
1. Happy path with 3 workers.
2. Worker dies mid-chunk, task still completes.
3. Cheating worker returns random output, caught by L1.
4. Colluding pair, flagged by L2/L3.
5. Corrupted download, detected by hash and re-fetched.
6. Orchestrator restart during a task.
7. Version mismatch on a worker.
8. Insufficient resources: worker declines with reason.
9. Zero-credit requester blocked.
10. Output equals single-node output for the same deterministic workload.

## Test data
Public prompt sets only (ethical scope). Prepared canary sets with known outputs. Seed DB script for portal tests.

## Environments
| Env | Setup |
|---|---|
| Dev | all services on one PC, workers as multiple processes/containers |
| Lab | 3+ machines on one LAN |
| Demo | lab + optional ngrok for remote access |

## Acceptance for the whole MVP
- All 10 core scenarios pass twice in a row.
- Benchmark dataset produced (module 11).
- Demo script runs in under 15 minutes without manual fixes.
- Known limitations documented.

## Tools (planned)
pytest-style test runner for Python, a test runner for the portal/Node parts, Docker Compose for local multi-worker setups, network-shaping tool for delay/bandwidth, simple load script for heartbeats.

## Bug tracking
Issue list with severity; any bug that breaks a core scenario blocks the next milestone.

## MVP demo acceptance (from the requirements document)
- [ ] User installs the app with no manual steps beyond running the installer (Docker present).
- [ ] App detects real hardware and shows the right tier.
- [ ] App connects and shows "Online".
- [ ] A test task (even simulated) is received, run in an isolated container, and a result returned.
- [ ] After the task no files from it remain on the host.
- [ ] UI shows live status while idle and while processing.
- [ ] (Stretch) Portal shows the task's live progress from the requestor side.

Extra checks specific to the seeder app: sandbox escape attempts fail (host read, outbound network), killing the app mid-task leaves no container, Docker stopped produces a clear message, per-task swarm is gone after completion.

## Out of scope
Formal security audit, large-scale load testing.
