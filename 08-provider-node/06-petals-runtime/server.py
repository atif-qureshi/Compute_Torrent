"""Start an upstream Petals block server with resource-aware placement.

Petals owns block discovery, contiguous range selection, throughput reporting,
and rebalancing. This wrapper only validates configuration and starts its
official server implementation; it does not emulate tensor execution.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def build_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-m", "petals.cli.run_server", args.model]
    if args.swarm_mode == "new":
        command.append("--new_swarm")
    elif args.initial_peers:
        command.extend(["--initial_peers", *args.initial_peers])
    else:
        raise ValueError("Joining a private swarm requires at least one --initial-peer multiaddr")
    command.extend(["--port", str(args.port), "--device", args.device,
                    "--torch_dtype", args.dtype, "--compression", args.compression,
                    "--throughput", "auto", "--update_period", str(args.update_period)])
    if args.num_blocks is not None:
        command.extend(["--num_blocks", str(args.num_blocks)])
    if args.quant_type:
        command.extend(["--quant_type", args.quant_type])
    if args.cache_dir:
        command.extend(["--cache_dir", args.cache_dir])
    if args.identity_path:
        command.extend(["--identity_path", args.identity_path])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Petals distributed Transformer-block server")
    parser.add_argument("--model", required=True, help="Hugging Face model id supported by Petals")
    parser.add_argument("--swarm-mode", choices=("new", "join", "public"), default="join")
    parser.add_argument("--initial-peer", dest="initial_peers", action="append", default=[])
    parser.add_argument("--port", type=int, default=31330)
    parser.add_argument("--device", default="auto", help="auto, cuda, cpu, or a torch device")
    parser.add_argument("--dtype", choices=("auto", "float16", "bfloat16", "float32"), default="auto")
    parser.add_argument("--compression", choices=("NONE", "FLOAT16"), default="FLOAT16")
    parser.add_argument("--num-blocks", type=int)
    parser.add_argument("--quant-type", choices=("int8", "nf4"))
    parser.add_argument("--cache-dir")
    parser.add_argument("--identity-path")
    parser.add_argument("--update-period", type=int, default=120)
    args = parser.parse_args()

    if args.swarm_mode == "public":
        args.swarm_mode = "join"
        args.initial_peers = []
    if args.device == "auto":
        args.device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES", "") not in {"", "-1"} else "cpu"
        try:
            import torch
            args.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            pass
    if shutil.which(sys.executable) is None:
        raise SystemExit(f"Python executable not found: {sys.executable}")
    try:
        command = build_command(args)
    except ValueError as error:
        parser.error(str(error))
    print("Starting upstream Petals block server:", " ".join(command), flush=True)
    print("Petals will select contiguous blocks from available device memory and publish throughput.", flush=True)
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
