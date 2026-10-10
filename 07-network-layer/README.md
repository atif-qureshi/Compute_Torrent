# 07 — Network Layer (per-task private WebTorrent swarms + connectivity)

## Purpose
Move datasets, models and prompt chunks between the server side and seeders through **private per-task swarms**, and keep seeders reachable through the relay with an optional direct upgrade. This module covers the data plane; the control plane (WebSocket messages) belongs to modules 02 and 08/02-networking-client.

## Design decisions (from the requirements document)
| Topic | Decision |
|---|---|
| Swarm scope | One private swarm **per task**, only that task's server-side seeder and its assigned seeders (WT-1) |
| Integrity | SHA-1 piece hashing built into WebTorrent plus our own SHA-256 chunk hashes from the manifest |
| Lifetime | Swarm is torn down after the task completes; seeders leave and stop seeding (WT-4) |
| Connectivity | Relay through the coordination server by default; try STUN then WebRTC for a direct link; failure is silent (NC-4) |
| Discovery | The assignment message names the swarm (`swarm_id`, infohash); no public tracker or public DHT needed |
| libp2p Kademlia DHT and Circuit Relay | Listed in the research proposal; **optional, post-MVP**. The MVP uses the WebSocket relay and STUN instead |

## Responsibilities
1. **Server-side swarm service (Node.js):** create a torrent for a task's chunks and model reference, seed it, return the infohash, tear it down on completion or failure.
2. **Seeder-side transfer:** implemented in `08-provider-node/04-webtorrent-sync`, using the same protocol.
3. **Connectivity helper:** STUN check and WebRTC upgrade attempt where supported; relay fallback.
4. **Integrity and bad peers:** discard bad pieces, re-fetch, drop peers that serve corrupted data.
5. **Resource control:** upload and download rate limits configurable per seeder.
6. **Local control API:** a small local interface so the Python server can say "create swarm", "tear down swarm", "status of swarm".

## Inputs / Outputs
| In | Out |
|---|---|
| task payload files and manifest | swarm_id, infohash, seeding status |
| teardown request | confirmation that the swarm is gone |
| peer events | active seeder count per swarm (for the portal, WP-2) |

## Dependencies
- Standalone core; soft dependency on 10 (model files and versions).
- Used by: 02 (creates and tears down swarms), 04 (payload files), 08 (seeder download).
- Tech: Node.js, WebTorrent; WebRTC/STUN support in the Node process; Socket.io only for status events if needed.

## Rules
1. Never trust a peer: verify before use.
2. A swarm must contain only the people who belong to that task.
3. The server side keeps seeding a task's data until all assigned seeders finish or the task fails, then tears the swarm down.
4. Small payloads may go directly over the WebSocket; use the swarm when size justifies it. Measure the threshold in module 11.

## Build steps
1. Two processes on one PC share a test file through a swarm.
2. Server creates a per-task swarm; a test seeder joins by infohash and downloads.
3. Add hash check, interruption and resume test.
4. Add teardown and verify nothing keeps seeding.
5. Add STUN/WebRTC attempt with relay fallback.
6. (Optional later) libp2p DHT and Circuit Relay.

## Acceptance checks
- A seeder downloads its chunk from the task swarm and cannot see another task's swarm.
- A corrupted piece is detected and re-fetched.
- After completion, the swarm no longer exists and no process seeds the task's data.
- When WebRTC fails, the transfer still works through the relay with no user-visible error.

## Out of scope
Public torrents, incentivized seeding, global-scale discovery tuning.