// Shared fake app for the presets tests: a ParamsApp (as in params-roundtrip) plus small fake plugin sections.
import { defaultSettings } from '../src/controller';
import type { ControllerSettings } from '../src/controller';
import { MemoryStorage } from '../src/selectionSets';
import { registerParamSection } from '../src/ui/params';
import type { ParamsApp, ParamsEnv } from '../src/ui/params';
import { modelOf } from './sidebar-model';

class V3 {
  constructor(public x = 0, public y = 0, public z = 0) {}
  set(x: number, y: number, z: number): this {
    this.x = x;
    this.y = y;
    this.z = z;
    return this;
  }
}

export interface Fake {
  app: ParamsApp;
  env: ParamsEnv;
  cfg: Record<string, unknown>;
  calls: { reclassify: number };
}

export function fakeApp(): Fake {
  const m = modelOf(Array.from({ length: 4 }, (_, i) => ({ cls: 'IfcSlab', name: `E${i}`, storey: 0 })), [{ id: 0, name: 'L0', elevation: 0 }]);
  const settings = defaultSettings();
  const controllerSettings: ControllerSettings = { ...settings };
  const calls = { reclassify: 0 };
  const cfg: Record<string, unknown> = {
    flyTo: true,
    bloom: false,
    edgeGlow: false,
    autoOrbit: false,
    dressing: true,
    reveal: true,
    dollyPlaying: false,
    dollyProgress: 0,
    sweep: { enabled: true, mode: 'both', durationMs: 900 },
    grade: { enabled: false, strength: 0.5 },
  };
  const app: ParamsApp = {
    modelName: 'building',
    settings,
    display: { edgeAlpha: 0.8, ghostDesaturate: 0.8, inFront: true },
    controller: { model: m, settings: controllerSettings },
    renderer: { camera: { position: new V3(10, 8, 10) }, controls: { target: new V3(0, 0, 0), update() {} } },
    reclassify: () => void calls.reclassify++,
  };
  return { app, env: { storage: new MemoryStorage(), cinematic: cfg, now: new Date('2026-01-02T03:04:05Z') }, cfg, calls };
}

/** Register a fake section that stores whatever object it is given (merging first-level and second-level keys that exist). */
export function fakeSection<T extends Record<string, unknown>>(name: string, initial: T): { state: T; off: () => void } {
  const state = JSON.parse(JSON.stringify(initial)) as T;
  const merge = (dst: Record<string, unknown>, src: unknown, path: string, bad: string[]): void => {
    if (!src || typeof src !== 'object' || Array.isArray(src)) {
      bad.push(path);
      return;
    }
    for (const [k, v] of Object.entries(src)) {
      if (!(k in dst)) bad.push(`${path}.${k}`);
      else if (dst[k] && typeof dst[k] === 'object' && !Array.isArray(dst[k])) merge(dst[k] as Record<string, unknown>, v, `${path}.${k}`, bad);
      else dst[k] = v;
    }
  };
  const off = registerParamSection(name, {
    collect: () => JSON.parse(JSON.stringify(state)),
    apply: (v, bad, path) => merge(state, v, path, bad),
  });
  return { state, off };
}
