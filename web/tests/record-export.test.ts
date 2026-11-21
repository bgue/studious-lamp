import { describe, expect, it } from 'vitest';
import { etaMs, formatDuration, frameCount, frameTime, frameTimes } from '../src/anim/record/schedule';
import { avcCandidates, avcLevel, bitrateFor, chooseEncoder } from '../src/anim/record/encoder';
import type { ProbeConfig } from '../src/anim/record/encoder';
import { StoreZip, frameFileName } from '../src/anim/record/zip';
import { readZip } from '../src/bcf/zip';
import { hudPixelRatio, resolveOutputSize, withOutputSize } from '../src/anim/record/size';
import type { SizableRenderer } from '../src/anim/record/size';
import { runFrameLoop } from '../src/anim/record/frames';
import type { CanvasLike, FrameLoopDeps, FrameSink } from '../src/anim/record/frames';
import type { HudFrame, HudLayer } from '../src/anim/hud';
import { DEFAULT_OPTIONS, fileBase, sanitizeOptions, summarize } from '../src/anim/record/options';

describe('frame schedule', () => {
  it('has duration * fps frames, at least 1', () => {
    expect(frameCount(3, 30)).toBe(90);
    expect(frameCount(2.5, 24)).toBe(60);
    expect(frameCount(2, 60)).toBe(120);
    expect(frameCount(0.01, 30)).toBe(1);
    expect(frameCount(0, 30)).toBe(1);
    expect(frameCount(NaN, 30)).toBe(1);
  });
  it('steps by exactly 1 / fps from 0 and ends one step before the end', () => {
    const t = frameTimes(2, 30);
    expect(t.length).toBe(60);
    expect(t[0]).toBe(0);
    expect(t[1]).toBeCloseTo(1 / 30, 12);
    expect(t[59]).toBeCloseTo(59 / 30, 12);
    expect(t[59]!).toBeLessThan(2);
    for (let i = 1; i < t.length; i++) expect(t[i]! - t[i - 1]!).toBeCloseTo(1 / 30, 12);
    expect(frameTime(90, 30)).toBe(3);
  });
  it('estimates the time left from the mean frame time', () => {
    expect(etaMs(0, 100, 0)).toBeNull();
    expect(etaMs(10, 100, 5000)).toBe(45000);
    expect(etaMs(100, 100, 5000)).toBe(0);
  });
  it('formats durations', () => {
    expect(formatDuration(42000)).toBe('42 s');
    expect(formatDuration(185000)).toBe('3 min 05 s');
    expect(formatDuration(3720000)).toBe('1 h 02 min');
  });
});

