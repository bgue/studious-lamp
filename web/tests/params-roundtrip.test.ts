// Export / import of viewer parameters: collect -> JSON -> apply round trip, globalId mapping, unknown keys,
// share-URL encoding and the Python dict output.

import { describe, expect, it } from 'vitest';
import { defaultSettings } from '../src/controller';
import type { ControllerSettings } from '../src/controller';
import { MemoryStorage, saveSets } from '../src/selectionSets';
import {
  PARAMS_SCHEMA,
  applyParams,
  collectParams,
  decodeShare,
  defaultParams,
  encodeShare,
  shareFromHash,
  shareSubset,
  shareUrl,
  snapshotSections,
  toPython,
  VIEWER_VERSION,
} from '../src/ui/params';
import { fakeSection } from './presets-helpers';
import type { ParamsApp, ParamsEnv } from '../src/ui/params';
import { modelOf } from './sidebar-model';
import pkg from '../package.json';

const specs = Array.from({ length: 6 }, (_, i) => ({ cls: i < 3 ? 'IfcDuctSegment' : 'IfcSlab', name: `E${i}`, storey: 0 }));
const storeys = [{ id: 0, name: 'L0', elevation: 0 }];

class V3 {
  constructor(public x = 0, public y = 0, public z = 0) {}
  set(x: number, y: number, z: number): this {
    this.x = x;
    this.y = y;
    this.z = z;
    return this;
  }
}

interface Fake {
  app: ParamsApp;
  env: ParamsEnv;
  calls: { reclassify: number; edge: number[] };
  cfg: Record<string, unknown>;
}

/** A plain-object stand-in for ViewerApp. `reverse` lists the elements in the opposite order (different numeric ids). */
function fakeApp(reverse = false, model = 'building'): Fake {
  const order = reverse ? [...specs].reverse() : specs;
  const m = modelOf(order.map((s, i) => ({ ...s, name: `${s.name}-${i}` })), storeys);
  // globalIds follow the spec, not the position, so a reversed order has different ids for the same globalId.
  const ids = reverse ? [5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5];
  m.elements.forEach((e, i) => (e.globalId = `GID-${ids[i]}`));
  m.byGlobalId = new Map(m.elements.map((e) => [e.globalId, e.id]));

  const settings = defaultSettings();
  const controllerSettings: ControllerSettings = { ...settings }; // shallow copy, like XrayController
  const calls = { reclassify: 0, edge: [] as number[] };
  const cfg = {
    flyTo: true,
    flyMs: 900,
    fogStrength: 0.4,
    dollyPlaying: false,
    dollyProgress: 0,
    sweep: { enabled: true, mode: 'both', durationMs: 900 },
  };
  const camera = { position: new V3(10, 8, 10) };
  const controls = { target: new V3(0, 0, 0), update() {} };
  const app: ParamsApp = {
    modelName: model,
    settings,
    display: { edgeAlpha: 0.8, ghostDesaturate: 0.8, inFront: true },
    controller: {
      model: m,
      settings: controllerSettings,
      setClassStyles(styles, aliases) {
        controllerSettings.classStyles = styles;
        if (aliases) controllerSettings.materialAliases = aliases;
      },
    },
    renderer: { camera, controls, setEdgeAlpha: (v) => calls.edge.push(v) },
    reclassify: () => void calls.reclassify++,
  };
  return { app, env: { storage: new MemoryStorage(), cinematic: cfg, now: new Date('2026-01-02T03:04:05Z') }, calls, cfg };
}

