#!/usr/bin/env python3
# Same RunPod API client as generate.py, but exposes Pixal3D-ComfyUI workflow parameters.
import argparse
import base64
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


def api_url(endpoint_id: str, mode: str) -> str:
    return f"https://api.runpod.ai/v2/{endpoint_id}/{mode}"


def request_job(endpoint_id: str, api_key: str, payload: dict, sync: bool) -> dict:
    r = requests.post(
        api_url(endpoint_id, "runsync" if sync else "run"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"input": payload},
        timeout=190 if sync else 60,
    )
    r.raise_for_status()
    return r.json()


def poll(endpoint_id: str, api_key: str, job_id: str) -> dict:
    while True:
        r = requests.get(api_url(endpoint_id, f"status/{job_id}"), headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        r.raise_for_status()
        data = r.json()
        print("status:", data.get("status"))
        if data.get("status") in {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}:
            return data
        time.sleep(3)


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Generate GLB via RunPod Serverless ComfyUI + Pixal3D-ComfyUI")
    p.add_argument("--image", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--endpoint-id", default=os.getenv("RUNPOD_ENDPOINT_ID"))
    p.add_argument("--api-key", default=os.getenv("RUNPOD_API_KEY"))
    p.add_argument("--pipeline-type", default="1024_cascade", choices=["1024_cascade", "1536_cascade"])
    p.add_argument("--background-mode", default="none", choices=["auto_remove", "keep_alpha", "none"])
    p.add_argument("--camera-mode", default="manual", choices=["manual", "moge"])
    p.add_argument("--steps", type=int, default=12)
    p.add_argument("--guidance", type=float, default=7.5)
    p.add_argument("--texture-guidance", type=float, default=1.0)
    p.add_argument("--texture-size", type=int, default=2048)
    p.add_argument("--decimation-target", type=int, default=1000000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--async-run", action="store_true")
    args = p.parse_args()

    if not args.api_key or not args.endpoint_id:
        print("Missing RUNPOD_API_KEY or RUNPOD_ENDPOINT_ID", file=sys.stderr)
        return 2

    payload = {
        "image_base64": base64.b64encode(Path(args.image).read_bytes()).decode("ascii"),
        "pipeline_type": args.pipeline_type,
        "background_mode": args.background_mode,
        "camera_mode": args.camera_mode,
        "steps": args.steps,
        "guidance": args.guidance,
        "texture_guidance": args.texture_guidance,
        "texture_size": args.texture_size,
        "decimation_target": args.decimation_target,
        "seed": args.seed,
        "low_vram": args.pipeline_type == "1024_cascade",
        "timeout_sec": 1800,
    }
    data = request_job(args.endpoint_id, args.api_key, payload, sync=not args.async_run)
    if args.async_run:
        data = poll(args.endpoint_id, args.api_key, data["id"])
    output = data.get("output") or data
    if not output.get("ok"):
        print(output, file=sys.stderr)
        return 1
    Path(args.output).write_bytes(base64.b64decode(output["glb_base64"]))
    print(f"wrote {args.output} ({Path(args.output).stat().st_size} bytes), seconds={output.get('seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
