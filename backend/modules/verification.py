"""Replica agreement for GGUF tasks."""
from collections import Counter
from hashlib import sha256
from typing import Any


def verify_replicas(results: list[dict[str, Any]], required_replicas: int = 1,
                    task_id: str = "", chunk_id: str = "", model_sha256: str = "",
                    prompt_sha256: str = "") -> dict[str, Any]:
    """Return a deterministic majority verdict over provider output hashes.

    With one configured replica the output is accepted provisionally; enable
    three replicas for majority verification. Ties and missing replicas fail
    closed. Provider identities are kept in the evidence for trust accounting.
    """
    valid = [r for r in results if isinstance(r, dict)
             and isinstance(r.get("seeder_id"), str) and r.get("seeder_id")
             and isinstance(r.get("output_sha256"), str)
             and len(r["output_sha256"]) == 64 and isinstance(r.get("output"), str)
             and sha256(r["output"].encode("utf-8")).hexdigest() == r["output_sha256"].lower()]
    unique: dict[str, dict[str, Any]] = {}
    for row in valid:
        unique.setdefault(row["seeder_id"], row)
    valid = list(unique.values())
    required = max(1, min(int(required_replicas), 3))
    counts = Counter(r["output_sha256"] for r in valid)
    if not counts:
        return {"verified": False, "status": "pending", "winner_hash": None,
                "agreement": 0, "required": required, "providers": []}
    winner_hash, agreement = counts.most_common(1)[0]
    tied = len([count for count in counts.values() if count == agreement]) > 1
    verified = not tied and agreement >= (2 if required > 1 else 1)
    winner = next((r for r in valid if r["output_sha256"] == winner_hash), None)
    return {"verified": verified, "status": "verified" if verified else "disputed",
            "winner_hash": winner_hash if verified else None,
            "output": winner["output"] if verified and winner else None,
            "agreement": agreement, "required": required,
            "providers": [r.get("seeder_id") for r in valid],
            "outliers": [r.get("seeder_id") for r in valid if r["output_sha256"] != winner_hash]}