/** Put the fake app into a non-default state that touches every exported block. */
function tweak(f: Fake): void {
  const { app } = f;
  const s = app.settings;
  s.classification.bufferBase = 0.42;
  s.classification.focusClasses = ['IfcDuctSegment'];
  s.sightlines.gamma = 1.25;
  s.sightlines.occluderScope = 'near';
  (s.sightlines as unknown as Record<string, unknown>)['layerWeighting'] = 'exp';
  s.overrides.userPinFloor = 0.7;
  s.overrides.categoryFloors['IfcSlab'] = 0.33;
  s.overrides.userPins.add(1);
  s.overrides.userHides.add(4);
  s.overrides.projectPins[2] = 0.9;
  s.farMode = 'hidden';
  s.tiersMode = true;
  s.tiers = [['IfcDuctSegment'], ['IfcSlab']];
  app.display.edgeAlpha = 0.5;
  app.display.inFront = false;
  app.controller.settings.classStyles = { IfcSlab: { alphaMax: 0.6, color: [0.1, 0.2, 0.3] } };
  app.controller.settings.materialAliases = { Steel: ['IfcBeam:steel'] };
  f.cfg['flyMs'] = 1500;
  (f.cfg['sweep'] as Record<string, unknown>)['mode'] = 'stagger';
  f.cfg['dollyPlaying'] = true; // transient, must not be exported
  app.renderer.camera.position.set(1.5, 2.5, 3.5);
  app.renderer.controls!.target.set(4, 5, 6);
  saveSets(f.env.storage!, app.modelName, [{ name: 'Ducts', globalIds: ['GID-0', 'GID-1'] }]);
}

/** A fresh app with the same extra sightline key as the source (the real defaults carry it). */
function fresh(reverse = false): Fake {
  const f = fakeApp(reverse);
  (f.app.settings.sightlines as unknown as Record<string, unknown>)['layerWeighting'] = 'none';
  return f;
}

function normalise(p: unknown): unknown {
  const c = JSON.parse(JSON.stringify(p)) as Record<string, unknown>;
  delete c['exportedAt'];
  return c;
}

describe('collect / apply round trip', () => {
  it('collects the documented schema', () => {
    const f = fresh();
    tweak(f);
    const p = collectParams(f.app, f.env);
    expect(p.schema).toBe(PARAMS_SCHEMA);
    expect(p.exportedAt).toBe('2026-01-02T03:04:05.000Z');
    expect(p.viewer.version).toBe(pkg.version);
    expect(VIEWER_VERSION).toBe(pkg.version);
    expect(p.model).toBe('building');
    expect(Object.keys(p).sort()).toEqual(
      ['camera', 'cinematic', 'classStyles', 'classification', 'display', 'exportedAt', 'farMode', 'materialAliases', 'model', 'overrides',
        'schema', 'selectionSets', 'sightlines', 'tiers', 'tiersMode', 'viewer', 'xray'].sort(),
    );
    // Sightlines are copied generically: the extra key is there next to the standard ones.
    expect(p.sightlines['layerWeighting']).toBe('exp');
    expect(p.sightlines['occluderScope']).toBe('near');
    expect(p.sightlines['farWeight']).toBe(0.7);
    // Transient playback state is not a parameter.
    expect(p.cinematic).toBeDefined();
    expect('dollyPlaying' in p.cinematic!).toBe(false);
    expect(p.cinematic!['flyMs']).toBe(1500);
    expect(p.camera).toEqual({ position: [1.5, 2.5, 3.5], target: [4, 5, 6] });
    // No rendering block without setOit.
    expect(p.rendering).toBeUndefined();
  });

  it('JSON -> fresh app yields equal settings and a second collect equals the first', () => {
    const a = fresh();
    tweak(a);
    const json = JSON.stringify(collectParams(a.app, a.env), null, 2);

    const b = fresh();
    b.env.storage = new MemoryStorage();
    const bad = applyParams(b.app, JSON.parse(json), { env: b.env });
    expect(bad).toEqual([]);
    expect(b.calls.reclassify).toBe(1);

    expect(b.app.settings.classification).toEqual(a.app.settings.classification);
    expect(b.app.settings.sightlines).toEqual(a.app.settings.sightlines);
    expect(b.app.settings.overrides).toEqual(a.app.settings.overrides);
    expect(b.app.settings.farMode).toBe('hidden');
    expect(b.app.settings.tiersMode).toBe(true);
    expect(b.app.settings.tiers).toEqual([['IfcDuctSegment'], ['IfcSlab']]);
    expect(b.app.display).toEqual(a.app.display);
    expect(b.calls.edge).toEqual([0.5]);
    expect(b.app.controller.settings.classStyles).toEqual(a.app.controller.settings.classStyles);
    expect(b.app.controller.settings.materialAliases).toEqual(a.app.controller.settings.materialAliases);
    // The controller's own copy of the scalar settings follows too (it is a shallow copy of app.settings).
    expect(b.app.controller.settings.farMode).toBe('hidden');
    expect(b.app.controller.settings.tiersMode).toBe(true);
    expect(b.cfg['flyMs']).toBe(1500);
    expect((b.cfg['sweep'] as Record<string, unknown>)['mode']).toBe('stagger');
    expect(b.app.renderer.camera.position).toMatchObject({ x: 1.5, y: 2.5, z: 3.5 });
    expect(b.app.renderer.controls!.target).toMatchObject({ x: 4, y: 5, z: 6 });

    expect(normalise(collectParams(b.app, b.env))).toEqual(normalise(JSON.parse(json)));
  });

  it('maps globalIds back to ids of a model that numbers its elements differently', () => {
    const a = fresh();
    tweak(a);
    const p = collectParams(a.app, a.env);
    expect(p.overrides.userPins).toEqual(['GID-1']);
    expect(p.overrides.userHides).toEqual(['GID-4']);
    expect(p.overrides.projectPins).toEqual({ 'GID-2': 0.9 });

    const b = fresh(true); // ids reversed: GID-1 is element 4, GID-4 is element 1, GID-2 is element 3
    expect(b.app.controller.model.byGlobalId.get('GID-1')).toBe(4);
    const bad = applyParams(b.app, JSON.parse(JSON.stringify(p)), { env: b.env });
    expect(bad).toEqual([]);
    expect([...b.app.settings.overrides.userPins]).toEqual([4]);
    expect([...b.app.settings.overrides.userHides]).toEqual([1]);
    expect(b.app.settings.overrides.projectPins).toEqual({ 3: 0.9 });
    // And back again: the globalIds are stable.
    expect(collectParams(b.app, b.env).overrides).toEqual(p.overrides);
  });

  it('replaces pins, hides and project pins instead of merging them', () => {
    const b = fresh();
    b.app.settings.overrides.userPins.add(0);
    b.app.settings.overrides.projectPins[5] = 0.5;
    applyParams(b.app, { schema: PARAMS_SCHEMA, overrides: { userPins: ['GID-2'], userHides: [], projectPins: {} } }, { env: b.env });
    expect([...b.app.settings.overrides.userPins]).toEqual([2]);
    expect(b.app.settings.overrides.projectPins).toEqual({});
  });

  it('writes the selection sets to the storage key of the model', () => {
    const a = fresh();
    tweak(a);
    const p = collectParams(a.app, a.env);
    expect(p.selectionSets).toEqual([{ name: 'Ducts', globalIds: ['GID-0', 'GID-1'] }]);
    const b = fresh();
    b.env.storage = new MemoryStorage();
    applyParams(b.app, p, { env: b.env });
    expect(JSON.parse(b.env.storage.getItem('xray.sets.building')!)).toEqual({ version: 1, sets: p.selectionSets });
  });
});

