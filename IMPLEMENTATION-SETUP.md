# ComputeTorrent implementation and setup

This repository contains a local GGUF workflow and a separate Petals model-parallel pilot for small BLOOM models, managed from the portal and Windows provider app.

## Run locally (no domain or public deployment)

From the repository root, create a private environment file and set unique values for every secret before starting the stack:

```powershell
Copy-Item .env.example .env
```

Replace the secret placeholders with unique private values, then start Docker Desktop. Start only the local profile:

```powershell
.\Start-ComputeTorrent.ps1
```

Open `http://localhost:3000` and sign in with `COMPUTETORRENT_PORTAL_PASSWORD`. Docker Desktop groups this canonical stack as `computetorrent-mvp`; the older stopped `computetorrent` group came from `docker/docker-compose.yml`. The coordinator API is at `http://127.0.0.1:8001`; PostgreSQL and swarm administration stay loopback-only. The first GGUF task creates a demo balance of 100 credits and each task costs 1 credit. This command does not start Caddy or require a DNS name.

## Run a small model across provider PCs

Start the optional gateway with `.\Start-ComputeTorrent.ps1 -WithPetals`, then open `http://localhost:3000/inference`. Connect at least two provider PCs, enable “Share model layers”, and install each provider's CPU Petals runtime. Providers with NVIDIA GPUs can install the separate CUDA runtime. Upload JSON or XML with `model_id` set to `bigscience/bloom-560m` or `bigscience/bloomz-560m`, plus a prompt and optional `max_new_tokens` (1–128) and `min_peers` (2–8). `revision: "main"` resolves to a fixed Hugging Face commit before workers start. Model weights download and cache automatically on providers; submitters do not download model files. The coordinator also needs internet access and spare RAM to download the model for reference verification. For trusted LAN providers, configure the coordinator's private IPv4 address as described below and allow TCP ports 8001, 31330 and 31331 in Windows Firewall. Keep `127.0.0.1` only for a single-PC setup. Model Studio runs use their own job history and verification receipts, separate from GGUF task history and credits. See [Petals runtime details](docs/PETALS-PAPER-IMPLEMENTATION.md).

## Connect volunteer computers on your local network

For a single computer, leave the default loopback settings. For computers on the same trusted LAN, find the coordinator computer's private IPv4 address (for example `192.168.1.5`) and set these values in `.env`:

```dotenv
COMPUTETORRENT_BIND_IP=0.0.0.0
COMPUTETORRENT_LIBP2P_BIND_IP=0.0.0.0
COMPUTETORRENT_LIBP2P_ADVERTISE_HOST=192.168.1.5
```

Recreate the local stack with `docker compose -f docker-compose.local.yml up --build -d`. Allow TCP ports 8001 and 9100 only on the private LAN in Windows Firewall. Do not port-forward them on your router. In each desktop provider app, enter `ws://192.168.1.5:8001/ws/seeder` and the enrollment code. The provider joins the coordinator's libp2p LAN discovery/relay overlay, which reports peer connectivity but does not transfer task files. Model and prompt files still use configured WebTorrent peers and tracker signalling. Each provider receives its own revocable credential. Never share the portal password or API token with volunteers. The portal's copy-address helper uses its current browser host; when opened on localhost, replace that address with the coordinator's private LAN IP on other PCs.

WebTorrent tracker endpoints need outbound connectivity for peer signalling; LAN control connectivity does not remove that dependency. Private swarms restrict intended membership, and downloaded content is SHA-256 checked, but trackerless file transport is not implemented yet. See [network-layer status](07-network-layer/README.md).

The enrollment code is a network join secret. Share it only with people you intend to invite; rotate it by changing `COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN` and recreating the orchestrator. Existing providers retain their individual credentials. This LAN setup intentionally has no public domain, router forwarding, or public deployment step.

## Register a model

Start the stack first, then register an operator-approved `.gguf` file:

```powershell
python orchestrator\app\register_model.py qwen-small D:\models\model.gguf --label "Qwen small"
```

Registration hashes the source, copies it into `runtime/swarm/models/`, seeds a model WebTorrent swarm, and atomically updates `orchestrator/app/models.json`. The loopback-only swarm control port lets this host-side command seed assets without exposing swarm administration to the internet. The portal discovers registered models without a restart. Keep the model's distribution license and provenance with your operator records; this repository does not bundle model weights.

