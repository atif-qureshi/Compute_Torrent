"""Real TLS/TCP relay tests and explicit direct/fallback selection checks."""
import asyncio
from contextlib import suppress
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.legacy.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("08-provider-node/06-petals-runtime", "orchestrator/app")]
import relay_transport as transport
import route_selection
from worker import layer_failure
import control_routes
from test_phase3_connectivity import tls_contexts


class SelectionTests(unittest.TestCase):
    def test_legacy_bare_bootstrap_does_not_force_lan_into_relay(self):
        address = "/ip4/192.168.100.7/tcp/31331/p2p/Qm" + "a" * 44
        direct = Mock(return_value=True)
        relay = Mock(side_effect=AssertionError("LAN must not use relay"))
        selected, handle = route_selection.prepare_route(dict(
            bootstrap=[address.rsplit("/p2p/", 1)[0], address],
            advertise_maddrs=["/ip4/192.168.100.8/tcp/31330"], relay={"fixture": True}),
            direct_probe=direct, relay_factory=relay)
        self.assertEqual(direct.call_args.kwargs["initial_peers"], [address])
        self.assertEqual(selected["transport"], "direct")
        self.assertIsNone(handle)
        relay.assert_not_called()
        with self.assertRaisesRegex(ValueError, "identity-qualified"):
            route_selection.prepare_route(dict(bootstrap=["/ip4/192.168.100.7/tcp/31331"]))

    def test_layer_failure_preserves_exception_and_redacts_credentials(self):
        error, tail = layer_failure(1, ["Traceback (most recent call last):\n",
            "TypeError: unsupported TinyLlama configuration Bearer secret hf_abc123\n"])
        self.assertIn("TypeError", error)
        self.assertIn("TinyLlama", error)
        self.assertNotIn("secret", error + tail)
        self.assertNotIn("hf_abc123", error + tail)

    def test_positive_lan_probe_precedes_relay_and_unknown_uses_relay(self):
        request = dict(bootstrap=["/ip4/192.168.1.2/tcp/31331/p2p/Qm" + "a" * 44],
            advertise_maddrs=["/ip4/192.168.1.3/tcp/31330"], relay={"advertise_maddrs": ["/ip4/127.0.0.1/tcp/40000"]})
        factory = Mock(return_value=SimpleNamespace(start=Mock(), stop=Mock(),
                              client=SimpleNamespace(bootstrap_port=12345)))
        direct, handle = route_selection.prepare_route(request, direct_probe=lambda **_: True,
                                                      relay_factory=factory)
        self.assertEqual(direct["transport"], "direct")
        self.assertIsNone(handle)
        factory.assert_not_called()
        relayed, handle = route_selection.prepare_route(request, direct_probe=lambda **_: None,
                                                       relay_factory=factory)
        self.assertEqual(relayed["transport"], "wss")
        self.assertIn("/tcp/12345/p2p/", relayed["bootstrap"][0])
        handle.start.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "reverse reachability"):
            route_selection.prepare_route({**request, "network_policy": "direct"},
                                           direct_probe=lambda **_: False)

    def test_endpoint_selection_proves_identity_and_falls_back_on_network_change(self):
        primary, lan = "wss://coordinator.example/ws/seeder", "ws://192.168.1.2:8001/ws/seeder"
        key = hashlib.sha256(b"fixture").hexdigest()
        def valid(url, nonce):
            return {"proof": control_routes.proof(key, "ct-endpoint-v1", nonce, url)}
        self.assertEqual(control_routes.select_endpoint(primary, [primary, lan], "node", "fixture", valid), lan)
        def switched(url, nonce):
            if url == lan:
                raise ConnectionRefusedError()
            return valid(url, nonce)
        self.assertEqual(control_routes.select_endpoint(primary, [lan, primary], "node", "fixture", switched), primary)
        self.assertEqual(control_routes.select_endpoint(primary, [lan], "node", "fixture",
                         lambda *_: {"proof": "forged"}), primary)
        with self.assertRaises(ValueError):
            control_routes.candidates(["ws://untrusted.example/ws/seeder"])


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_bidirectional_concurrent_streams_half_close_and_revocation(self):
        async def echo(reader, writer):
            try:
                payload = await reader.read()
                writer.write(payload[::-1])
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        with tempfile.TemporaryDirectory() as folder:
            server_tls, client_tls = tls_contexts(Path(folder))
            gateway = await asyncio.start_server(echo, "127.0.0.1", 0)
            worker_target = await asyncio.start_server(echo, "127.0.0.1", 0)
            broker = transport.Broker("wss://localhost:1/ws/petals-relay",
                gateway=("127.0.0.1", gateway.sockets[0].getsockname()[1]), max_leases=1)
            listener = await transport.serve_broker(broker, "127.0.0.1", 0, tls=server_tls)
            broker.public_url = f"wss://localhost:{listener.sockets[0].getsockname()[1]}/ws/petals-relay"
            lease = await broker.create("job", "node")
            worker = transport.Worker(lease, tls=client_tls,
                target=("127.0.0.1", worker_target.sockets[0].getsockname()[1]))
            task = asyncio.create_task(worker.run())
            try:
                await asyncio.wait_for(worker.ready.wait(), 5)
                with self.assertRaisesRegex(ValueError, "capacity"):
                    await broker.create("other", "other")
                with self.assertRaises(ConnectionClosed):
                    async with connect(lease["url"], ssl=client_tls,
                        extra_headers={"Authorization": "Bearer " + lease["token"]}) as replay:
                        await replay.recv()
                broker_port = broker.leases[lease["id"]]["listener"].sockets[0].getsockname()[1]
                async def roundtrip(port, index):
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    data = bytes([index]) * (256 * 1024 + index)
                    try:
                        writer.write(data)
                        await writer.drain()
                        writer.write_eof()
                        self.assertEqual(await asyncio.wait_for(reader.read(), 10), data[::-1])
                    finally:
                        writer.close()
                        await writer.wait_closed()
                await asyncio.gather(*(roundtrip(worker.bootstrap_port if i % 2 else broker_port, i)
                                       for i in range(8)))
                await broker.revoke(lease["id"])
                await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)
                self.assertFalse(broker.leases)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await broker.close()
                listener.close()
                await listener.wait_closed()
                gateway.close()
                worker_target.close()
                await gateway.wait_closed()
                await worker_target.wait_closed()

    async def test_tls_auth_expiry_and_frame_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            server_tls, client_tls = tls_contexts(Path(folder))
            broker = transport.Broker("wss://localhost:1/ws/petals-relay")
            listener = await transport.serve_broker(broker, "127.0.0.1", 0, tls=server_tls)
            broker.public_url = f"wss://localhost:{listener.sockets[0].getsockname()[1]}/ws/petals-relay"
            lease = await broker.create("job", "node")
            try:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    await transport.Worker(lease).run()
                with self.assertRaises(ConnectionClosed):
                    async with connect(lease["url"], ssl=client_tls,
                        extra_headers={"Authorization": "Bearer wrong"}) as denied:
                        await denied.recv()
                async with connect(lease["url"], ssl=client_tls,
                    extra_headers={"Authorization": "Bearer " + lease["token"]}) as ws:
                    self.assertEqual(await ws.recv(), b"CT_RELAY_1")
                    await ws.send(b"bad")
                    with self.assertRaises(ConnectionClosed):
                        await ws.recv()
                expired = await broker.create("job", "node")
                broker.leases[expired["id"]]["deadline"] = 0
                with self.assertRaises(ConnectionClosed):
                    async with connect(expired["url"], ssl=client_tls,
                        extra_headers={"Authorization": "Bearer " + expired["token"]}) as ws:
                        await ws.recv()
                await broker.expire()
                self.assertFalse(broker.leases)
                with self.assertRaises(ValueError):
                    transport.Broker("ws://localhost/ws/petals-relay")
            finally:
                await broker.close()
                listener.close()
                await listener.wait_closed()