describe('rendering (OIT)', () => {
  function withOit(f: Fake, supported = true) {
    const st = { on: true, w: 1 };
    const r = f.app.renderer as unknown as Record<string, unknown>;
    r['getOit'] = () => ({ orderIndependent: st.on, depthWeight: st.w });
    r['setOit'] = (o: { orderIndependent?: boolean; depthWeight?: number }) => {
      if (o.orderIndependent !== undefined) st.on = o.orderIndependent && supported;
      if (o.depthWeight !== undefined) st.w = o.depthWeight;
    };
    return st;
  }

  it('is exported and applied through renderer.getOit / setOit', () => {
    const a = fresh();
    const sa = withOit(a);
    sa.on = false;
    sa.w = 0;
    const p = collectParams(a.app, a.env);
    expect(p.rendering).toEqual({ orderIndependent: false, depthWeight: 0 });
    const b = fresh();
    const sb = withOit(b);
    expect(applyParams(b.app, JSON.parse(JSON.stringify(p)), { env: b.env })).toEqual([]);
    expect(sb).toEqual({ on: false, w: 0 });
  });

  it('reports a renderer that cannot do OIT', () => {
    const b = fresh();
    withOit(b, false);
    expect(applyParams(b.app, { schema: PARAMS_SCHEMA, rendering: { orderIndependent: true, depthWeight: 1 } }, { env: b.env })).toEqual(['rendering.orderIndependent']);
  });
});

