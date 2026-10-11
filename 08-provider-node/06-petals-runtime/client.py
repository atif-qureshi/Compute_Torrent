"""Generate text through real Petals remote Transformer blocks."""
from __future__ import annotations

import argparse
import sys


def generate(model_name: str, prompt: str, *, max_new_tokens: int = 64,
             initial_peers: list[str] | None = None, dht_prefix: str | None = None,
             temperature: float = 0.7) -> str:
    try:
        import torch
        from transformers import AutoTokenizer
        from petals import AutoDistributedModelForCausalLM
    except ImportError as error:
        raise RuntimeError(
            "Petals runtime is not installed. Install this folder's requirements-petals.txt "
            "in Python 3.10+ (Linux/WSL recommended)."
        ) from error

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    client_options = {"show_route": "inference"}
    if initial_peers:
        client_options["initial_peers"] = initial_peers
    if dht_prefix:
        client_options["dht_prefix"] = dht_prefix
    model = AutoDistributedModelForCausalLM.from_pretrained(model_name, **client_options)
    encoded = tokenizer(prompt, return_tensors="pt")
    generation_options = {"max_new_tokens": max_new_tokens, "do_sample": temperature > 0}
    if temperature > 0:
        generation_options["temperature"] = temperature
    with torch.inference_mode():
        output = model.generate(**encoded, **generation_options)
    return tokenizer.decode(output[0], skip_special_tokens=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM generation through Petals peers")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--initial-peer", dest="initial_peers", action="append", default=[])
    parser.add_argument("--dht-prefix")
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()
    if args.max_new_tokens < 1 or args.max_new_tokens > 2048:
        parser.error("--max-new-tokens must be between 1 and 2048")
    print(generate(args.model, args.prompt, max_new_tokens=args.max_new_tokens,
                   initial_peers=args.initial_peers, dht_prefix=args.dht_prefix,
                   temperature=args.temperature))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Petals inference failed: {error}", file=sys.stderr)
        raise SystemExit(2)
