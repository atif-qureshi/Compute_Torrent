# ComputeTorrent

ComputeTorrent is a local volunteer-computing proof of concept. The portal supports independent GGUF prompt jobs and a separate small-model Petals pilot that assigns consecutive Transformer layers to connected provider PCs. The coordinator tracks results, local verification, and demo credits for GGUF jobs.

## Local development

This project is intended to run locally or across a trusted LAN while it is being developed. No domain or public deployment is required.

1. Copy `.env.example` to `.env` and replace every secret placeholder with private values.
2. Start Docker Desktop and run `.\Start-ComputeTorrent.ps1` from this folder. Docker Desktop shows the current stack under `computetorrent-mvp`; the stopped `computetorrent` group belongs to the older standalone Compose file under `docker/`.
3. Open `http://localhost:3000` and sign in with the password from `COMPUTETORRENT_PORTAL_PASSWORD`.
4. Register an operator-approved GGUF model after the stack is running:

   ```powershell
   python orchestrator/app/register_model.py qwen-small D:\models\model.gguf --label "Qwen small"
   ```

5. Build the provider package with `08-provider-node/05-desktop-app-shell/build_installer.ps1`. Install it on this PC or other trusted LAN computers and connect them to the coordinator's private WebSocket address.
6. For Model Studio, run `.\Start-ComputeTorrent.ps1 -WithPetals`. Each provider must opt in to layer sharing and install its CPU or NVIDIA Petals runtime in the desktop app. The first build and model download require substantial time and disk space.

The stack and provider workflow are documented in [IMPLEMENTATION-SETUP.md](IMPLEMENTATION-SETUP.md). The local infrastructure scripts are in `infrastructure/`.

## Implemented MVP features

- GGUF inference through llama.cpp in a network-disabled, resource-limited Docker container. Model and adapter files are hash-checked before use; model weights must be supplied by the operator.
- Per-task private WebTorrent transfers for prompts and models, with SHA-256 checks and provider-side progress reporting.
- Independent prompt slicing, WS-RR and CC-BP provider selection, unique-provider replica agreement, private known-answer canary jobs, and challenged VeriLLM-inspired output-report receipts with checkable Merkle proofs.
- Portal task submission, task history, verified results, download, and requestor credit ledger pages.
- Windows provider app, enrollment, resource controls, local work history, and PyInstaller packaging scripts.
- Local Compose setup for the portal, coordinator, swarm service, and PostgreSQL, with loopback defaults and optional trusted-LAN bindings.
- Model Studio JSON/XML recipe upload, pinned small BLOOM model revisions, layer allocation across at least two enrolled providers, job history, local boundary replay, hidden canary checks, and measured generation timings. This path requires the optional Petals gateway image and ready provider runtimes.

## Architecture and source trees

The numbered modules are the canonical implementation. The separately requested `backend/`, `frontend/`, and `desktop/` folders are independent copies derived from those modules; changes in one tree do not automatically update the other. `docker/docker-compose.yml` builds the standalone backend and frontend copies, while `docker-compose.local.yml` builds the canonical numbered modules. Choose one Compose stack at a time because they share local ports and container names.

| Path | Role |
|---|---|
| `01-submitter-portal/` | Canonical Next.js requestor portal |
| `orchestrator/` | Canonical FastAPI coordinator and model registration |
| `04-task-slicer-scheduler/` | Prompt chunking and scheduling metadata |
| `06-verification-engine/` | MVP hash, replica, canary, and challenged transcript receipt checks; full VeriLLM/canary trust architecture is future work |
| `07-network-layer/` | WebTorrent file transfer plus a separate libp2p LAN discovery/relay overlay |
| `08-provider-node/` | Canonical provider desktop app and packaging |
| `08-provider-node/06-petals-runtime/` | Separate real Petals block-server and distributed-generation client |
| `backend/`, `frontend/`, `desktop/` | Separate rebuilt application trees |
| `infrastructure/`, `docker/` | Local stack helpers and separate Compose/Docker files |
| `docs/` | Architecture, flow, contracts, decisions, and research notes |

## Limits to keep clear

- The portal's `/api/tasks` workflow runs independent GGUF prompt batches. Model Studio runs Petals layer jobs with separate history and verification receipts; a live multi-PC run still requires ready provider machines and model downloads.
- WebTorrent currently transfers model and prompt files through configured WebRTC tracker signalling. The libp2p LAN overlay supports discovery/relay connectivity only; trackerless libp2p file transfer remains future architecture work.
- GGUF replica agreement and known-answer canary jobs are local MVP checks. Model Studio replays generated tokens and provider layer boundaries against a trusted local reference model and runs a hidden canary. The proposal excludes blockchain; this off-chain check does not claim the public VeriLLM protocol's chain-backed incentives or disputes.
- Exact-output comparison may reject valid outputs across different runtimes or hardware. A single provider does not provide replica agreement.
- Credits are demo accounting with no monetary value. The portal currently has a single operator login and a fixed requestor account.
- Model weights are not included. Their license, provenance, size, and suitability are the operator's responsibility.
- See [implementation status](docs/IMPLEMENTATION-STATUS.md) for a concise boundary between working components and future architecture work.