For a compatible GGUF LoRA adapter, add `--adapter D:\models\adapter.gguf`; the model and adapter are delivered together and both hashes are checked before the runtime applies the adapter. The limited canary MVP accepts an operator-owned JSON suite with known prompt/expected-output pairs using `--canary-suite D:\models\canaries.json`. The expected-output hash stays coordinator-side; an eligible provider receives a separate internal canary task containing the probe prompt. `COMPUTETORRENT_CANARY_PERCENT` controls how often a user submission may trigger a probe (default 10%). Validate exact outputs against the same model, seed, runtime, and token limit before enabling these checks. Robust canary security and full VeriLLM verification remain future architecture work; see [implementation status](docs/IMPLEMENTATION-STATUS.md).

## Run a seeder

Build the Windows package from PowerShell:

```powershell
cd 08-provider-node\05-desktop-app-shell
.\build_installer.ps1
```

The build requires Python, Node.js, npm, and network access to install build dependencies. The resulting `dist\ComputeTorrent-Seeder-Installer.zip` contains the executable and install/uninstall scripts. On a provider machine, extract the archive and run `Install-ComputeTorrent.ps1`. Docker Desktop must be installed and running. The first assigned task pulls the pinned-by-configuration llama.cpp image if it is not already present; model files are fetched from their WebTorrent swarm and checked against the manifest SHA-256 before inference.

The app stores connection settings, its per-device credential, recent contribution history, and resource limits under `%LOCALAPPDATA%\ComputeTorrent`. The one-time enrollment code is held in memory and is not saved in provider settings. The app also starts a local libp2p peer while connected and stops it when the app closes. Provider resource use can be bounded from onboarding and new assignments can be paused while an active task completes. To re-enroll a revoked PC, remove its node in the portal, close the desktop app, delete `%LOCALAPPDATA%\ComputeTorrent\seeder-settings.json`, then reopen the app and enter the join code again. The libp2p Kademlia DHT/Circuit Relay overlay is not a trackerless file-transfer path: model/prompt files still use WebTorrent WebRTC tracker signalling. Full trackerless libp2p data transfer is future work. Private magnet URIs act as bearer capabilities, so distribute them only to intended peers.

## How task execution works

Each input prompt is an independent, ordered chunk. The orchestrator sends chunk content over a task-specific WebTorrent swarm, while WebSocket carries assignments and status. Providers verify downloaded payload, model, and optional adapter hashes, then run llama.cpp in a disposable Docker container with network disabled, a read-only model mount, resource limits, and a temporary output mount. CPU work uses `ghcr.io/ggml-org/llama.cpp:light`; `COMPUTETORRENT_LLAMA_IMAGE` can select another compatible image. CUDA work uses `ghcr.io/ggml-org/llama.cpp:full-cuda` with `--gpus all`; GPU providers need a working NVIDIA container runtime, and `COMPUTETORRENT_LLAMA_CUDA_IMAGE` can select a compatible build. See the [llama.cpp Docker instructions](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md) and [CLI options](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md).

At submission, the orchestrator requests up to three replicas based on connected, hardware-eligible providers. WS-RR rotates work across capable idle providers; CC-BP prefers the highest-capacity provider meeting the requested RAM/GPU constraints. SERENE-lite compares exact output SHA-256 values and accepts a strict majority; disagreement fails closed. If enabled by the operator, a randomly selected fraction of submissions may create a separate internal canary task from the registered model's known-answer suite. A mismatch receives no provider credit and increments that provider's canary failure count. This narrow exact-output diagnostic requires deterministic runtime behavior and is not a full robust canary layer. The VeriLLM-inspired receipt commits provider/output/canary reports in a Merkle tree and includes sampled inclusion paths; it does not implement hidden-state prefill verification, sound VRFs, peer-prediction incentives, or a dispute protocol. Full VeriLLM/canary architecture remains future work, not a simulated feature. With one eligible provider, replica verification is only a single-result integrity check. Results and chunk progress appear in Task history; the Credits page shows demo ledger entries. Provider credits are demonstration accounting only, not redeemable value.

## Operational limits

- The local Compose profile provides an operator password session, server-side API authentication, per-provider credentials, and a LAN discovery/relay overlay. The portal currently has one operator account and one fixed requestor ledger identifier, not public self-service user registration or per-customer billing.
- The compose file binds model/swarm data to `runtime/swarm`; back up that directory and the PostgreSQL volume.
- The libp2p overlay serves peer discovery/relay connectivity only; it does not carry files or make this LAN setup reachable over the public internet. P2P file transfer still depends on WebTorrent peer connectivity and its configured tracker signalling. Remote use needs separate network planning.
- Exact-output replication can reject valid outputs when different inference hardware or runtime versions produce different tokens. Model/runtime pinning and replica agreement reduce, but do not eliminate, this risk.
- The installer packages the seeder application; Docker Desktop remains a provider prerequisite.