describe('encoder choice', () => {
  const spec = { width: 1920, height: 1080, fps: 30, bitrate: 5e6 };
  const only = (...prefixes: string[]) => async (c: ProbeConfig) => prefixes.some((p) => c.codec.startsWith(p));

  it('auto prefers H.264 in MP4', async () => {
    const c = await chooseEncoder('auto', spec, only('avc1', 'vp09', 'vp8'));
    expect(c).toMatchObject({ container: 'mp4', codec: 'avc' });
    expect(c!.codecString.startsWith('avc1.')).toBe(true);
  });
  it('auto falls to VP9, then VP8 in WebM', async () => {
    expect(await chooseEncoder('auto', spec, only('vp09', 'vp8'))).toMatchObject({ container: 'webm', codec: 'vp9' });
    expect(await chooseEncoder('auto', spec, only('vp8'))).toMatchObject({ container: 'webm', codec: 'vp8', codecString: 'vp8' });
  });
  it('mp4 never falls back to WebM, webm never uses H.264', async () => {
    expect(await chooseEncoder('mp4', spec, only('vp09', 'vp8'))).toBeNull();
    expect(await chooseEncoder('webm', spec, only('avc1', 'vp09'))).toMatchObject({ container: 'webm', codec: 'vp9' });
    expect(await chooseEncoder('webm', spec, only('avc1'))).toBeNull();
  });
  it('returns null when nothing is supported and survives a throwing probe', async () => {
    expect(await chooseEncoder('auto', spec, async () => false)).toBeNull();
    expect(
      await chooseEncoder('auto', spec, async (c) => {
        if (c.codec.startsWith('avc1')) throw new Error('bad codec string');
        return c.codec === 'vp8';
      }),
    ).toMatchObject({ codec: 'vp8' });
  });
  it('tries the next H.264 profile when High is missing and passes the size and rate to the probe', async () => {
    const seen: ProbeConfig[] = [];
    const c = await chooseEncoder('mp4', spec, async (cfg) => {
      seen.push(cfg);
      return cfg.codec.startsWith('avc1.4d');
    });
    expect(c!.codecString.startsWith('avc1.4d')).toBe(true);
    expect(seen[0]).toMatchObject({ width: 1920, height: 1080, framerate: 30, bitrate: 5e6 });
    expect(seen.length).toBe(2);
  });
  it('picks an H.264 level that fits the size and the rate', () => {
    expect(avcLevel(1280, 720, 30)).toBe('1F');
    expect(avcLevel(1920, 1080, 30)).toBe('28');
    expect(avcLevel(1920, 1080, 60)).toBe('2A');
    expect(avcLevel(3840, 2160, 30)).toBe('33');
    expect(avcLevel(3840, 2160, 60)).toBe('34');
    expect(avcCandidates(1280, 720, 30)[0]).toBe('avc1.64001F');
  });
  it('gives bitrates that grow with size, rate and quality and stay in range', () => {
    expect(bitrateFor(1920, 1080, 30, 'low')).toBeLessThan(bitrateFor(1920, 1080, 30, 'medium'));
    expect(bitrateFor(1920, 1080, 30, 'medium')).toBeLessThan(bitrateFor(1920, 1080, 30, 'high'));
    expect(bitrateFor(1920, 1080, 60, 'medium')).toBeGreaterThan(bitrateFor(1920, 1080, 30, 'medium'));
    expect(bitrateFor(16, 16, 24, 'low')).toBe(1e6);
    expect(bitrateFor(7680, 4320, 60, 'high')).toBe(120e6);
  });
});

describe('store-only zip', () => {
  it('writes entries that the reader reads back, byte for byte', async () => {
    const z = new StoreZip(new Date(Date.UTC(2026, 5, 1, 12, 0, 0)));
    const a = new Uint8Array([1, 2, 3, 4, 5]);
    const b = new Uint8Array(1000).map((_, i) => i % 251);
    z.add(frameFileName(0), a);
    z.add(frameFileName(1, 'shot'), b);
    expect(z.count).toBe(2);
    const blob = z.finish();
    const entries = readZip(new Uint8Array(await blob.arrayBuffer()));
    expect(entries.map((e) => e.name)).toEqual(['frame-000001.png', 'shot-000002.png']);
    expect(entries.every((e) => e.method === 0)).toBe(true);
    expect(Array.from(await entries[0]!.read())).toEqual(Array.from(a));
    expect(Array.from(await entries[1]!.read())).toEqual(Array.from(b));
  });
  it('writes an empty archive that the reader accepts', async () => {
    const entries = readZip(new Uint8Array(await new StoreZip().finish().arrayBuffer()));
    expect(entries).toEqual([]);
  });
});

