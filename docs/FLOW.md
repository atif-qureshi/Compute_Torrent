# ComputeTorrent architecture and end-to-end flow

ComputeTorrent is a local-first volunteer-computing MVP. One coordinator manages task state and provider assignment; multiple provider PCs can join from a trusted LAN. This is independent prompt inference, not distributed training or model-parallel inference.

## Current planes

| Plane | Current implementation | Centralized? |
|---|---|---|
| Portal/API | Next.js portal calls the FastAPI coordinator through a server-side authenticated proxy. | Yes |
| Control | HTTP API and provider WebSocket carry enrollment, heartbeat, task assignments, status, and inline results. | Yes |
| File data | Private WebTorrent swarms transfer prompt payloads and GGUF model/adapter files. WebRTC peer signalling uses configured tracker endpoints; providers validate SHA-256 manifests. | Swarm-based, but current discovery depends on tracker signalling. |
| LAN discovery overlay | A separate libp2p Kademlia/Circuit Relay peer network provides LAN peer connectivity information. It does not transport task files. | Coordinator bootstraps it. |
| Execution | Provider launches llama.cpp inside a disposable network-disabled Docker container. | Provider-local |
| Verification | Strict replica-output majority when replicas are available; optional separate known-answer canary task; limited Merkle output-transcript receipt. | Coordinator-managed |
| Results and credits | Coordinator stores task history/results and demo credit ledger entries. | Yes |

## Happy path

1. The operator starts the local Compose stack and registers a licensed, operator-supplied GGUF model.
2. The requestor signs into the local portal, selects the model/scheduler/resource filters, and submits one prompt or a batch of independent prompts.
3. The coordinator validates and slices the prompts into ordered one-prompt chunks, applies the current provider limit/requirements, records the one-credit demo task charge, and waits for eligible providers if none are connected.
4. The coordinator creates private WebTorrent swarms for task payloads. Registered model files are served through their model swarm.
5. Each idle eligible provider receives one assignment over WebSocket, downloads the model/chunk over WebTorrent, verifies hashes, and runs inference in its sandbox.
6. Providers send status and output over WebSocket. The coordinator validates output hashes, collects configured replicas, and accepts only a strict majority when multiple replicas are required.
7. If the operator enabled known-answer probes, a separate internal canary task may be queued. Its expected-output hash is checked coordinator-side; this MVP check is exact-output and runtime-sensitive.
8. The coordinator stores a limited Merkle commitment to replica reports, reassembles verified prompt outputs in order, awards demo provider credits, and tears down task swarms.
9. The portal shows task/chunk status, verification detail, downloadable results, and the demo credit ledger. System canary tasks are hidden from requestor history.

## Multi-PC local setup

Use the coordinator's private LAN IPv4 address in provider apps on other PCs, for example `ws://192.168.1.5:8001/ws/seeder`; `127.0.0.1` only points back to the same PC. Share the enrollment code only with intended volunteers. Bind required ports only on the trusted LAN and do not configure router port forwarding or a public domain for this development environment. Full steps are in [IMPLEMENTATION-SETUP.md](../IMPLEMENTATION-SETUP.md).

## Future work that is not simulated

- Trackerless libp2p data transfer: authenticated chunk protocol, relay-based file transfer, resumability, and tested fallback. Existing libp2p discovery/relay code does not move files.
- Full VeriLLM and robust canary architecture: hidden-state/pre-fill checks, sound challenge generation, peer prediction, collusion resistance, dispute handling, and measured security properties. Current Merkle records and known-answer probes are narrower MVP aids only.
- Internet-scale discovery/NAT traversal, multi-coordinator operation, multi-user authorization, and production incentives.

Do not describe these roadmap components as implemented. See [implementation status](IMPLEMENTATION-STATUS.md).
