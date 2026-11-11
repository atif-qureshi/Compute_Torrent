"""Unit tests for live runtime telemetry, accuracy metrics, provider progress, and host Wi-Fi IP sync."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LiveTelemetryAndAccuracyTests(unittest.TestCase):
    def test_generate_job_streams_tokens_and_computes_real_accuracy_metrics(self):
        import torch

        gen_mod = load_module("generate_job_under_test", ROOT / "08-provider-node" / "06-petals-runtime" / "generate_job.py")
        events = []

        class FakeSeqManager:
            dht = type("FakeDHT", (), {"shutdown": lambda self: None})()

            def make_sequence(self, mode=None):
                return None

            def is_alive(self):
                return True

            def update(self, wait=False):
                return None

            def shutdown(self):
                return None

        class FakeStage:
            def __init__(self, n):
                self.n = n
                self.sequence_manager = FakeSeqManager()

            def inference_session(self, max_length=None):
                class Ctx:
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                return Ctx()

            def __call__(self, hidden):
                return hidden + 0.1

        class FakeRemoteList(list):
            def __init__(self):
                super().__init__([FakeStage(0), FakeStage(1), FakeStage(2), FakeStage(3)])
                self.sequence_manager = FakeSeqManager()

            def __getitem__(self, s):
                return FakeStage(0)

        class FakeDistributedModel:
            def __init__(self):
                self.transformer = types.SimpleNamespace(
                    word_embeddings=lambda ids: torch.ones((1, ids.shape[1], 4), dtype=torch.float32),
                    word_embeddings_layernorm=lambda e: e,
                    h=FakeRemoteList(),
                    ln_f=lambda h: h,
                )

            def eval(self):
                return self

            def lm_head(self, x):
                logits = torch.zeros((x.shape[0], x.shape[1], 10), dtype=torch.float32)
                logits[..., 7] = 5.0
                return logits

        class FakeReferenceModel:
            def eval(self):
                return self

            def generate(self, input_ids, max_new_tokens=2, **kwargs):
                extra = torch.full((1, max_new_tokens), 7, dtype=torch.long)
                return torch.cat([input_ids, extra], dim=1)

        class FakeTokenizer:
            eos_token_id = 99

            def __call__(self, text, return_tensors="pt"):
                return {"input_ids": torch.tensor([[1, 2]], dtype=torch.long)}

            def decode(self, ids, skip_special_tokens=True):
                return " ".join(f"tok{i}" for i in ids)

        fake_transformers = types.ModuleType("transformers")
        fake_transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **k: FakeTokenizer())
        fake_transformers.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **k: FakeReferenceModel())
        fake_petals = types.ModuleType("petals")
        fake_petals.AutoDistributedModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **k: FakeDistributedModel())

        job = {
            "id": "a" * 32,
            "prefix": "ct-" + "a" * 32,
            "bootstrap": ["/ip4/192.168.100.7/tcp/31331/p2p/test"],
            "plan": [{"node_id": "n1", "peer_id": "p1", "start": 0, "end": 4}],
            "spec": {"model_id": "bigscience/bloom-560m", "revision": "main", "prompt": "Hello", "max_new_tokens": 3, "benchmark": True},
        }
        with patch.dict(sys.modules, {"transformers": fake_transformers, "petals": fake_petals}):
            res = gen_mod.execute(job, lambda status, extra=None: events.append((status, extra)))

        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["result"], "tok7 tok7 tok7")
        m = res["metrics"]
        self.assertEqual(m["generated_tokens"], 3)
        self.assertGreater(m["token_confidence_pct"], 80.0)
        self.assertGreater(m["perplexity"], 1.0)
        self.assertEqual(m["finite_logits_pct"], 100.0)
        self.assertEqual(m["baseline_token_match_pct"], 100.0)
        self.assertEqual(m["baseline_prefix_match_tokens"], 3)
        self.assertTrue(m["baseline_exact_text_match"])
        running_updates = [extra for st, extra in events if st == "running" and (extra or {}).get("generated_tokens", 0) > 0]
        self.assertEqual([u["generated_tokens"] for u in running_updates], [1, 2, 3])
        self.assertEqual(running_updates[0]["partial_result"], "tok7")

    def test_petals_control_status_attaches_download_progress_and_log_tail(self):
        pc_mod = load_module("pc_under_test", ROOT / "08-provider-node" / "05-desktop-app-shell" / "petals_control.py")
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = pc_mod.PetalsControl(tmp)
            ctrl.job_id = "b" * 32
            ctrl.container = "ct-layer-test"
            folder = ctrl.root / ctrl.job_id
            folder.mkdir(parents=True)
            (folder / "status.json").write_text(json.dumps({"job_id": ctrl.job_id, "status": "loading"}))
            (folder / "request.json").write_text(json.dumps({"spec": {"model_id": "bigscience/bloom-560m", "weights_bytes": 1000}}))
            (folder / "layer.log").write_text("line1\nline2\nCT_STATUS loading\n")
            with patch.object(pc_mod, "command", side_effect=["true", "500"]):
                st = ctrl.status(renew=False)
            self.assertEqual(st["status"], "loading")
            self.assertEqual(st["progress"]["downloaded_bytes"], 500)
            self.assertEqual(st["progress"]["total_bytes"], 1000)
            self.assertEqual(st["progress"]["percent"], 50)
            self.assertEqual(st["progress"]["log_tail"], ["line1", "line2", "CT_STATUS loading"])

    def test_orchestrator_host_lan_state_and_weights_resolution(self):
        orch_dir = str(ROOT / "orchestrator" / "app")
        if orch_dir not in sys.path:
            sys.path.insert(0, orch_dir)
        with patch("sqlalchemy.create_engine", side_effect=RuntimeError("isolated")), \
                tempfile.TemporaryDirectory() as tmp:
            import main_production as orch
            from fastapi.testclient import TestClient
            net_file = Path(tmp) / "host-network.json"
            with patch.object(orch, "HOST_NETWORK_FILE", net_file), \
                    patch.dict(orch.os.environ, {"COMPUTETORRENT_API_TOKEN": "tok-123"}), \
                    patch.object(orch, "API_TOKEN", "tok-123"):
                orch._RUNTIME_HOST_NETWORK.clear()
                saved = orch.record_host_lan_state("192.168.43.18", interface="Wi-Fi", source="local-provider-wifi")
                self.assertEqual(saved["lan_ip"], "192.168.43.18")
                self.assertTrue(net_file.is_file())
                with TestClient(orch.app) as client:
                    resp = client.get("/api/network", headers={"Authorization": "Bearer tok-123"})
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["lan_host"], "192.168.43.18")
                self.assertEqual(body["lan_interface"], "Wi-Fi")
                self.assertEqual(body["lan_address"], "ws://192.168.43.18:8001/ws/seeder")

        import distributed as dist_mod

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return json.dumps({
                    "sha": "a" * 40,
                    "siblings": [
                        {"rfilename": "model.safetensors", "size": 1118459525},
                        {"rfilename": "pytorch_model.bin", "size": 1118531895},
                    ],
                }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            resolved = dist_mod.resolve_revision({"model_id": "bigscience/bloom-560m", "revision": "main"})
        self.assertEqual(resolved["weights_bytes"], 1118459525)

        cloned = dist_mod.parse_manifest({
            "model_id": "bigscience/bloom-560m",
            "revision": "a" * 40,
            "prompt": "What is the capital of Italy",
            "max_new_tokens": 32,
            "min_peers": 2,
            "max_peers": 4,
            "benchmark": False,
            "weights_bytes": 1118459525,
        }, "json")
        self.assertNotIn("weights_bytes", cloned)
        self.assertEqual(cloned["prompt"], "What is the capital of Italy")
        with self.assertRaises(ValueError):
            dist_mod.parse_manifest({"model_id": "bigscience/bloom-560m", "prompt": "hi", "unexpected_key": 1}, "json")

    def test_generate_job_prompt_formatting_and_repeat_blocking(self):
        import torch

        gen_mod = load_module("generate_job_fmt_test", ROOT / "08-provider-node" / "06-petals-runtime" / "generate_job.py")
        plain_tok = types.SimpleNamespace(chat_template=None)
        qa_prompt, qa_mode = gen_mod._format_prompt("bigscience/bloom-560m", plain_tok, "What is the capital of US")
        self.assertEqual(qa_mode, "qa")
        self.assertEqual(qa_prompt, "Q: What is the capital of US?\nA:")

        instruct_prompt, instruct_mode = gen_mod._format_prompt("bigscience/bloomz-560m", plain_tok, "What is the capital of US")
        self.assertEqual(instruct_mode, "raw")
        self.assertEqual(instruct_prompt, "What is the capital of US?")

        scores = torch.tensor([0.1, 0.2, 9.0, 5.0])
        blocked = gen_mod._block_repeated_ngrams([1, 2, 2, 2], scores.clone(), ngram_size=3)
        self.assertEqual(blocked[2].item(), float("-inf"))
        self.assertEqual(int(blocked.argmax().item()), 3)

        cleaned, stopped = gen_mod._clean_output_text("  Washington, DC.\nQ: Next question", "qa")
        self.assertTrue(stopped)
        self.assertEqual(cleaned, "Washington, DC.")


if __name__ == "__main__":
    unittest.main()
