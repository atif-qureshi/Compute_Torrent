# 05 — Memory and Churn-Aware Allocator

## Purpose
Implements the concept's **Decentralized Node Coordination**: peer matching, connection handling input, and fault tolerance. Choose which provider (seeder) runs which chunk, accounting for memory limits and the chance that a provider disappears; re-assign chunks if a provider drops offline mid-task. Runs inside the Coordination Server using the seeder registry, capability tiers (Tier-1 for VRAM of 8 GB or more, Tier-2 otherwise), and live heartbeats. Tier decides which task kinds a seeder may receive.

## Key idea
Each worker j has an availability score u_j (0 to 1) estimated from its history (uptime ratio, session length, recent heartbeat gaps). Lower u_j means more risk, so important or long chunks go to higher u_j workers, or get replicated.

## Responsibilities
1. Filter eligible workers: enough RAM/VRAM for the model, Docker OK, status ONLINE, not suspended.
2. Score workers: capacity (speed benchmark), availability u_j, trust score (from 06/09), current load.
3. Assign chunks: greedy or waterfilling style, largest chunks to best scores.
4. Replication policy: replicate when u_j below threshold, chunk is critical (canary pair, long chunk), or task tier demands it.
5. Reassignment on churn: when WORKER_LOST fires, move its chunks to others, preferring workers already holding the model weights.
6. Load balancing over time: avoid piling onto the same worker.
7. Record decisions and reasons (needed for benchmark analysis and defense).

## Inputs / Outputs
| In | Out |
|---|---|
| chunk plan from 04 | assignments (chunk -> worker, replica number, deadline) |
| worker profiles and history from 03 | updated availability scores |
| WORKER_LOST / CHUNK_FAILED events | reassignment actions |

## Availability score (conceptual)
Combine: fraction of time online in last window, average session length, heartbeat regularity, and recent drops. Smooth with a moving window so one bad hour does not ruin a worker. Exact formula is a documented design choice, tuned in module 11.

## Dependencies
- Needs: 03, 04, 08 (profiles); soft: 09 (priority/trust).
- Feeds: 02.
- Tech: Python; no heavy solver needed for MVP.

## Rules
1. Never assign a chunk the worker cannot fit in memory.
2. Replicas of the same chunk go to different workers, ideally different networks.
3. A retry limit exists; after the limit the task fails with a clear message.
4. Deadlines scale with chunk size and worker speed.

## Build steps
1. Eligibility filter + round-robin.
2. Capacity-weighted assignment.
3. Availability score + replication threshold.
4. Churn reassignment loop.
5. Decision logging.

## Acceptance checks
- Killing a worker mid-run results in reassignment and a completed task.
- Replication triggers for low-u_j workers and not for high-u_j ones.
- Allocator decisions can be explained from logged inputs.

## Out of scope
Global optimal solver, geographic latency-aware routing (future work).
