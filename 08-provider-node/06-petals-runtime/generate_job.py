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
    started = time.perf_counter()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from petals import AutoDistributedModelForCausalLM
    spec = job["spec"]
    revision = spec.get("revision") if spec.get("revision") != "main" else None
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=revision, trust_remote_code=True)
    model = AutoDistributedModelForCausalLM.from_pretrained(spec["model_id"], revision=revision,
        initial_peers=job["bootstrap"], dht_prefix=job["prefix"], torch_dtype=torch.float32,
        allowed_servers=[s["peer_id"] for s in job["plan"]],
        max_retries=2, request_timeout=60, show_route=True, trust_remote_code=True)
    model.eval()
    model_load_seconds = time.perf_counter() - started
    remote = getattr(model, "transformer", getattr(model, "model", None))
    if hasattr(remote, "h"):
        remote = remote.h
    elif hasattr(remote, "layers"):
        remote = remote.layers
    elif hasattr(model, "layers"):
        remote = model.layers
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
                if hasattr(model, "transformer") and hasattr(model.transformer, "word_embeddings"):
                    embeds = model.transformer.word_embeddings(tokens)
                    hidden = model.transformer.word_embeddings_layernorm(embeds) if hasattr(model.transformer, "word_embeddings_layernorm") else embeds
                elif hasattr(model, "model") and hasattr(model.model, "embed_tokens"):
                    hidden = model.model.embed_tokens(tokens)
                else:
                    hidden = model.get_input_embeddings()(tokens)
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
                if hasattr(model, "lm_head"):
                    ln = getattr(getattr(model, "transformer", getattr(model, "model", None)), "ln_f", None) or getattr(getattr(model, "model", None), "norm", None)
                    normed = ln(hidden[:, -1:, :]) if ln else hidden[:, -1:, :]
                    logits = model.lm_head(normed)
                else:
                    logits = model(inputs_embeds=hidden).logits
                token = int(logits[0, -1].argmax())
                output.append(token)
                tokens = torch.tensor([[token]], dtype=torch.long)
                if token == tokenizer.eos_token_id:
                    break
        return original, output, trace, activations

    progress("running")
    generation_started = time.perf_counter()
    original, output, trace, activations = generate(spec["prompt"], spec["max_new_tokens"])
    generation_seconds = time.perf_counter() - generation_started
    envelope = {"job_id": job["id"], "model_id": spec["model_id"], "revision": spec["revision"],
        "prompt_sha256": hashlib.sha256(spec["prompt"].encode()).hexdigest(),
        "route": job["plan"], "token_ids": output, "trace": trace}
    commitment = digest(envelope)
    nonce = secrets.token_hex(32)  # Chosen after generation/commitment.
    samples = sorted(range(len(output)), key=lambda n: digest([nonce, commitment, n]))[:min(4, len(output))]
    progress("verifying")
    reference = AutoModelForCausalLM.from_pretrained(spec["model_id"], revision=revision,
        torch_dtype=torch.float32, trust_remote_code=True).eval()

    def replay(original, output, captured):
        context = torch.cat([original, torch.tensor([output[:-1]], dtype=torch.long)], dim=1)
        start = original.shape[1] - 1
        boundaries = {}
        hooks = []
        reference_layers = getattr(getattr(reference, "transformer", getattr(reference, "model", None)), "h", getattr(getattr(reference, "model", None), "layers", getattr(reference, "layers", [])))
        for i, stage in enumerate(job["plan"]):
            def capture(_module, _input, result, index=i):
                boundaries[index] = result[0][:, start:, :].detach().float().clone()
            hooks.append(reference_layers[stage["end"] - 1].register_forward_hook(capture))
        try:
            with torch.inference_mode():
                logits = reference(context, use_cache=False).logits[0, start:, :]
            predicted = logits.argmax(dim=-1).tolist()
            token_match = predicted == output
            checks = []
            for step in range(len(output)):
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

    verification_started = time.perf_counter()
    verification = replay(original, output, activations)
    verification_seconds = time.perf_counter() - verification_started
    # Every small-model job also gets an undisclosed random prompt. Workers see
    # ordinary activations, never expected tokens or a canary flag.
    progress("canary")
    canary_started = time.perf_counter()
    canary_prompt = secrets.choice([
        "Continue the sentence: The sun rises in the",
        "Translate to French: Good morning.",
        "A computer uses memory to",
        "The sequence is one, two, three,",
    ]) + " " * secrets.randbelow(3)
    c_input, c_output, c_trace, c_activations = generate(canary_prompt, 4)
    canary = replay(c_input, c_output, c_activations)
    canary_seconds = time.perf_counter() - canary_started
    passed = verification["passed"] and canary["passed"]
    baseline_seconds = None
    baseline_tokens = None
    if passed and spec.get("benchmark", False):
        progress("benchmarking")
        baseline_started = time.perf_counter()
        with torch.inference_mode():
            baseline = reference.generate(original, max_new_tokens=spec["max_new_tokens"],
                do_sample=False, use_cache=True, pad_token_id=tokenizer.eos_token_id)
        baseline_seconds = round(time.perf_counter() - baseline_started, 3)
        baseline_tokens = int(baseline.shape[1] - original.shape[1])
    receipt = {"protocol": "local-boundary-replay-v1", "full_verillm": False,
        "commitment_sha256": commitment, "envelope": envelope, "challenge_nonce": nonce,
        "sample_steps": samples, "comparison_scope": "all_generated_positions_at_every_stage",
        "rtol": .02, "atol": .02,
        "verification": verification, "canary": {"passed": canary["passed"], "checks": canary["checks"],
            "token_match": canary["token_match"], "trace_sha256": digest(c_trace)},
        "trust": "Coordinator/reference model trusted; all generated stage boundaries checked locally; no independent provider proofs or on-chain disputes"}
    metrics = {"model_load_seconds": round(model_load_seconds, 3),
        "distributed_generation_seconds": round(generation_seconds, 3),
        "verification_seconds": round(verification_seconds, 3),
        "canary_seconds": round(canary_seconds, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "generated_tokens": len(output), "provider_count": len(job["plan"])}
    if baseline_seconds is not None:
        metrics.update(single_node_reference_seconds=baseline_seconds,
            single_node_reference_tokens=baseline_tokens,
            reference_device="coordinator_cpu")
    return {"status": "completed" if passed else "failed", "result": tokenizer.decode(output, skip_special_tokens=True),
        "metrics": metrics,
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
