# 07 — Network Layer

## Working MVP data path

The swarm service uses private WebTorrent swarms to deliver registered model files and per-task prompt payloads to providers. It uses the configured WebTorrent tracker endpoints for WebRTC peer signalling. WebTorrent piece integrity is supplemented by manifest SHA-256 checks after download. Result text returns through the coordinator WebSocket.

The same service also starts a libp2p LAN overlay using Kademlia peer discovery and Circuit Relay v2. Providers can join the coordinator's advertised peer address, and the portal can display the overlay's connected-peer count. The overlay is real networking code, but it is **not currently integrated into the model/prompt file transfer path**.

## Status by capability

| Capability | Status |
|---|---|
| Private per-task WebTorrent swarms | Implemented; configured trackers are still used for WebRTC signalling. |
| Model and prompt transfer | Implemented over WebTorrent, with manifest SHA-256 validation at the provider. |
| Per-task swarm cleanup | Implemented by the coordinator after task completion or failure. |
| libp2p LAN DHT and Circuit Relay overlay | Implemented for peer discovery/connectivity reporting; not used to transport task files. |
| Trackerless libp2p data plane and relay-based file transfer | Future architecture work. Do not present this as an active transfer fallback. |
| Internet-scale NAT traversal and volunteer discovery | Future work; current multi-PC guidance is for a trusted LAN. |

## Boundaries

- WebSocket carries assignments, progress, verdicts, and inline results; it is the centralized control channel.
- WebTorrent carries model and prompt files. Tracker services may observe peer connection metadata even though the torrents are private and content hashes are verified.
- A private magnet URI is a bearer capability. Only share it with intended providers.
- The libp2p peer overlay and WebTorrent transport are separate paths today. Failure to join libp2p does not fall back to trackerless file transfer; WebTorrent remains the configured data path.
- Never expose the local coordinator or swarm administration API to the public internet as part of this development setup.

## Future implementation work

1. Define an authenticated libp2p data protocol for model/prompt manifests and chunks.
2. Add relay-assisted transfer, peer authorization, resumability, and abuse limits.
3. Make providers select a transport based on a real end-to-end transfer probe.
4. Test multi-peer LAN churn and failure recovery before describing trackerless transfer as available.

See [implementation status](../docs/IMPLEMENTATION-STATUS.md) and [local multi-PC setup](../IMPLEMENTATION-SETUP.md).
