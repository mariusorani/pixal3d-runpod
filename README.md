# Pixal3D on RunPod Serverless

Local Mac UI/client + GPU-only RunPod Serverless worker. RunPod starts only for generation when `min workers = 0`.

## Architecture

```text
MacBook local client/app -> RunPod Serverless API -> Pixal3D worker -> .glb back to Mac
```

## Cost-safe RunPod settings

Use **Serverless**, not a normal Pod:

- Min Workers: `0`
- Max Workers: `1` initially
- Idle Timeout: `5-30s`
- GPU: start with `L40S 48GB` or `A6000 48GB`
- Optional but recommended: Network Volume for HuggingFace/model cache

## Files

- `runpod-worker/`: Docker image + serverless handler
- `local-client/`: local CLI to send an image and download `.glb`
- `scripts/`: helper scripts

## 1) Build/push worker image

Edit the image name in `scripts/build-and-push.sh`, then:

```bash
cd pixal3d-runpod
./scripts/build-and-push.sh
```

## 2) Create RunPod Serverless Endpoint

In RunPod:

1. Serverless → New Endpoint
2. Container Image: your pushed image
3. GPU: L40S/A6000/A100
4. Min Workers: `0`
5. Max Workers: `1`
6. Idle Timeout: `10s`
7. Container Disk: at least `80-120GB` if no network volume
8. Env vars, optional:
   - `HF_TOKEN` if gated/private models are needed
   - `MODEL_CACHE_DIR=/runpod-volume/hf-cache` if using Network Volume

## 3) Local usage

Create `.env`:

```bash
cp local-client/.env.example local-client/.env
```

Fill:

```env
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...
```

Install client deps:

```bash
cd local-client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Generate:

```bash
python generate.py --image ./input.png --output ./output.glb --low-vram --resolution 1024
```

## Notes

- Returning base64 GLB through RunPod is easiest, but for very large `.glb` files use `--upload-url` with a presigned S3/R2 URL.
- First request after scale-to-zero can be slow because the worker cold-starts and may download models. Use a Network Volume to cache weights.

---

## Optional: ComfyUI + Pixal3D-ComfyUI Serverless worker

I also added a ComfyUI-based worker:

```text
runpod-worker-comfy/
├── Dockerfile
├── handler.py
└── pixal3d_api_prompt.json
```

Build/push:

```bash
cd /Users/webcreatics/pixal3d-runpod
IMAGE=docker.io/YOURUSER/pixal3d-comfy-runpod:latest ./scripts/build-and-push-comfy.sh
```

Create another RunPod Serverless Endpoint using that image with the same cost-safe settings:

```text
Min Workers: 0
Max Workers: 1
Idle Timeout: 5-30s
GPU: L40S 48GB / A6000 48GB / A100
Container Disk: 100GB+
Network Volume: recommended for HF cache
```

Local ComfyUI worker call:

```bash
cd /Users/webcreatics/pixal3d-runpod/local-client
python generate_comfy.py --image input.png --output output.glb --pipeline-type 1024_cascade --background-mode none
```

### Direct worker vs ComfyUI worker

- `runpod-worker/`: simpler/faster direct Pixal3D `inference.py` path.
- `runpod-worker-comfy/`: heavier but flexible ComfyUI workflow path using `Saganaki22/Pixal3D-ComfyUI`.

The ComfyUI worker starts ComfyUI inside the serverless container, uploads the input image to ComfyUI, queues an API workflow, waits for `Pixal3DExportGLB`, then returns the `.glb`.

---

## Local Web App for both workers

A modern local web UI is available in:

```text
web-app/
```

It supports both:

- Direct Pixal3D worker
- ComfyUI + Pixal3D-ComfyUI worker

Setup:

```bash
cd /Users/webcreatics/pixal3d-runpod/web-app
cp .env.example .env
```

Fill `.env`:

```env
RUNPOD_API_KEY=...
RUNPOD_DIRECT_ENDPOINT_ID=...
RUNPOD_COMFY_ENDPOINT_ID=...
PORT=8787
```

Install and run:

```bash
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The API key stays server-side in the local Express proxy, not in browser JavaScript.

---

## Build without using Mac disk space: GitHub Actions + GHCR

If your Mac does not have enough free disk for CUDA Docker images, do **not** build locally. Push this folder to GitHub and let GitHub Actions build the images in the cloud, then push them to GitHub Container Registry.

Workflow included:

```text
.github/workflows/build-runpod-images.yml
```

It builds:

```text
ghcr.io/YOUR_GITHUB_USERNAME/pixal3d-runpod-direct:latest
ghcr.io/YOUR_GITHUB_USERNAME/pixal3d-runpod-comfy:latest
```

Steps:

```bash
cd /Users/webcreatics/pixal3d-runpod
git init
git add .
git commit -m "Initial Pixal3D RunPod serverless setup"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/pixal3d-runpod.git
git push -u origin main
```

Then open GitHub:

```text
https://github.com/YOUR_GITHUB_USERNAME/pixal3d-runpod/actions
```

Run workflow:

```text
Build RunPod Images → Run workflow → direct/comfy/both
```

Use the resulting GHCR image in RunPod Serverless.
