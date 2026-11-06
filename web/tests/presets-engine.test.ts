// Applying presets: base defaults vs current, markers, skipped keys, actions, clearance switch, capture, settings hash.
import { afterEach, describe, expect, it } from 'vitest';
import { registerAction } from '../src/input/actions';
import { BUILTIN_PRESETS } from '../src/presets/builtin';
import { applyPreset, capturePreset, captureSections, resetDocument, settingsHash } from '../src/presets/engine';
import type { EngineEnv } from '../src/presets/engine';
import type { Preset } from '../src/presets/model';
import { DEFAULT_SIGHTLINES } from '../src/types';
import { PARAMS_SCHEMA } from '../src/ui/params';
import { fakeApp, fakeSection } from './presets-helpers';

const offs: Array<() => void> = [];
afterEach(() => {
  while (offs.length) offs.pop()!();
});

const mk = (over: Partial<Preset>): Preset => ({ id: 't', name: 'T', description: 'Test.', group: 'Basic', base: 'current', params: { schema: PARAMS_SCHEMA }, builtIn: false, ...over });

describe('applyPreset: base', () => {
  it('current applies over the present state and leaves untouched keys alone', () => {
    const f = fakeApp();
    f.app.settings.sightlines.gamma = 2;
    f.app.settings.sightlines.alphaMin = 0.5;
    const r = applyPreset(f.app, mk({ params: { sightlines: { alphaMin: 0 } } }), { paramsEnv: f.env });
    expect(f.app.settings.sightlines.alphaMin).toBe(0);
    expect(f.app.settings.sightlines.gamma).toBe(2);
    expect(r.skipped).toEqual([]);
    expect(r.partial).toBe(false);
    expect(f.calls.reclassify).toBe(1);
  });

  it('defaults first resets the touched section to the factory values, then applies', () => {
    const f = fakeApp();
    f.app.settings.sightlines.gamma = 2;
    f.app.settings.sightlines.layerFalloff = 0.9;
    f.app.display.edgeAlpha = 0.1;
    applyPreset(f.app, mk({ base: 'defaults', params: { sightlines: { alphaMin: 0 } } }), { paramsEnv: f.env });
    expect(f.app.settings.sightlines.alphaMin).toBe(0);
    expect(f.app.settings.sightlines.gamma).toBe(DEFAULT_SIGHTLINES.gamma);
    expect(f.app.settings.sightlines.layerFalloff).toBe(DEFAULT_SIGHTLINES.layerFalloff);
    // display is not touched by this preset, so it keeps the user's value
    expect(f.app.display.edgeAlpha).toBe(0.1);
  });

  it('an empty object marks a section as touched: reset under defaults, ignored under current', () => {
    const a = fakeApp();
    a.app.settings.sightlines.gamma = 2;
    applyPreset(a.app, mk({ base: 'defaults', params: { sightlines: {} } }), { paramsEnv: a.env });
    expect(a.app.settings.sightlines.gamma).toBe(DEFAULT_SIGHTLINES.gamma);
    const b = fakeApp();
    b.app.settings.sightlines.gamma = 2;
    const r = applyPreset(b.app, mk({ base: 'current', params: { sightlines: {} } }), { paramsEnv: b.env });
    expect(b.app.settings.sightlines.gamma).toBe(2);
    expect(r.skipped).toEqual([]);
  });

  it('resets plugin sections from the injected factory values, and cinematic only at the named first-level keys', () => {
    const f = fakeApp();
    const vm = fakeSection('viewModes', { behind: { enabled: false, frontTreatment: 'cut' }, peel: { enabled: false } });
    offs.push(vm.off);
    vm.state.peel.enabled = true;
    f.cfg['bloom'] = true;
    f.cfg['flyTo'] = false;
    const factory = { viewModes: { behind: { enabled: false, frontTreatment: 'cut' }, peel: { enabled: false } }, cinematic: { bloom: false, flyTo: true, grade: { enabled: false, strength: 0.5 } } };
    const env: EngineEnv = { paramsEnv: f.env, factory: (s) => (factory as Record<string, unknown>)[s] };
    applyPreset(f.app, mk({ base: 'defaults', params: { viewModes: { behind: { enabled: true } }, cinematic: { bloom: false } } }), env);
    expect(vm.state.peel.enabled).toBe(false); // reset
    expect(vm.state.behind.enabled).toBe(true); // applied
    expect(f.cfg['bloom']).toBe(false);
    expect(f.cfg['flyTo']).toBe(false); // not named, not reset
    const doc = resetDocument(f.app, { cinematic: { grade: { enabled: true } } }, env);
    expect(doc['cinematic']).toEqual({ grade: { enabled: false, strength: 0.5 } });
  });

  it('never resets the camera, overrides or selection sets', () => {
    const f = fakeApp();
    const doc = resetDocument(f.app, { camera: {}, overrides: {}, selectionSets: [], sightlines: {} });
    expect(Object.keys(doc).sort()).toEqual(['schema', 'sightlines']);
  });
});

