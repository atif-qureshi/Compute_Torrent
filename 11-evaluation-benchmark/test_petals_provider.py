"""Provider regressions for LAN bootstrap routing and runtime upgrades (no Docker)."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SOURCE = Path(__file__).resolve().parents[1] / "08-provider-node" / "05-desktop-app-shell" / "petals_control.py"
SPEC = importlib.util.spec_from_file_location("petals_provider_under_test", SOURCE)
provider = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider)
JOB = "a" * 32
IMAGE_ID = "sha256:" + "1" * 64


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.control = provider.PetalsControl(self.temp.name)

    def request(self):
        return {"job_id": JOB, "prefix": "ct-" + JOB,
                "spec": {"model_id": "bigscience/bloom-560m"},
                "stage": {"node_id": "provider-one", "device": "cpu", "start": 0, "end": 12},
                "bootstrap": ["/ip4/192.168.1.10/tcp/31331/p2p/test-peer"]}

    def start_with_network(self, coordinator, route_ip, resolved=None, request=None):
        hostname = "provider-host"
        resolved = resolved or {"192.168.1.10": "192.168.1.10", hostname: "192.168.1.20"}
        route = MagicMock()
        route.getsockname.return_value = (route_ip, 50000)
        with patch.object(provider.socket, "gethostname", return_value=hostname), \
                patch.object(provider.socket, "gethostbyname", side_effect=lambda host: resolved.get(host, host)), \
                patch.object(provider.socket, "socket") as socket_factory, \
                patch.object(provider.socket, "create_connection") as preflight, \
                patch.object(provider, "runtime_digest", return_value="expected-digest"), \
                patch.object(provider, "command", return_value="container-id") as docker, \
                patch.object(self.control, "_validated_image_id", return_value=IMAGE_ID):
            socket_factory.return_value.__enter__.return_value = route
            self.control.start(request or self.request(), coordinator, 2, 4)
        written = json.loads((self.control.root / JOB / "request.json").read_text())
        return written, docker, preflight

    def test_remote_provider_keeps_lan_bootstrap_and_announces_its_own_ip(self):
        data, docker, preflight = self.start_with_network("ws://192.168.1.10:8001/ws/seeder", "192.168.1.20")
        self.assertEqual(data["bootstrap"], self.request()["bootstrap"])
        self.assertEqual(data["advertise_maddrs"], ["/ip4/192.168.1.20/tcp/31330"])
        preflight.assert_called_once_with(("192.168.1.10", 31331), timeout=5)
        self.assertNotIn("--add-host", docker.call_args.args[0])
        self.assertEqual(docker.call_args.args[0][-3:], [IMAGE_ID, "python", "/app/worker.py"])

    def test_loopback_coordinator_uses_docker_host_alias_without_remote_preflight(self):
        data, docker, preflight = self.start_with_network("ws://127.0.0.1:8001/ws/seeder", "127.0.0.1")
        self.assertIn("/dns4/host.docker.internal/tcp/31331/p2p/test-peer", data["bootstrap"])
        self.assertIn("/dns4/host.docker.internal/tcp/31330", data["advertise_maddrs"])
        self.assertIn("host.docker.internal:host-gateway", docker.call_args.args[0])
        preflight.assert_not_called()

    def test_coordinator_lan_ip_on_same_pc_also_uses_docker_host_alias(self):
        data, _, preflight = self.start_with_network("ws://192.168.1.10:8001/ws/seeder", "192.168.1.10")
        self.assertTrue(data["bootstrap"][0].startswith("/dns4/host.docker.internal/"))
        preflight.assert_not_called()

    def test_loopback_provider_advertises_bootstrap_lan_ip_before_hostname_virtual_nic(self):
        data, _, _ = self.start_with_network("ws://127.0.0.1:8001/ws/seeder", "127.0.0.1",
                                            resolved={"provider-host": "192.168.56.1"})
        self.assertEqual(data["advertise_host"], "192.168.1.10")
        self.assertIn("/ip4/192.168.1.10/tcp/31330", data["advertise_maddrs"])
        self.assertNotIn("192.168.56.1", json.dumps(data["advertise_maddrs"]))

    def test_remote_provider_repairs_legacy_docker_alias_without_advertising_it(self):
        request = self.request()
        request["bootstrap"] = ["/dns4/host.docker.internal/tcp/31331/p2p/test-peer"]
        data, _, _ = self.start_with_network("ws://192.168.1.10:8001/ws/seeder", "192.168.1.20", request=request)
        self.assertEqual(data["bootstrap"], self.request()["bootstrap"])
        self.assertNotIn("host.docker.internal", json.dumps(data["advertise_maddrs"]))

    def test_start_rebuilds_stale_image_and_runs_validated_immutable_image_id(self):
        route = MagicMock()
        route.getsockname.return_value = ("192.168.1.10", 50000)
        with patch.object(provider.socket, "gethostbyname", return_value="192.168.1.10"), \
                patch.object(provider.socket, "socket") as factory, \
                patch.object(provider, "runtime_digest", return_value="new-digest"), \
                patch.object(self.control, "_validated_image_id", return_value=None), \
                patch.object(self.control, "install_runtime", return_value=IMAGE_ID) as build, \
                patch.object(provider.time, "time", side_effect=[10.0, 3610.0]), \
                patch.object(provider, "command", return_value="container") as docker:
            factory.return_value.__enter__.return_value = route
            self.control.start(self.request(), "ws://192.168.1.10:8001/ws/seeder", 2, 4)
        build.assert_called_once_with("cpu")
        self.assertEqual(docker.call_args.args[0][-3:], [IMAGE_ID, "python", "/app/worker.py"])
        self.assertEqual(float((self.control.root / JOB / "lease").read_text()), 3610.0)

    def test_stopped_container_preserves_actionable_worker_error(self):
        self.control.job_id = JOB
        self.control.container = "stopped-container"
        folder = self.control.root / JOB
        folder.mkdir()
        actionable = "Cannot reach DHT at 192.168.1.10:31331. Allow private LAN TCP traffic. " + "detail " * 200
        (folder / "status.json").write_text(json.dumps({"job_id": JOB, "status": "failed", "error": actionable}))
        with patch.object(provider, "command", return_value="false") as docker:
            status = self.control.status()
        self.assertEqual(status["error"], actionable)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(docker.call_count, 1)  # Docker log tail must not replace the worker diagnosis.

    def test_startup_failure_survives_repeated_status_heartbeats(self):
        with patch.object(self.control, "_start", side_effect=RuntimeError("DHT port is unreachable")), \
                patch.object(provider, "command") as docker:
            with self.assertRaisesRegex(RuntimeError, "DHT port is unreachable"):
                self.control.start(self.request(), "ws://192.168.1.10:8001/ws/seeder", 2, 4)
            first = self.control.status()
            self.assertEqual(self.control.status(), first)
        self.assertEqual(first["status"], "failed")
        self.assertEqual(first["error"], "DHT port is unreachable")
        self.assertEqual(self.control.phase, "failed")
        self.assertEqual(json.loads((self.control.root / JOB / "status.json").read_text()), first)
        docker.assert_not_called()
        self.control.stop()
        self.assertEqual(self.control.status(), {"status": "idle"})

    def test_matching_runtime_label_is_required_for_readiness(self):
        stale = json.dumps({"Id": IMAGE_ID, "Config": {"Labels": {provider.DIGEST_LABEL: "old"}}})
        current = json.dumps({"Id": IMAGE_ID, "Config": {"Labels": {provider.DIGEST_LABEL: "current"}}})
        with patch.object(provider, "runtime_digest", return_value="current"), \
                patch.object(provider, "command", side_effect=[stale, current]):
            capabilities = self.control.capabilities()
        self.assertFalse(capabilities["petals_image_ready"])
        self.assertTrue(capabilities["petals_cuda_ready"])
        self.assertEqual(capabilities["petals_network_revision"], 2)

    def test_build_labels_image_and_refuses_unverified_output(self):
        with patch.object(provider, "runtime_digest", return_value="current"), \
                patch.object(provider.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as build, \
                patch.object(self.control, "_validated_image_id", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "expected source revision"):
                self.control.install_runtime()
        args = build.call_args.args[0]
        self.assertIn(provider.DIGEST_LABEL + "=current", args)
        self.assertNotIn("--no-cache", args)


class RuntimeDigestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("Dockerfile", "Dockerfile.cuda", "worker.py", "requirements-petals.txt"):
            (self.root / name).write_text(name)
        self.addCleanup(provider.runtime_digest.cache_clear)

    def digest(self):
        provider.runtime_digest.cache_clear()
        with patch.object(provider, "RUNTIME_DIR", self.root):
            return provider.runtime_digest()

    def test_worker_and_new_python_helpers_invalidate_runtime_but_cache_does_not(self):
        initial = self.digest()
        (self.root / "__pycache__").mkdir()
        (self.root / "__pycache__" / "worker.pyc").write_bytes(b"ignored cache")
        (self.root / "dependency.whl").write_bytes(b"not hashed on every heartbeat")
        self.assertEqual(self.digest(), initial)
        (self.root / "worker.py").write_text("updated worker")
        changed = self.digest()
        self.assertNotEqual(changed, initial)
        (self.root / "bootstrap_probe.py").write_text("new network helper")
        self.assertNotEqual(self.digest(), changed)


if __name__ == "__main__":
    unittest.main()
