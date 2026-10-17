# Petals paper implementation map

ComputeTorrent's Model Studio is a local, small-model Petals pilot. Its gateway
runs a private Hivemind DHT, the coordinator assigns contiguous Transformer
blocks to enrolled provider PCs according to their reported free RAM/VRAM, and
the generation client sends hidden states through those blocks for every token.
The user uploads JSON or XML model details; model weights download and cache on
the provider PCs and on the coordinator's trusted reference verifier.

## Current flow

1. The portal sends the recipe to `/api/distributed/jobs` through its authenticated proxy.
2. The coordinator validates the model ID and pins its Hugging Face revision to a commit.
3. It allocates all 24 BLOOM blocks to at least two opted-in, runtime-ready providers.
4. The provider app starts one resource-limited Petals block server per assigned range.
5. The private gateway runs token generation through the reported peer route.
6. A trusted local reference model replays the generated sequence and compares
   every generated token's stage-boundary activation. An undisclosed short canary
   runs through the same route and replay. Failed checks do not yield a verified result.
7. The job, route, timings, result, and off-chain receipt appear in Model Studio.

The GGUF `/api/tasks` route is a separate workflow. It assigns independent
prompts, not model layers. Its WebTorrent transport currently uses tracker
signalling; Petals uses its own Hivemind DHT for model-layer routing.

## Relation to the Petals paper

| Paper behavior | Local implementation |
|---|---|
| Consecutive model blocks on different peers | Explicit contiguous layer allocation and upstream Petals block servers |
| Resource-aware placement | Conservative CPU/GPU memory budget from provider heartbeats |
| DHT discovery and routed hidden states | Private upstream Hivemind DHT and Petals remote sequences |
| Per-session KV cache | Upstream Petals inference sessions |
| Client-side tokenizer and output head | Gateway generation client |
| Throughput-driven balancing and fast churn recovery | Not yet measured or implemented by the coordinator; a lost peer fails the job and requires resubmission |
| Quantized serving | The pilot uses FP32 with no tensor compression so local replay is comparable |

The proposal asks for blockchain-free verification. The receipt therefore
records a local activation commitment, a post-commit challenge, full trusted
reference replay, and a hidden canary. It does not implement VeriLLM's public
chain, VRF, peer-prediction incentives, or dispute contracts. Trust in the
coordinator and its reference model remains an explicit assumption.

## Running

From the repository root use `.\Start-ComputeTorrent.ps1 -WithPetals`. On each
provider, install its hardware-matched Petals runtime in the desktop app and
turn on layer sharing. The coordinator's advertised private IPv4 address and
LAN TCP port 31331 must be reachable from the provider PCs. Provider block
servers use TCP port 31330. The first image build and first model download can
be large. The generated provider installer bundles the runtime build recipes,
not model weights.

A successful model-parallel claim requires a completed local job with at least
two actual provider PCs, its route, and a passing receipt. Source compilation
and the existence of a job screen alone do not establish that result.
