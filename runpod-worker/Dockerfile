# Pixal3D/TRELLIS.2 require Linux + NVIDIA CUDA. This image is intended for RunPod Serverless.
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIXAL3D_DIR=/workspace/Pixal3D \
    ATTN_BACKEND=sdpa

RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs curl wget ca-certificates build-essential ninja-build \
    python3.10 python3.10-dev python3.10-venv python3-pip \
    libgl1 libglib2.0-0 libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip

WORKDIR /workspace

# Base serverless deps
COPY requirements.txt /tmp/worker-requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -r /tmp/worker-requirements.txt

# Clone project repos. TRELLIS.2 is included in PYTHONPATH because Pixal3D uses it as backbone.
RUN git clone --recursive https://github.com/microsoft/TRELLIS.2.git /workspace/TRELLIS.2 && \
    git clone -b master https://github.com/TencentARC/Pixal3D.git /workspace/Pixal3D

# Install Pixal3D HF demo dependencies, but do not use the hosted natten wheel.
# Pixal3D's requirements-hfdemo.txt is built for HF/H-series GPUs; A40 needs sm86 kernels.
RUN grep -v '^https://github.com/LDYang694/Storages/releases/download/20260430/natten-' /workspace/Pixal3D/requirements-hfdemo.txt > /tmp/requirements-hfdemo-no-natten.txt && \
    python -m pip install -r /tmp/requirements-hfdemo-no-natten.txt && \
    NATTEN_CUDA_ARCH="8.6" NATTEN_N_WORKERS=4 python -m pip install natten==0.21.0 --no-build-isolation && \
    python -m pip install https://github.com/LDYang694/Storages/releases/download/20260430/utils3d-0.0.2-py3-none-any.whl

ENV PYTHONPATH=/workspace/Pixal3D:/workspace/TRELLIS.2

COPY patch_pixal3d_naf.py /workspace/patch_pixal3d_naf.py
RUN python /workspace/patch_pixal3d_naf.py

COPY handler.py /workspace/handler.py
CMD ["python", "-u", "/workspace/handler.py"]
