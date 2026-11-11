"""Production control/scheduler paths with isolated DB and gateway fixtures.

These tests don't establish real Petals inference or Internet reachability.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator/app"))
import distributed


def profile(**overrides):
    return dict(petals_enabled=True, docker_ok=True, petals_protocol_version=1,
                petals_network_revision=2, free_ram_gb=6, memory_limit_gb=6,
                disk_free_gb=10, gpu_free_mib=0, petals_relay_protocol=1, **overrides)


class CapacityTests(unittest.TestCase):
    def test_spare_requires_current_capacity_and_device_is_recomputed(self):
        spec = dict(layers=24, hidden_size=1024)
        stage = dict(node_id="lost", start=12, end=24, device="cuda")
        good = profile()
        peers = {"paused": dict(state="paused", profile=good),
                 "old": dict(profile={**good, "petals_protocol_version": 0}),
                 "small": dict(profile={**good, "free_ram_gb": 0.5}),
                 "assigned": dict(profile=good), "cpu-spare": dict(profile=good)}
        replacement = distributed.replacement_stage(spec, stage, peers, {"assigned"})
        self.assertEqual(replacement, {**stage, "node_id": "cpu-spare", "device": "cpu"})
        del peers["cpu-spare"]
        self.assertIsNone(distributed.replacement_stage(spec, stage, peers, {"assigned"}))

    def test_invalid_or_missing_telemetry_is_not_assumed_to_be_capacity(self):
        for value in (float("nan"), float("inf"), -1, "invalid", None):
            with self.subTest(value=value):
                self.assertEqual(distributed.provider_capacity(dict(layers=24, hidden_size=1024),
                    dict(profile={**profile(), "free_ram_gb": value}))[0], 0)
        self.assertEqual(distributed.provider_capacity(dict(layers=24, hidden_size=1024),
                        dict(profile={}))[0], 0)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("isolated_hybrid_control",
                    ROOT / "orchestrator/app/main_production.py")
        cls.control = importlib.util.module_from_spec(spec)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "COMPUTETORRENT_JOB_DATA": folder}), patch("sqlalchemy.create_engine",
            side_effect=RuntimeError("isolated fixture")):
            spec.loader.exec_module(cls.control)

    async def test_replacement_reserves_ownership_before_awaiting_old_close(self):
        manager = self.control.ConnectionManager()
        old, new, newest = AsyncMock(), AsyncMock(), AsyncMock()
        await manager.connect("node", old)
        async def close_old(**_):
            self.assertFalse(manager.disconnect("node", old))
            await manager.connect("node", newest)
        old.close.side_effect = close_old
        self.assertFalse(await manager.connect("node", new))
        self.assertIs(manager.active_seeders["node"], newest)
        self.assertFalse(manager.disconnect("node", new))

    async def test_buffered_message_from_replaced_socket_cannot_change_state(self):
        control = self.control
        manager = control.ConnectionManager()
        old, new = AsyncMock(), AsyncMock()
        old.headers = {"authorization": "Bearer fixture"}
        old.client.host = "192.168.1.5"
        calls = 0
        async def receive():
            nonlocal calls
            calls += 1
            if calls == 1:
                return json.dumps(dict(type="register", node_id="node", tier=1, profile={}))
            await manager.connect("node", new)
            return json.dumps(dict(type="heartbeat", state="paused"))
        old.receive_text.side_effect = receive
        with patch.object(control, "manager", manager), patch.object(control, "DB_AVAILABLE", False), \
                patch.dict(control.MOCK_SEEDER_CREDENTIALS,
                           node=hashlib.sha256(b"fixture").hexdigest()), \
                patch.object(control, "allocate_pending_tasks", new=AsyncMock()), \
                patch.object(control, "handle_seeder_message", new=AsyncMock()) as handler:
            await control.websocket_seeder(old)
            handler.assert_not_called()
            self.assertIs(manager.active_seeders["node"], new)

    async def test_registration_always_records_client_host_including_reported_modes(self):
        from types import SimpleNamespace
        control = self.control
        cases = [
            ("LAN", "192.168.100.7", {}, "LAN", "192.168.100.7"),
            ("WAN", "192.168.100.7", {}, "WAN", "192.168.100.7"),
            (None, "127.0.0.1", {}, "LAN", "127.0.0.1"),
            (None, "8.8.8.8", {}, "WAN", "8.8.8.8"),
            ("LAN", None, {}, "LAN", "unknown"),
            ("WAN", "127.0.0.1", {"x-forwarded-for": "8.8.8.8, 127.0.0.1"}, "WAN", "8.8.8.8"),
        ]
        for reported, host, headers, expected_mode, expected_host in cases:
            with self.subTest(reported=reported, host=host):
                manager = control.ConnectionManager()
                ws = AsyncMock()
                ws.client = SimpleNamespace(host=host) if host else None
                ws.headers = {"authorization": "Bearer fixture", **headers}
                message = dict(type="register", node_id="node", tier=2, profile={})
                if reported is not None:
                    message["network_mode"] = reported
                ws.receive_text.side_effect = [json.dumps(message), control.WebSocketDisconnect()]
                with patch.object(control, "manager", manager), patch.object(control, "DB_AVAILABLE", False), \
                     patch.dict(control.MOCK_SEEDER_CREDENTIALS, node=hashlib.sha256(b"fixture").hexdigest()), \
                     patch.object(control, "allocate_pending_tasks", new=AsyncMock()):
                    await control.websocket_seeder(ws)
                ack = json.loads(ws.send_text.call_args_list[0].args[0])
                self.assertEqual(ack["type"], "register_ack")
                self.assertEqual(ack["network_mode"], expected_mode)
                self.assertEqual(ack["client_ip"], expected_host)



class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_rejects_bad_telemetry_without_crashing(self):
        from types import SimpleNamespace
        manager = SimpleNamespace(active_seeders={"node": object()},
            seeder_info={"node": dict(profile={**profile(), "free_ram_gb": "invalid"})})
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,
                COMPUTETORRENT_JOB_DATA=folder), patch.object(distributed.asyncio,
                "to_thread", new=AsyncMock(return_value={"status": "ready"})):
            app = FastAPI()
            distributed.install(app, manager)
            status = next(r.endpoint for r in app.routes if r.path == "/api/distributed/status")
            result = await status()
            self.assertFalse(result["providers"][0]["layer_ready"])
            self.assertIn("telemetry", result["providers"][0]["layer_reason"])

    async def exercise(self, failure=None):
        from types import SimpleNamespace
        manager = SimpleNamespace(active_seeders={n: object() for n in ("a", "b")},
            seeder_info={n: dict(profile=profile(), state="idle", busy=False)
                         for n in ("a", "b", "small", "spare")})
        manager.seeder_info["small"]["profile"]["free_ram_gb"] = 0.5
        sent, replaced, inference, dropped = [], False, False, False
        routes, revoked = [], []
        async def send(message, node):
            nonlocal replaced
            sent.append((node, dict(message)))
            if message["type"] == "petals_start":
                manager.seeder_info[node]["profile"]["petals"] = dict(
                    job_id=message["job_id"], status="loading" if node == "b" else "serving",
                    peer_id="peer-" + node, network_revision=2,
                    transport="wss" if failure in {"relay", "bad_probe"} else "direct")
                if node == "b" and failure == "delivery":
                    manager.active_seeders.pop("b")
                    manager.seeder_info["b"].update(busy=False, state="offline")
                    manager.active_seeders.update(small=object(), spare=object())
                    replaced = True
                    return False
            return node in manager.active_seeders
        manager.send_to_seeder = send
        real_sleep = asyncio.sleep
        async def sleep(_):
            nonlocal replaced, dropped
            if not replaced:
                manager.active_seeders.pop("b")
                manager.seeder_info["b"].update(busy=False, state="offline")
                if failure != "no_spare":
                    manager.active_seeders.update(small=object(), spare=object())
                replaced = True
            elif inference and failure in {"disconnect", "reconnect"} and not dropped:
                if failure == "reconnect":
                    manager.active_seeders["spare"] = object()
                else:
                    manager.active_seeders.pop("spare")
                manager.seeder_info["spare"].update(busy=False,
                    state="idle" if failure == "reconnect" else "offline")
                dropped = True
            await real_sleep(0)
        async def background(func, *args):
            nonlocal inference
            if func is distributed.resolve_revision:
                return {**args[0], **distributed.CATALOG[args[0]["model_id"]]}
            path = args[0]
            if path == "/health":
                return dict(status="ready", bootstrap=["fixture"], relay_enabled=failure in {"relay", "bad_probe"})
            if path == "/routes":
                route = dict(id=str(len(routes)), token="fixture", url="wss://fixture/ws/petals-relay/fixture")
                routes.append(route)
                return route
            if path == "/routes/probe":
                return dict(status="failed" if failure == "bad_probe" else "verified", peer_id=args[1]["peer_id"])
            if path == "/routes/revoke":
                revoked.append(args[1]["id"])
                return dict(status="revoked")
            if path == "/jobs":
                inference = True
                return dict(status="running")
            if path.startswith("/jobs/"):
                return dict(status="running" if failure in {"disconnect", "reconnect"} else "completed")
            return dict(status="stopped")
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,
                COMPUTETORRENT_JOB_DATA=folder), patch.object(distributed.asyncio,
                "to_thread", side_effect=background), patch.object(distributed.asyncio,
                "sleep", side_effect=sleep):
            app = FastAPI()
            distributed.install(app, manager)
            submit = next(r.endpoint for r in app.routes
                          if r.path == "/api/distributed/jobs" and "POST" in r.methods)
            listing = next(r.endpoint for r in app.routes
                           if r.path == "/api/distributed/jobs" and "GET" in r.methods)
            await submit(distributed.Upload(content=dict(model_id="bigscience/bloom-560m",
                prompt="fixture", min_peers=2, max_peers=2)))
            for _ in range(100):
                await real_sleep(0.01)
                jobs = await listing()
                if jobs[0]["status"] in {"completed", "failed"}:
                    break
            for shutdown in app.router.on_shutdown:
                await shutdown()
            job = (await listing())[0]
        starts = [(n, msg) for n, msg in sent if msg["type"] == "petals_start"]
        self.assertEqual([n for n, _ in starts], ["a", "b"] if failure == "no_spare" else ["a", "b", "spare"])
        self.assertEqual(starts[-1][1]["stage"]["device"], "cpu")
        self.assertFalse(manager.seeder_info["a"]["busy"])
        self.assertFalse(manager.seeder_info["spare"]["busy"])
        self.assertEqual(set(revoked), {r["id"] for r in routes})
        if routes:
            self.assertTrue(all("relay" in msg for _, msg in starts))
        return job

    async def test_actual_scheduler_allocates_probes_and_revokes_relay_leases(self):
        self.assertEqual((await self.exercise("relay"))["status"], "completed")

    async def test_unverified_relay_worker_never_starts_inference(self):
        job = await self.exercise("bad_probe")
        self.assertEqual(job["status"], "failed")
        self.assertIn("could not verify", job["error"])

    async def test_actual_scheduler_reassigns_setup_stage(self):
        self.assertEqual((await self.exercise())["status"], "completed")

    async def test_no_spare_fails_and_releases_remaining_stages(self):
        job = await self.exercise("no_spare")
        self.assertEqual(job["status"], "failed")
        self.assertIn("no alternative provider", job["error"])
        self.assertTrue(all(p["status"] in {"stopped", "failed"} for p in job["stage_status"].values()))

    async def test_assignment_delivery_failure_uses_available_spare(self):
        self.assertEqual((await self.exercise("delivery"))["status"], "completed")

    async def test_actual_scheduler_aborts_lost_inference_session(self):
        job = await self.exercise("disconnect")
        self.assertEqual(job["status"], "failed")
        self.assertIn("cannot migrate safely", job["error"])

    async def test_reconnected_identity_does_not_reuse_lost_kv_session(self):
        job = await self.exercise("reconnect")
        self.assertEqual(job["status"], "failed")
        self.assertIn("cannot migrate safely", job["error"])


if __name__ == "__main__":
    unittest.main()
