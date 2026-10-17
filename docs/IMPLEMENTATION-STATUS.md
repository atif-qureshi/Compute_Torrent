# ComputeTorrent implementation status

This page separates working MVP code from roadmap architecture. A protocol name in the repository does not imply that the complete research protocol is implemented.

## Available in the local MVP

| Area | Current implementation |
|---|---|
| Submitter portal | Local operator sign-in, task submission, progress/history, verified-result download, credit ledger, provider list and credential revocation. |
| Coordinator | Central FastAPI control plane, provider enrollment/credentials, WebSocket assignments and status, model registry, prompt chunking and scheduling. |
| Provider desktop app | Windows Python UI, hardware profile, resource caps, pause/resume, reconnect, local contribution history, GGUF inference in a network-disabled Docker container, and PyInstaller packaging scripts. |
| Inference | Operator-provided GGUF model and optional adapter run through llama.cpp. Model/adapter files are hash-checked; model weights are not included. |
| File transport | Private WebTorrent swarms transfer model and prompt files. Configured tracker endpoints still provide WebRTC peer signalling; the provider validates final SHA-256 digests. |
| LAN overlay | libp2p Kademlia discovery and Circuit Relay v2 connection code runs separately and exposes peer connectivity. The overlay does not carry model/prompt files. |
| Result checks | Provider output hash validation and strict unique-provider replica output-hash majority, up to three replicas when available. One replica only provides a single reported result plus integrity checks. |
| Canary MVP | If an operator supplies exact expected-output hashes, the coordinator randomly schedules separate internal known-answer checks through the same worker queue/runtime and rejects mismatches. The private expected hash remains coordinator-side; provider failures accumulate toward quarantine. Canary jobs are not mixed into user prompts. |
| Audit receipt | Reports are committed before a fresh challenge nonce selects up to two distinct report openings. The Merkle report root and task, chunk, model, prompt, and verdict metadata are bound into a SHA-256 envelope. The API independently recomputes the challenge and inclusion proofs. This proves transcript consistency, not correct hidden-state inference. |
| Credits | Submitter requests cost one demo credit each; verified provider work can add demo credits. Credits have no cash value. |
| Deployment target | Local machine and trusted LAN during development. No public domain or public deployment is required. |
| Model Studio pilot | JSON/XML recipes for BLOOM/BLOOMZ 560M, pinned Hub revisions, RAM/VRAM-aware allocation of contiguous layers to two to eight opted-in providers, private Hivemind DHT routing, coordinator-side generation, token/boundary replay, a hidden canary, and per-job timing. The Petals image and model weights must be downloaded; a live multi-PC result requires connected provider machines. |
| Benchmark export | Optional coordinator CPU baseline for Model Studio jobs, fixed peer-count repeat runner, and prompt-free CSV/JSON export. Results exist only after real jobs complete. |

## Explicit future architecture work

- **Trackerless libp2p data plane:** transfer model/prompt chunks over authenticated libp2p protocols with relay-assisted fallback, resumption, access control, and measured multi-peer failure recovery. The existing LAN discovery/relay overlay is not a file-transfer implementation.
- **Full VeriLLM:** Model Studio captures and checks real stage activations against a trusted local replay, but per-layer provider-signed commitments, independent verifiers, indistinguishable inference/verification work, VRF/on-chain challenge and dispute contracts, and peer-prediction incentives remain absent. The proposal excludes blockchain. The GGUF output-report receipts also are not full VeriLLM proofs.
- **Production canary layer:** GGUF jobs have hidden exact-answer tasks and provider failure tracking. Model Studio sends a second undisclosed prompt through the assigned layer route and compares its tokens and every stage boundary with a coordinator replay. Stronger probe secrecy/rotation, collusion analysis, bounded recovery, and measured false-positive/false-negative rates remain future work.
- **Internet-scale volunteer network:** public discovery, NAT traversal strategy, operator identity, abuse response, and security review. Current setup is trusted-LAN only and must not be router-forwarded.
- **Multi-user service:** self-service accounts, per-user task ownership and authorization, organization isolation, and non-demo billing/incentives. Current portal uses one local operator login and a fixed requestor account.

These are future work, not simulated features. User-facing screens and documentation should describe only the narrow implemented behavior above.

## Local run path

Use the canonical local stack from the repository root. Replace every secret placeholder in `.env` with a unique private value before starting it:

```powershell
Copy-Item .env.example .env
.\Start-ComputeTorrent.ps1
# Once the large Petals runtime image is built:
.\Start-ComputeTorrent.ps1 -WithPetals
```

Open `http://localhost:3000`; use the provider app with `ws://127.0.0.1:8001/ws/seeder` on the coordinator machine. For additional trusted-LAN PCs, use the coordinator's private IP in the provider app and bind only the local portal/coordinator and libp2p ports to the LAN as described in [IMPLEMENTATION-SETUP.md](../IMPLEMENTATION-SETUP.md). Do not expose these services publicly.

Docker Desktop groups the current containers under `computetorrent-mvp`. The older stopped `computetorrent` group uses the standalone Compose file in `docker/`; it does not contain the running portal. `backend/`, `frontend/`, and `desktop/` are separate rebuilt source trees, not live links to the canonical numbered modules. Update them deliberately when maintaining the standalone stack.
