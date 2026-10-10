"""Register a locally available GGUF file in the model manifest."""
import argparse
import hashlib
import json
import re
import os
import shutil
import urllib.request
from pathlib import Path


def hash_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Stable model key used by tasks")
    parser.add_argument("file", type=Path, help="GGUF model file")
    parser.add_argument("--adapter", type=Path, help="Optional GGUF LoRA adapter compatible with the base model")
    parser.add_argument("--canary-suite", type=Path,
                        help="Optional JSON array of deterministic prompt/expected_output checks for hidden worker audits")
    parser.add_argument("--label", help="Human-readable label")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("models.json"))
    parser.add_argument("--swarm-data", type=Path, default=Path(os.getenv("COMPUTETORRENT_SWARM_DATA", "runtime/swarm")))
    parser.add_argument("--swarm-url", default=os.getenv("COMPUTETORRENT_SWARM_URL", "http://127.0.0.1:4001"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", args.name):
        parser.error("name may contain only letters, numbers, dot, underscore, and dash")
    source = args.file.resolve(strict=True)
    if source.suffix.lower() != ".gguf" or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}\.gguf", source.name):
        parser.error("file must be a safe, single-name GGUF model filename")
    adapter_source = args.adapter.resolve(strict=True) if args.adapter else None
    if adapter_source and (adapter_source.suffix.lower() != ".gguf"
                           or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}\.gguf", adapter_source.name)):
        parser.error("adapter must be a safe, single-name GGUF LoRA adapter filename")
    if adapter_source and adapter_source.name == source.name:
        parser.error("model and adapter filenames must differ")
    canaries = []
    if args.canary_suite:
        try:
            suite = json.loads(args.canary_suite.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            parser.error(f"could not read canary suite: {error}")
        if not isinstance(suite, list) or not 1 <= len(suite) <= 100:
            parser.error("canary suite must be a JSON array with 1 to 100 entries")
        for index, item in enumerate(suite):
            if (not isinstance(item, dict) or not isinstance(item.get("prompt"), str)
                    or not item["prompt"].strip() or len(item["prompt"]) > 20000
                    or not isinstance(item.get("expected_output"), str)
                    or not item["expected_output"].strip() or len(item["expected_output"]) > 20000):
                parser.error(f"canary entry {index} needs non-empty prompt and expected_output strings")
            canaries.append({
                "id": f"canary-{index:03d}",
                "prompt": item["prompt"],
                "expected_output_sha256": hashlib.sha256(item["expected_output"].strip().encode("utf-8")).hexdigest(),
                "max_tokens": min(max(int(item.get("max_tokens", 64)), 1), 2048),
                "seed": int(item.get("seed", 42)),
            })
    expected_digest = hash_file(source)
    adapter_digest = hash_file(adapter_source) if adapter_source else None
    model_dir = (args.swarm_data.resolve() / "models" / args.name)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / source.name
    if not model_path.exists() or model_path.stat().st_size != source.stat().st_size or hash_file(model_path) != expected_digest:
        shutil.copy2(source, model_path)
    files = [model_path.relative_to(args.swarm_data.resolve()).as_posix()]
    if adapter_source:
        adapter_path = model_dir / adapter_source.name
        if not adapter_path.exists() or adapter_path.stat().st_size != adapter_source.stat().st_size or hash_file(adapter_path) != adapter_digest:
            shutil.copy2(adapter_source, adapter_path)
        files.append(adapter_path.relative_to(args.swarm_data.resolve()).as_posix())
    swarm_digest = expected_digest[:12] if not adapter_digest else hashlib.sha256((expected_digest + adapter_digest).encode()).hexdigest()[:12]
    model_swarm_id = "model-" + args.name + "-" + swarm_digest
    request = urllib.request.Request(args.swarm_url.rstrip("/") + "/create-swarm",
        data=json.dumps({"task_id": model_swarm_id, "files": files}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        magnet_uri = json.loads(response.read().decode("utf-8"))["magnet_uri"]
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    entry = {"file": source.name, "sha256": expected_digest, "label": args.label or args.name,
             "magnet_uri": magnet_uri}
    if adapter_source:
        entry.update({"adapter_file": adapter_source.name, "adapter_sha256": adapter_digest})
    if canaries:
        entry["canaries"] = canaries
    manifest[args.name] = entry
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    print(f"Registered {args.name}: {source.name} SHA-256 {expected_digest}")
    if adapter_source:
        print(f"Registered LoRA adapter {adapter_source.name} SHA-256 {adapter_digest}")
    if canaries:
        print(f"Registered {len(canaries)} hidden worker canary checks")
    print(f"Providers will fetch this model by WebTorrent on demand: {magnet_uri}")


if __name__ == "__main__":
    main()
