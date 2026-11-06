import asyncio
import json
from pathlib import Path
import ssl
import sys
import threading
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from websockets.legacy.server import serve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "08-provider-node/05-desktop-app-shell"))
from production_seeder import ComputeTorrentSeeder, connection_failure, normalize_coordinator_address


def fixture_app(url):
    app = SimpleNamespace(orchestrator_url=url, node_id="fixture-peer", access_token="fixture-token",
                          enrollment_token="", is_connected=False, shutting_down=False,
                          disconnect_requested=threading.Event(), websocket=None,
                          current_task=None, connection_note="", states=[],
                          profile=dict(tier=2, GPU=None, VRAM=0, CUDA=False, gpu_count=0,
                                       gpu_devices=[], RAM=8, cpu_cores=4, docker_ok=False))
    def state(name, message):
        app.connection_note = message
        app.states.append(name)
    async def message(_):
        pass
    async def heartbeat(_):
        await asyncio.Future()
    app.set_connection_state = state
    app.handle_message = message
    app.send_heartbeats = heartbeat
    app.start_libp2p_peer = lambda: None
    app.watch_control_close = MethodType(ComputeTorrentSeeder.watch_control_close, app)
    return app


class OnboardingTests(unittest.TestCase):
    def test_address_shorthand_and_security(self):
        self.assertEqual(normalize_coordinator_address("192.168.0.5"), "ws://192.168.0.5:8001/ws/seeder")
        self.assertEqual(normalize_coordinator_address("localhost"), "ws://localhost:8001/ws/seeder")
        self.assertEqual(normalize_coordinator_address("192.168.0.5:9001"), "ws://192.168.0.5:9001/ws/seeder")
        self.assertEqual(normalize_coordinator_address("https://coord.example/"), "wss://coord.example/ws/seeder")
        for value in ("", "http://coord.example", "wss://user@coord.example",
                      "https://coord.example/api", "https://coord.example?token=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_coordinator_address(value)

    def test_actionable_nonretryable_errors_do_not_display_raw_details(self):
        error = HTTPError("https://coord.example", 401, "secret fixture", None, None)
        message, retry = connection_failure(error)
        self.assertFalse(retry)
        self.assertIn("Join code rejected", message)
        self.assertNotIn("secret fixture", message)
        self.assertFalse(connection_failure(URLError(ssl.SSLCertVerificationError()))[1])
        self.assertTrue(connection_failure(ConnectionRefusedError())[1])

    def test_pause_leaves_active_worker_running(self):
        app = SimpleNamespace(paused=False, current_task="Petals: fixture", petals=Mock(),
                              pause_btn=Mock(), update_status=Mock(), websocket=None)
        ComputeTorrentSeeder.toggle_pause(app)
        self.assertTrue(app.paused)
        app.petals.stop.assert_not_called()
        self.assertIn("current task will finish", app.update_status.call_args.args[0])


    def test_disconnect_and_quit_explain_active_work_guard(self):
        app = SimpleNamespace(paused=False, current_task="Petals: fixture", shutting_down=False,
                              disconnect_requested=threading.Event(), connection_thread=object(),
                              event_loop=None, connection_task=Mock(), update_status=Mock())
        ComputeTorrentSeeder.disconnect_provider(app)
        ComputeTorrentSeeder.close_application(app)
        self.assertFalse(app.disconnect_requested.is_set())
        self.assertFalse(app.shutting_down)
        app.connection_task.cancel.assert_not_called()
        self.assertEqual(app.update_status.call_count, 2)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_acknowledgment_gates_connected_state_and_reconnects(self):
        first_registration = asyncio.Event()
        allow_ack = asyncio.Event()
        allow_close = asyncio.Event()
        second_registration = asyncio.Event()
        count = 0

        async def coordinator(ws):
            nonlocal count
            self.assertEqual(json.loads(await ws.recv())["node_id"], "fixture-peer")
            count += 1
            if count == 1:
                first_registration.set()
                await allow_ack.wait()
            await ws.send(json.dumps({"type": "register_ack", "node_id": "fixture-peer"}))
            if count == 1:
                await allow_close.wait()
                await ws.close()
            else:
                second_registration.set()
                await ws.wait_closed()

        async with serve(coordinator, "127.0.0.1", 0) as server:
            app = fixture_app(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/ws/seeder")
            worker = asyncio.create_task(ComputeTorrentSeeder.connect_to_orchestrator(app))
            try:
                await asyncio.wait_for(first_registration.wait(), 5)
                self.assertFalse(app.is_connected)
                self.assertNotIn("Registered", app.states)
                allow_ack.set()
                for _ in range(100):
                    if app.is_connected:
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(app.is_connected)
                allow_close.set()
                await asyncio.wait_for(second_registration.wait(), 8)
                self.assertIn("Reconnecting", app.states)
                self.assertGreaterEqual(count, 2)
            finally:
                allow_ack.set()
                allow_close.set()
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
            self.assertFalse(app.is_connected)

    async def test_transport_loss_is_visible_while_task_handler_is_busy(self):
        working = asyncio.Event()
        release = asyncio.Event()

        async def coordinator(ws):
            await ws.recv()
            await ws.send(json.dumps({"type": "register_ack", "node_id": "fixture-peer"}))
            await ws.send(json.dumps({"type": "task_assign"}))
            await working.wait()
            await ws.close()

        async def handle(raw):
            if json.loads(raw)["type"] == "task_assign":
                working.set()
                await release.wait()

        async with serve(coordinator, "127.0.0.1", 0) as server:
            app = fixture_app(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/ws/seeder")
            app.handle_message = handle
            worker = asyncio.create_task(ComputeTorrentSeeder.connect_to_orchestrator(app))
            try:
                await asyncio.wait_for(working.wait(), 5)
                for _ in range(100):
                    if not app.is_connected:
                        break
                    await asyncio.sleep(.01)
                self.assertFalse(app.is_connected)
                self.assertEqual(app.states[-1], "Reconnecting")
                self.assertFalse(release.is_set())
            finally:
                release.set()
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

    async def test_wrong_identity_stops_without_green_state(self):
        async def coordinator(ws):
            await ws.recv()
            await ws.send(json.dumps({"type": "register_ack", "node_id": "wrong"}))
            await ws.wait_closed()

        async with serve(coordinator, "127.0.0.1", 0) as server:
            app = fixture_app(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/ws/seeder")
            await asyncio.wait_for(ComputeTorrentSeeder.connect_to_orchestrator(app), 5)
            self.assertFalse(app.is_connected)
            self.assertNotIn("Registered", app.states)
            self.assertIn("invalid", app.connection_note)

    async def test_disconnect_cancels_pending_registration(self):
        registration = asyncio.Event()

        async def coordinator(ws):
            await ws.recv()
            registration.set()
            await ws.wait_closed()

        async with serve(coordinator, "127.0.0.1", 0) as server:
            app = fixture_app(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/ws/seeder")
            app.event_loop = asyncio.get_running_loop()
            app.connection_thread = object()
            app.update_status = Mock()
            task = asyncio.create_task(ComputeTorrentSeeder.connect_to_orchestrator(app))
            app.connection_task = task
            await asyncio.wait_for(registration.wait(), 5)
            ComputeTorrentSeeder.disconnect_provider(app)
            result = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)
            self.assertIsInstance(result[0], asyncio.CancelledError)
            self.assertTrue(app.disconnect_requested.is_set())
            self.assertEqual(app.states[-1], "Disconnecting")
            self.assertFalse(app.is_connected)


if __name__ == "__main__":
    unittest.main()
