# 08.03 — Docker Sandbox Runtime (DS-1 to DS-6)

## Purpose
Run every task inside a fresh, locked-down, disposable container so the donor's PC is never at risk. This is the project's central safety guarantee.

## Requirements
| ID | Requirement | How we meet it |
|---|---|---|
| DS-1 | Fresh disposable container per task; never reuse | New container for each assignment (the earlier "warm reuse" idea is dropped) |
| DS-2 | Hard CPU and memory caps; GPU via NVIDIA Container Toolkit only for the assigned task | Resource limits at container creation; GPU device attached only for that run |
| DS-3 | No network except pulling its chunk and returning its result; no host filesystem beyond its mounted workspace | **Resolved:** network is fully disabled; the app downloads the chunk (module 04) and mounts it; the app, not the container, returns the result |
| DS-4 | Destroy the container immediately after success or failure; no leftover state or files | Automatic removal plus workspace deletion; a leftover check at the end |
| DS-5 | Crash, timeout or limit exceeded -> report `failed`, no silent retry | Map container exit codes and timeouts to `status_update: failed` with a reason |
| DS-6 | Log lifecycle events locally (created, started, completed, destroyed); never send raw logs to the network | Local log view in the app for transparency |

## Container contract
| Item | Rule |
|---|---|
| Image | One approved inference image (small, pinned by digest) holding the runtime and nothing sensitive |
| Mounts | Chunk directory read-only; a separate empty output directory writable; nothing else |
| User | Non-root inside the container |
| Network | None |
| Limits | CPU cores, memory, and wall-clock timeout set per task from the assignment and tier |
| GPU | Attached only when the task kind needs it and the node is Tier-1 |
| Inference settings | Fixed by the assignment (greedy decoding, seed, max tokens) so results can be verified |
| Model access | Model files provided read-only through the same chunk/mount mechanism |

## Run sequence
Prepare workspace -> create container with limits -> start -> watch (timeout, memory) -> collect output file(s) -> stop and remove container -> hash and hand output to the app -> delete workspace -> log "destroyed".

## Safety checks (NFR-1)
1. A test task that tries to read a host path, write outside the mount, or open a network connection must fail.
2. After every run, confirm no container, volume or temp file remains.
3. If the check finds leftovers, remove them and log a warning.

## Dependencies
- Needs: Docker Engine (Docker Desktop on Windows), NVIDIA Container Toolkit for GPU, chunk directory from 04-webtorrent-sync.
- Feeds: 02-networking-client (results, failure reasons).
- Tech: Docker SDK for Python or Docker CLI calls from the app.

## Build steps
1. Run a dummy script in an isolated container and read its output.
2. Add limits, timeout, no-network, non-root.
3. Mount chunk read-only plus writable output; destroy and verify clean.
4. Add failure mapping (crash, timeout, out of memory).
5. Add GPU attach for Tier-1 and a small real model run.
6. Run the escape tests from "Safety checks".

## Acceptance checks
- After a task, `docker ps -a` and the workspace show nothing left.
- Escape attempts (host read, outbound network) are blocked.
- Killing the app mid-task leaves no running container after restart (startup cleanup).
- Timeout produces `failed`, not a hang.

## Out of scope
Multiple concurrent containers per seeder (one task at a time for MVP), non-NVIDIA GPU passthrough.
