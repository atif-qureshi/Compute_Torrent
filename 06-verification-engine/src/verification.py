"""Replica, hidden-canary, and independently checkable audit receipts.

The receipt format is VeriLLM-inspired. It is not the full hidden-state/on-chain
VeriLLM protocol; it commits only to output reports available to this runtime.
"""
from collections import Counter
import hashlib
import json
import secrets
from typing import Any


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _challenge_indices(nonce: str, count: int, sample_count: int) -> list[int]:
    """Derive distinct post-commit samples using domain-separated challenges."""
    selected: list[int] = []
    counter = 0
    while len(selected) < min(count, sample_count):
        candidate = int(_sha256(f"computetorrent-audit-v2:{nonce}:{counter}".encode("ascii")), 16) % count
        if candidate not in selected:
            selected.append(candidate)
        counter += 1
    return sorted(selected)


def _receipt_commitment(task_id: str, chunk_id: str, model_sha256: str,
                        prompt_sha256: str, reports_root: str, report_count: int,
                        winner_hash: str | None) -> str:
    envelope = {"domain": "computetorrent-audit-envelope-v2", "task_id": task_id,
                "chunk_id": chunk_id, "model_sha256": model_sha256,
                "prompt_sha256": prompt_sha256, "reports_root": reports_root,
                "report_count": report_count, "winner_sha256": winner_hash}
    return _sha256(_canonical(envelope))


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
    """Commit replica reports, then derive an unpredictable audit sample.

    ``commitment_root`` binds the Merkle report root to the task/model/prompt and
    verdict metadata. The challenge nonce is generated only after reports are
    fixed. This proves transcript inclusion, not correct model execution.
    """
    ordered = sorted(results, key=lambda item: str(item.get("seeder_id", "")))
    payloads = [_canonical({"provider": item.get("seeder_id"),
                            "output_sha256": item.get("output_sha256"),
                            "canary_passed": bool(item.get("canary_passed")),
                            "canary_id": item.get("canary_id")})
                for item in ordered]
    leaves = [_sha256(payload).encode("ascii") for payload in payloads]
    layer = leaves or [_sha256(b"empty").encode("ascii")]
    while len(layer) > 1:
        if len(layer) % 2:
            layer = [*layer, layer[-1]]
        layer = [_sha256(layer[offset] + layer[offset + 1]).encode("ascii")
                 for offset in range(0, len(layer), 2)]
    nonce = secrets.token_hex(32)
    reports_root = layer[0].decode("ascii")
    sample_indices = _challenge_indices(nonce, len(ordered), 2) if ordered else []
    samples = [{"index": index, "provider": ordered[index].get("seeder_id"),
                "output_sha256": ordered[index].get("output_sha256"),
                "canary_passed": bool(ordered[index].get("canary_passed")),
                "canary_id": ordered[index].get("canary_id"),
                "leaf_sha256": leaves[index].decode("ascii"),
                "proof": _merkle_proof(leaves, index)}
               for index in sorted(set(sample_indices))]
    return {
        "protocol": "computetorrent-verillm-transcript-v2",
        "task_id": task_id,
        "chunk_id": chunk_id,
        "model_sha256": model_sha256,
        "prompt_sha256": prompt_sha256,
        "winner_sha256": winner_hash,
        "report_count": len(ordered),
        "reports_root": reports_root,
        "commitment_root": _receipt_commitment(task_id, chunk_id, model_sha256,
                                               prompt_sha256, reports_root, len(ordered),
                                               winner_hash),
        "challenge_nonce": nonce,
        "sampled_indices": sample_indices,
        "sampled_reports": samples,
        "assurance": "auditable output-report inclusion and post-commit sampling; no hidden-state proof or public consensus anchor",
    }


def verify_verillm_sample(receipt: dict[str, Any], sample: dict[str, Any]) -> bool:
    """Verify an included provider/output report against its committed Merkle root."""
    try:
        payload = _canonical({"provider": sample["provider"],
                              "output_sha256": sample["output_sha256"],
                              "canary_passed": bool(sample.get("canary_passed")),
                              "canary_id": sample.get("canary_id")})
        leaf = _sha256(payload)
        if leaf != sample["leaf_sha256"]:
            return False
        node = leaf.encode("ascii")
        cursor = int(sample["index"])
        width = int(receipt["report_count"])
        if cursor < 0 or cursor >= width:
            return False
        for step in sample["proof"]:
            sibling = step["sha256"].encode("ascii")
            expected_side = "left" if cursor % 2 else "right"
            if step["side"] != expected_side:
                return False
            if step["side"] == "left":
                node = _sha256(sibling + node).encode("ascii")
            else:
                node = _sha256(node + sibling).encode("ascii")
            width = (width + 1) // 2
            cursor //= 2
        return (width == 1 and cursor == 0
                and node.decode("ascii") == receipt["reports_root"])
    except (KeyError, TypeError, ValueError, UnicodeError):
        return False


def verify_verillm_receipt(receipt: dict[str, Any]) -> bool:
    """Validate receipt envelope, challenge derivation, and every sample proof."""
    try:
        if receipt.get("protocol") != "computetorrent-verillm-transcript-v2":
            return False
        count = receipt["report_count"]
        if not isinstance(count, int) or count < 0 or count > 10000:
            return False
        for key in ("commitment_root", "reports_root", "model_sha256", "prompt_sha256"):
            if not isinstance(receipt[key], str) or len(receipt[key]) != 64:
                return False
            int(receipt[key], 16)
        expected_root = _receipt_commitment(
            receipt["task_id"], receipt["chunk_id"], receipt["model_sha256"],
            receipt["prompt_sha256"], receipt["reports_root"], count,
            receipt.get("winner_sha256"))
        if expected_root != receipt["commitment_root"]:
            return False
        nonce = receipt["challenge_nonce"]
        if not isinstance(nonce, str) or len(nonce) != 64:
            return False
        int(nonce, 16)
        expected_indices = _challenge_indices(nonce, count, 2) if count else []
        if receipt["sampled_indices"] != expected_indices:
            return False
        samples = receipt["sampled_reports"]
        if not isinstance(samples, list) or [sample.get("index") for sample in samples] != expected_indices:
            return False
        return all(verify_verillm_sample(receipt, sample) for sample in samples)
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
    valid = [r for r in results if isinstance(r, dict)
             and isinstance(r.get("seeder_id"), str) and r.get("seeder_id")
             and isinstance(r.get("output_sha256"), str)
             and len(r["output_sha256"]) == 64 and isinstance(r.get("output"), str)
             and _sha256(r["output"].encode("utf-8")) == r["output_sha256"].lower()]
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
    receipt = build_verillm_receipt(task_id, chunk_id, model_sha256, prompt_sha256, valid,
                                    winner_hash if verified else None)
    return {"verified": verified, "status": "verified" if verified else "disputed",
            "winner_hash": winner_hash if verified else None,
            "output": winner["output"] if verified and winner else None,
            "agreement": agreement, "required": required,
            "providers": [r.get("seeder_id") for r in valid],
            "outliers": [r.get("seeder_id") for r in valid if r["output_sha256"] != winner_hash],
            "verillm_audit": receipt}