describe('output size and restore', () => {
  const window = { width: 1001, height: 563 };
  it('resolves choices to even sizes and caps them by the card limit', () => {
    expect(resolveOutputSize('1920x1080', window)).toEqual({ width: 1920, height: 1080 });
    expect(resolveOutputSize('window', window)).toEqual({ width: 1002, height: 564 });
    expect(resolveOutputSize('3840x2160', window, 2048)).toEqual({ width: 2048, height: 1152 });
    expect(resolveOutputSize('window', { width: 0, height: 0 })).toEqual({ width: 1280, height: 720 });
  });
  it('scales the HUD with the video height', () => {
    expect(hudPixelRatio({ width: 3840, height: 2160 }, 720)).toBe(3);
    expect(hudPixelRatio({ width: 640, height: 360 }, 720)).toBe(0.5);
  });

  class FakeRenderer implements SizableRenderer {
    size = { w: 800, h: 600 };
    calls: string[] = [];
    dirty = 0;
    setOutputSize(w: number, h: number): void {
      this.calls.push(`set ${w}x${h}`);
      this.size = { w, h };
    }
    clearOutputSize(): void {
      this.calls.push('clear');
      this.size = { w: 800, h: 600 };
    }
    markDirty(): void {
      this.dirty++;
    }
  }
  it('sets the size for the work and restores it after', async () => {
    const r = new FakeRenderer();
    const seen = await withOutputSize(r, { width: 1280, height: 720 }, () => r.size.w);
    expect(seen).toBe(1280);
    expect(r.size).toEqual({ w: 800, h: 600 });
    expect(r.calls).toEqual(['set 1280x720', 'clear']);
    expect(r.dirty).toBe(1);
  });
  it('restores when the work throws or rejects', async () => {
    const r = new FakeRenderer();
    await expect(withOutputSize(r, { width: 640, height: 360 }, () => Promise.reject(new Error('boom')))).rejects.toThrow('boom');
    expect(r.size).toEqual({ w: 800, h: 600 });
    await expect(
      withOutputSize(r, { width: 640, height: 360 }, () => {
        throw new Error('sync');
      }),
    ).rejects.toThrow('sync');
    expect(r.calls.filter((c) => c === 'clear').length).toBe(2);
  });
});

// ------------------------------------------------------------------ the frame loop with fake canvases

class FakeCtx {
  draws: string[] = [];
  fillStyle: unknown = '';
  constructor(private readonly tag: string) {}
  clearRect(): void {
    this.draws.push(`${this.tag}:clear`);
  }
  fillRect(): void {}
  drawImage(img: unknown): void {
    this.draws.push(`${this.tag}:image(${(img as { tag?: string }).tag ?? '?'})`);
  }
}
class FakeCanvas implements CanvasLike {
  ctx: FakeCtx;
  constructor(
    public width: number,
    public height: number,
    readonly tag: string,
  ) {
    this.ctx = new FakeCtx(tag);
  }
  getContext(): unknown {
    return this.ctx;
  }
}

function setup(over: Partial<FrameLoopDeps> = {}) {
  const canvases: FakeCanvas[] = [];
  const added: Array<{ index: number; time: number; dur: number }> = [];
  const steps: Array<{ i: number; t: number }> = [];
  const events: string[] = [];
  const sink: FrameSink = {
    start: async () => void events.push('start'),
    add: async (_c, index, time, dur) => void added.push({ index, time, dur }),
    finish: async () => ({ blob: new Blob([]), mime: 'x', extension: 'x', frames: added.length, description: 'fake' }),
    cancel: async () => void events.push('cancel'),
  };
  let clock = 0;
  const hudFrames: HudFrame[] = [];
  const hud: HudLayer = { active: (t) => t >= 0.1, draw: (_ctx, f) => void hudFrames.push(f) };
  const deps: FrameLoopDeps = {
    frames: 6,
    fps: 30,
    width: 640,
    height: 360,
    duration: 0.2,
    step: (i, t) => {
      steps.push({ i, t });
    },
    source: { tag: 'gl' },
    project: () => null,
    hud,
    hudPixelRatio: 0.5,
    sink,
    isCancelled: () => false,
    onProgress: () => {},
    yieldTurn: async () => {},
    now: () => (clock += 10),
    makeCanvas: (w, h) => {
      const c = new FakeCanvas(w, h, canvases.length === 0 ? 'out' : 'hud');
      canvases.push(c);
      return c;
    },
    ...over,
  };
  return { deps, canvases, added, steps, events, hudFrames };
}

