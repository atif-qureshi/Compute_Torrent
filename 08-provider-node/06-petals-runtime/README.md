# Petals distributed inference runtime

The local Compose stack runs a private Hivemind DHT and authenticated
generation gateway. The provider desktop app builds the pinned Petals runtime
image locally and starts a resource-limited worker container for each assigned
layer range. Upstream Petals hosts contiguous Transformer blocks, reports
throughput, keeps inference KV state, and routes hidden states.

## Portal workflow

From the repository root, start the local Compose stack with
`.\Start-ComputeTorrent.ps1 -WithPetals`, then open `http://localhost:3000/inference`. At
least two provider apps must be connected. On each, opt in to “Share model
layers” and install the CPU or NVIDIA runtime. Upload a JSON or XML manifest
using `bigscience/bloom-560m` or `bigscience/bloomz-560m`. `revision: "main"`
resolves to a fixed Hub commit before workers are assigned. Providers download
and cache weights automatically; the submitter does not handle weight files or
send its raw prompt to layer providers. The coordinator downloads weights too
for local reference verification, so it needs spare RAM and internet access.
This pilot runs one distributed job at a time with up to 128 output tokens.

Example JSON:

```json
{
  "model_id": "bigscience/bloomz-560m",
  "revision": "main",
  "prompt": "Explain volunteer computing in one sentence.",
  "max_new_tokens": 32,
  "min_peers": 2,
  "max_peers": 4,
  "benchmark": false
}
```

The XML format uses the same field names as flat child elements under
`<inference>`. The format validator rejects unknown fields, duplicate JSON keys,
XML entities and DTDs.

The provider app shows CPU, GPU, VRAM, RAM, operating system and disk capacity.
Only capacity metrics are reported; the app does not scan personal files.
Allow trusted LAN TCP ports 8001, 31330 and 31331. The coordinator's advertised
address must be its private LAN IPv4 address, not `127.0.0.1`.

Provider builds report network revision 2. Older apps remain visible but cannot
receive layer assignments until updated. Install the current ZIP on every PC,
close older app instances, then reconnect. The app checks a digest of its bundled
runtime and rebuilds an outdated Docker image automatically using Docker's cache.
Local coordinator providers use Docker Desktop's host alias; remote PCs keep
the coordinator LAN address and advertise their own LAN address.

Before downloading blocks, the worker performs a real libp2p handshake from
inside its Docker network. The gateway keeps its peer identity under
`runtime/petals-cache/petals/dht-identity.key` across restarts. A worker is marked
serving only when its Petals module container is ready and healthy. Failed jobs
stop every assigned peer; the portal preserves the failing peer's error.

## Verification boundary

The generation client commits real stage-boundary activations, chooses a fresh
challenge after the commitment, then compares every generated stage boundary
with a full local reference-model replay. A second random hidden canary prompt goes through the same peer layers
and local replay. A mismatch fails the job and does not receive a verified
result. The receipt labels this `local-boundary-replay-v1`; it is a
VeriLLM-inspired local check, not the complete on-chain VeriLLM protocol, a
blockchain settlement, or a dispute system. The local verifier is trusted and
uses numeric activation tolerances; the route and challenges are recorded in
the downloadable receipt.

`benchmark: true` also times a full-model CPU reference generation on the
coordinator. Use `min_peers` and `max_peers` with the same value to require an
exact provider count, and run `11-evaluation-benchmark/run_petals_experiment.py`
for repeated 2/4-peer jobs. `export_petals_runs.py` exports the measured job
records and group summaries without raw prompts. No speedup claim is made
unless both runs generated the same number of tokens.

Model Studio jobs appear in that page's job history and do not use the existing
GGUF task history or demo credits. Root `/api/tasks` continues to run the full
GGUF model on one provider.

## Manual upstream tools

`server.py` and `client.py` remain command-line tools for development outside
the portal path. Use Python 3.10+ in Linux or WSL2. Install a hardware-matched
PyTorch build and then `requirements-petals.txt`. Start the first node with
`--swarm-mode new`; join other nodes with its printed Petals DHT multiaddr.
The runtime's `public` mode joins the Petals public DHT. Other operators then
process prompt activations, so do not use it for private inputs.
