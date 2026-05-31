import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@google/model-viewer';
import {
  ArrowDown,
  BracketsCurly,
  CheckCircle,
  CloudArrowUp,
  Cpu,
  Cube,
  DownloadSimple,
  GearSix,
  ImageSquare,
  Lightning,
  SlidersHorizontal,
  Sparkle,
  WarningCircle
} from '@phosphor-icons/react';
import './styles.css';

type Variant = 'direct' | 'comfy';
type Health = { ok: boolean; directConfigured: boolean; comfyConfigured: boolean; hasApiKey: boolean };

type GenerationState = 'idle' | 'ready' | 'running' | 'done' | 'error';

const variantCopy = {
  direct: {
    title: 'Direct Pixal3D',
    subtitle: 'Lean inference worker',
    text: 'Fast path via inference.py. Best for quick GLB generation and fewer moving parts.',
    meta: 'lower cold-start weight'
  },
  comfy: {
    title: 'ComfyUI Workflow',
    subtitle: 'Node graph pipeline',
    text: 'Runs the Pixal3D-ComfyUI workflow. Best when you want camera, texture and graph controls.',
    meta: 'more control, heavier runtime'
  }
};

function App() {
  const [variant, setVariant] = useState<Variant>('direct');
  const [health, setHealth] = useState<Health | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>('');
  const [modelUrl, setModelUrl] = useState<string>('');
  const [state, setState] = useState<GenerationState>('idle');
  const [error, setError] = useState('');
  const [seconds, setSeconds] = useState('');
  const [bytes, setBytes] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number | null>(null);

  const [form, setForm] = useState({
    lowVram: true,
    resolution: '1024',
    pipelineType: '1024_cascade',
    backgroundMode: 'none',
    cameraMode: 'manual',
    steps: '12',
    guidance: '7.5',
    textureGuidance: '1.0',
    textureSize: '2048',
    decimationTarget: '1000000',
    seed: '42'
  });

  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => null);
  }, []);

  useEffect(() => {
    if (state !== 'running') return;
    startedAt.current = Date.now();
    const timer = window.setInterval(() => {
      if (startedAt.current) setElapsed(Math.round((Date.now() - startedAt.current) / 1000));
    }, 500);
    return () => window.clearInterval(timer);
  }, [state]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (modelUrl) URL.revokeObjectURL(modelUrl);
    };
  }, [previewUrl, modelUrl]);

  const canGenerate = useMemo(() => {
    const configured = variant === 'direct' ? health?.directConfigured : health?.comfyConfigured;
    return Boolean(image && health?.hasApiKey && configured && state !== 'running');
  }, [image, health, variant, state]);

  function update(name: string, value: string | boolean) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  function onFile(file: File | null) {
    setImage(file);
    setError('');
    setState(file ? 'ready' : 'idle');
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(file ? URL.createObjectURL(file) : '');
  }

  async function generate() {
    if (!image) return;
    setState('running');
    setError('');
    setSeconds('');
    setBytes('');
    setElapsed(0);
    if (modelUrl) URL.revokeObjectURL(modelUrl);
    setModelUrl('');

    const body = new FormData();
    body.append('image', image);
    body.append('variant', variant);
    Object.entries(form).forEach(([key, value]) => body.append(key, String(value)));

    try {
      const response = await fetch('/api/generate', { method: 'POST', body });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.error || `Generation failed with ${response.status}`);
      }
      const blob = await response.blob();
      setSeconds(response.headers.get('X-Pixal3D-Seconds') || '');
      setBytes(response.headers.get('X-Pixal3D-Bytes') || String(blob.size));
      setModelUrl(URL.createObjectURL(blob));
      setState('done');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState('error');
    }
  }

  function downloadModel() {
    if (!modelUrl) return;
    const anchor = document.createElement('a');
    anchor.href = modelUrl;
    anchor.download = `pixal3d-${variant}-${Date.now()}.glb`;
    anchor.click();
  }

  const active = variantCopy[variant];

  return (
    <main className="shell">
      <div className="grain" />
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><Cube size={16} weight="duotone" /> Pixal3D RunPod Console</div>
          <h1>Generate 3D assets without keeping a GPU online.</h1>
          <p>
            A local control surface for two RunPod Serverless workers: direct Pixal3D inference and a ComfyUI graph.
            Your Mac handles upload, preview and download; RunPod wakes only for the render.
          </p>
        </div>
        <StatusPanel health={health} variant={variant} state={state} elapsed={elapsed} />
      </section>

      <section className="workspace">
        <aside className="control-rail">
          <div className="panel variant-panel">
            <div className="panel-label"><Lightning size={16} /> Engine</div>
            <Segmented variant={variant} setVariant={setVariant} />
            <div className="engine-note">
              <strong>{active.subtitle}</strong>
              <span>{active.text}</span>
              <small>{active.meta}</small>
            </div>
          </div>

          <UploadPanel image={image} previewUrl={previewUrl} onFile={onFile} />

          <SettingsPanel variant={variant} form={form} update={update} />

          <button className="generate-button" disabled={!canGenerate} onClick={generate}>
            <CloudArrowUp size={20} weight="duotone" />
            {state === 'running' ? `Generating ${elapsed}s` : 'Generate GLB'}
          </button>
          {!health?.hasApiKey && <InlineNotice tone="error" text="RUNPOD_API_KEY is missing in web-app/.env" />}
          {health && variant === 'direct' && !health.directConfigured && <InlineNotice tone="error" text="RUNPOD_DIRECT_ENDPOINT_ID is missing" />}
          {health && variant === 'comfy' && !health.comfyConfigured && <InlineNotice tone="error" text="RUNPOD_COMFY_ENDPOINT_ID is missing" />}
        </aside>

        <section className="stage-panel">
          <div className="stage-header">
            <div>
              <span className="panel-label"><ImageSquare size={16} /> Output stage</span>
              <h2>{state === 'done' ? 'Generated model ready' : 'Waiting for a generation'}</h2>
            </div>
            {modelUrl && <button className="secondary-button" onClick={downloadModel}><DownloadSimple size={18} /> Download GLB</button>}
          </div>

          <div className="viewer-shell">
            {modelUrl ? (
              <model-viewer
                src={modelUrl}
                camera-controls
                auto-rotate
                shadow-intensity="0.7"
                exposure="0.9"
                style={{ width: '100%', height: '100%' }}
              />
            ) : (
              <EmptyStage state={state} previewUrl={previewUrl} error={error} />
            )}
          </div>

          <div className="metrics-strip">
            <Metric label="Mode" value={active.title} />
            <Metric label="Generation" value={seconds ? `${seconds}s` : state === 'running' ? `${elapsed}s` : 'not started'} />
            <Metric label="GLB size" value={bytes ? formatBytes(Number(bytes)) : 'pending'} />
          </div>
        </section>
      </section>
    </main>
  );
}