describe('applyPreset: skipped keys', () => {
  it('applies the rest and lists unknown sections and keys', () => {
    const f = fakeApp();
    const r = applyPreset(f.app, mk({ params: { sightlines: { alphaMin: 0, noSuchKey: 1 }, imaging: { style: 'radiograph' }, xray: false } }), { paramsEnv: f.env });
    expect(f.app.settings.sightlines.alphaMin).toBe(0);
    expect(f.app.settings.xray).toBe(false);
    expect(r.skipped.sort()).toEqual(['imaging', 'sightlines.noSuchKey']);
    expect(r.partial).toBe(true);
    expect(r.applied).toContain('xray');
    expect(r.applied).not.toContain('imaging');
  });

  it('does not report empty markers of sections this build does not have', () => {
    const f = fakeApp();
    const r = applyPreset(f.app, mk({ base: 'defaults', params: { imaging: {}, section: {}, viewModes: {} } }), { paramsEnv: f.env });
    expect(r.skipped).toEqual([]);
  });

  it('applies a section when its plugin is present', () => {
    const f = fakeApp();
    const im = fakeSection('imaging', { style: 'standard', palette: 'classic', mri: { scan: false } });
    offs.push(im.off);
    const r = applyPreset(f.app, mk({ params: { imaging: { style: 'mri', mri: { scan: true } } } }), { paramsEnv: f.env });
    expect(r.skipped).toEqual([]);
    expect(im.state.style).toBe('mri');
    expect(im.state.mri.scan).toBe(true);
  });

  it('the built-in presets apply to a core-only app with skipped keys only for plugin sections', () => {
    for (const p of BUILTIN_PRESETS) {
      const f = fakeApp();
      const r = applyPreset(f.app, p, { paramsEnv: f.env, clearance: null, runAction: () => true });
      for (const s of r.skipped) expect(/^(viewModes|imaging|section|clearance)/.test(s), `${p.id}: ${s}`).toBe(true);
    }
    const f = fakeApp();
    applyPreset(f.app, BUILTIN_PRESETS.find((p) => p.id === 'hide-blockers')!, { paramsEnv: f.env });
    expect(f.app.settings.sightlines).toMatchObject({ alphaMin: 0, alphaMax: 1, farWeight: 1, layerWeighting: 'budget' });
    applyPreset(f.app, BUILTIN_PRESETS.find((p) => p.id === 'plain')!, { paramsEnv: f.env });
    expect(f.app.settings.xray).toBe(false);
    applyPreset(f.app, BUILTIN_PRESETS.find((p) => p.id === 'coordination')!, { paramsEnv: f.env });
    expect(f.app.settings.xray).toBe(true);
    expect(f.app.settings.sightlines.alphaMin).toBe(DEFAULT_SIGHTLINES.alphaMin);
  });
});

describe('applyPreset: actions and clearance', () => {
  it('runs the actions after the params are applied, in order', () => {
    const f = fakeApp();
    const order: string[] = [];
    offs.push(registerAction({ id: 'test.first', label: 'x', group: 'Test', keys: [], run: () => void order.push(`first:${f.app.settings.xray}`) }));
    offs.push(registerAction({ id: 'test.second', label: 'x', group: 'Test', keys: [], run: () => void order.push('second') }));
    const r = applyPreset(f.app, mk({ params: { xray: false }, actions: ['test.first', 'test.second', 'test.missing'] }), { paramsEnv: f.env });
    expect(order).toEqual(['first:false', 'second']);
    expect(r.actions).toEqual([{ id: 'test.first', ran: true }, { id: 'test.second', ran: true }, { id: 'test.missing', ran: false }]);
    expect(r.skipped).toEqual(['action:test.missing']);
  });

  it('switches clearance through its API (enabled is not a params field)', () => {
    const f = fakeApp();
    const sw = { enabled: true, setEnabled(on: boolean) { this.enabled = on; } };
    const cl = fakeSection('clearance', { tight: 0.05, max: 0.5 });
    offs.push(cl.off);
    const env: EngineEnv = { paramsEnv: f.env, clearance: sw, factory: () => ({ tight: 0.05, max: 0.5 }) };
    cl.state.max = 3;
    const r = applyPreset(f.app, mk({ base: 'defaults', params: { clearance: { enabled: true, tight: 0.1 } } }), env);
    expect(sw.enabled).toBe(true);
    expect(cl.state).toEqual({ tight: 0.1, max: 0.5 });
    expect(r.skipped).toEqual([]);
    applyPreset(f.app, mk({ base: 'defaults', params: { clearance: {} } }), env);
    expect(sw.enabled).toBe(false);
    // without the clearance tool, enabled is reported
    const r2 = applyPreset(f.app, mk({ params: { clearance: { enabled: true } } }), { paramsEnv: f.env, clearance: null });
    expect(r2.skipped).toContain('clearance.enabled');
  });
});

