"""Replica, hidden-canary and VeriLLM-inspired transcript verification."""
from collections import Counter
import hashlib
import json
import secrets
from typing import Any


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _merkle_proof(leaves: list[bytes], index: int) -> list[dict[str, str]]:
    proof: list[dict[str, str]] = []
    layer = leaves
    cursor = index
    while len(layer) > 1:
        if len(layer) % 2:
            layer = [*layer, layer[-1]]
        sibling = cursor - 1 if cursor % 2 else cursor + 1
        proof.append({"side": "left" if sibling < cursor else "right", "sha256": layer[sibling].decode("ascii")})
        layer = [_sha256(layer[offset] + layer[offset + 1]).encode("ascii")
                 for offset in range(0, len(layer), 2)]
        cursor //= 2
    return proof


def build_verillm_receipt(task_id: str, chunk_id: str, model_sha256: str,
                           prompt_sha256: str, results: list[dict[str, Any]],
                           winner_hash: str | None) -> dict[str, Any]:
    """Commit replica reports and choose an unpredictable post-report audit sample.

    This is a tamper-evident output transcript inspired by VeriLLM's commitment
    and sampling pattern. It is not a proof of intermediate model hidden states.
    """
    ordered = sorted(results, key=lambda item: str(item.get("seeder_id", "")))
    payloads = [json.dumps({"provider": item.get("seeder_id"),
                            "output_sha256": item.get("output_sha256"),
                            "canary_passed": bool(item.get("canary_passed")),
                            "canary_id": item.get("canary_id")},
                           sort_keys=True, separators=(",", ":")).encode("utf-8")
                for item in ordered]
    leaves = [_sha256(payload).encode("ascii") for payload in payloads]
    layer = leaves or [_sha256(b"empty").encode("ascii")]
    while len(layer) > 1:
        if len(layer) % 2:
            layer = [*layer, layer[-1]]
        layer = [_sha256(layer[offset] + layer[offset + 1]).encode("ascii")
                 for offset in range(0, len(layer), 2)]
    nonce = secrets.token_hex(32)
    sample_indices = []
    if ordered:
        sample_indices = [int(_sha256(f"{nonce}:{index}".encode("ascii")), 16) % len(ordered)
                          for index in range(min(2, len(ordered)))]
    samples = [{"provider": ordered[index].get("seeder_id"),
                "output_sha256": ordered[index].get("output_sha256"),
                "canary_passed": bool(ordered[index].get("canary_passed")),
                "canary_id": ordered[index].get("canary_id"),
                "leaf_sha256": leaves[index].decode("ascii"),
                "proof": _merkle_proof(leaves, index)}
               for index in sorted(set(sample_indices))]
    return {
        "protocol": "verillm-inspired-output-audit-v1",
        "task_id": task_id,
        "chunk_id": chunk_id,
        "model_sha256": model_sha256,
        "prompt_sha256": prompt_sha256,
        "winner_sha256": winner_hash,
        "commitment_root": layer[0].decode("ascii"),
        "challenge_nonce": nonce,
        "sampled_reports": samples,
        "assurance": "replica-output transcript commitment; hidden-state inference proof is not included",
    }


def verify_verillm_sample(receipt: dict[str, Any], sample: dict[str, Any]) -> bool:
    """Verify an included provider/output report against its committed Merkle root."""
    try:
        payload = json.dumps({"provider": sample["provider"],
                              "output_sha256": sample["output_sha256"],
                              "canary_passed": bool(sample.get("canary_passed")),
                              "canary_id": sample.get("canary_id")},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        leaf = _sha256(payload)
        if leaf != sample["leaf_sha256"]:
            return False
        node = leaf.encode("ascii")
        for step in sample["proof"]:
            sibling = step["sha256"].encode("ascii")
            if step["side"] == "left":
                node = _sha256(sibling + node).encode("ascii")
            elif step["side"] == "right":
                node = _sha256(node + sibling).encode("ascii")
            else:
                return False
        return node.decode("ascii") == receipt["commitment_root"]
    except (KeyError, TypeError, ValueError, UnicodeError):
        return False


def verify_replicas(results: list[dict[str, Any]], required_replicas: int = 1,
                    task_id: str = "", chunk_id: str = "", model_sha256: str = "",
                    prompt_sha256: str = "") -> dict[str, Any]:
    """Return a deterministic majority verdict over provider output hashes.

    With one configured replica the output is accepted provisionally; enable
    three replicas for majority verification. Ties and missing replicas fail
    closed. Provider identities are kept in the evidence for trust accounting.
    """
    valid = [r for r in results if isinstance(r.get("output_sha256"), str)
             and len(r["output_sha256"]) == 64 and isinstance(r.get("output"), str)
             and _sha256(r["output"].encode("utf-8")) == r["output_sha256"].lower()]
    required = max(1, min(int(required_replicas), 3))
    counts = Counter(r["output_sha256"] for r in valid)
    if not counts:
        return {"verified": False, "status": "pending", "winner_hash": None,
                "agreement": 0, "required": required, "providers": []}
    winner_hash, agreement = counts.most_common(1)[0]
    tied = len([count for count in counts.values() if count == agreement]) > 1
    verified = not tied and agreement >= (2 if required > 1 else 1)
    winner = next((r for r in valid if r["output_sha256"] == winner_hash), None)
    receipt = build_verillm_receipt(task_id, chunk_id, model_sha256, prompt_sha256, valid,
                                    winner_hash if verified else None)
    return {"verified": verified, "status": "verified" if verified else "disputed",
            "winner_hash": winner_hash if verified else None,
            "output": winner["output"] if verified and winner else None,
            "agreement": agreement, "required": required,
            "providers": [r.get("seeder_id") for r in valid],
            "outliers": [r.get("seeder_id") for r in valid if r["output_sha256"] != winner_hash],
            "verillm_audit": receipt}
