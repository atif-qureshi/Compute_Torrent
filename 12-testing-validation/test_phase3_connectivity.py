import asyncio
import datetime
import os
from pathlib import Path
import ssl
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed
from websockets.legacy.server import serve

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("orchestrator/app", "11-evaluation-benchmark", "08-provider-node/05-desktop-app-shell")]
import petals_relay_prototype as relay
from production_seeder import coordinator_endpoint


class CoordinatorTests(unittest.TestCase):
    def test_plaintext_is_only_allowed_on_local_endpoints(self):
        self.assertEqual(coordinator_endpoint("ws://192.168.1.2:8001/ws/seeder"),
                         ("ws", "192.168.1.2", 8001))
        self.assertEqual(coordinator_endpoint("wss://relay.example/ws/seeder")[2], 443)
        for url in ("ws://relay.example/ws/seeder", "wss://x@y.example/ws/seeder",
                    "wss://relay.example/ws/seeder?x=1"):
            with self.assertRaises(ValueError):
                coordinator_endpoint(url)

    def test_registration_ownership_lease_and_legacy_retirement(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN": "fixture-join",
            "COMPUTETORRENT_API_TOKEN": "fixture-api",
            "COMPUTETORRENT_JOB_DATA": root,
        }), patch("sqlalchemy.create_engine", side_effect=RuntimeError("isolated fixture")):
            import main_production as coordinator
            with patch.object(coordinator, "PROVIDER_HEARTBEAT_TIMEOUT", 1.0), TestClient(coordinator.app) as client:
                data = {"tier": 1, "profile": {}}
                def enroll(code):
                    return client.post("/api/seeders/enroll", json=data, headers={"X-Enrollment-Token": code})
                self.assertEqual(enroll("local-volunteer-join").status_code, 401)
                self.assertEqual(client.get("/api/provider-update/manifest").status_code, 410)
                result = enroll("fixture-join")
                self.assertEqual(result.status_code, 200)
                identity = result.json()
                headers = {"Authorization": "Bearer " + identity["access_token"]}
                message = {"type": "register", "node_id": identity["node_id"], **data}
                with client.websocket_connect("/ws/seeder", headers=headers) as first:
                    first.send_json(message)
                    self.assertEqual(first.receive_json()["type"], "register_ack")
                    with client.websocket_connect("/ws/seeder", headers={"Authorization": "Bearer wrong"}) as wrong:
                        wrong.send_json(message)
                        with self.assertRaises(WebSocketDisconnect) as denied:
                            wrong.receive_json()
                        self.assertEqual(denied.exception.code, 1008)
                    with client.websocket_connect("/ws/seeder", headers=headers) as duplicate:
                        duplicate.send_json(message)
                        self.assertEqual(duplicate.receive_json()["node_id"], identity["node_id"])
                        with self.assertRaises(WebSocketDisconnect) as replaced:
                            first.receive_json()
                        self.assertEqual(replaced.exception.code, 1000)
                        status = client.get("/api/seeders", headers={"Authorization": "Bearer fixture-api"}).json()
                        self.assertIsNotNone(status[0]["control_age_seconds"])
                        with self.assertRaises(WebSocketDisconnect) as stale:
                            duplicate.receive_json()
                        self.assertEqual(stale.exception.code, 1013)
                with client.websocket_connect("/ws/seeder", headers=headers) as reconnect:
                    reconnect.send_json(message)
                    self.assertEqual(reconnect.receive_json()["node_id"], identity["node_id"])


def tls_contexts(root):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(minutes=10))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = Path(root) / "cert.pem", Path(root) / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_path, key_path)
    return server, ssl.create_default_context(cafile=str(cert_path))


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_reverse_stream_and_role_authorization(self):
        async def echo(reader, writer):
            try:
                while payload := await reader.read(1024):
                    writer.write(payload)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        with tempfile.TemporaryDirectory() as root:
            server_tls, client_tls = tls_contexts(root)
            route = relay.Route("fixture", "ingress-secret", "worker-secret", time.monotonic() + 15, 512)
            broker = relay.Relay(route)
            async with await asyncio.start_server(echo, "127.0.0.1", 0) as destination:
                async with serve(broker.accept, "127.0.0.1", 0, ssl=server_tls, max_size=relay.CHUNK) as ws:
                    url = f"wss://localhost:{ws.sockets[0].getsockname()[1]}/fixture"
                    async with relay._connect(url + "/worker", "ingress-secret", client_tls) as wrong:
                        with self.assertRaises(ConnectionClosed) as denied:
                            await wrong.recv()
                        self.assertEqual(denied.exception.code, 1008)
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        async with relay._connect(url + "/worker", "worker-secret", ssl.create_default_context()):
                            self.fail("accepted an untrusted broker")
                    worker = asyncio.create_task(relay.worker(url + "/worker", "worker-secret", client_tls,
                                                                destination.sockets[0].getsockname()))
                    async def ingress(reader, writer):
                        try:
                            await relay.ingress(url + "/ingress", "ingress-secret", client_tls, reader, writer)
                        except ConnectionClosed as error:
                            self.assertEqual(error.rcvd.code, 1008)
                    try:
                        async with await asyncio.start_server(ingress, "127.0.0.1", 0) as listener:
                            reader, writer = await asyncio.open_connection(*listener.sockets[0].getsockname())
                            try:
                                writer.write(b"native tcp fixture")
                                await writer.drain()
                                self.assertEqual(await asyncio.wait_for(reader.readexactly(18), 5), b"native tcp fixture")
                                writer.write(b"x" * 500)
                                await writer.drain()
                                self.assertEqual(await asyncio.wait_for(reader.read(1), 5), b"")
                            finally:
                                writer.close()
                                await writer.wait_closed()
                        await asyncio.wait_for(worker, 5)
                    finally:
                        worker.cancel()
                        await asyncio.gather(worker, return_exceptions=True)
                    async with relay._connect(url + "/worker", "worker-secret", client_tls) as replay:
                        with self.assertRaises(ConnectionClosed) as denied:
                            await replay.recv()
                        self.assertEqual(denied.exception.code, 1008)


    async def test_unpaired_relay_expires_and_denies_late_worker(self):
        with tempfile.TemporaryDirectory() as root:
            server_tls, client_tls = tls_contexts(root)
            route = relay.Route("expiry", "ingress-secret", "worker-secret", time.monotonic() + 8, 512)
            broker = relay.Relay(route)
            async with serve(broker.accept, "127.0.0.1", 0, ssl=server_tls, max_size=relay.CHUNK) as ws:
                base = f"wss://localhost:{ws.sockets[0].getsockname()[1]}/expiry"
                async with relay._connect(base + "/ingress", route.ingress_token, client_tls) as waiting:
                    with self.assertRaises(ConnectionClosed) as expired:
                        await asyncio.wait_for(waiting.recv(), 12)
                    self.assertEqual(expired.exception.rcvd.reason, "Relay lease expired")
                async with relay._connect(base + "/worker", route.worker_token, client_tls) as late:
                    with self.assertRaises(ConnectionClosed) as denied:
                        await late.recv()
                    self.assertEqual(denied.exception.rcvd.code, 1008)


if __name__ == "__main__":
    unittest.main()