describe('unknown and invalid input', () => {
  it('reports unknown keys and bad values instead of throwing', () => {
    const f = fresh();
    const before = JSON.stringify(f.app.settings.sightlines);
    let bad: string[] = [];
    expect(() => {
      bad = applyParams(
        f.app,
        {
          schema: PARAMS_SCHEMA,
          futureThing: 1,
          classification: { bufferBase: 0.9, nope: 3, storeyBand: 'wide' },
          sightlines: { gamma: 2, missingKey: 1, occluderScope: 7 },
          overrides: { userPinFloor: 'x', userPins: ['GID-1', 'NOPE'], extra: 1 },
          farMode: 'sideways',
          display: { edgeAlpha: 0.1, sparkle: true },
          camera: { position: [1, 2], target: [0, 0, 0] },
          cinematic: { bogus: 1, flyMs: 'slow' },
          rendering: { orderIndependent: true },
        },
        { env: f.env },
      );
    }).not.toThrow();
    expect(bad).toEqual(
      expect.arrayContaining([
        'futureThing',
        'classification.nope',
        'classification.storeyBand',
        'sightlines.missingKey',
        'sightlines.occluderScope',
        'overrides.userPinFloor',
        'overrides.userPins[NOPE]',
        'overrides.extra',
        'farMode',
        'display.sparkle',
        'camera',
        'cinematic.bogus',
        'cinematic.flyMs',
        'rendering', // no setOit on the fake renderer
      ]),
    );
    // The valid parts were applied, the invalid ones left alone.
    expect(f.app.settings.classification.bufferBase).toBe(0.9);
    expect(f.app.settings.classification.storeyBand).toBe(1);
    expect(f.app.settings.sightlines.gamma).toBe(2);
    expect(f.app.settings.farMode).toBe('opaque');
    expect([...f.app.settings.overrides.userPins]).toEqual([1]);
    expect(f.app.display.edgeAlpha).toBe(0.1);
    expect(f.app.renderer.camera.position).toMatchObject({ x: 10, y: 8, z: 10 });
    expect(JSON.stringify(f.app.settings.sightlines)).not.toBe(before);
  });

  it('survives non-object input and a foreign schema', () => {
    const f = fresh();
    expect(applyParams(f.app, null)).toEqual(['<root>']);
    expect(applyParams(f.app, 'text')).toEqual(['<root>']);
    expect(applyParams(f.app, [1, 2])).toEqual(['<root>']);
    expect(applyParams(f.app, { schema: 'xray-params/2' }, { env: f.env })).toEqual(['schema']);
    expect(applyParams(f.app, {}, { env: f.env })).toEqual(['schema']);
  });
});

describe('cinematic edge glow scope', () => {
  it('maps the old glowNear switch to glowScope and rejects an unknown scope', () => {
    const f = fresh();
    (f.cfg as Record<string, unknown>)['glowScope'] = 'focus';
    expect(applyParams(f.app, { schema: PARAMS_SCHEMA, cinematic: { glowNear: true } }, { env: f.env })).toEqual([]);
    expect((f.cfg as Record<string, unknown>)['glowScope']).toBe('near');
    expect(applyParams(f.app, { schema: PARAMS_SCHEMA, cinematic: { glowNear: false } }, { env: f.env })).toEqual([]);
    expect((f.cfg as Record<string, unknown>)['glowScope']).toBe('focus');
    // A new document wins over the old key when both are present.
    expect(applyParams(f.app, { schema: PARAMS_SCHEMA, cinematic: { glowNear: true, glowScope: 'all' } }, { env: f.env })).toEqual([]);
    expect((f.cfg as Record<string, unknown>)['glowScope']).toBe('all');
    expect(applyParams(f.app, { schema: PARAMS_SCHEMA, cinematic: { glowScope: 'host' } }, { env: f.env })).toEqual(['cinematic.glowScope']);
    expect((f.cfg as Record<string, unknown>)['glowScope']).toBe('all');
  });
});

