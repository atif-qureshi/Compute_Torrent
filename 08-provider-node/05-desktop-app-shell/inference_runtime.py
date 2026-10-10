"""Deterministic llama.cpp inference in a disposable Docker container."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


DEFAULT_IMAGE = "ghcr.io/ggml-org/llama.cpp:light"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_inference(task: dict, *, models_dir: str | None = None,
                  image: str | None = None, docker: str = "docker") -> dict:
    """Run an assigned prompt with a locally provisioned GGUF model.

    Model weights are mounted read-only and are never fetched by the container.
    A task must carry the model filename and expected content digest.
    """
    model_name = task.get("model_name")
    filename = task.get("model_file")
    expected_hash = task.get("model_sha256")
    prompt = task.get("prompt")
    if not isinstance(model_name, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", model_name):
        raise ValueError("Invalid model name")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith(".gguf"):
        raise ValueError("Assignment has no valid GGUF model filename")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
        raise ValueError("Assignment has no valid model SHA-256")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise ValueError("Prompt must contain 1 to 20,000 characters")

    default_root = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ComputeTorrent" / "models"
    model_root = Path(models_dir or os.getenv("COMPUTETORRENT_MODELS_DIR", str(default_root))).expanduser().resolve()
    model_path = (model_root / model_name / filename).resolve()
    if not model_path.is_relative_to(model_root) or not model_path.is_file():
        raise FileNotFoundError(f"Model file is not installed: {model_name}/{filename}")
    actual_hash = sha256_file(model_path)
    if actual_hash.lower() != expected_hash.lower():
        raise ValueError("Installed model SHA-256 does not match the task manifest")
    adapter_path = None
    adapter_filename = task.get("adapter_file")
    adapter_hash = task.get("adapter_sha256")
    if adapter_filename:
        if not isinstance(adapter_filename, str) or Path(adapter_filename).name != adapter_filename or not adapter_filename.lower().endswith(".gguf"):
            raise ValueError("Assignment has no valid GGUF adapter filename")
        if not isinstance(adapter_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", adapter_hash):
            raise ValueError("Assignment has no valid adapter SHA-256")
        adapter_path = (model_root / model_name / adapter_filename).resolve()
        if not adapter_path.is_relative_to(model_root) or not adapter_path.is_file():
            raise FileNotFoundError(f"LoRA adapter file is not installed: {model_name}/{adapter_filename}")
        if sha256_file(adapter_path).lower() != adapter_hash.lower():
            raise ValueError("Installed adapter SHA-256 does not match the task manifest")

    timeout = min(max(int(task.get("timeout_seconds", 900)), 30), 3600)
    max_tokens = min(max(int(task.get("max_tokens", 256)), 1), 2048)
    use_cuda = bool(task.get("require_cuda", False))
    if use_cuda and not task.get("cuda_available", True):
        raise RuntimeError("This assignment requires CUDA, but the provider does not advertise CUDA")
    selected_image = image or task.get("docker_image") or (
        os.getenv("COMPUTETORRENT_LLAMA_CUDA_IMAGE", "ghcr.io/ggml-org/llama.cpp:full-cuda") if use_cuda
        else os.getenv("COMPUTETORRENT_LLAMA_IMAGE", DEFAULT_IMAGE))
    if not re.fullmatch(r"[A-Za-z0-9./:_@-]{1,256}", selected_image):
        raise ValueError("Invalid inference image reference")

    workspace = Path(tempfile.mkdtemp(prefix="computetorrent-inference-"))
    # The container runs as an unprivileged UID. Allow it to create only its
    # short-lived result in this dedicated bind mount (model data stays RO).
    try:
        os.chmod(workspace, 0o777)
    except OSError:
        # Windows Docker Desktop applies host ACLs to bind mounts instead.
        pass
    input_file = workspace / "prompt.txt"
    output_file = workspace / "result.txt"
    input_file.write_text(prompt, encoding="utf-8")
    container = f"computetorrent-{re.sub('[^A-Za-z0-9_-]', '-', str(task.get('task_id', 'task')))[:40]}-{int(time.time())}"
    try:
        image_check = subprocess.run([docker, "image", "inspect", selected_image], capture_output=True, text=True, timeout=30)
        if image_check.returncode:
            pulled = subprocess.run([docker, "pull", selected_image], capture_output=True, text=True, timeout=1800)
            if pulled.returncode:
                detail = (pulled.stderr or pulled.stdout or "Docker could not download the inference runtime")[-1000:]
                raise RuntimeError(f"Could not prepare inference image {selected_image}: {detail}")
        args = [docker, "run", "--name", container, "--rm", "--network", "none", "--read-only"]
        if use_cuda:
            args.extend(["--gpus", "all"])
        args.extend([
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--pids-limit", "128",
                "--cpus", str(min(max(float(task.get("cpu_limit", 2)), 1), 16)),
                "--memory", f"{min(max(int(task.get('memory_limit_gb', 8)), 2), 64)}g",
                "--user", "65534:65534", "--tmpfs", "/tmp:rw,noexec,nosuid,size=512m",
                "-v", f"{model_root.as_posix()}:/models:ro", "-v", f"{workspace.as_posix()}:/task:rw",
                "--entrypoint", "/app/llama-cli", selected_image,
                "-m", f"/models/{model_name}/{filename}", "-f", "/task/prompt.txt",
                "-n", str(max_tokens), "--temp", "0", "--seed", str(int(task.get("seed", 42))),
                "--simple-io", "--single-turn", "--no-display-prompt", "--no-show-timings",
                "--output", "/task/result.txt"])
        if use_cuda:
            args.extend(["--n-gpu-layers", "-1"])
        if adapter_path:
            args.extend(["--lora", f"/models/{model_name}/{adapter_filename}"])
        started = time.monotonic()
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
        output = output_file.read_text(encoding="utf-8").strip()
        if not output:
            raise RuntimeError("Inference runtime returned an empty output")
        return {"output": output, "output_hash": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                "model_sha256": actual_hash, "runtime_image": selected_image,
                "adapter_sha256": adapter_hash,
                "run_seconds": round(time.monotonic() - started, 3), "seed": int(task.get("seed", 42)),
                "max_tokens": max_tokens}
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Inference exceeded its {timeout}s time limit") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "llama.cpp exited unsuccessfully")[-1000:]
        raise RuntimeError(f"Inference failed: {detail}") from exc
    finally:
        subprocess.run([docker, "rm", "-f", container], capture_output=True, timeout=15)
        shutil.rmtree(workspace, ignore_errors=True)
