#!/usr/bin/env python3
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


def post_runpod(endpoint_id: str, api_key: str, payload: dict, sync: bool) -> dict:
    mode = "runsync" if sync else "run"
    r = requests.post(
        api_url(endpoint_id, mode),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"input": payload},
        timeout=190 if sync else 60,
    )
    r.raise_for_status()
    return r.json()


def poll(endpoint_id: str, api_key: str, job_id: str, interval: float = 3.0) -> dict:
    url = api_url(endpoint_id, f"status/{job_id}")
    while True:
        r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        print(f"status: {status}")
        if status in {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}:
            return data
        time.sleep(interval)


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Generate a 3D GLB from an image via RunPod Pixal3D Serverless")
    p.add_argument("--image", required=True, help="Input image path")
    p.add_argument("--output", required=True, help="Output .glb path")
    p.add_argument("--endpoint-id", default=os.getenv("RUNPOD_ENDPOINT_ID"))
    p.add_argument("--api-key", default=os.getenv("RUNPOD_API_KEY"))
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--low-vram", action="store_true", default=True)
    p.add_argument("--no-low-vram", dest="low_vram", action="store_false")
    p.add_argument("--async-run", action="store_true", help="Use async /run + polling instead of /runsync")
    p.add_argument("--timeout-sec", type=int, default=1800)
    args = p.parse_args()

    if not args.api_key or not args.endpoint_id:
        print("Missing RUNPOD_API_KEY or RUNPOD_ENDPOINT_ID. Put them in local-client/.env or pass flags.", file=sys.stderr)
        return 2

    image_bytes = Path(args.image).read_bytes()
    payload = {
        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
        "low_vram": args.low_vram,
        "resolution": args.resolution,
        "timeout_sec": args.timeout_sec,
    }

    if args.async_run:
        first = post_runpod(args.endpoint_id, args.api_key, payload, sync=False)
        job_id = first.get("id")
        if not job_id:
            print(first, file=sys.stderr)
            return 1
        print(f"job id: {job_id}")
        data = poll(args.endpoint_id, args.api_key, job_id)
    else:
        data = post_runpod(args.endpoint_id, args.api_key, payload, sync=True)

    output = data.get("output") or data
    if not output.get("ok"):
        print("RunPod/Pixal3D failed:", file=sys.stderr)
        print(output, file=sys.stderr)
        return 1

    if "glb_base64" not in output:
        print("No glb_base64 in response. If the file is large, configure output_upload_url.", file=sys.stderr)
        print(output, file=sys.stderr)
        return 1

    Path(args.output).write_bytes(base64.b64decode(output["glb_base64"]))
    print(f"wrote {args.output} ({Path(args.output).stat().st_size} bytes), generation seconds={output.get('seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