function StatusPanel({ health, variant, state, elapsed }: { health: Health | null; variant: Variant; state: GenerationState; elapsed: number }) {
  const endpointReady = variant === 'direct' ? health?.directConfigured : health?.comfyConfigured;
  return (
    <div className="status-panel">
      <div className="status-topline"><Cpu size={18} /> Serverless readiness</div>
      <div className="status-grid">
        <StatusItem label="API key" ok={Boolean(health?.hasApiKey)} />
        <StatusItem label="Direct" ok={Boolean(health?.directConfigured)} />
        <StatusItem label="ComfyUI" ok={Boolean(health?.comfyConfigured)} />
        <StatusItem label="Selected" ok={Boolean(endpointReady)} />
      </div>
      <div className="runtime-line">
        <span className={`pulse ${state === 'running' ? 'active' : ''}`} />
        {state === 'running' ? `RunPod worker active for ${elapsed}s` : 'Worker remains at zero until you generate'}
      </div>
    </div>
  );
}

function StatusItem({ label, ok }: { label: string; ok: boolean }) {
  return <div className="status-item"><span>{label}</span>{ok ? <CheckCircle size={18} weight="fill" /> : <WarningCircle size={18} weight="fill" />}</div>;
}

function Segmented({ variant, setVariant }: { variant: Variant; setVariant: (value: Variant) => void }) {
  return (
    <div className="segmented">
      {(['direct', 'comfy'] as Variant[]).map((item) => (
        <button key={item} className={variant === item ? 'selected' : ''} onClick={() => setVariant(item)}>
          {item === 'direct' ? <BracketsCurly size={17} /> : <SlidersHorizontal size={17} />}
          {variantCopy[item].title}
        </button>
      ))}
    </div>
  );
}

