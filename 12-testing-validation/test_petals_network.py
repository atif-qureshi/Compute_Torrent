"""Regression checks for real bootstrap selection and terminated stage state."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


probe = module("bootstrap_probe", "08-provider-node/06-petals-runtime/bootstrap_probe.py")
distributed = module("distributed", "orchestrator/app/distributed.py")


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_handshaken_address_is_forwarded_to_server(self):
        calls, closed = [], []
        class Peer:
            async def shutdown(self):
                closed.append(True)
        async def create(**kwargs):
            calls.append(kwargs)
            if kwargs["initial_peers"] == ["unreachable"]:
                raise RuntimeError("connection refused")
            return Peer()
        chosen = await probe.reachable_bootstrap(["unreachable", "reachable", "reachable"], create_peer=create)
        self.assertEqual(chosen, ["reachable"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(closed, [True])
        self.assertTrue(calls[0]["no_listen"])
        self.assertFalse(calls[0]["use_auto_relay"])
        self.assertNotIn("tls", calls[0])  # Keep the upstream secure default.

    async def test_failure_reports_the_actual_peer_address(self):
        async def create(**_):
            raise RuntimeError("peer identity mismatch")
        address = "/ip4/192.168.1.5/tcp/31331/p2p/expected-peer"
        with self.assertRaisesRegex(RuntimeError, "expected-peer.*identity mismatch"):
            await probe.reachable_bootstrap([address], attempts=1, create_peer=create)


class SchedulingTests(unittest.TestCase):
    def test_old_provider_is_not_assigned_another_failing_job(self):
        profile = {"petals_enabled": True, "docker_ok": True, "petals_protocol_version": 1,
                   "free_ram_gb": 6, "memory_limit_gb": 6, "disk_free_gb": 10}
        spec = {"layers": 24, "hidden_size": 1024, "min_peers": 1, "max_peers": 2}
        with self.assertRaisesRegex(ValueError, "found 0"):
            distributed.placement(spec, {"old": {"profile": profile}})
        profile["petals_network_revision"] = 2
        plan = distributed.placement(spec, {"current": {"profile": profile}})
        self.assertEqual(plan[0]["end"], 24)

    def test_failed_job_never_keeps_another_peer_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            store = distributed.Store(Path(folder) / "jobs.db")
            job = {"id": "example", "status": "failed", "stage_status": {
                "bad": {"status": "failed", "error": "bootstrap failed"},
                "other": {"status": "loading"}}}
            store.save(job)
            persisted = store.get("example")
            self.assertEqual(persisted["stage_status"]["bad"]["status"], "failed")
            self.assertEqual(persisted["stage_status"]["other"]["status"], "stopped")
            self.assertEqual(persisted["stage_status"]["other"]["last_status"], "loading")


if __name__ == "__main__":
    unittest.main()