describe('frame loop', () => {
  it('encodes duration * fps frames at 1 / fps steps and never reads the wall clock for the time', async () => {
    const s = setup();
    const r = await runFrameLoop(s.deps);
    expect(r.kind).toBe('done');
    expect(s.added.map((a) => a.index)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(s.added.map((a) => a.time)).toEqual([0, 1 / 30, 2 / 30, 3 / 30, 4 / 30, 5 / 30]);
    expect(s.added.every((a) => Math.abs(a.dur - 1 / 30) < 1e-12)).toBe(true);
    expect(s.steps.map((x) => x.i)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(s.events).toEqual(['start']);
  });
  it('draws the HUD over the frame only when the layer is active, with the recording frame', async () => {
    const s = setup();
    await runFrameLoop(s.deps);
    // t = 0, 0.033, 0.067 inactive; 0.1 and later active
    expect(s.hudFrames.length).toBe(3);
    expect(s.hudFrames[0]).toMatchObject({ recording: true, pixelRatio: 0.5, width: 1280, height: 720, duration: 0.2 });
    expect(s.hudFrames[0]!.t).toBeCloseTo(0.1, 9);
    const out = s.canvases[0]!;
    expect(out.ctx.draws.filter((d) => d === 'out:image(hud)').length).toBe(3);
    expect(out.ctx.draws.filter((d) => d === 'out:image(gl)').length).toBe(6);
  });
  it('skips the HUD without a layer', async () => {
    const s = setup({ hud: null });
    await runFrameLoop(s.deps);
    expect(s.canvases.length).toBe(1);
  });
  it('uses the clock the step returns for the HUD time', async () => {
    const s = setup({ step: () => 9 });
    await runFrameLoop(s.deps);
    expect(s.hudFrames.every((f) => f.t === 9)).toBe(true);
  });
  it('reports progress with frames done, total and a time left', async () => {
    const seen: Array<{ done: number; total: number; eta: number | null }> = [];
    const s = setup({ onProgress: (p) => void seen.push({ done: p.done, total: p.total, eta: p.etaMs }) });
    await runFrameLoop(s.deps);
    expect(seen.map((p) => p.done)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(seen.every((p) => p.total === 6)).toBe(true);
    expect(seen[5]!.eta).toBe(0);
    expect(seen[0]!.eta).toBeGreaterThan(0);
  });
  it('stops on cancel, cancels the sink and makes no file', async () => {
    let n = 0;
    const s = setup({ isCancelled: () => n >= 2, step: () => void n++ });
    const r = await runFrameLoop(s.deps);
    expect(r.kind).toBe('cancelled');
    expect(s.added.length).toBe(2);
    expect(s.events).toEqual(['start', 'cancel']);
  });
  it('cancels the sink and rethrows when a frame fails', async () => {
    const s = setup({
      step: (i) => {
        if (i === 3) throw new Error('render failed');
      },
    });
    await expect(runFrameLoop(s.deps)).rejects.toThrow('render failed');
    expect(s.events).toEqual(['start', 'cancel']);
    expect(s.added.length).toBe(3);
  });
});

describe('export options', () => {
  it('keeps good fields and drops bad ones', () => {
    expect(sanitizeOptions({ size: '3840x2160', fps: 60, quality: 'high', format: 'webm', hud: false, name: 'x' })).toEqual({ size: '3840x2160', fps: 60, quality: 'high', format: 'webm', hud: false, name: 'x' });
    expect(sanitizeOptions({ size: '1x1', fps: 500, quality: 'ultra', format: 'avi', hud: 'yes' })).toEqual(DEFAULT_OPTIONS);
    expect(sanitizeOptions(null)).toEqual(DEFAULT_OPTIONS);
    expect(sanitizeOptions({ fps: 12 }).fps).toBe(12); // any whole rate 1 to 120 (scripts, the xray-4d CLI)
  });
  it('makes a safe file name', () => {
    expect(fileBase('Tour: level 1/2')).toBe('Tour-level-1-2');
    expect(fileBase('  ')).toBe('fly-through');
    expect(fileBase('', 'script')).toBe('script');
    expect(fileBase('../../x')).toBe('x');
  });
  it('summarizes frames and a rough size', () => {
    const s = summarize(3, DEFAULT_OPTIONS, 1920, 1080);
    expect(s.frames).toBe(90);
    expect(s.megabytes).toBeGreaterThan(1);
    expect(summarize(3, { ...DEFAULT_OPTIONS, format: 'png' }, 640, 360).megabytes).toBeGreaterThan(10);
  });
});
