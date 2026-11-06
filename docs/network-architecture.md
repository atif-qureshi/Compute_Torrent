# ComputeTorrent Phase 3 relay integration

This report extends the [Phase 2 design](network-design.md) and the [Phase 3 control-plane implementation](phase-3-connectivity.md). The experiment uses disposable Docker containers with no published ports and no external network. It does not change provider packaging, Compose, release settings, or production scheduling.

## Pinned runtime and actual paths

| Item | Observed implementation |
| --- | --- |
| Runtime | Cached CPU image `computetorrent-petals:local`, ID prefix `b8ab9a7b532b`. Installed Petals 2.3.0.dev2 at `22afba627a7eb4fcfe9418c49472c6a51334b8ac`, Hivemind 1.2.0.dev0 at `213bff98a62accb91f254e2afdccbf1d69ebdea9`, torch 2.2.2+cpu, Transformers 4.43.1. Verified image package metadata rather than inferring versions from tags. |
| Bootstrap and identity | `gateway.py` starts a Hivemind DHT on TCP 31331 with an identity file and an explicit announced multiaddress. `bootstrap_probe.py` checks an initial address including peer ID from inside the worker. `worker.py` validates its TCP announcements, and `layer_server.py` uses those addresses and reports the worker DHT peer ID. |
| Discovery and sessions | The coordinator assigns contiguous ranges under a job prefix. Petals workers announce served blocks in the DHT. `generate_job.py:execute` restricts eligible peer IDs, checks route coverage, and enters a Petals inference session per stage. This adapter invokes stage slices in sequence with the coordinator-side generation client passing hidden states between them. It does not enable a direct worker-to-worker activation path. |
| Native relay | The installed Hivemind P2P API supports `use_relay`, `use_auto_relay`, `trusted_relays` and forced reachability. The Petals server API has relay reachability options. The current gateway, worker and bootstrap probe explicitly disable native relay/AutoNAT/NAT mapping for the trusted LAN path. The separate JS overlay and WebTorrent service are not the Petals activation transport. |
| Custom WSS relay | Carries native TCP bytes through TLS-verified outbound streams with authenticated one-use role tickets. Hivemind still authenticates the bootstrap peer ID. The lab allocates one bounded stream pair per incoming TCP connection. It does not modify libp2p framing, peer IDs or Petals. A deployable connector still needs authenticated control and mapped listener/announcement paths in both directions. |

**Recommendation.** Keep direct TCP as the baseline and retain the custom bridge as an experimental fallback. The pinned runtime exposes native relay support, but a loopback fixture with a forced-public candidate and a forced-private peer using that trusted candidate did not announce a circuit within 12 seconds. This is inconclusive for real NAT and does not establish native incompatibility. Prove native reservations, reachability, and inference under a genuinely separated topology before deciding whether custom operational complexity is necessary. The custom bridge currently supports a single stream pair with close on EOF. Test TCP half-close and multiple simultaneous streams before relying on it for stage traffic.

## Isolated measurements and model attempt

Host Windows 10, Intel x64, four logical CPUs. Docker Engine reported four CPUs and about 7.7 GiB RAM. The experiment was limited to two CPUs and 3 GiB RAM. Both transport paths ran on loopback within one Linux container using `--network none`. Custom WSS used a disposable certificate, certificate/hostname verification and the host's read-only websockets 13.1 Python package. Each run started a direct DHT, then a proxied DHT. The same seed key was reopened across paths. Each path queried five unique records written before its client joined, with successful retrieval of each exact record. The relay byte count increased after bootstrap, confirming DHT traffic during the lookup interval.

| Trial | Path | Bootstrap to ready | Median DHT lookup | Lookup success | TCP payload forwarded by WSS broker |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Direct | 520.49 ms | 14.23 ms | 5/5 | — |
| 1 | Custom WSS | 733.49 ms | 15.29 ms | 5/5 | 12,008 bytes, 2,660 after bootstrap |
| 2 | Direct | 510.03 ms | 10.88 ms | 5/5 | — |
| 2 | Custom WSS | 888.49 ms | 25.43 ms | 5/5 | 10,706 bytes, 2,660 after bootstrap |
| Native probe | Circuit relay | Unmeasured | Unmeasured | No circuit advertised in the fixture | — |

Both direct and custom paths bootstrapped in two of two local trials. These timings include daemon/DHT work and do not represent wire RTT. Counts are forwarded payload, not TLS or framing overhead. The sample is too small for a performance claim. Sustained throughput, wire overhead, long-session stability, activation latency, inference completion and tokens/sec remain unmeasured.

The runner attempted an offline load of `bigscience/bloom-560m` with Transformers in the pinned image. The cache contains config/tokenizer metadata and an incomplete download, but neither `model.safetensors` nor `pytorch_model.bin` was resolvable. The installed loader raised `AttributeError` on a missing archive path. The runner reports the missing weight state and exits 2. It did not launch model workers, advertise real blocks, submit a coordinator job, or produce inference output. The DHT fixture records are transport evidence only.

## Reproduction

Run from the repository root on a machine with the cached image, a local model cache and a compatible Python websockets package. The following command creates only a disposable, network-disabled container and mounts inputs read-only.

```powershell
$ws = python -c "import pathlib,websockets; print(pathlib.Path(websockets.__file__).parent)"
docker run --rm --network none --cpus 2 --memory 3g `
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e HF_HOME=/cache/huggingface `
  -e PYTHONPATH=/opt/ct-fixture `
  --mount "type=bind,source=$ws,target=/opt/ct-fixture/websockets,readonly" `
  --mount "type=bind,source=$((Resolve-Path 11-evaluation-benchmark).Path),target=/smoke,readonly" `
  --mount "type=bind,source=$((Resolve-Path runtime/petals-cache).Path),target=/cache,readonly" `
  --entrypoint timeout computetorrent-petals:local 140s python -B /smoke/smoke_pinned_petals_relay.py
```

## Next validation matrix

1. Stage a complete, approved model checkpoint pinned to its immutable revision. Use a separate isolated coordinator/gateway, fresh test credentials and two worker instances with complementary ranges. Require two registration acknowledgements, two expected runtime identities, complete DHT coverage, and real inference plus the current boundary and canary checks. Keep the existing production-oriented smoke pointed at its current target until a separately isolated endpoint configuration is provided.
2. Prove each route from container network namespaces before involving remote devices. For native relay require an actual circuit reservation/address and independently confirm traffic traverses it. For custom WSS require worker-to-bootstrap and gateway-to-worker routes, matching identities, no alternate direct path during the relay run, and clean expiry/disconnect. Test slow consumer/backpressure, TCP half-close and concurrent stage streams before integration.
3. Repeat the same manifest on two same-Wi-Fi PCs, separate LANs, distinct ISP links, CGNAT, restrictive firewall/proxy, and a controlled unstable link. Record route selection and reachability from the containers. For disconnect during inference, record stage, lease cleanup, terminal job state, and whether a fresh request succeeds. Do not assume in-session failover. Use only authorized networks and no router or public relay changes without separate approval.
4. Use matching model/revision, device limits, prompt/context, verification policy and cache state across runs. Measure attempts and successes, connect time, transport RTT, steady throughput, bytes on the wire, activation transfer latency, first token and total duration, tokens/sec, reconnect time and failures. Record sample count and network conditions for each direct, native and custom route.

The standalone `backend/app/main.py` still fails Python parsing at the block near lines 1003–1004. The canonical coordinator is `orchestrator/app/main_production.py`, so the standalone issue does not block this isolated harness or the canonical integration plan. No change was made to that backend.