describe('defaults', () => {
  it('defaultParams applied to a tweaked app restores the default settings', () => {
    const f = fresh();
    tweak(f);
    const bad = applyParams(f.app, defaultParams(f.app, { classStyles: { IfcSlab: { alphaMax: 0.9 } } }), { env: f.env });
    expect(bad).toEqual([]);
    const d = defaultSettings();
    expect(f.app.settings.classification).toEqual(d.classification);
    expect(f.app.settings.farMode).toBe('opaque');
    expect(f.app.settings.tiersMode).toBe(false);
    expect(f.app.settings.overrides.userPins.size).toBe(0);
    expect(f.app.settings.overrides.userPinFloor).toBe(d.overrides.userPinFloor);
    expect(f.app.display).toEqual({ edgeAlpha: 0.8, ghostDesaturate: 0.8, inFront: true });
    expect(f.app.controller.settings.classStyles).toEqual({ IfcSlab: { alphaMax: 0.9 } });
  });
});

describe('defaults of plugin sections', () => {
  it('a snapshot taken after the first model restores plugin sections that defaultParams does not cover', () => {
    const modes = fakeSection('viewModes', { peel: { enabled: false, radius: 1 } });
    const keys = fakeSection('keymap', { overrides: { a: ['x'] } });
    try {
      const f = fresh();
      const factory = snapshotSections(collectParams(f.app, f.env));
      expect(factory).toEqual({ viewModes: { peel: { enabled: false, radius: 1 } } }); // keymap left out
      tweak(f);
      modes.state.peel.enabled = true;
      modes.state.peel.radius = 3;
      keys.state.overrides = { a: ['y'] };
      const bad = applyParams(f.app, { ...defaultParams(f.app), ...factory }, { env: f.env });
      expect(bad).toEqual([]);
      expect(modes.state.peel).toEqual({ enabled: false, radius: 1 });
      expect(keys.state.overrides).toEqual({ a: ['y'] });
      expect(f.app.settings.farMode).toBe('opaque');
      // the snapshot is a copy, not a live reference
      modes.state.peel.enabled = true;
      expect(factory['viewModes']).toEqual({ peel: { enabled: false, radius: 1 } });
    } finally {
      modes.off();
      keys.off();
    }
  });
});

describe('factory value of a plugin section (fix w7-1)', () => {
  it('a section with factory() resets to that value, not to the state restored from localStorage at load', async () => {
    const { registerParamSection } = await import('../src/ui/params');
    const { gizmoFactoryState } = await import('../src/plugins/gizmo');
    const state = { visible: false, collapsed: true }; // hidden in an earlier visit (localStorage)
    const off = registerParamSection('gizmoTest', {
      collect: () => ({ ...state }),
      apply: (v) => Object.assign(state, v as object),
      factory: () => gizmoFactoryState(false),
    });
    try {
      const f = fresh();
      const factory = snapshotSections(collectParams(f.app, f.env));
      expect(factory['gizmoTest']).toEqual({ visible: true, collapsed: false });
      expect(applyParams(f.app, { ...defaultParams(f.app), ...factory }, { env: f.env })).toEqual([]);
      expect(state).toEqual({ visible: true, collapsed: false });
      expect(gizmoFactoryState(true)).toEqual({ visible: true, collapsed: true }); // phones start collapsed
    } finally {
      off();
    }
  });
});

describe('share URL', () => {
  it('round-trips the compact subset through base64url', () => {
    const f = fresh();
    tweak(f);
    f.app.modelName = 'fzk-haus Ünïcode ✓';
    const p = collectParams(f.app, f.env);
    const enc = encodeShare(p);
    expect(enc).toMatch(/^[A-Za-z0-9_-]+$/);
    const dec = decodeShare(enc)!;
    expect(dec).toEqual(shareSubset(p));
    expect(Object.keys(dec).sort()).toEqual(['camera', 'classification', 'display', 'farMode', 'model', 'schema', 'sightlines', 'tiersMode']);
    expect(dec.model).toBe('fzk-haus Ünïcode ✓');
    // Not in the subset: overrides, class styles, cinematic, sets.
    expect('overrides' in dec).toBe(false);
    expect('cinematic' in dec).toBe(false);
  });

  it('builds a URL whose fragment decodes, and ignores a broken fragment', () => {
    const f = fresh();
    const p = collectParams(f.app, f.env);
    const url = new URL(shareUrl(p, { origin: 'http://localhost:5173', pathname: '/' }));
    expect(url.searchParams.get('model')).toBe('building');
    expect(shareFromHash(url.hash)).toEqual(shareSubset(p));
    expect(shareFromHash('#a=1&p=' + encodeShare(p))).toEqual(shareSubset(p));
    expect(shareFromHash('')).toBeNull();
    expect(shareFromHash('#p=!!!notbase64')).toBeNull();
    expect(decodeShare('e30')).toEqual({}); // "{}"
    expect(decodeShare(btoa('[1]').replace(/=+$/, ''))).toBeNull(); // JSON, but not an object
  });

  it('a decoded share applies cleanly to a fresh app', () => {
    const a = fresh();
    tweak(a);
    const b = fresh();
    const bad = applyParams(b.app, decodeShare(encodeShare(collectParams(a.app, a.env))), { env: b.env });
    expect(bad).toEqual([]);
    expect(b.app.settings.sightlines).toEqual(a.app.settings.sightlines);
    expect(b.app.settings.farMode).toBe('hidden');
    expect(b.app.renderer.camera.position).toMatchObject({ x: 1.5, y: 2.5, z: 3.5 });
  });

  it('skipCamera leaves the camera alone', () => {
    const a = fresh();
    tweak(a);
    const b = fresh();
    applyParams(b.app, collectParams(a.app, a.env), { env: b.env, skipCamera: true });
    expect(b.app.renderer.camera.position).toMatchObject({ x: 10, y: 8, z: 10 });
  });
});

