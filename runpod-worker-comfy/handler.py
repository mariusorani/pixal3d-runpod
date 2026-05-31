import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import runpod
from huggingface_hub import login as hf_login

COMFY_DIR = Path(os.environ.get("COMFY_DIR", "/workspace/ComfyUI"))
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8188"))
COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"
PROMPT_TEMPLATE = Path(os.environ.get("PROMPT_TEMPLATE", "/workspace/pixal3d_api_prompt.json"))
MAX_INLINE_MB = int(os.environ.get("MAX_INLINE_MB", "80"))

_comfy_proc: Optional[subprocess.Popen] = None


def _wait_for_comfy(timeout: int = 180) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if r.ok:
                return
        except Exception as e:
            last_err = e
        time.sleep(1)
    raise RuntimeError(f"ComfyUI did not become ready within {timeout}s: {last_err}")


def _start_comfy() -> None:
    global _comfy_proc
    if _comfy_proc and _comfy_proc.poll() is None:
        return

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    hf_token = env.get("HF_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN")
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

    _comfy_proc = subprocess.Popen(
        [
            "python",
            "main.py",
            "--listen",
            COMFY_HOST,
            "--port",
            str(COMFY_PORT),
            "--disable-auto-launch",
        ],
        cwd=str(COMFY_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _wait_for_comfy()


def _decode_image(inp: Dict[str, Any], path: Path) -> None:
    if inp.get("image_base64"):
        raw = inp["image_base64"]
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        path.write_bytes(base64.b64decode(raw))
        return
    if inp.get("image_url"):
        r = requests.get(inp["image_url"], timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
        return
    raise ValueError("Missing input.image_base64 or input.image_url")


def _upload_to_comfy(image_path: Path, filename: str) -> str:
    with image_path.open("rb") as f:
        files = {"image": (filename, f, "image/png")}
        data = {"overwrite": "true", "type": "input"}
        r = requests.post(f"{COMFY_URL}/upload/image", files=files, data=data, timeout=120)
    r.raise_for_status()
    info = r.json()
    # Usually returns {name, subfolder, type}; LoadImage wants the returned name or subfolder/name.
    name = info.get("name", filename)
    subfolder = info.get("subfolder", "")
    return f"{subfolder}/{name}" if subfolder else name


def _build_prompt(inp: Dict[str, Any], image_name: str) -> Dict[str, Any]:
    prompt = json.loads(PROMPT_TEMPLATE.read_text())
    prompt["1"]["inputs"]["image"] = image_name

    loader = prompt["2"]["inputs"]
    loader["attention_backend"] = inp.get("attention_backend", loader["attention_backend"])
    loader["vram_mode"] = inp.get("vram_mode", loader["vram_mode"])
    loader["download_if_missing"] = bool(inp.get("download_if_missing", loader["download_if_missing"]))
    loader["load_moge"] = bool(inp.get("load_moge", loader["load_moge"]))
    loader["load_rembg"] = bool(inp.get("load_rembg", loader["load_rembg"]))
    loader["naf_mode"] = inp.get("naf_mode", loader["naf_mode"])
    loader["preload_naf"] = bool(inp.get("preload_naf", loader["preload_naf"]))
    loader["force_reload"] = bool(inp.get("force_reload", loader["force_reload"]))

    cam = prompt["3"]["inputs"]
    cam["fov_degrees"] = float(inp.get("fov_degrees", cam["fov_degrees"]))
    cam["distance"] = float(inp.get("distance", cam["distance"]))
    cam["mesh_scale"] = float(inp.get("mesh_scale", cam["mesh_scale"]))

    gen = prompt["4"]["inputs"]
    low_vram = bool(inp.get("low_vram", True))
    gen["seed"] = int(inp.get("seed", gen["seed"]))
    gen["pipeline_type"] = inp.get("pipeline_type", "1024_cascade" if low_vram else "1536_cascade")
    gen["background_mode"] = inp.get("background_mode", gen["background_mode"])
    gen["camera_mode"] = inp.get("camera_mode", gen["camera_mode"])
    gen["manual_distance"] = float(inp.get("distance", gen["manual_distance"]))
    gen["mesh_scale"] = float(inp.get("mesh_scale", gen["mesh_scale"]))
    gen["extend_pixel"] = int(inp.get("extend_pixel", gen["extend_pixel"]))
    gen["camera_resolution"] = int(inp.get("camera_resolution", gen["camera_resolution"]))
    gen["steps"] = int(inp.get("steps", gen["steps"]))
    gen["guidance"] = float(inp.get("guidance", gen["guidance"]))
    gen["texture_guidance"] = float(inp.get("texture_guidance", gen["texture_guidance"]))
    gen["max_num_tokens"] = int(inp.get("max_num_tokens", gen["max_num_tokens"]))
    gen["force_offload"] = bool(inp.get("force_offload", low_vram))

    export = prompt["5"]["inputs"]
    export["decimation_target"] = int(inp.get("decimation_target", export["decimation_target"]))
    export["texture_size"] = int(inp.get("texture_size", export["texture_size"]))
    export["remesh"] = bool(inp.get("remesh", export["remesh"]))
    export["filename_prefix"] = inp.get("filename_prefix", f"pixal3d_runpod_{uuid.uuid4().hex[:8]}")
    return prompt


def _queue_prompt(prompt: Dict[str, Any]) -> str:
    client_id = str(uuid.uuid4())
    r = requests.post(f"{COMFY_URL}/prompt", json={"prompt": prompt, "client_id": client_id}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "prompt_id" not in data:
        raise RuntimeError(f"Unexpected /prompt response: {data}")
    return data["prompt_id"]


def _poll_history(prompt_id: str, timeout: int) -> Dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=30)
        r.raise_for_status()
        data = r.json()
        if prompt_id in data:
            return data[prompt_id]
        time.sleep(2)
    raise TimeoutError(f"ComfyUI prompt timed out after {timeout}s")


def _find_glb_from_history(hist: Dict[str, Any]) -> Optional[Path]:
    outputs = hist.get("outputs", {})
    for node_out in outputs.values():
        ui = node_out.get("ui") or {}
        texts = ui.get("text") or []
        for txt in texts:
            p = Path(str(txt))
            if p.suffix.lower() == ".glb" and p.exists():
                return p
    return None


def _find_latest_glb(since: float) -> Optional[Path]:
    out = COMFY_DIR / "output"
    candidates = []
    if out.exists():
        for p in out.rglob("*.glb"):
            try:
                if p.stat().st_mtime >= since:
                    candidates.append(p)
            except FileNotFoundError:
                pass
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _upload_file(upload_url: str, path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        r = requests.put(upload_url, data=f, timeout=600)
    r.raise_for_status()
    return {"uploaded": True, "status_code": r.status_code}


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    started = time.time()
    inp = event.get("input") or {}
    _start_comfy()

    with tempfile.TemporaryDirectory() as td:
        local_img = Path(td) / "input.png"
        _decode_image(inp, local_img)
        comfy_name = _upload_to_comfy(local_img, f"runpod_{uuid.uuid4().hex}.png")
        prompt = _build_prompt(inp, comfy_name)
        prompt_id = _queue_prompt(prompt)
        hist = _poll_history(prompt_id, int(inp.get("timeout_sec", 1800)))
        glb_path = _find_glb_from_history(hist) or _find_latest_glb(started)
        if not glb_path or not glb_path.exists():
            return {"ok": False, "error": "No GLB found after ComfyUI workflow", "prompt_id": prompt_id, "history": hist}

        # Copy to temp before optional cleanup/download.
        result_glb = Path(td) / "output.glb"
        shutil.copy2(glb_path, result_glb)
        size = result_glb.stat().st_size
        result: Dict[str, Any] = {
            "ok": True,
            "prompt_id": prompt_id,
            "filename": "output.glb",
            "source_path": str(glb_path),
            "bytes": size,
            "seconds": round(time.time() - started, 2),
        }

        if inp.get("output_upload_url"):
            result["upload"] = _upload_file(inp["output_upload_url"], result_glb)
            return result

        max_inline = MAX_INLINE_MB * 1024 * 1024
        if size > max_inline:
            return {**result, "ok": False, "error": f"GLB is larger than inline limit {max_inline}; use output_upload_url."}
        result["glb_base64"] = base64.b64encode(result_glb.read_bytes()).decode("ascii")
        return result


runpod.serverless.start({"handler": handler})
