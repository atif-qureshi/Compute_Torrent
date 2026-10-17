"""Run the same public prompt through exact peer-count Petals configurations."""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def local_token(path):
    token = os.getenv("COMPUTETORRENT_API_TOKEN", "")
    if token:
        return token
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("COMPUTETORRENT_API_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("Set COMPUTETORRENT_API_TOKEN or supply a local .env file")


def request(base, token, path, data=None):
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Coordinator returned {error.code}: {detail}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--model-id", choices=["bigscience/bloom-560m", "bigscience/bloomz-560m"],
        default="bigscience/bloomz-560m")
    parser.add_argument("--prompt", default="Explain volunteer computing in one sentence.")
    parser.add_argument("--output-tokens", type=int, default=32)
    parser.add_argument("--peers", type=int, nargs="+", default=[2, 4])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.output_tokens <= 128 or not 1 <= args.repeats <= 20:
        parser.error("Use 1–128 output tokens and 1–20 repeats")
    if any(not 2 <= count <= 8 for count in args.peers):
        parser.error("Each peer count must be 2–8")
    token = local_token(args.env_file)
    status = request(args.url, token, "/api/distributed/status")
    if status.get("status") != "ready":
        raise RuntimeError("Petals gateway is unavailable; start the local stack with -WithPetals")

    fixed_revision = None
    for peer_count in args.peers:
        for repeat in range(1, args.repeats + 1):
            recipe = {"model_id": args.model_id, "revision": fixed_revision or "main",
                "prompt": args.prompt, "max_new_tokens": args.output_tokens,
                "min_peers": peer_count, "max_peers": peer_count, "benchmark": True}
            job = request(args.url, token, "/api/distributed/jobs",
                {"format": "json", "content": json.dumps(recipe)})
            job_id = job["id"]
            print(f"{peer_count} peers, run {repeat}/{args.repeats}: {job_id}", flush=True)
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline:
                job = request(args.url, token, "/api/distributed/jobs/" + job_id)
                if job["status"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(5)
            else:
                raise TimeoutError(f"Job {job_id} exceeded the one-hour experiment deadline")
            if job["status"] != "completed":
                raise RuntimeError(f"Job {job_id} {job['status']}: {job.get('error', 'no detail')}")
            revision = job["spec"]["revision"]
            if fixed_revision and revision != fixed_revision:
                raise RuntimeError("Model revision changed during the experiment")
            fixed_revision = revision
            metrics = job.get("metrics") or {}
            print(f"  revision {revision[:12]}, generation {metrics.get('distributed_generation_seconds')}s, "
                  f"single-node CPU {metrics.get('single_node_reference_seconds')}s, "
                  f"boundary/canary passed", flush=True)
    print("Export measured CSV and group summaries with export_petals_runs.py.")


if __name__ == "__main__":
    main()
