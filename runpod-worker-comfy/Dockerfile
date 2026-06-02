FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    COMFY_DIR=/workspace/ComfyUI \
    PYTHONPATH=/workspace/ComfyUI:/workspace/ComfyUI/custom_nodes/Pixal3D-ComfyUI:/workspace/Pixal3D:/workspace/TRELLIS.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs curl wget ca-certificates build-essential cmake ninja-build \
    python3.10 python3.10-dev python3.10-venv python3-pip \
    libgl1 libglib2.0-0 libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip

WORKDIR /workspace
COPY requirements.txt /tmp/worker-requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -r /tmp/worker-requirements.txt

# Core repos
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /workspace/ComfyUI && \
    git clone --recursive https://github.com/microsoft/TRELLIS.2.git /workspace/TRELLIS.2 && \
    git clone -b master https://github.com/TencentARC/Pixal3D.git /workspace/Pixal3D && \
    git clone https://github.com/Saganaki22/Pixal3D-ComfyUI.git /workspace/ComfyUI/custom_nodes/Pixal3D-ComfyUI

# Install CUDA/Torch stack from Pixal3D HF demo, then ComfyUI and custom node safe deps.
# Do not use the hosted natten wheel: it is built for HF/H-series GPUs; A40 needs sm86 kernels.
RUN grep -v '^https://github.com/LDYang694/Storages/releases/download/20260430/natten-' /workspace/Pixal3D/requirements-hfdemo.txt > /tmp/requirements-hfdemo-no-natten.txt && \
    grep -Ev '^(torch|torchvision|torchaudio)([=<>~ ].*)?$' /workspace/ComfyUI/requirements.txt > /tmp/comfyui-requirements-no-torch.txt && \
    grep -Ev '^(natten|utils3d)([=<>~ ].*)?$' /workspace/ComfyUI/custom_nodes/Pixal3D-ComfyUI/requirements.txt > /tmp/pixal3d-comfy-requirements-safe.txt && \
    python -m pip install -r /tmp/requirements-hfdemo-no-natten.txt && \
    python -m pip install --no-deps --index-url https://download.pytorch.org/whl/cu124 torchaudio==2.6.0+cu124 && \
    NATTEN_CUDA_ARCH="8.6" NATTEN_N_WORKERS=4 python -m pip install natten==0.21.0 --no-build-isolation && \
    python -m pip install https://github.com/LDYang694/Storages/releases/download/20260430/utils3d-0.0.2-py3-none-any.whl && \
    python -m pip install -r /tmp/comfyui-requirements-no-torch.txt && \
    python -m pip install -r /tmp/pixal3d-comfy-requirements-safe.txt && \
    python -c "import torch, torchvision, torchaudio, natten, o_voxel; print('torch', torch.__version__); print('torchvision', torchvision.__version__); print('torchaudio', torchaudio.__version__); print('natten', natten.__version__); print('o_voxel ok')"

# Let the nodepack use the cloned Pixal3D repo if it supports PIXAL3D_REPO_PATH.
ENV PIXAL3D_REPO_PATH=/workspace/Pixal3D

COPY patch_pixal3d_naf.py /workspace/patch_pixal3d_naf.py
RUN python /workspace/patch_pixal3d_naf.py

COPY pixal3d_api_prompt.json /workspace/pixal3d_api_prompt.json
COPY handler.py /workspace/handler.py
CMD ["python", "-u", "/workspace/handler.py"]