/** Tokenise a Python literal and turn it back into JSON: True/False/None outside strings, drop trailing commas. */
function pythonLiteralToJson(src: string): unknown {
  let out = '';
  let i = 0;
  const stack: string[] = [];
  while (i < src.length) {
    const ch = src[i]!;
    if (ch === '"') {
      let j = i + 1;
      while (src[j] !== '"') j += src[j] === '\\' ? 2 : 1;
      out += src.slice(i, j + 1);
      i = j + 1;
    } else if (/[A-Za-z]/.test(ch)) {
      const m = /^[A-Za-z_]\w*/.exec(src.slice(i))![0];
      const map: Record<string, string> = { True: 'true', False: 'false', None: 'null' };
      if (!(m in map)) throw new Error(`unexpected identifier ${m}`);
      out += map[m];
      i += m.length;
    } else {
      if (ch === '{' || ch === '[') stack.push(ch === '{' ? '}' : ']');
      if (ch === '}' || ch === ']') {
        if (stack.pop() !== ch) throw new Error('unbalanced');
        out = out.replace(/,(\s*)$/, '$1'); // trailing comma
      }
      out += ch;
      i++;
    }
  }
  if (stack.length) throw new Error('unbalanced');
  return JSON.parse(out);
}

describe('Python dict export', () => {
  it('is an XRAY_PARAMS literal with balanced braces and Python constants', () => {
    const f = fresh();
    tweak(f);
    const p = collectParams(f.app, f.env);
    p.selectionSets = [{ name: 'quote " and \\ and ünï', globalIds: [] }];
    const py = toPython(p);
    expect(py).toMatch(/^# .*\nXRAY_PARAMS = \{/m);
    expect(py.endsWith('}\n')).toBe(true);

    // Outside string literals: no JSON constants, balanced brackets.
    const bare = py.replace(/"(?:[^"\\]|\\.)*"/g, '""').replace(/^#.*$/gm, '');
    expect(bare).not.toMatch(/\b(true|false|null)\b/);
    const count = (c: string): number => bare.split(c).length - 1;
    expect(count('{')).toBe(count('}'));
    expect(count('[')).toBe(count(']'));
    expect(bare).toMatch(/\bTrue\b/);
    expect(bare).toMatch(/\bFalse\b/);

    const lit = py.slice(py.indexOf('XRAY_PARAMS = ') + 'XRAY_PARAMS = '.length);
    expect(pythonLiteralToJson(lit)).toEqual(JSON.parse(JSON.stringify(p)));
  });

  it('maps null and non-finite numbers to None', () => {
    const py = toPython({ schema: PARAMS_SCHEMA, sightlines: { a: null, b: Number.NaN, c: true, d: false, e: [], f: {} } });
    expect(py).toContain('"a": None');
    expect(py).toContain('"b": None');
    expect(py).toContain('"c": True');
    expect(py).toContain('"d": False');
    expect(py).toContain('"e": []');
    expect(py).toContain('"f": {}');
  });
});