function UploadPanel({ image, previewUrl, onFile }: { image: File | null; previewUrl: string; onFile: (file: File | null) => void }) {
  return (
    <label className="panel upload-panel">
      <input type="file" accept="image/*" onChange={(event) => onFile(event.target.files?.[0] || null)} />
      {previewUrl ? <img src={previewUrl} alt="Selected source" /> : <div className="upload-empty"><ArrowDown size={22} /> Drop or choose an image</div>}
      <div className="upload-caption">
        <strong>{image?.name || 'Source image'}</strong>
        <span>{image ? formatBytes(image.size) : 'PNG or JPG, object centered works best'}</span>
      </div>
    </label>
  );
}

function SettingsPanel({ variant, form, update }: { variant: Variant; form: Record<string, string | boolean>; update: (name: string, value: string | boolean) => void }) {
  return (
    <div className="panel settings-panel">
      <div className="panel-label"><GearSix size={16} /> Parameters</div>
      <div className="field-row split">
        <label>
          <span>Low VRAM</span>
          <select value={String(form.lowVram)} onChange={(e) => update('lowVram', e.target.value === 'true')}>
            <option value="true">Enabled</option>
            <option value="false">Disabled</option>
          </select>
        </label>
        <label>
          <span>Seed</span>
          <input value={String(form.seed)} onChange={(e) => update('seed', e.target.value)} />
        </label>
      </div>

      {variant === 'direct' ? (
        <label>
          <span>Resolution</span>
          <select value={String(form.resolution)} onChange={(e) => update('resolution', e.target.value)}>
            <option value="1024">1024</option>
            <option value="1536">1536</option>
          </select>
        </label>
      ) : (
        <>
          <div className="field-row split">
            <label>
              <span>Pipeline</span>
              <select value={String(form.pipelineType)} onChange={(e) => update('pipelineType', e.target.value)}>
                <option value="1024_cascade">1024 cascade</option>
                <option value="1536_cascade">1536 cascade</option>
              </select>
            </label>
            <label>
              <span>Background</span>
              <select value={String(form.backgroundMode)} onChange={(e) => update('backgroundMode', e.target.value)}>
                <option value="none">None</option>
                <option value="keep_alpha">Keep alpha</option>
                <option value="auto_remove">Auto remove</option>
              </select>
            </label>
          </div>
          <div className="field-row split">
            <label>
              <span>Steps</span>
              <input value={String(form.steps)} onChange={(e) => update('steps', e.target.value)} />
            </label>
            <label>
              <span>Texture</span>
              <select value={String(form.textureSize)} onChange={(e) => update('textureSize', e.target.value)}>
                <option value="1024">1024</option>
                <option value="2048">2048</option>
                <option value="4096">4096</option>
              </select>
            </label>
          </div>
          <div className="field-row split">
            <label>
              <span>Guidance</span>
              <input value={String(form.guidance)} onChange={(e) => update('guidance', e.target.value)} />
            </label>
            <label>
              <span>Texture guidance</span>
              <input value={String(form.textureGuidance)} onChange={(e) => update('textureGuidance', e.target.value)} />
            </label>
          </div>
        </>
      )}
    </div>
  );
}

function EmptyStage({ state, previewUrl, error }: { state: GenerationState; previewUrl: string; error: string }) {
  if (state === 'running') {
    return <div className="empty-stage"><div className="loader-bars"><span /><span /><span /></div><h3>Worker is generating the GLB</h3><p>Cold starts can take longer on the first request, especially while model weights are cached.</p></div>;
  }
  if (state === 'error') {
    return <div className="empty-stage error"><WarningCircle size={34} weight="duotone" /><h3>Generation stopped</h3><p>{error}</p></div>;
  }
  return <div className="empty-stage">{previewUrl ? <img src={previewUrl} alt="Source preview" /> : <Sparkle size={34} weight="duotone" />}<h3>{previewUrl ? 'Source image loaded' : 'Load an image to begin'}</h3><p>Select a worker, tune the parameters, then generate a GLB without leaving a GPU running.</p></div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function InlineNotice({ text }: { tone: 'error'; text: string }) {
  return <div className="inline-notice"><WarningCircle size={16} weight="fill" /> {text}</div>;
}

function formatBytes(value: number) {
  if (!Number.isFinite(value)) return 'pending';
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

createRoot(document.getElementById('root')!).render(<App />);
