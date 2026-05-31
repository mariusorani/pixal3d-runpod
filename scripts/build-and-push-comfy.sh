#!/usr/bin/env bash
set -euo pipefail

# Change this to your registry/image, e.g. docker.io/YOURUSER/pixal3d-comfy-runpod:latest
IMAGE="${IMAGE:-YOUR_REGISTRY_OR_DOCKERHUB_USER/pixal3d-comfy-runpod:latest}"

if [[ "$IMAGE" == YOUR_REGISTRY_OR_DOCKERHUB_USER* ]]; then
  echo "Run with: IMAGE=docker.io/you/pixal3d-comfy-runpod:latest ./scripts/build-and-push-comfy.sh" >&2
  exit 2
fi

cd "$(dirname "$0")/../runpod-worker-comfy"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
echo "Pushed: $IMAGE"
