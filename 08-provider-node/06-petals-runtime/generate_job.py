"""Generate tokens using assigned Petals stages."""
import contextlib
import json
import math
import os
import sys
import threading
import time
from pathlib import Path


def atomic(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value))
    temp.replace(path)


def _model_cache_bytes(model_id: str) -> int:
    hub_cache = Path(os.getenv("HF_HUB_CACHE", str(Path(os.getenv("HF_HOME", "/cache/huggingface")) / "hub")))
    blobs_dir = hub_cache / ("models--" + model_id.replace("/", "--")) / "blobs"
    if not blobs_dir.is_dir():
        return 0
    total = 0
    try:
        for item in blobs_dir.iterdir():
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _safe_perplexity(log_probs):
    if not log_probs:
        return None
    avg_nll = max(0.0, min(-sum(log_probs) / len(log_probs), 20.0))
    return round(math.exp(avg_nll), 3)


_QUESTION_PREFIXES = (
    "what ", "what's ", "who ", "who's ", "where ", "where's ",
    "when ", "why ", "how ", "which ", "is ", "are ", "was ",
    "were ", "can ", "could ", "do ", "does ", "did ",
    "name ", "define ", "explain ", "tell me ", "list ",
)
_INTERROGATIVE_PREFIXES = _QUESTION_PREFIXES[:19]
_STOP_MARKERS = ("\nQ:", "\nQuestion:", "\nUser:", "\n\nQ:", "<|user|>", "<|im_end|>")


def _format_prompt(model_id: str, tokenizer, raw_prompt: str):
    """Format user prompt cleanly for instruct/chat or base completion models."""
    text = (raw_prompt or "").strip()
    if not text:
        return raw_prompt or "", "raw"

    if getattr(tokenizer, "chat_template", None) and hasattr(tokenizer, "apply_chat_template"):
        try:
            rendered = tokenizer.apply_chat_template(
                [{"role": "user", "content": text}],
                tokenize=False,
                add_generation_prompt=True,
            )
            return rendered, "chat"
        except Exception:
            pass

    lower = text.lower()
    if any(marker in text for marker in ("\nA:", "\nAnswer:", "Answer:", "<|assistant|>")):
        return text, "raw"

    is_question = text.endswith("?") or lower.startswith(_QUESTION_PREFIXES)
    normalized = text
    if text[-1:] not in "?.!:" and lower.startswith(_INTERROGATIVE_PREFIXES):
        normalized = f"{text}?"

    mid = (model_id or "").lower()
    is_instruct = any(tag in mid for tag in ("bloomz", "instruct", "-chat", "alpaca", "vicuna"))
    if is_question and not is_instruct:
        return f"Q: {normalized}\nA:", "qa"
    return normalized, "raw"


def _block_repeated_ngrams(sequence, scores, ngram_size: int = 3):
    """Mask next tokens that would repeat any n-gram already present in `sequence`."""
    if ngram_size < 2 or len(sequence) < ngram_size - 1:
        return scores
    prefix = tuple(sequence[-(ngram_size - 1):])
    banned = set()
    for idx in range(len(sequence) - ngram_size + 1):
        if tuple(sequence[idx : idx + ngram_size - 1]) == prefix:
            banned.add(sequence[idx + ngram_size - 1])
    if not banned:
        return scores
    adjusted = scores.clone()
    for tok in banned:
        adjusted[tok] = float("-inf")
    return adjusted


def _clean_output_text(text: str, mode: str):
    """Trim chat/QA whitespace and cut cleanly before synthetic next-turn markers."""
    stopped = False
    cut_at = None
    for marker in _STOP_MARKERS:
        idx = text.find(marker)
        if idx != -1 and (cut_at is None or idx < cut_at):
            cut_at = idx
            stopped = True
    if cut_at is not None:
        text = text[:cut_at]
    if mode in ("qa", "chat"):
        text = text.lstrip()
    return text, stopped


def _emit(progress, status, extra=None):
    if extra is None:
        progress(status)
        return
    try:
        progress(status, extra)
    except TypeError:
        progress(status)


def execute(job, progress):
    managers = []
    try:
        return _execute(job, progress, managers)
    finally:
        unique = {id(manager): manager for manager in managers}.values()
        dhts = {}
        for manager in unique:
            dhts[id(manager.dht)] = manager.dht
            try:
                manager.shutdown()
            except Exception:
                pass
        for dht in dhts.values():
            try:
                dht.shutdown()
            except Exception:
                pass


