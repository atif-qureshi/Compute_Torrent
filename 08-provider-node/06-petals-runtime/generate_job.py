"""BLOOM pipeline generation with committed boundary traces and trusted replay.

Local research verification, not a blockchain or full VeriLLM implementation.
Actual generation activations are captured before the audit challenge is chosen.
"""
import contextlib
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def atomic(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value))
    temp.replace(path)


def execute(job, progress):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from petals import AutoDistributedModelForCausalLM
    from hivemind import PeerID
    spec = job["spec"]
    if spec["model_id"] not in {"bigscience/bloom-560m", "bigscience/bloomz-560m"}:
        raise ValueError("Unsupported model")
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=spec["revision"], trust_remote_code=False)
    model = AutoDistributedModelForCausalLM.from_pretrained(spec["model_id"], revision=spec["revision"],
        initial_peers=job["bootstrap"], dht_prefix=job["prefix"], torch_dtype=torch.float32,
        allowed_servers=[PeerID.from_base58(s["peer_id"]) for s in job["plan"]],
        max_retries=2, request_timeout=60, show_route=True, trust_remote_code=False)
    model.eval()
    remote = model.transformer.h
    # The allocator fixes complete non-overlapping intervals across >=2 peers.
    stages = [remote[s["start"]:s["end"]] for s in job["plan"]]
    deadline = time.monotonic() + 600
    while True:
        try:
            for layer_stage in stages:
                layer_stage.sequence_manager.make_sequence(mode="min_latency")
            break
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError("No complete Petals route after 10 minutes; model layers are unavailable")
            time.sleep(5)
            for layer_stage in stages:
                if layer_stage.sequence_manager.is_alive():
                    layer_stage.sequence_manager.update(wait=False)

    def generate(prompt, limit):
        tokens = tokenizer(prompt, return_tensors="pt")["input_ids"]
        if tokens.shape[1] + limit > 512:
            raise ValueError("Prompt plus output exceeds the small-model limit of 512 tokens")
        original = tokens.clone()
        output, trace, activations = [], [], []
        with torch.inference_mode(), contextlib.ExitStack() as stack:
            for layer_stage in stages:
                stack.enter_context(layer_stage.inference_session(max_length=tokens.shape[1] + limit))
            for step in range(limit):
                hidden = model.transformer.word_embeddings_layernorm(model.transformer.word_embeddings(tokens))
                step_values = []
                for index, layer_stage in enumerate(stages):
                    hidden = layer_stage(hidden)
                    boundary = hidden[:, -1:, :].detach().cpu().float().clone()
                    if not torch.isfinite(boundary).all():
                        raise RuntimeError("Provider returned non-finite activations")
                    step_values.append(boundary)
                    trace.append({"step": step, "stage": index,
                        "activation_sha256": hashlib.sha256(boundary.numpy().tobytes()).hexdigest()})
                activations.append(step_values)
                logits = model.lm_head(model.transformer.ln_f(hidden[:, -1:, :]))
                token = int(logits[0, -1].argmax())
                output.append(token)
                tokens = torch.tensor([[token]], dtype=torch.long)
                if token == tokenizer.eos_token_id:
                    break
        return original, output, trace, activations

    progress("running")
    original, output, trace, activations = generate(spec["prompt"], spec["max_new_tokens"])
    envelope = {"job_id": job["id"], "model_id": spec["model_id"], "revision": spec["revision"],
        "prompt_sha256": hashlib.sha256(spec["prompt"].encode()).hexdigest(),
        "route": job["plan"], "token_ids": output, "trace": trace}
    commitment = digest(envelope)
    nonce = secrets.token_hex(32)  # Chosen after generation/commitment.
    samples = sorted(range(len(output)), key=lambda n: digest([nonce, commitment, n]))[:min(4, len(output))]
    progress("verifying")
    reference = AutoModelForCausalLM.from_pretrained(spec["model_id"], revision=spec["revision"],
        torch_dtype=torch.float32, trust_remote_code=False).eval()

    def replay(original, output, captured, samples):
        context = torch.cat([original, torch.tensor([output[:-1]], dtype=torch.long)], dim=1)
        start = original.shape[1] - 1
        boundaries = {}
        hooks = []
        for i, stage in enumerate(job["plan"]):
            def capture(_module, _input, result, index=i):
                boundaries[index] = result[0][:, start:, :].detach().float().clone()
            hooks.append(reference.transformer.h[stage["end"] - 1].register_forward_hook(capture))
        try:
            with torch.inference_mode():
                logits = reference(context, use_cache=False).logits[0, start:, :]
            predicted = logits.argmax(dim=-1).tolist()
            token_match = predicted == output
            checks = []
            for step in samples:
                for index, stage in enumerate(job["plan"]):
                    expected = boundaries[index][:, step:step+1, :]
                    actual = captured[step][index]
                    passed = bool(torch.allclose(expected, actual, rtol=.02, atol=.02))
                    checks.append({"step": step, "node_id": stage["node_id"], "end_layer": stage["end"],
                        "passed": passed, "max_abs_error": float((expected - actual).abs().max())})
            return {"token_match": token_match, "checks": checks,
                    "passed": token_match and all(c["passed"] for c in checks)}
        finally:
            for hook in hooks:
                hook.remove()

    verification = replay(original, output, activations, samples)
    # Every small-model job also gets an undisclosed random prompt. Workers see
    # ordinary activations, never expected tokens or a canary flag.
    progress("canary")
    canary_prompt = secrets.choice([
        "Continue the sentence: The sun rises in the",
        "Translate to French: Good morning.",
        "A computer uses memory to",
        "The sequence is one, two, three,",
    ]) + " " * secrets.randbelow(3)
    c_input, c_output, c_trace, c_activations = generate(canary_prompt, 4)
    canary = replay(c_input, c_output, c_activations, list(range(len(c_output))))
    passed = verification["passed"] and canary["passed"]
    receipt = {"protocol": "local-boundary-replay-v1", "full_verillm": False,
        "commitment_sha256": commitment, "envelope": envelope, "challenge_nonce": nonce,
        "sample_steps": samples, "rtol": .02, "atol": .02,
        "verification": verification, "canary": {"passed": canary["passed"], "checks": canary["checks"],
            "token_match": canary["token_match"], "trace_sha256": digest(c_trace)},
        "trust": "Coordinator/reference model trusted; sampled boundary checks; no on-chain disputes"}
    return {"status": "completed" if passed else "failed", "result": tokenizer.decode(output, skip_special_tokens=True),
        "receipt": receipt, "error": None if passed else "Verification mismatch: inspect layer replay/canary receipt; no verified reward issued"}


if __name__ == "__main__":
    request = Path(sys.argv[1])
    job = json.loads(request.read_text())
    output_path = request.with_name(job["id"] + ".result.json")
    try:
        result = execute(job, lambda status: atomic(request.with_name(job["id"] + ".progress.json"), {"status": status}))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = {"status": "failed", "error": str(exc)[:1000]}
    atomic(output_path, result)