describe('applyPreset: frame selection (fix w7-10)', () => {
  it('frames the selection after the actions only when the preset asks for it', () => {
    const f = fakeApp();
    const order: string[] = [];
    offs.push(registerAction({ id: 'test.fit', label: 'x', group: 'Test', keys: [], run: () => void order.push('fit') }));
    const env: EngineEnv = { paramsEnv: f.env, frameSelection: () => (order.push('frame'), true) };
    const r = applyPreset(f.app, mk({ actions: ['test.fit'], frame: 'selection' }), env);
    expect(order).toEqual(['fit', 'frame']);
    expect(r.framed).toBe(true);
    expect(r.partial).toBe(false);
    order.length = 0;
    const r2 = applyPreset(f.app, mk({ actions: ['test.fit'] }), env);
    expect(order).toEqual(['fit']); // no flag: the camera is never moved
    expect(r2.framed).toBeUndefined();
    // nothing selected: not framed, and not reported as skipped
    const r3 = applyPreset(f.app, mk({ frame: 'selection' }), { paramsEnv: f.env, frameSelection: () => false });
    expect(r3.framed).toBe(false);
    expect(r3.skipped).toEqual([]);
  });

  it('section-focus, behind-only, peelback and peel-only frame the selection; the others do not', () => {
    const framed = BUILTIN_PRESETS.filter((p) => p.frame === 'selection').map((p) => p.id).sort();
    expect(framed).toEqual(['behind-only', 'peel-only', 'peelback', 'section-focus']);
  });
});

describe('capture', () => {
  it('stores the ticked sections as a partial params document and reports missing ones', () => {
    const f = fakeApp();
    f.app.settings.sightlines.alphaMin = 0.01;
    f.app.display.inFront = false;
    const { preset, missing } = capturePreset(f.app, ['sightlines', 'display', 'imaging'], { name: 'My look', description: ' Mine. ' }, { paramsEnv: f.env });
    expect(missing).toEqual(['imaging']);
    expect(Object.keys(preset.params).sort()).toEqual(['display', 'schema', 'sightlines']);
    expect((preset.params['sightlines'] as { alphaMin: number }).alphaMin).toBe(0.01);
    expect(preset).toMatchObject({ id: 'my-look', name: 'My look', description: 'Mine.', builtIn: false, base: 'current' });
    expect(captureSections(f.app, { paramsEnv: f.env })).toContain('sightlines');
    expect(captureSections(f.app, { paramsEnv: f.env })).not.toContain('selectionSets');
  });

  it('a captured preset applies back to the same state', () => {
    const f = fakeApp();
    f.app.settings.sightlines.alphaMin = 0.01;
    f.app.settings.farMode = 'hidden';
    const { preset } = capturePreset(f.app, ['sightlines', 'farMode'], { name: 'A' }, { paramsEnv: f.env });
    f.app.settings.sightlines.alphaMin = 0.7;
    f.app.settings.farMode = 'opaque';
    applyPreset(f.app, preset, { paramsEnv: f.env });
    expect(f.app.settings.sightlines.alphaMin).toBe(0.01);
    expect(f.app.settings.farMode).toBe('hidden');
  });

  it('captures the clearance switch', () => {
    const f = fakeApp();
    const cl = fakeSection('clearance', { tight: 0.05, max: 0.5 });
    offs.push(cl.off);
    const { preset } = capturePreset(f.app, ['clearance'], { name: 'C' }, { paramsEnv: f.env, clearance: { enabled: true, setEnabled() {} } });
    expect(preset.params['clearance']).toEqual({ tight: 0.05, max: 0.5, enabled: true });
  });
});

describe('settingsHash', () => {
  it('changes with settings, not with the camera', () => {
    const f = fakeApp();
    const env: EngineEnv = { paramsEnv: f.env, clearance: null };
    const h0 = settingsHash(f.app, env);
    f.app.renderer.camera.position.set(1, 2, 3);
    expect(settingsHash(f.app, env)).toBe(h0);
    f.cfg['dollyProgress'] = 0.5;
    expect(settingsHash(f.app, env)).toBe(h0);
    f.app.settings.sightlines.gamma = 1.7;
    expect(settingsHash(f.app, env)).not.toBe(h0);
  });
});
