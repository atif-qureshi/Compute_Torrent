"""Offline two-worker real Petals inference over the integrated WSS byte relay.

Uses a tiny randomly initialized BLOOM checkpoint, not a pretrained model or
real CGNAT. Run only inside a disposable, network-disabled pinned CPU container.
"""
import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def worker_main(request_path):
    from petals.server.server import Server
    from petals.utils.convert_block import QuantType
    from hivemind.proto.runtime_pb2 import CompressionType
    request = json.loads(Path(request_path).read_text())
    server = Server(initial_peers=request["bootstrap"], dht_prefix="ct-relay-offline",
        converted_model_name_or_path=request["model"], block_indices=request["blocks"],
        device="cpu", torch_dtype="float32", quant_type=QuantType.NONE,
        compression=CompressionType.NONE, host_maddrs=[f"/ip4/127.0.0.1/tcp/{request['port']}"],
        announce_maddrs=request["announce"], reachable_via_relay=True,
        use_relay=False, use_auto_relay=False, auto_nat=False, nat_port_map=False,
        skip_reachability_check=True, inference_max_length=32, attn_cache_tokens=128,
        num_handlers=1, throughput=1.0, balance_quality=0, update_period=2)
    Path(request_path + ".peer").write_text(str(server.dht.peer_id))
    try:
        server.run()
    finally:
        server.shutdown()


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def main():
    import torch
    from transformers import BloomConfig, BloomForCausalLM, LlamaConfig, LlamaForCausalLM
    from petals import AutoDistributedModelForCausalLM
    from hivemind import DHT
    from relay_transport import Broker, Worker, serve_broker
    from smoke_pinned_petals_relay import tls_fixture
    torch.set_num_threads(1)
    torch.manual_seed(123)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        architecture = os.getenv("CT_FIXTURE_MODEL", "bloom")
        layer_count = int(os.getenv("CT_FIXTURE_LAYERS", "2"))
        if layer_count not in {2, 4}:
            raise ValueError('Fixture supports two or four blocks')
        model_path = root / ("tiny-" + architecture)
        if architecture == "llama":
            reference = LlamaForCausalLM(LlamaConfig(hidden_size=64, intermediate_size=128,
                num_hidden_layers=layer_count, num_attention_heads=4, num_key_value_heads=2,
                max_position_embeddings=64, vocab_size=64, bos_token_id=1, eos_token_id=2, pad_token_id=0)).eval()
        elif architecture == "bloom":
            reference = BloomForCausalLM(BloomConfig(hidden_size=64, n_layer=layer_count, n_head=4,
                vocab_size=64, bos_token_id=1, eos_token_id=2, pad_token_id=0)).eval()
        else:
            raise ValueError("Fixture architecture must be bloom or llama")
        reference.save_pretrained(model_path, safe_serialization=False)
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from tokenizers.pre_tokenizers import Whitespace
        from transformers import PreTrainedTokenizerFast
        vocabulary = {f"t{i}": i for i in range(64)}
        tokenizer = Tokenizer(WordLevel(vocabulary, unk_token="t0"))
        tokenizer.pre_tokenizer = Whitespace()
        PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="t0", bos_token="t1",
            eos_token="t2", pad_token="t0").save_pretrained(model_path)
        # Petals BLOOM block loading uses its distributed config's block prefix;
        # local Transformers LM checkpoints also keep the transformer.* wrapper.
        from petals.utils.auto_config import AutoDistributedConfig
        prefix = AutoDistributedConfig.from_pretrained(str(model_path)).block_prefix
        weights = reference.state_dict()
        weights.update({prefix + key[len("transformer.h"):]: value
                        for key, value in list(weights.items()) if key.startswith("transformer.h.")})
        torch.save(weights, model_path / "pytorch_model.bin")
        from capacity_probe import measure
        capacity = measure(dict(spec=dict(model_id=str(model_path), revision="main"),
                                device="cpu", cpu_limit=1, memory_gb=5))
        assert capacity["block_bytes"] > 0 and capacity["capacity_layers"] == layer_count and capacity["inference_rps"] > 0, capacity
        print("CT_NATIVE_CAPACITY " + json.dumps(capacity), flush=True)
        sun_fixture = os.getenv('CT_FIXTURE_SUN') == '1'
        if sun_fixture:
            sys.path.insert(0, '/work/orchestrator/app')
            from sun_optimizer import Server as PlanningServer, cg_block_placement, shortest_route
            # Controlled memory caps and link costs are fixture inputs, NOT
            # measurements of physical heterogeneous peers or claimed speedups.
            caps = [layer_count-1, max(1,layer_count//2)]
            candidates = [PlanningServer(f'fixture-{i}', caps[i]*(capacity['block_bytes']+capacity['cache_bytes_per_block']),
                capacity['block_bytes'],capacity['cache_bytes_per_block'],1/capacity['inference_rps'],{'fixture-client':.01}) for i in range(2)]
            hosting = cg_block_placement(candidates,layer_count)
            route = shortest_route(candidates,hosting,layer_count,'fixture-client',min_nodes=2)
            ranges = [(stage.start,stage.end) for stage in route.stages]
            route_nodes = [stage.node_id for stage in route.stages]
        else:
            midpoint = layer_count//2
            ranges = [(0,midpoint),(midpoint,layer_count)]
            route_nodes = ['fixture-0','fixture-1']
        async with AsyncExitStack() as stack:
            seed = DHT(start=True, host_maddrs=["/ip4/127.0.0.1/tcp/0"],
                use_relay=False, use_auto_relay=False, auto_nat=False, nat_port_map=False)
            stack.callback(seed.shutdown)
            seed_addr = str(seed.get_visible_maddrs()[0])
            seed_peer = str(seed.peer_id)
            seed_port = int(seed_addr.split("/tcp/")[1].split("/")[0])
            server_tls, client_tls = tls_fixture(root)
            broker = Broker("wss://localhost:1/ws/petals-relay", gateway=("127.0.0.1", seed_port))
            stack.push_async_callback(broker.close)
            listener = await stack.enter_async_context(await serve_broker(broker, "127.0.0.1", 0, tls=server_tls))
            broker.public_url = f"wss://localhost:{listener.sockets[0].getsockname()[1]}/ws/petals-relay"
            peers = []
            processes = []
            for index in range(2):
                lease = await broker.create("fixture", f"worker-{index}")
                port = free_port()
                connector = Worker(lease, tls=client_tls, target=("127.0.0.1", port))
                task = asyncio.create_task(connector.run())
                async def stop_task(task=task):
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                stack.push_async_callback(stop_task)
                await asyncio.wait_for(connector.ready.wait(), 10)
                request_path = root / f"worker-{index}.json"
                request_path.write_text(json.dumps(dict(model=str(model_path), blocks=f"{ranges[index][0]}:{ranges[index][1]}",
                    port=port, announce=lease["advertise_maddrs"],
                    bootstrap=[f"/ip4/127.0.0.1/tcp/{connector.bootstrap_port}/p2p/{seed_peer}"])))
                log = stack.enter_context((root / f"worker-{index}.log").open("w+"))
                process = subprocess.Popen([sys.executable, __file__, "worker", str(request_path)], stdout=log, stderr=log)
                processes.append((process, log))
                def terminate(process=process):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                stack.callback(terminate)
                for _ in range(90):
                    if Path(str(request_path) + ".peer").exists():
                        peers.append(Path(str(request_path) + ".peer").read_text())
                        break
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError("Worker failed: " + log.read()[-5000:])
                    await asyncio.sleep(1)
                else:
                    log.seek(0)
                    raise RuntimeError("Worker startup timeout: " + log.read()[-5000:])

            def infer():
                model = AutoDistributedModelForCausalLM.from_pretrained(str(model_path),
                    initial_peers=[seed_addr], dht_prefix="ct-relay-offline", torch_dtype=torch.float32,
                    allowed_servers=peers, max_retries=2, request_timeout=30)
                model.eval()
                remote = model.transformer.h if hasattr(model, "transformer") else model.model.layers
                try:
                    for attempt in range(60):
                        try:
                            remote.sequence_manager.make_sequence(mode="min_latency")
                            break
                        except Exception:
                            if attempt == 59:
                                raise
                            remote.sequence_manager.update(wait=False)
                            time.sleep(1)
                    tokens = torch.tensor([[1, 5, 9]])
                    with torch.inference_mode():
                        expected = reference.generate(tokens, max_new_tokens=3, do_sample=False)
                        actual = model.generate(tokens, max_new_tokens=3, do_sample=False)
                    assert torch.equal(actual, expected), (actual, expected)
                    return actual.tolist()
                finally:
                    remote.sequence_manager.shutdown()
                    remote.sequence_manager.dht.shutdown()
            before = sum(2**30 - route["mux"].remaining for route in broker.leases.values())
            try:
                tokens = await asyncio.wait_for(asyncio.to_thread(infer), 150)
            except BaseException:
                for process, log in processes:
                    log.flush()
                    log.seek(0)
                    print(log.read()[-7000:], flush=True)
                raise
            from generate_job import execute
            job = dict(id="1" * 32, bootstrap=[seed_addr], prefix="ct-relay-offline",
                spec=dict(model_id=str(model_path), revision="main", prompt="t1 t5 t9",
                          max_new_tokens=5 if sun_fixture else 3, benchmark=False),
                plan=[dict(node_id=route_nodes[i], peer_id=peer, start=ranges[i][0], end=ranges[i][1], device="cpu")
                      for i, peer in enumerate(peers)])
            production = await asyncio.wait_for(asyncio.to_thread(execute, job,
                lambda status: print("CT_JOB " + status, flush=True)), 120)
            assert production["status"] == "completed", production
            assert production["receipt"]["canary"]["passed"], production
            timings = production['metrics'].get('stage_rpc_timings',[])
            assert timings and all(row['seconds'] > 0 for row in timings), 'Missing actual stage timing data'
            assert {row['node_id'] for row in timings} == set(route_nodes)
            assert any(row['phase']=='decode' for row in timings)
            after = sum(2**30 - route["mux"].remaining for route in broker.leases.values())
            assert after > before, "No native inference traffic traversed WSS"
            print("CT_INTEGRATED_RELAY " + json.dumps(dict(status="passed", worker_peers=peers,
                layers=layer_count, optimizer_fixture=sun_fixture, ranges=ranges, rpc_samples=len(timings),
                planner_link_inputs="controlled fixture" if sun_fixture else "not used", tokens=tokens, post_startup_payload_bytes=after-before,
                checkpoint="random tiny " + architecture, production_pipeline=production["status"],
                canary=production["receipt"]["canary"]["passed"], real_cgnat=False)), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker_main(sys.argv[2])
    else:
        asyncio.run(main())
