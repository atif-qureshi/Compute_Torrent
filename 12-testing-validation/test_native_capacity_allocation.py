"""Capacity/rate allocation and actual pre-allocation scheduler control flow."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator/app"))
import distributed

SPEC = dict(model_id="bigscience/bloom-560m", revision="a" * 40,
            layers=24, hidden_size=1024, min_peers=2, max_peers=2)


def peer(ram=8):
    return dict(state="idle", busy=False, profile=dict(petals_enabled=True, docker_ok=True,
        petals_protocol_version=1, petals_network_revision=2, free_ram_gb=ram,
        memory_limit_gb=ram, disk_free_gb=20, gpu_free_mib=0, petals_capacity_protocol=1))


def record(rate=4, capacity=24):
    return dict(model_id=SPEC["model_id"], revision=SPEC["revision"], device="cpu",
        dtype="float32", quant_type="none", block_bytes=64 * 2**20,
        cache_bytes_per_block=8 * 2**20, available_bytes=6 * 2**30,
        reserve_bytes=256 * 2**20, capacity_layers=capacity, inference_rps=rate,
        measured_at=time.time(), source="petals-native-v1")


class AllocationTests(unittest.TestCase):
    def test_large_ram_is_not_flattened_by_model_layer_cap(self):
        peers = {"large": peer(32), "small": peer(8)}
        self.assertEqual(distributed.provider_capacity(SPEC, peers["large"])[0], 24)
        self.assertEqual(distributed.provider_capacity(SPEC, peers["small"])[0], 24)
        plan = distributed.placement(SPEC, peers)
        counts = {p["node_id"]: p["end"] - p["start"] for p in plan}
        self.assertGreater(counts["large"], counts["small"])
        self.assertTrue(all(p["allocation_basis"] == "estimated_memory_capacity" for p in plan))

    def test_measured_rate_controls_split_but_never_exceeds_memory(self):
        peers = {"fast": peer(), "slow": peer()}
        peers["fast"]["profile"]["petals_capacity"] = record(4, 16)
        peers["slow"]["profile"]["petals_capacity"] = record(1, 24)
        plan = distributed.placement(SPEC, peers)
        counts = {p["node_id"]: p["end"] - p["start"] for p in plan}
        self.assertEqual(counts, {"fast": 16, "slow": 8})
        self.assertTrue(all(p["allocation_basis"] == "native_inference_rps" for p in plan))
        self.assertEqual([(p["start"], p["end"]) for p in plan], [(0, 16), (16, 24)])

    def test_equal_capacity_and_rate_can_legitimately_have_equal_ranges(self):
        peers = {"a": peer(), "b": peer()}
        for info in peers.values():
            info["profile"]["petals_capacity"] = record(4, 24)
        self.assertEqual([p["end"] - p["start"] for p in distributed.placement(SPEC, peers)], [12, 12])

    def test_stale_wrong_model_and_nonfinite_measurements_are_not_reused(self):
        for override in (dict(revision="b" * 40), dict(model_id="other/model"),
                         dict(measured_at=time.time()-7200), dict(inference_rps=float("nan"))):
            with self.subTest(override=override):
                info = peer()
                info["profile"]["petals_capacity"] = {**record(), **override}
                self.assertIsNone(distributed.native_capacity(SPEC, info))


class ProfilingFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_specific_probe_precedes_assignment_and_controls_ranges(self):
        manager = SimpleNamespace(active_seeders={"fast": object(), "slow": object()},
            seeder_info={"fast": peer(), "slow": peer()})
        # Old exhausted measurements must not block a fresh preflight after RAM frees.
        for info in manager.seeder_info.values():
            info["profile"]["petals_capacity"] = record(1, 0)
        events = []
        async def send(message, node):
            events.append((message["type"], node))
            info = manager.seeder_info[node]
            if message["type"] == "petals_capacity":
                self.assertEqual(info["capacity_reservation"], message["job_id"])
                self.assertEqual(message["spec"]["revision"], SPEC["revision"])
                info["profile"]["petals_capacity"] = record(4 if node == "fast" else 1,
                                                           16 if node == "fast" else 24)
                info["capacity_response"] = dict(job_id=message["job_id"], error=None)
            elif message["type"] == "petals_start":
                info["profile"]["petals"] = dict(job_id=message["job_id"], status="serving",
                    peer_id=node, network_revision=2, transport="direct")
            return True
        manager.send_to_seeder = send
        async def background(func, *args):
            if func is distributed.resolve_revision:
                return {**args[0], **SPEC}
            if args[0] == "/health":
                return dict(status="ready", bootstrap=["fixture"], relay_enabled=False)
            return dict(status="completed")
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,
                COMPUTETORRENT_JOB_DATA=folder, COMPUTETORRENT_PETALS_NETWORK_POLICY="auto"), \
                patch.object(distributed.asyncio, "to_thread", side_effect=background):
            app = FastAPI()
            distributed.install(app, manager)
            submit = next(r.endpoint for r in app.routes if r.path == "/api/distributed/jobs" and "POST" in r.methods)
            listing = next(r.endpoint for r in app.routes if r.path == "/api/distributed/jobs" and "GET" in r.methods)
            await submit(distributed.Upload(content={**SPEC, "prompt": "fixture"}))
            for _ in range(100):
                jobs = await listing()
                if jobs[0]["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(.01)
            for shutdown in app.router.on_shutdown:
                await shutdown()
            job = (await listing())[0]
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual([kind for kind, _ in events[:4]],
                         ["petals_capacity", "petals_capacity", "petals_start", "petals_start"])
        self.assertEqual([s["end"] - s["start"] for s in job["plan"]], [16, 8])
        self.assertTrue(all(not info.get("capacity_reservation") for info in manager.seeder_info.values()))


if __name__ == "__main__":
    unittest.main()
