# Petals distributed inference runtime

This is the project's real Petals-compatible model-parallel execution path.
It launches the upstream Petals block server and generation client. Petals
servers announce contiguous Transformer block ranges, measure throughput,
rebalance block ownership, keep inference KV state, and route hidden states.
This is separate from ComputeTorrent's existing GGUF/WebTorrent full-model
provider path; the GGUF format is not used by Petals.

## Requirements

- Python 3.10 or newer, preferably Linux or WSL2. Upstream Petals documents
  Windows use through WSL.
- Install a hardware-appropriate PyTorch build, then install
  `requirements-petals.txt` in a dedicated environment on each serving PC.
- Use one identical, Petals-supported Hugging Face model id and revision on all
  peers. The model weights are downloaded by Petals and are not included here.
- Open the chosen TCP listen port between trusted machines. Public swarm mode
  exposes requests to unrelated operators; do not send private prompts to it.

## Start a private swarm on the coordinator/first provider

```powershell
python server.py --model bigscience/bloom-560m --swarm-mode new --port 31330 --device auto
```

Keep this process running. Copy the Petals DHT multiaddr printed during startup
from its logs. Other providers join the same `--model` and must bootstrap with
that address:

```powershell
python server.py --model bigscience/bloom-560m --swarm-mode join --initial-peer "/ip4/COORDINATOR-LAN-IP/tcp/31330/p2p/PEER_ID" --port 31330 --device auto
```

Petals chooses block ranges according to available memory and its measured
throughput. `--num-blocks` can cap a node's contribution. The model must have
enough total eligible memory across peers to provide a complete block chain.
Use `--swarm-mode public` to join Petals' public DHT; this is not the same as a
private ComputeTorrent network.

## Run inference through those peers

```powershell
python client.py --model bigscience/bloom-560m --initial-peer "/ip4/COORDINATOR-LAN-IP/tcp/31330/p2p/PEER_ID" --prompt "Explain distributed computing in one paragraph." --max-new-tokens 64
```

The generation client keeps tokenization/sampling local and requests each
generation step from the Petals-distributed model. Petals chooses a live route
and reports it in client logs. Upstream Petals handles session KV caches,
throughput-based rebalancing, and retry/rerouting behavior.

## Current project boundary

These scripts are a separate real Petals runtime; they do not yet connect to
the portal's `/api/tasks` or ComputeTorrent's provider WebSocket. Do not mark a
portal task as Petals-distributed until a gateway, model catalog, task receipts,
and end-to-end result persistence are connected. The current portal's GGUF
workflow remains single-provider inference. Petals server/client security and
privacy inherit upstream behavior; public peers can process prompt activations.
