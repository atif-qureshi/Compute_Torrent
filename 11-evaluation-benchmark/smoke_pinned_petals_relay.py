"""Offline integration check for the pinned Petals image, with no published ports."""
import asyncio
from contextlib import AsyncExitStack
import datetime as dt
import json
from pathlib import Path
import secrets
import ssl
import statistics
import tempfile
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from hivemind import DHT
from hivemind.p2p import P2P
from huggingface_hub import try_to_load_from_cache
from transformers import AutoModelForCausalLM
from websockets.legacy.server import serve

from petals_relay_prototype import Relay, Route, ingress, worker


def tls_fixture(folder):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(minutes=10))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_path, key_path)
    return server, ssl.create_default_context(cafile=str(cert_path))


async def start_dht(stack, **kwargs):
    peer = DHT(start=False, host_maddrs=["/ip4/127.0.0.1/tcp/0"], auto_nat=False,
               nat_port_map=False, startup_timeout=20, **kwargs)
    peer.run_in_background(await_ready=False)
    stack.callback(peer.shutdown)
    await asyncio.to_thread(peer.wait_until_ready, 30)
    return peer


async def exercise(relayed, folder):
    options = dict(use_relay=False, use_auto_relay=False)
    async with AsyncExitStack() as stack:
        seed = await start_dht(stack, identity_path=str(folder / "seed.key"), **options)
        seed_address = str(seed.get_visible_maddrs()[0])
        _, _, host, _, port, _, peer_id = seed_address.split("/")
        assert host == "127.0.0.1" and peer_id == str(seed.peer_id)
        brokers = {}
        route_tasks = set()
        if relayed:
            server_tls, client_tls = tls_fixture(folder)

            async def dispatch(socket, path):
                broker = brokers.get(path.split("/")[1])
                if broker is None:
                    await socket.close(code=1008)
                else:
                    await broker.accept(socket, path)

            listener = await stack.enter_async_context(
                serve(dispatch, "127.0.0.1", 0, ssl=server_tls, max_size=64 * 1024)
            )
            relay_port = listener.sockets[0].getsockname()[1]

            async def accept(reader, writer):
                task = asyncio.current_task()
                route_tasks.add(task)
                route = Route(secrets.token_hex(8), secrets.token_urlsafe(24),
                              secrets.token_urlsafe(24), time.monotonic() + 60, 16 * 1024 * 1024)
                brokers[route.route_id] = Relay(route)
                url = f"wss://localhost:{relay_port}/{route.route_id}"
                try:
                    await asyncio.gather(ingress(url + "/ingress", route.ingress_token, client_tls, reader, writer),
                                         worker(url + "/worker", route.worker_token, client_tls, (host, int(port))))
                finally:
                    route_tasks.discard(task)

            async def cancel_routes():
                for task in tuple(route_tasks):
                    task.cancel()
                await asyncio.gather(*tuple(route_tasks), return_exceptions=True)

            stack.push_async_callback(cancel_routes)
            proxy = await stack.enter_async_context(await asyncio.start_server(accept, "127.0.0.1", 0))
            proxy_port = proxy.sockets[0].getsockname()[1]
            seed_address = f"/ip4/127.0.0.1/tcp/{proxy_port}/p2p/{peer_id}"

        records = {"ct-isolated-" + secrets.token_hex(8): {"fixture": i, "range": [0, 1]}
                   for i in range(5)}
        for key, value in records.items():
            assert await asyncio.to_thread(seed.store, key, value, time.time() + 60)
        started = time.perf_counter()
        client = await start_dht(stack, initial_peers=[seed_address], **options)
        bootstrap_ms = (time.perf_counter() - started) * 1000
        initial_bytes = sum(b.route.byte_limit - b.remaining for b in brokers.values())
        samples = []
        for key, value in records.items():
            started = time.perf_counter()
            result = await asyncio.to_thread(client.get, key, latest=True)
            samples.append((time.perf_counter() - started) * 1000)
            assert result and result.value == value
        total = sum(b.route.byte_limit - b.remaining for b in brokers.values())
        if relayed:
            assert total > initial_bytes > 0, "no native DHT traffic traversed the WSS relay after bootstrap"
        return {"seed_peer": peer_id, "bootstrap_ms": round(bootstrap_ms, 2),
                "dht_lookup_median_ms": round(statistics.median(samples), 2),
                "lookups": len(samples), "relay_payload_bytes": total, "post_bootstrap_relay_bytes": total - initial_bytes}


async def probe_native_relay():
    options = dict(use_relay=True, auto_nat=False, nat_port_map=False, startup_timeout=10)
    public = await P2P.create(force_reachability="public", **options)
    try:
        seed = await public.get_visible_maddrs()
        remote = await P2P.create(initial_peers=seed, trusted_relays=seed, use_auto_relay=True,
                                  force_reachability="private", **options)
        try:
            for _ in range(12):
                addresses = await remote.get_visible_maddrs()
                circuit = next((addr for addr in addresses if "/p2p-circuit" in str(addr)), None)
                if circuit is not None:
                    client = await P2P.create(initial_peers=[circuit], **options)
                    try:
                        connected = any(peer.peer_id == remote.peer_id for peer in await client.list_peers())
                        return {"status": "connected" if connected else "peer_not_found"}
                    finally:
                        await client.shutdown()
                await asyncio.sleep(1)
            return {"status": "no_circuit_announced", "observation_seconds": 12}
        finally:
            await remote.shutdown()
    finally:
        await public.shutdown()


async def main():
    with tempfile.TemporaryDirectory() as root:
        direct = await exercise(False, Path(root))
        proxied = await exercise(True, Path(root))
        assert direct["seed_peer"] == proxied["seed_peer"], "persistent bootstrap identity changed"
        print("CT_TRANSPORT " + json.dumps({"direct": direct, "custom_wss": proxied}), flush=True)
    print("CT_NATIVE_RELAY " + json.dumps(await probe_native_relay()), flush=True)
    model = "bigscience/bloom-560m"
    try:
        AutoModelForCausalLM.from_pretrained(model, local_files_only=True)
    except (OSError, AttributeError) as error:
        weights = {name: isinstance(try_to_load_from_cache(model, name), str)
                   for name in ("model.safetensors", "pytorch_model.bin")}
        if isinstance(error, AttributeError) and any(weights.values()):
            raise
        print("CT_MODEL_LOAD " + json.dumps({"status": "blocked", "model": model,
              "cached_weights": weights, "error": str(error)}), flush=True)
        return 2
    print("CT_MODEL_LOAD " + json.dumps({"status": "weights_loaded", "model": model}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