def _execute(job, progress, managers):
    started = time.perf_counter()
    import torch
    from transformers import AutoTokenizer
    from petals import AutoDistributedModelForCausalLM

    spec = job["spec"]
    revision = spec.get("revision") if spec.get("revision") != "main" else None
    weights_bytes = int(spec.get("weights_bytes") or 0)
    torch.set_num_threads(2)

    stop_dl_watch = threading.Event()

    def watch_download():
        last_bytes = _model_cache_bytes(spec["model_id"])
        last_t = time.perf_counter()
        while not stop_dl_watch.is_set():
            now_bytes = _model_cache_bytes(spec["model_id"])
            now_t = time.perf_counter()
            dt = max(now_t - last_t, 0.001)
            speed_bps = max(0, int((now_bytes - last_bytes) / dt))
            last_bytes, last_t = now_bytes, now_t
            percent = None
            if weights_bytes > 0 and now_bytes > 0:
                percent = min(99, max(1, int((now_bytes * 100) / weights_bytes)))
            _emit(progress, "downloading_model", {
                "downloaded_bytes": now_bytes,
                "total_bytes": weights_bytes or None,
                "percent": percent,
                "speed_bps": speed_bps,
                "elapsed_seconds": round(now_t - started, 1),
            })
            stop_dl_watch.wait(2.0)

    _emit(progress, "downloading_model", {
        "downloaded_bytes": _model_cache_bytes(spec["model_id"]),
        "total_bytes": weights_bytes or None,
        "percent": 0 if weights_bytes else None,
        "elapsed_seconds": 0.0,
    })
    dl_thread = threading.Thread(target=watch_download, daemon=True)
    dl_thread.start()
    try:
        tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=revision, trust_remote_code=False)
        model = AutoDistributedModelForCausalLM.from_pretrained(
            spec["model_id"],
            revision=revision,
            initial_peers=job["bootstrap"],
            dht_prefix=job["prefix"],
            torch_dtype=torch.float32,
            allowed_servers=[s["peer_id"] for s in job["plan"]],
            max_retries=2,
            request_timeout=60,
            show_route=True,
            trust_remote_code=False,
        )
    finally:
        stop_dl_watch.set()
        dl_thread.join(timeout=1.0)

    model.eval()
    _emit(progress, "connecting_layers", {
        "downloaded_bytes": _model_cache_bytes(spec["model_id"]),
        "total_bytes": weights_bytes or None,
        "percent": 100 if weights_bytes else None,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    })

    remote = getattr(model, "transformer", getattr(model, "model", None))
    if hasattr(remote, "h"):
        remote = remote.h
    elif hasattr(remote, "layers"):
        remote = remote.layers
    elif hasattr(model, "layers"):
        remote = model.layers
    managers.append(remote.sequence_manager)
    stages = [remote[s["start"]:s["end"]] for s in job["plan"]]
    managers.extend(stage.sequence_manager for stage in stages)
    deadline = time.monotonic() + 600
    while True:
        try:
            for layer_stage in stages:
                layer_stage.sequence_manager.make_sequence(mode="min_latency")
            break
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError("No complete Petals route after 10 minutes; model layers are unavailable")
            _emit(progress, "connecting_layers", {
                "elapsed_seconds": round(time.perf_counter() - started, 1),
            })
            time.sleep(5)
            for layer_stage in stages:
                if layer_stage.sequence_manager.is_alive():
                    layer_stage.sequence_manager.update(wait=False)

    model_load_seconds = time.perf_counter() - started
    rpc_timings = []
    chosen_probs = []
    log_probs = []
    finite_logit_steps = 0

    formatted_prompt, prompt_mode = _format_prompt(spec["model_id"], tokenizer, spec["prompt"])

    def build_live_metrics(output_ids, gen_elapsed, prefill_sec):
        count = len(output_ids)
        partial = ""
        if count:
            partial, _ = _clean_output_text(tokenizer.decode(output_ids, skip_special_tokens=True), prompt_mode)
        return {
            "partial_result": partial,
            "generated_tokens": count,
            "max_new_tokens": int(spec["max_new_tokens"]),
            "model_load_seconds": round(model_load_seconds, 3),
            "distributed_generation_seconds": round(gen_elapsed, 3),
            "throughput_tokens_per_sec": round(count / gen_elapsed, 2) if gen_elapsed > 0 and count > 0 else 0.0,
            "latency_per_token_ms": round((gen_elapsed / count) * 1000, 2) if count > 0 else 0.0,
            "prefill_latency_seconds": round(prefill_sec, 3) if prefill_sec is not None else None,
            "token_confidence_pct": round(100.0 * sum(chosen_probs) / len(chosen_probs), 2) if chosen_probs else None,
            "perplexity": _safe_perplexity(log_probs),
            "finite_logits_pct": round(100.0 * finite_logit_steps / count, 2) if count else None,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        }

    def generate(prompt, limit):
        nonlocal finite_logit_steps
        tokens = tokenizer(prompt, return_tensors="pt")["input_ids"]
        if tokens.shape[1] + limit > 512:
            raise ValueError("Prompt plus output exceeds the small-model limit of 512 tokens")
        original = tokens.clone()
        prompt_ids = original[0].tolist()
        output = []
        gen_started = time.perf_counter()
        prefill_sec = None
        _emit(progress, "running", build_live_metrics(output, 0.0, None))
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
                step_rpc_sum = 0.0
                for index, layer_stage in enumerate(stages):
                    rpc_started = time.perf_counter()
                    hidden = layer_stage(hidden)
                    rpc_elapsed = time.perf_counter() - rpc_started
                    step_rpc_sum += rpc_elapsed
                    assignment = job['plan'][index]
                    rpc_timings.append(dict(
                        node_id=assignment['node_id'],
                        phase='prefill' if step == 0 else 'decode',
                        blocks=assignment['end'] - assignment['start'],
                        input_tokens=int(tokens.shape[1]),
                        seconds=rpc_elapsed,
                    ))
                if step == 0:
                    prefill_sec = step_rpc_sum
                if hasattr(model, "lm_head"):
                    ln = getattr(getattr(model, "transformer", getattr(model, "model", None)), "ln_f", None) or getattr(getattr(model, "model", None), "norm", None)
                    normed = ln(hidden[:, -1:, :]) if ln else hidden[:, -1:, :]
                    logits = model.lm_head(normed)
                else:
                    logits = model(inputs_embeds=hidden).logits

                step_logits = logits[0, -1].float()
                filtered_logits = _block_repeated_ngrams(prompt_ids + output, step_logits, ngram_size=3)
                token = int(filtered_logits.argmax())
                try:
                    if bool(torch.isfinite(step_logits).all().item()):
                        finite_logit_steps += 1
                    safe_logits = torch.nan_to_num(step_logits, nan=-1e9, posinf=1e4, neginf=-1e9)
                    probs = torch.softmax(safe_logits, dim=-1)
                    logp = torch.log_softmax(safe_logits, dim=-1)
                    chosen_probs.append(float(probs[token].item()))
                    log_probs.append(float(logp[token].item()))
                except Exception:
                    pass

                output.append(token)
                decoded_so_far, hit_stop = _clean_output_text(tokenizer.decode(output, skip_special_tokens=True), prompt_mode)
                _emit(progress, "running", build_live_metrics(output, time.perf_counter() - gen_started, prefill_sec))
                tokens = torch.tensor([[token]], dtype=torch.long)
                if token == tokenizer.eos_token_id or hit_stop:
                    break
                if prompt_mode == "qa" and len(output) >= 6 and decoded_so_far.rstrip().endswith(".") and decoded_so_far.endswith("\n"):
                    break
        return original, output, time.perf_counter() - gen_started

    original, output, generation_seconds = generate(formatted_prompt, spec["max_new_tokens"])
    dist_text, _ = _clean_output_text(tokenizer.decode(output, skip_special_tokens=True), prompt_mode)
    tokens_count = len(output)
    throughput = round(tokens_count / generation_seconds, 2) if generation_seconds > 0 else 0.0
    latency_per_token_ms = round((generation_seconds / tokens_count) * 1000, 2) if tokens_count > 0 else 0.0
    prefill_seconds = round(sum(t['seconds'] for t in rpc_timings if t.get('phase') == 'prefill'), 3)

    metrics = {
        "model_load_seconds": round(model_load_seconds, 3),
        "distributed_generation_seconds": round(generation_seconds, 3),
        "throughput_tokens_per_sec": throughput,
        "latency_per_token_ms": latency_per_token_ms,
        "prefill_latency_seconds": prefill_seconds,
        "total_seconds": round(time.perf_counter() - started, 3),
        "generated_tokens": tokens_count,
        "max_new_tokens": int(spec["max_new_tokens"]),
        "provider_count": len(job["plan"]),
        "token_confidence_pct": round(100.0 * sum(chosen_probs) / len(chosen_probs), 2) if chosen_probs else None,
        "perplexity": _safe_perplexity(log_probs),
        "finite_logits_pct": round(100.0 * finite_logit_steps / tokens_count, 2) if tokens_count else None,
        "stage_rpc_timings": rpc_timings,
    }

    if spec.get("benchmark", False):
        from transformers import AutoModelForCausalLM

        _emit(progress, "benchmarking", {
            "partial_result": dist_text,
            "generated_tokens": tokens_count,
            "max_new_tokens": int(spec["max_new_tokens"]),
            "model_load_seconds": metrics["model_load_seconds"],
            "distributed_generation_seconds": metrics["distributed_generation_seconds"],
            "throughput_tokens_per_sec": throughput,
            "latency_per_token_ms": latency_per_token_ms,
            "prefill_latency_seconds": prefill_seconds,
            "token_confidence_pct": metrics["token_confidence_pct"],
            "perplexity": metrics["perplexity"],
            "finite_logits_pct": metrics["finite_logits_pct"],
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        })
        reference = AutoModelForCausalLM.from_pretrained(
            spec["model_id"],
            revision=revision,
            torch_dtype=torch.float32,
            trust_remote_code=False,
        ).eval()
        baseline_started = time.perf_counter()
        with torch.inference_mode():
            baseline = reference.generate(
                original,
                max_new_tokens=spec["max_new_tokens"],
                do_sample=False,
                no_repeat_ngram_size=3,
                use_cache=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        baseline_seconds = round(time.perf_counter() - baseline_started, 3)
        raw_baseline_out = baseline[0, original.shape[1]:].tolist()
        baseline_out = []
        for tok in raw_baseline_out:
            baseline_out.append(tok)
            decoded_base, hit_stop = _clean_output_text(tokenizer.decode(baseline_out, skip_special_tokens=True), prompt_mode)
            if hit_stop or (prompt_mode == "qa" and len(baseline_out) >= 6 and decoded_base.rstrip().endswith(".") and decoded_base.endswith("\n")):
                break
        baseline_tokens = len(baseline_out)
        baseline_text, _ = _clean_output_text(tokenizer.decode(baseline_out, skip_special_tokens=True), prompt_mode)
        compared = max(len(output), len(baseline_out))
        matches = sum(1 for a, b in zip(output, baseline_out) if a == b)
        prefix_matches = 0
        for a, b in zip(output, baseline_out):
            if a != b:
                break
            prefix_matches += 1
        metrics.update(
            single_node_reference_seconds=baseline_seconds,
            single_node_reference_tokens=baseline_tokens,
            single_node_throughput_tokens_per_sec=round(baseline_tokens / baseline_seconds, 2) if baseline_seconds > 0 else 0.0,
            speedup=round(baseline_seconds / generation_seconds, 2) if generation_seconds > 0 else None,
            single_node_reference_text=baseline_text,
            baseline_token_match_pct=round(100.0 * matches / compared, 2) if compared > 0 else 100.0,
            baseline_prefix_match_tokens=prefix_matches,
            baseline_compared_tokens=compared,
            baseline_exact_text_match=(dist_text == baseline_text),
            total_seconds=round(time.perf_counter() - started, 3),
            reference_device="coordinator_cpu",
        )

    return {"status": "completed", "result": dist_text, "metrics": metrics, "error": None}


if __name__ == "__main__":
    request = Path(sys.argv[1])
    job = json.loads(request.read_text())
    output_path = request.with_name(job["id"] + ".result.json")
    try:
        result = execute(
            job,
            lambda status, extra=None: atomic(
                request.with_name(job["id"] + ".progress.json"),
                {"status": status, **(extra or {})},
            ),
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = {"status": "failed", "error": str(exc)[:1000]}
    atomic(output_path, result)
