# ComputeTorrent implementation and setup

This repository now contains an end-to-end MVP path for local GGUF inference, WebTorrent delivery, independent prompt chunks, replica comparison, requestor credits/history, and a Windows seeder package.

## Run locally (no domain or public deployment)

From the repository root, create a private environment file and set unique values for every secret before starting the stack:

```powershell
Copy-Item .env.example .env
```

Replace the secret placeholders with unique private values, then start Docker Desktop. Start only the local profile:

```powershell
docker compose -f docker-compose.local.yml up --build
```

Open `http://localhost:3000` and sign in with `COMPUTETORRENT_PORTAL_PASSWORD`. The coordinator API is at `http://127.0.0.1:8001`; PostgreSQL and swarm administration stay loopback-only. The first task creates a demo balance of 100 credits and each task costs 1 credit. This command does not start Caddy or require a DNS name.

## Connect volunteer computers on your local network

For a single computer, leave the default loopback settings. For computers on the same trusted LAN, find the coordinator computer's private IPv4 address (for example `192.168.1.5`) and set these values in `.env`:

```dotenv
COMPUTETORRENT_BIND_IP=0.0.0.0
COMPUTETORRENT_LIBP2P_BIND_IP=0.0.0.0
COMPUTETORRENT_LIBP2P_ADVERTISE_HOST=192.168.1.5
```

Recreate the local stack with `docker compose -f docker-compose.local.yml up --build -d`. Allow TCP ports 8001 and 9100 only on the private LAN in Windows Firewall. Do not port-forward them on your router. In each desktop provider app, enter `ws://192.168.1.5:8001/ws/seeder` and the enrollment code. The app fetches the coordinator's libp2p bootstrap address, joins the private Kademlia DHT, and requests a Circuit Relay v2 reservation. This network overlay is for peer discovery and relay; model/prompt files continue to use the configured WebTorrent peers. Each provider receives its own revocable credential. Never share the portal password or API token with volunteers.

The enrollment code is a network join secret. Share it only with people you intend to invite; rotate it by changing `COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN` and recreating the orchestrator. Existing providers retain their individual credentials. This LAN setup intentionally has no public domain, router forwarding, or public deployment step.

## Register a model

Start the stack first, then register an operator-approved `.gguf` file:

```powershell
python orchestrator\app\register_model.py qwen-small D:\models\model.gguf --label "Qwen small"
```

Registration hashes the source, copies it into `runtime/swarm/models/`, seeds a model WebTorrent swarm, and atomically updates `orchestrator/app/models.json`. The loopback-only swarm control port lets this host-side command seed assets without exposing swarm administration to the internet. The portal discovers registered models without a restart. Keep the model's distribution license and provenance with your operator records; this repository does not bundle model weights.

For a compatible GGUF LoRA adapter, add `--adapter D:\models\adapter.gguf`; the model and adapter are delivered together and both hashes are checked before the runtime applies the adapter. To enable hidden worker spot checks, supply an operator-owned JSON suite with prompt/expected-output pairs using `--canary-suite D:\models\canaries.json`. Only expected output hashes are stored in the manifest; the suite's plaintext answers remain on the coordinator. `COMPUTETORRENT_CANARY_PERCENT` controls how often tasks receive a probe (default 10%). Validate canary answers against the exact registered model, seed, runtime and output token limit before enabling them.

## Run a seeder

Build the Windows package from PowerShell:

```powershell
cd 08-provider-node\05-desktop-app-shell
.\build_installer.ps1
```

The build requires Python, Node.js, npm, and network access to install build dependencies. The resulting `dist\ComputeTorrent-Seeder-Installer.zip` contains the executable and install/uninstall scripts. On a provider machine, extract the archive and run `Install-ComputeTorrent.ps1`. Docker Desktop must be installed and running. The first assigned task pulls the pinned-by-configuration llama.cpp image if it is not already present; model files are fetched from their WebTorrent swarm and checked against the manifest SHA-256 before inference.

The app stores connection settings, its per-device credential, recent contribution history, and resource limits under `%LOCALAPPDATA%\ComputeTorrent`. It also starts a local libp2p peer while connected and stops it when the app closes. Provider resource use can be bounded from the onboarding screen and new assignments can be paused while an active task completes. To re-enroll a revoked PC, remove its node in the portal, close the desktop app, delete `%LOCALAPPDATA%\ComputeTorrent\seeder-settings.json`, then reopen the app and enter the join code again. Model transfer still uses WebTorrent WebRTC trackers; the libp2p Kademlia DHT and circuit relay provide LAN peer discovery and relay connectivity. The swarms are private and magnet URIs act as bearer capabilities, so distribute them only to intended peers.

## How task execution works

Each input prompt is an independent, ordered chunk. The orchestrator sends chunk content over a task-specific WebTorrent swarm, while WebSocket carries assignments and status. Providers verify downloaded payload, model, and optional adapter hashes, then run llama.cpp in a disposable Docker container with network disabled, a read-only model mount, resource limits, and a temporary output mount. CPU work uses `ghcr.io/ggml-org/llama.cpp:light`; `COMPUTETORRENT_LLAMA_IMAGE` can select another compatible image. CUDA work uses `ghcr.io/ggml-org/llama.cpp:full-cuda` with `--gpus all`; GPU providers need a working NVIDIA container runtime, and `COMPUTETORRENT_LLAMA_CUDA_IMAGE` can select a compatible build. See the [llama.cpp Docker instructions](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md) and [CLI options](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md).

At submission, the orchestrator requests up to three replicas based on currently connected providers. WS-RR rotates work across capable idle providers; CC-BP prefers the highest-capacity provider meeting the requested RAM/GPU constraints. SERENE-lite compares exact output SHA-256 values and accepts a strict majority; disagreement fails closed. For a randomly selected fraction of requests, the coordinator also queues a private, normal-looking canary job from the registered model's operator-provided suite. Its expected output stays on the coordinator; mismatches receive no credit and count toward provider quarantine after three failures. The VeriLLM-inspired audit commits provider/output/canary reports in a Merkle tree, then records post-result random samples and inclusion paths in task history. This is an auditable transcript, not VeriLLM's full hidden-state prefill verification, VRF, peer-prediction incentives, or dispute protocol. With one eligible provider, replica verification is still only a single-result integrity check. Results and chunk progress appear in Task history; the Credits page shows demo ledger entries. Provider credits are demonstration accounting only, not redeemable value.

## Operational limits

- The local Compose profile provides an operator password session, server-side API authentication, per-provider credentials, a private LAN DHT and a libp2p circuit relay. The portal currently has one operator account and one fixed requestor ledger identifier, not public self-service user registration or per-customer billing.
- The compose file binds model/swarm data to `runtime/swarm`; back up that directory and the PostgreSQL volume.
- The libp2p relay serves the private coordinator network. It does not make this LAN setup reachable over the public internet; remote use needs separate network planning. P2P file transfer still depends on WebTorrent peer connectivity.
- Exact-output replication can reject valid outputs when different inference hardware or runtime versions produce different tokens. Model/runtime pinning and replica agreement reduce, but do not eliminate, this risk.
- The installer packages the seeder application; Docker Desktop remains a provider prerequisite.
