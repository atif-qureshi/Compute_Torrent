# 08.04 — WebTorrent File Sync Client (WT-1 to WT-5)

## Purpose
Fetch the dataset, model and prompt chunks a task needs from its private swarm, safely and resumably, then leave the swarm when the task is done.

## Requirements
| ID | Requirement | How we meet it |
|---|---|---|
| WT-1 | On assignment, join the per-task private swarm named in the message | Use `swarm_id` / infohash from `task_assign`; no public discovery |
| WT-2 | Download needed chunk(s) with integrity checks via SHA-1 piece hashing | Built-in WebTorrent hashing plus manifest SHA-256 check on the finished chunk |
| WT-3 | Resume if the download is interrupted | Keep partial data in the task workspace; re-join and continue |
| WT-4 | After completion and result submission, leave the swarm; do not seed forever | Explicit leave and delete; no background seeding of task data |
| WT-5 | Pass the downloaded chunk to the Docker sandbox as a mounted volume only | Hand the sandbox a directory inside the app workspace; never a host path outside it |

## How it runs
WebTorrent is a Node.js library while the app shell is Python, so a small **Node.js helper process** is bundled with the app and controlled over a local-only interface (start download, progress, stop, leave). Progress is reported as `downloading` status updates.

## Workspace rules
1. One workspace folder per task under the app's own data directory.
2. Everything inside is deleted after the task ends (success or failure).
3. Model files: by default **not cached** between tasks, so the "no task files remain" criterion holds. A "keep model cache" setting can come later and must be clearly visible to the user.

## Inputs / Outputs
| In | Out |
|---|---|
| `task_assign` (swarm_id, chunk ids, model_ref) | verified local chunk directory, progress events |
| completion signal from the app | swarm left, workspace deleted |

## Dependencies
- Needs: 02-networking-client (assignment), module 07 (swarm service on the server side).
- Feeds: 03-docker-sandbox (mounted chunk).
- Tech: Node.js, WebTorrent, local control interface between Python and Node.

## Build steps
1. Join a test swarm and download a test file.
2. Add progress reporting.
3. Interrupt and resume test.
4. Leave and cleanup, verify nothing keeps seeding.
5. Wire to `task_assign` and the sandbox mount.

## Acceptance checks
- Corrupted piece is detected and re-fetched.
- Download resumes after killing and restarting the app.
- After the task, no seeding connection and no files remain.
- Seeder cannot reach any swarm other than the one named in its assignment.

## Out of scope
Long-term seeding incentives, public torrents, cross-task caching (post-MVP).