class ControlProofTests(unittest.TestCase):
    def test_actual_coordinator_challenge_and_endpoint_identity(self):
        spec = importlib.util.spec_from_file_location("relay_control_fixture", ROOT / "orchestrator/app/main_production.py")
        control = importlib.util.module_from_spec(spec)
        lan = "ws://192.168.1.2:8001/ws/seeder"
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "COMPUTETORRENT_PROVIDER_ENDPOINTS": json.dumps([lan]), "COMPUTETORRENT_JOB_DATA": folder,
            "COMPUTETORRENT_API_TOKEN": "fixture-api", "COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN": "fixture-join"}), \
                patch("sqlalchemy.create_engine", side_effect=RuntimeError("isolated fixture")):
            spec.loader.exec_module(control)
            with TestClient(control.app) as client:
                identity = client.post("/api/seeders/enroll", json={"tier": 1, "profile": {}},
                                       headers={"X-Enrollment-Token": "fixture-join"}).json()
                node = identity["node_id"]
                key = hashlib.sha256(identity["access_token"].encode()).hexdigest()
                nonce = "a" * 64
                response = client.post("/api/network/identity", json=dict(node_id=node, nonce=nonce, endpoint=lan))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["proof"], control_routes.proof(key, "ct-endpoint-v1", nonce, lan))
                with client.websocket_connect("/ws/seeder") as ws:
                    ws.send_json(dict(type="auth_challenge", node_id=node, nonce=nonce))
                    challenge = ws.receive_json()
                    self.assertEqual(challenge["proof"], control_routes.proof(key, "ct-server-v1", nonce, challenge["nonce"], node))
                    message = dict(type="register", node_id=node, tier=1, profile={})
                    message["proof"] = control_routes.proof(key, "ct-register-v1", nonce,
                        challenge["nonce"], control_routes.register_digest(message))
                    ws.send_json(message)
                    self.assertEqual(ws.receive_json()["coordinator_endpoints"], [lan])
                with client.websocket_connect("/ws/seeder") as replay:
                    replay.send_json(dict(type="auth_challenge", node_id=node, nonce=nonce))
                    replay.receive_json()
                    replay.send_json(message)
                    with self.assertRaises(WebSocketDisconnect) as denied:
                        replay.receive_json()
                    self.assertEqual(denied.exception.code, 1008)


if __name__ == "__main__":
    unittest.main()
