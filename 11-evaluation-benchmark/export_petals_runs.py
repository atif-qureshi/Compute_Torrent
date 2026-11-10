"""Export measured Model Studio runs without copying user prompts into datasets."""
import argparse
import csv
import json
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

FIELDS = [
    "job_id", "model_id", "revision", "status", "created_at", "provider_count",
    "generated_tokens", "model_load_seconds", "distributed_generation_seconds",
    "throughput_tokens_per_sec", "latency_per_token_ms",
    "verification_seconds", "canary_seconds", "total_seconds",
    "single_node_reference_seconds", "single_node_reference_tokens", "speedup",
    "boundary_passed", "canary_passed",
]


def collect(database):
    if not database.is_file():
        raise FileNotFoundError(f"No Model Studio job database at {database}")
    with sqlite3.connect(database) as conn:
        bodies = [json.loads(body) for (body,) in conn.execute("SELECT body FROM jobs ORDER BY rowid")]
    rows = []
    for job in bodies:
        metrics = job.get("metrics") or {}
        receipt = job.get("receipt") or {}
        spec = job.get("spec") or {}
        distributed = metrics.get("distributed_generation_seconds")
        baseline = metrics.get("single_node_reference_seconds")
        gen_tokens = metrics.get("generated_tokens")
        same_tokens = gen_tokens == metrics.get("single_node_reference_tokens")
        speedup = round(baseline / distributed, 4) if same_tokens and baseline and distributed else ""

        throughput = metrics.get("throughput_tokens_per_sec")
        if throughput is None and distributed and gen_tokens:
            try:
                throughput = round(float(gen_tokens) / float(distributed), 2)
            except (ZeroDivisionError, ValueError):
                throughput = ""

        latency_ms = metrics.get("latency_per_token_ms")
        if latency_ms is None and distributed and gen_tokens:
            try:
                latency_ms = round((float(distributed) / float(gen_tokens)) * 1000, 2)
            except (ZeroDivisionError, ValueError):
                latency_ms = ""

        rows.append({
            "job_id": job.get("id", ""), "model_id": spec.get("model_id", ""),
            "revision": spec.get("revision", ""), "status": job.get("status", ""),
            "created_at": job.get("created_at", ""),
            "provider_count": metrics.get("provider_count", len(job.get("plan") or [])),
            "generated_tokens": gen_tokens or "",
            "model_load_seconds": metrics.get("model_load_seconds", ""),
            "distributed_generation_seconds": distributed or "",
            "throughput_tokens_per_sec": throughput if throughput is not None else "",
            "latency_per_token_ms": latency_ms if latency_ms is not None else "",
            "verification_seconds": metrics.get("verification_seconds", ""),
            "canary_seconds": metrics.get("canary_seconds", ""),
            "total_seconds": metrics.get("total_seconds", ""),
            "single_node_reference_seconds": baseline or "",
            "single_node_reference_tokens": metrics.get("single_node_reference_tokens", ""),
            "speedup": speedup,
            "boundary_passed": (receipt.get("verification") or {}).get("passed", ""),
            "canary_passed": (receipt.get("canary") or {}).get("passed", ""),
        })
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["status"] == "completed" and row["distributed_generation_seconds"] != "":
            groups[(row["model_id"], row["revision"], row["provider_count"])].append(row)
    summary = []
    for (model, revision, providers), group in sorted(groups.items()):
        durations = [float(row["distributed_generation_seconds"]) for row in group]
        comparable = [float(row["speedup"]) for row in group if row["speedup"] != ""]
        throughputs = [float(row["throughput_tokens_per_sec"]) for row in group if row.get("throughput_tokens_per_sec") not in ("", None)]
        latencies = [float(row["latency_per_token_ms"]) for row in group if row.get("latency_per_token_ms") not in ("", None)]
        summary.append({
            "model_id": model, "revision": revision,
            "provider_count": providers, "completed_runs": len(group),
            "mean_generation_seconds": round(statistics.mean(durations), 4),
            "stdev_generation_seconds": round(statistics.stdev(durations), 4) if len(durations) > 1 else None,
            "mean_throughput_tokens_per_sec": round(statistics.mean(throughputs), 2) if throughputs else None,
            "mean_latency_per_token_ms": round(statistics.mean(latencies), 2) if latencies else None,
            "mean_speedup_vs_coordinator_cpu": round(statistics.mean(comparable), 4) if comparable else None,
            "comparable_baseline_runs": len(comparable)
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("runtime/swarm/distributed/jobs.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("runtime/benchmarks/petals-runs.csv"))
    args = parser.parse_args()
    rows = collect(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summarize(rows), indent=2), encoding="utf-8")
    print(f"Exported {len(rows)} real job records to {args.output}")
    print(f"Group summaries: {summary_path}")


if __name__ == "__main__":
    main()
