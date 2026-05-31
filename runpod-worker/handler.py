import base64
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import requests
import runpod
from huggingface_hub import login as hf_login

PIXAL3D_DIR = Path(os.environ.get("PIXAL3D_DIR", "/workspace/Pixal3D"))
PYTHON_BIN = os.environ.get("PYTHON_BIN", "python")
MAX_INLINE_MB = int(os.environ.get("MAX_INLINE_MB", "80"))


def _write_input_image(inp: Dict[str, Any], workdir: Path) -> Path:
    image_path = workdir / "input.png"
    if inp.get("image_base64"):
        raw = inp["image_base64"]
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        image_path.write_bytes(base64.b64decode(raw))
        return image_path

    if inp.get("image_url"):
        r = requests.get(inp["image_url"], timeout=120)
        r.raise_for_status()
        image_path.write_bytes(r.content)
        return image_path

    raise ValueError("Missing input.image_base64 or input.image_url")


def _upload_file(upload_url: str, path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        r = requests.put(upload_url, data=f, timeout=600)
    r.raise_for_status()
    return {"uploaded": True, "status_code": r.status_code}


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    started = time.time()
    inp = event.get("input") or {}
    low_vram = bool(inp.get("low_vram", True))
    resolution = int(inp.get("resolution", 1024 if low_vram else 1536))
    seed = inp.get("seed")
    upload_url = inp.get("output_upload_url")

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        image_path = _write_input_image(inp, workdir)
        output_path = workdir / "output.glb"

        cmd = [
            PYTHON_BIN,
            str(PIXAL3D_DIR / "inference.py"),
            "--image", str(image_path),
            "--output", str(output_path),
            "--resolution", str(resolution),
        ]
        if low_vram:
            cmd.append("--low_vram")
        if seed is not None:
            cmd += ["--seed", str(seed)]

        env = os.environ.copy()
        env.setdefault("ATTN_BACKEND", "sdpa")

        # Hugging Face gated models, e.g. briaai/RMBG-2.0, require an auth token.
        # Prefer RunPod endpoint env vars, but also allow the local proxy to pass hf_token in the job input.
        hf_token = inp.get("hf_token") or env.get("HF_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            env["HF_TOKEN"] = hf_token
            env["HUGGINGFACE_HUB_TOKEN"] = hf_token
            env["HUGGING_FACE_HUB_TOKEN"] = hf_token
            try:
                hf_login(token=hf_token, add_to_git_credential=False)
            except Exception as exc:
                print(f"[HF] login warning: {exc}")

        if env.get("MODEL_CACHE_DIR"):
            env.setdefault("HF_HOME", env["MODEL_CACHE_DIR"])
            env.setdefault("HUGGINGFACE_HUB_CACHE", env["MODEL_CACHE_DIR"])

        proc = subprocess.run(
            cmd,
            cwd=str(PIXAL3D_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=int(inp.get("timeout_sec", 1800)),
        )

        log_tail = proc.stdout[-8000:]
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "Pixal3D inference failed",
                "returncode": proc.returncode,
                "log_tail": log_tail,
                "seconds": round(time.time() - started, 2),
            }
        if not output_path.exists():
            return {"ok": False, "error": "output.glb was not created", "log_tail": log_tail}

        size = output_path.stat().st_size
        result: Dict[str, Any] = {
            "ok": True,
            "filename": "output.glb",
            "bytes": size,
            "seconds": round(time.time() - started, 2),
            "log_tail": log_tail,
        }

        if upload_url:
            result["upload"] = _upload_file(upload_url, output_path)
            return result

        max_inline = MAX_INLINE_MB * 1024 * 1024
        if size > max_inline:
            return {
                **result,
                "ok": False,
                "error": f"GLB is {size} bytes; larger than inline limit {max_inline}. Use input.output_upload_url.",
            }

        result["glb_base64"] = base64.b64encode(output_path.read_bytes()).decode("ascii")
        return result


runpod.serverless.start({"handler": handler})
