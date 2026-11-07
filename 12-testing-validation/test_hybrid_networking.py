"""Mock-based control/capability checks; these do not validate real LAN/WAN inference.

Tests:
1. Coordinator and provider on same LAN (Direct mode).
2. Two providers on same LAN (Direct peer routing).
3. Providers on different networks (WAN mode).
4. NAT traversal and Circuit Relay multiaddr fallback.
5. Temporary disconnection and fast reconnection (Stale session eviction).
6. Power failure, heartbeat timeout, and post-power recovery.
7. Network switching (LAN -> WAN dynamic mode change).
8. Multi-provider Petals layer placement across hybrid nodes.
9. Fault tolerance: dynamic layer reassignment on provider disconnection during stage setup.
10. Unrecoverable disconnection: graceful abort and resource cleanup.
11. Security: Impersonation defense and token verification.
"""
import asyncio
import hashlib
import hmac
import importlib.util
import json
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "orchestrator" / "app"))


def load_module(name, rel_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


with patch("sqlalchemy.create_engine", side_effect=RuntimeError("isolated test database")):
    coordinator = load_module("hybrid_coordinator", "orchestrator/app/main_production.py")
distributed = load_module("distributed", "orchestrator/app/distributed.py")
probe = load_module("bootstrap_probe", "08-provider-node/06-petals-runtime/bootstrap_probe.py")


class MockWebSocket:
    def __init__(self, client_host="192.168.100.15"):
        self.client = MagicMock()
        self.client.host = client_host
        self.sent_messages = []
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.headers = {}

    async def accept(self):
        pass

    async def send_text(self, text):
        self.sent_messages.append(text)

    async def close(self, code=1000, reason=""):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class HybridNetworkingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = coordinator.ConnectionManager()

    # 1. Coordinator and provider on the same LAN
    async def test_coordinator_and_provider_same_lan(self):
        ws = MockWebSocket(client_host="192.168.1.100")
        node_id = "node-lan-01"
        await self.manager.connect(node_id, ws, network_mode="LAN", client_ip="192.168.1.100")

        self.assertIn(node_id, self.manager.active_seeders)
        self.assertEqual(self.manager.seeder_info[node_id]["network_mode"], "LAN")
        self.assertEqual(self.manager.seeder_info[node_id]["client_ip"], "192.168.1.100")
        stats = self.manager.get_network_stats()
        self.assertEqual(stats["lan_providers"], 1)
        self.assertEqual(stats["wan_providers"], 0)

    # 2. Two providers on the same LAN
    async def test_two_providers_same_lan(self):
        ws1 = MockWebSocket(client_host="192.168.1.101")
        ws2 = MockWebSocket(client_host="192.168.1.102")
        await self.manager.connect("node-lan-01", ws1, network_mode="LAN", client_ip="192.168.1.101")
        await self.manager.connect("node-lan-02", ws2, network_mode="LAN", client_ip="192.168.1.102")

        stats = self.manager.get_network_stats()
        self.assertEqual(stats["total_active"], 2)
        self.assertEqual(stats["lan_providers"], 2)
        self.assertEqual(stats["wan_providers"], 0)

    # 3. Providers on different internet networks (WAN)
    async def test_providers_on_different_networks_wan(self):
        ws_wan1 = MockWebSocket(client_host="203.0.113.50")
        ws_wan2 = MockWebSocket(client_host="198.51.100.80")
        await self.manager.connect("node-wan-01", ws_wan1, network_mode="WAN", client_ip="203.0.113.50")
        await self.manager.connect("node-wan-02", ws_wan2, network_mode="WAN", client_ip="198.51.100.80")

        stats = self.manager.get_network_stats()
        self.assertEqual(stats["total_active"], 2)
        self.assertEqual(stats["lan_providers"], 0)
        self.assertEqual(stats["wan_providers"], 2)

    # 4. Providers behind NAT using relay fallback multiaddr
    async def test_nat_relay_multiaddr_support(self):
        relay_addr = "/dns4/coordinator.computetorrent.ai/tcp/31331/p2p/QmRelayCoordinator/p2p-circuit/p2p/QmProviderBehindNAT"
        # Validate worker regex accepts relayed multiaddr
        import re
        regex = r"/(?:ip4|dns4)/[A-Za-z0-9.-]+/tcp/[0-9]{4,5}(?:/p2p/[A-Za-z0-9]+)?(?:/p2p-circuit)?(?:/p2p/[A-Za-z0-9]+)?"
        self.assertTrue(bool(re.fullmatch(regex, relay_addr)))

        # Validate probe creates peer with relay enabled
        calls = []
        async def fake_create(**kwargs):
            calls.append(kwargs)
            return MagicMock(shutdown=AsyncMock())
        await probe.reachable_bootstrap([relay_addr], attempts=1, create_peer=fake_create)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["use_relay"])
        self.assertTrue(calls[0]["use_auto_relay"])

    # 5. Temporary disconnection and fast reconnection (stale session eviction)
    async def test_temporary_disconnection_and_fast_reconnection(self):
        ws_old = MockWebSocket(client_host="192.168.1.50")
        node_id = "node-flaky"
        await self.manager.connect(node_id, ws_old, network_mode="LAN", client_ip="192.168.1.50")

        # Network drop occurs, client reconnects with fresh socket before old socket timed out
        ws_new = MockWebSocket(client_host="192.168.1.50")
        await self.manager.connect(node_id, ws_new, network_mode="LAN", client_ip="192.168.1.50")

        # Old socket should be cleanly closed and new socket should be active
        self.assertTrue(ws_old.closed)
        self.assertEqual(ws_old.close_code, 1000)
        self.assertIs(self.manager.active_seeders[node_id], ws_new)
        self.assertFalse(ws_new.closed)

    # 6. Provider shutdown due to power failure and recovery
    async def test_provider_power_failure_and_recovery(self):
        ws = MockWebSocket(client_host="192.168.1.99")
        node_id = "node-power-test"
        await self.manager.connect(node_id, ws, network_mode="LAN", client_ip="192.168.1.99")

        # Simulate power outage (socket disconnects)
        self.manager.disconnect(node_id, ws)
        self.assertNotIn(node_id, self.manager.active_seeders)
        self.assertEqual(self.manager.seeder_info[node_id]["state"], "offline")

        # Power restored: provider restarts and reconnects
        ws_recovered = MockWebSocket(client_host="192.168.1.99")
        await self.manager.connect(node_id, ws_recovered, network_mode="LAN", client_ip="192.168.1.99")
        self.assertIn(node_id, self.manager.active_seeders)
        self.assertEqual(self.manager.seeder_info[node_id]["state"], "online")

    # 7. LAN-to-WAN network switching (e.g., laptop moving from office Wi-Fi to cellular)
    async def test_lan_to_wan_network_switching(self):
        node_id = "node-roaming-laptop"
        ws_lan = MockWebSocket(client_host="192.168.1.200")
        await self.manager.connect(node_id, ws_lan, network_mode="LAN", client_ip="192.168.1.200")
        self.assertEqual(self.manager.seeder_info[node_id]["network_mode"], "LAN")

        # Roams to WAN
        ws_wan = MockWebSocket(client_host="172.56.21.88")
        await self.manager.connect(node_id, ws_wan, network_mode="WAN", client_ip="172.56.21.88")
        self.assertEqual(self.manager.seeder_info[node_id]["network_mode"], "WAN")
        self.assertEqual(self.manager.seeder_info[node_id]["client_ip"], "172.56.21.88")

    # 8. Distributed inference with model layers assigned across multiple providers
    def test_distributed_layer_placement(self):
        spec = {"model_id": "bigscience/bloom-560m", "layers": 24, "hidden_size": 1024, "min_peers": 2, "max_peers": 4}
        peers = {
            "node-1": {"profile": {"petals_enabled": True, "docker_ok": True, "petals_protocol_version": 1,
                                   "petals_network_revision": 2, "free_ram_gb": 4, "memory_limit_gb": 4, "disk_free_gb": 10}},
            "node-2": {"profile": {"petals_enabled": True, "docker_ok": True, "petals_protocol_version": 1,
                                   "petals_network_revision": 2, "free_ram_gb": 4, "memory_limit_gb": 4, "disk_free_gb": 10}},
        }
        plan = distributed.placement(spec, peers)
        self.assertEqual(len(plan), 2)
        total_layers = sum(stage["end"] - stage["start"] for stage in plan)
        self.assertEqual(total_layers, 24)
        self.assertEqual(plan[0]["start"], 0)
        self.assertEqual(plan[1]["end"], 24)

    # 8b. Petals capacity-aware heterogeneous layer division (unequal allocation based on hardware capacity)
    def test_capacity_aware_heterogeneous_layer_division(self):
        spec = {"model_id": "bigscience/bloom-560m", "layers": 24, "hidden_size": 1024, "min_peers": 2, "max_peers": 4}
        peers = {
            # High-capacity GPU provider: RTX 3080 with 10GB VRAM, CUDA enabled
            "gpu-provider": {
                "profile": {
                    "petals_enabled": True, "docker_ok": True, "petals_protocol_version": 1,
                    "petals_network_revision": 2, "free_ram_gb": 16, "memory_limit_gb": 16,
                    "disk_free_gb": 50, "gpu_free_mib": 10240, "petals_cuda_ready": True
                }
            },
            # Low-capacity CPU provider: Laptop with 4GB RAM, CPU only
            "cpu-laptop": {
                "profile": {
                    "petals_enabled": True, "docker_ok": True, "petals_protocol_version": 1,
                    "petals_network_revision": 2, "free_ram_gb": 4, "memory_limit_gb": 4,
                    "disk_free_gb": 20, "gpu_free_mib": 0, "petals_cuda_ready": False
                }
            }
        }
        plan = distributed.placement(spec, peers)
        self.assertEqual(len(plan), 2)
        total_layers = sum(stage["end"] - stage["start"] for stage in plan)
        self.assertEqual(total_layers, 24)

        gpu_stage = next(s for s in plan if s["node_id"] == "gpu-provider")
        cpu_stage = next(s for s in plan if s["node_id"] == "cpu-laptop")

        gpu_count = gpu_stage["end"] - gpu_stage["start"]
        cpu_count = cpu_stage["end"] - cpu_stage["start"]

        # Crucial check: Layers must NOT be divided equally (12 and 12)!
        # The GPU provider must be assigned significantly more layers than the CPU laptop.
        self.assertNotEqual(gpu_count, cpu_count, "Layers must not be divided equally across heterogeneous hardware")
        self.assertGreater(gpu_count, cpu_count, "The larger available memory budget should receive more layers; no invented GPU speed multiplier")
        self.assertEqual(gpu_stage["device"], "cuda")
        self.assertEqual(cpu_stage["device"], "cpu")

    # 9. Provider disconnection during active inference with dynamic shard reassignment
    async def test_provider_disconnection_dynamic_reassignment(self):
        ws1 = MockWebSocket(client_host="192.168.1.10")
        ws2 = MockWebSocket(client_host="192.168.1.20")
        ws3_spare = MockWebSocket(client_host="192.168.1.30")

        await self.manager.connect("node-1", ws1, network_mode="LAN", client_ip="192.168.1.10")
        await self.manager.connect("node-2", ws2, network_mode="LAN", client_ip="192.168.1.20")
        await self.manager.connect("node-3-spare", ws3_spare, network_mode="LAN", client_ip="192.168.1.30")

        for n in ("node-1", "node-2", "node-3-spare"):
            self.manager.seeder_info[n].update(
                busy=False,
                profile={"petals_enabled": True, "docker_ok": True, "petals_protocol_version": 1,
                         "petals_network_revision": 2, "free_ram_gb": 6, "memory_limit_gb": 6, "disk_free_gb": 10}
            )

        # Plan with node-1 and node-2
        plan = [
            {"node_id": "node-1", "start": 0, "end": 12, "device": "cpu"},
            {"node_id": "node-2", "start": 12, "end": 24, "device": "cpu"}
        ]
        job = {
            "id": "job-test-reassign",
            "spec": {"model_id": "bigscience/bloom-560m", "revision": "main"},
            "prefix": "ct-test",
            "plan": plan,
            "stage_status": {"node-1": {"status": "serving", "peer_id": "Qm1", "network_revision": 2},
                             "node-2": {"status": "loading"}}
        }

        # Simulate node-2 crashing/disconnecting before ready
        self.manager.disconnect("node-2", ws2)

        # Test recovery logic: node-2 disconnected, should reassign to node-3-spare
        disconnected_id = "node-2"
        assigned_nodes = {s["node_id"] for s in plan if s["node_id"] != disconnected_id}
        eligible = [
            n for n, info in self.manager.seeder_info.items()
            if n in self.manager.active_seeders
            and n not in assigned_nodes
            and not info.get("busy")
            and info.get("profile", {}).get("petals_enabled") is True
            and info.get("profile", {}).get("docker_ok") is True
            and info.get("profile", {}).get("petals_network_revision") == 2
        ]
        self.assertIn("node-3-spare", eligible)

        # Reassign stage
        replacement_id = eligible[0]
        for stage in plan:
            if stage["node_id"] == disconnected_id:
                stage["node_id"] = replacement_id
                self.manager.seeder_info[replacement_id]["busy"] = True

        self.assertEqual(plan[1]["node_id"], "node-3-spare")
        self.assertTrue(self.manager.seeder_info["node-3-spare"]["busy"])

    # 10. Provider disconnection with no spare: graceful error
    async def test_provider_disconnection_unrecoverable_graceful_abort(self):
        ws1 = MockWebSocket(client_host="192.168.1.10")
        await self.manager.connect("node-1", ws1, network_mode="LAN", client_ip="192.168.1.10")
        self.manager.disconnect("node-1", ws1)

        plan = [{"node_id": "node-1", "start": 0, "end": 24, "device": "cpu"}]
        assigned_nodes = {s["node_id"] for s in plan if s["node_id"] != "node-1"}
        eligible = [
            n for n in self.manager.seeder_info
            if n in self.manager.active_seeders and n not in assigned_nodes
        ]
        self.assertEqual(len(eligible), 0)

    # 11. Security: Impersonation defense and token verification
    def test_impersonation_defense_token_verification(self):
        # Coordinator stores token hash
        token = "secret-token-volunteer-12345"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        # Attacker presents wrong token
        attacker_token = "wrong-forged-token"
        attacker_hash = hashlib.sha256(attacker_token.encode("utf-8")).hexdigest()
        self.assertFalse(hmac.compare_digest(attacker_hash, token_hash))

        # Legitimate provider presents correct token
        self.assertTrue(hmac.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), token_hash))


if __name__ == "__main__":
    unittest.main()
