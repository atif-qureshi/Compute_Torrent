"""Pinned Petals server adapter with an explicit, truthful readiness signal."""
import json
import signal
import threading
import time
from pathlib import Path


def emit(**state):
    print("CT_STATUS " + json.dumps(state), flush=True)


def serve(request):
    from hivemind.proto.runtime_pb2 import CompressionType
    from petals.server.server import Server
    from petals.utils.convert_block import QuantType

    spec, stage = request["spec"], request["stage"]
    server = None

    def stop(*_):
        if server is None:
            raise SystemExit(0)
        server.stop.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server = Server(
            initial_peers=request["bootstrap"], dht_prefix=request["prefix"],
            converted_model_name_or_path=spec["model_id"], revision=spec["revision"],
            block_indices=f"{stage['start']}:{stage['end']}", device=stage["device"],
            torch_dtype="float32", quant_type=QuantType.NONE, compression=CompressionType.NONE,
            host_maddrs=["/ip4/0.0.0.0/tcp/31330"], announce_maddrs=request["advertise_maddrs"],
            # These are directly published trusted-LAN ports. Do not attempt to
            # discover public relays or run the public-swarm reachability probe.
            reachable_via_relay=False, use_relay=False, use_auto_relay=False,
            auto_nat=False, nat_port_map=False, startup_timeout=30,
            inference_max_length=512, attn_cache_tokens=1024, num_handlers=2,
            max_disk_space=8 * 1024**3, throughput="auto", balance_quality=0,
            update_period=10,
        )
        emit(status="loading", peer_id=str(server.dht.peer_id))

        def monitor():
            previous = None
            while not server.stop.is_set():
                container = server.module_container
                ready = container is not None and container.ready.is_set() and container.is_healthy()
                status = "serving" if ready else "loading"
                if status != previous:
                    emit(status=status, peer_id=str(server.dht.peer_id))
                    previous = status
                time.sleep(1)

        threading.Thread(target=monitor, daemon=True).start()
        server.run()
    finally:
        if server is not None:
            server.shutdown()


if __name__ == "__main__":
    serve(json.loads(Path("/state/request.json").read_text()))
