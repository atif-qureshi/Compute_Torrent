# Petals paper implementation map

This records the boundary between the attached paper's design, the separate
upstream Petals runtime, and the portal's existing independent-prompt workflow.
Petals model parallelism routes each token's hidden state through consecutive
Transformer blocks hosted by different peers.

## Paper requirements and project status

| Petals behavior | Current project state |
|---|---|
| Servers host contiguous model blocks sized for their resources | `08-provider-node/06-petals-runtime/server.py` launches upstream Petals, which chooses and serves resource-sized block ranges. Not wired to the ComputeTorrent provider desktop app. |
| Joining servers target weak-throughput blocks and ranges stay contiguous | Upstream Petals manages its DHT placement and rebalancing. `05-allocator-churn/layer_planner.py` is an unused planning helper. |
| Servers measure and publish compute/network throughput | Upstream Petals does this in its DHT; current ComputeTorrent heartbeats report only basic provider metrics. |
| Client selects a low-latency layer route | `client.py` calls upstream Petals' distributed generation client. The local beam-search helper is not involved. |
| Client tokenizes/samples locally while peers execute model blocks | Implemented by the separate Petals generation client, not by the existing `/api/tasks` endpoint. |
| Servers retain inference sessions/KV cache | Managed by upstream Petals block servers; ComputeTorrent's existing provider WebSocket has no activation/session protocol. |
| Client recovers from peer failure | Upstream Petals routing/retry behavior is used by the client; ComputeTorrent's existing retries remain prompt-chunk retries only. |
| Quantized weights and compressed hidden states | Petals server wrapper exposes upstream quantization and tensor-compression options. These options do not affect the GGUF runner. |
| Verify intermediate layer outputs | Not implemented. Existing output hashes/replicas do not verify hidden-state activations. |

## Runtime boundary and model format

The Petals entrypoints are in
[`08-provider-node/06-petals-runtime/`](../08-provider-node/06-petals-runtime/).
They use upstream Petals and its Hivemind DHT; the project's libp2p/WebTorrent
network is not a Petals DHT. Providers need a Petals-supported Hugging Face
Transformer checkpoint and compatible hardware/runtime. The current Qwen2.5
GGUF is for single-provider llama.cpp and cannot be loaded by the Petals block
server as-is.

The upstream Petals server chooses block ranges and reports throughput. For a
private home network, start one node with `--swarm-mode new`, then join the
printed DHT multiaddr from other trusted nodes. The `public` mode joins the
public Petals DHT, where other operators process activations and may recover
prompt content. Never send secrets to a public swarm.

The Petals runtime is not yet connected to the portal's `/api/tasks`, model
catalog, ComputeTorrent enrollment credentials, history/results, or credits.
Only generation launched through the Petals client is distributed Petals
inference; the portal's current full-model Docker task must not be labeled so.

## Remaining integration work

1. Add a Petals model catalog with architecture, revision, license and hardware
   estimates, separate from the GGUF manifest.
2. Add an authenticated local gateway that submits requests to Petals and
   persists route/model/result receipts into task history.
3. Add provider desktop controls and private DHT bootstrap address exchange;
   keep one-time enrollment credentials separate from DHT addresses.
4. Add activation integrity challenges and per-layer verification. Current
   output hashes, replicas and canaries do not verify intermediate tensors.
5. Exercise a complete multi-PC inference and failover run using the actual
   machines and model before calling portal integration complete.
