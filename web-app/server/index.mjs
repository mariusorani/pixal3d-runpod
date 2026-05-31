import 'dotenv/config';
import express from 'express';
import multer from 'multer';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 25 * 1024 * 1024 } });
const PORT = Number(process.env.PORT || 8787);

app.use(express.json({ limit: '1mb' }));

function endpointForVariant(variant) {
  if (variant === 'direct') return process.env.RUNPOD_DIRECT_ENDPOINT_ID;
  if (variant === 'comfy') return process.env.RUNPOD_COMFY_ENDPOINT_ID;
  return undefined;
}

function runpodUrl(endpointId, mode) {
  return `https://api.runpod.ai/v2/${endpointId}/${mode}`;
}

async function runpodRequest(endpointId, payload, sync = true) {
  const apiKey = process.env.RUNPOD_API_KEY;
  if (!apiKey) throw new Error('RUNPOD_API_KEY is missing');

  const res = await fetch(runpodUrl(endpointId, sync ? 'runsync' : 'run'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ input: payload }),
    signal: AbortSignal.timeout(sync ? 190_000 : 60_000)
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error || `RunPod request failed with ${res.status}`);
  return data;
}

async function pollRunpod(endpointId, jobId, timeoutMs = 30 * 60 * 1000) {
  const apiKey = process.env.RUNPOD_API_KEY;
  const started = Date.now();

  while (Date.now() - started < timeoutMs) {
    const res = await fetch(runpodUrl(endpointId, `status/${jobId}`), {
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: AbortSignal.timeout(60_000)
    });
    const data = await res.json();
    if (['COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(data.status)) return data;
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }

  throw new Error('RunPod job polling timed out');
}

function normalizeOutput(data) {
  if (data?.output) return data.output;
  return data;
}

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    directConfigured: Boolean(process.env.RUNPOD_DIRECT_ENDPOINT_ID),
    comfyConfigured: Boolean(process.env.RUNPOD_COMFY_ENDPOINT_ID),
    hasApiKey: Boolean(process.env.RUNPOD_API_KEY)
  });
});

app.post('/api/generate', upload.single('image'), async (req, res) => {
  try {
    const variant = String(req.body.variant || 'direct');
    const endpointId = endpointForVariant(variant);
    if (!endpointId) throw new Error(`Endpoint for variant '${variant}' is not configured`);
    if (!req.file) throw new Error('Missing image file');

    const lowVram = req.body.lowVram !== 'false';
    const shared = {
      image_base64: req.file.buffer.toString('base64'),
      low_vram: lowVram,
      timeout_sec: Number(req.body.timeoutSec || 1800),
      seed: Number(req.body.seed || 42)
    };

    const directPayload = {
      ...shared,
      resolution: Number(req.body.resolution || (lowVram ? 1024 : 1536))
    };

    const comfyPayload = {
      ...shared,
      pipeline_type: String(req.body.pipelineType || (lowVram ? '1024_cascade' : '1536_cascade')),
      background_mode: String(req.body.backgroundMode || 'none'),
      camera_mode: String(req.body.cameraMode || 'manual'),
      steps: Number(req.body.steps || 12),
      guidance: Number(req.body.guidance || 7.5),
      texture_guidance: Number(req.body.textureGuidance || 1.0),
      texture_size: Number(req.body.textureSize || 2048),
      decimation_target: Number(req.body.decimationTarget || 1000000),
      vram_mode: String(req.body.vramMode || 'native_low_vram'),
      force_offload: lowVram,
      load_moge: req.body.cameraMode === 'moge',
      load_rembg: req.body.backgroundMode === 'auto_remove'
    };

    const payload = variant === 'comfy' ? comfyPayload : directPayload;

    let data = await runpodRequest(endpointId, payload, false);
    if (data?.id) data = await pollRunpod(endpointId, data.id, Number(payload.timeout_sec) * 1000 + 120_000);

    const output = normalizeOutput(data);
    if (!output?.ok) {
      return res.status(502).json({ ok: false, error: output?.error || 'Generation failed', details: output });
    }
    if (!output.glb_base64) {
      return res.status(502).json({ ok: false, error: 'Worker did not return glb_base64', details: output });
    }

    const buffer = Buffer.from(output.glb_base64, 'base64');
    res.setHeader('Content-Type', 'model/gltf-binary');
    res.setHeader('Content-Disposition', `attachment; filename="pixal3d-${variant}.glb"`);
    res.setHeader('X-Pixal3D-Seconds', String(output.seconds || ''));
    res.setHeader('X-Pixal3D-Bytes', String(buffer.length));
    res.send(buffer);
  } catch (error) {
    res.status(500).json({ ok: false, error: error instanceof Error ? error.message : String(error) });
  }
});

if (process.env.NODE_ENV === 'production') {
  const dist = path.resolve(__dirname, '../dist');
  app.use(express.static(dist));
  app.get('*', (_req, res) => res.sendFile(path.join(dist, 'index.html')));
}

app.listen(PORT, '127.0.0.1', () => {
  console.log(`Pixal3D web API listening on http://127.0.0.1:${PORT}`);
});
