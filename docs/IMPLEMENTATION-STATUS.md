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
| Result checks | Provider output hash validation and strict replica output-hash majority, up to three replicas when available. One replica only provides a single reported result plus integrity checks. |
| Canary MVP | If an operator supplies exact expected-output hashes, the coordinator can schedule a separate internal known-answer task and reject a mismatch. It is not injected into each user's real task. |
| Audit receipt | The coordinator stores a Merkle commitment to replica reports and exposes sampled inclusion proofs. This is an output transcript commitment, not proof of hidden-state inference. |
| Credits | Submitter requests cost one demo credit each; verified provider work can add demo credits. Credits have no cash value. |
| Deployment target | Local machine and trusted LAN during development. No public domain or public deployment is required. |

## Explicit future architecture work

- **Trackerless libp2p data plane:** transfer model/prompt chunks over authenticated libp2p protocols with relay-assisted fallback, resumption, access control, and measured multi-peer failure recovery. The existing LAN discovery/relay overlay is not a file-transfer implementation.
- **Full VeriLLM:** hidden-state or prefill verification, sound challenge generation, peer-prediction incentives, dispute flow, and protocol-specific trust assumptions. Current Merkle receipts are only inspired output records.
- **Production canary layer:** stronger probe secrecy and rotation, cross-runtime tolerances, collusion analysis, bounded retries, and measured false-positive/false-negative rates. Current exact-hash canaries are a narrow MVP diagnostic.
- **Internet-scale volunteer network:** public discovery, NAT traversal strategy, operator identity, abuse response, and security review. Current setup is trusted-LAN only and must not be router-forwarded.
- **Multi-user service:** self-service accounts, per-user task ownership and authorization, organization isolation, and non-demo billing/incentives. Current portal uses one local operator login and a fixed requestor account.

These are future work, not simulated features. User-facing screens and documentation should describe only the narrow implemented behavior above.

## Local run path

Use the canonical local stack from the repository root. Replace every secret placeholder in `.env` with a unique private value before starting it:

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.local.yml up --build -d
```

Open `http://localhost:3000`; use the provider app with `ws://127.0.0.1:8001/ws/seeder` on the coordinator machine. For additional trusted-LAN PCs, use the coordinator's private IP in the provider app and bind only the local portal/coordinator and libp2p ports to the LAN as described in [IMPLEMENTATION-SETUP.md](../IMPLEMENTATION-SETUP.md). Do not expose these services publicly.

`backend/`, `frontend/`, and `desktop/` are separate rebuilt source trees, not live links to the canonical numbered modules. Update them deliberately when maintaining the standalone stack.
