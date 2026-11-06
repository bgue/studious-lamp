// Saved views: capture -> JSON -> restore round trip on a fake app, against a model whose element ids changed
// (GlobalIds stay), with a plugin section and the factory merge of a partial (shared) view.
import { afterEach, describe, expect, it } from 'vitest';
import { applyPlan, captureView, currentViewParams, planRestore } from '../src/views/capture';
import type { ViewsApp } from '../src/views/capture';
import { mergeParams, parseViewsDocument, shareView } from '../src/views/model';
import { fakeApp, fakeSection } from './presets-helpers';

const offs: Array<() => void> = [];
afterEach(() => {
  while (offs.length) offs.pop()!();
});

/** The presets fake app plus a selection, selectIds and a camera with up and fov. Element ids optionally reversed. */
function viewsApp(reverse = false): { app: ViewsApp; env: ReturnType<typeof fakeApp>['env']; selects: number } {
  const f = fakeApp();
  const m = f.app.controller.model as unknown as { elements: Array<{ id: number; globalId: string }>; byGlobalId: Map<string, number> };
  if (reverse) {
    const n = m.elements.length;
    m.elements.forEach((e, i) => (e.globalId = `G${n - 1 - i}`));
    m.byGlobalId = new Map(m.elements.map((e) => [e.globalId, e.id]));
  }
  const selection = new Set<number>();
  const cam = f.app.renderer.camera as unknown as Record<string, unknown>;
  cam['up'] = { x: 0, y: 1, z: 0, set() {} };
  cam['fov'] = 45;
  const out = { app: f.app as ViewsApp, env: f.env, selects: 0 };
  (out.app.controller as unknown as { selection: Set<number> }).selection = selection;
  out.app.selectIds = (ids) => {
    out.selects++;
    selection.clear();
    for (const id of ids) selection.add(id);
  };
  return out;
}

describe('capture and restore', () => {
  it('captures camera, selection, hides, pins and params by GlobalId', () => {
    const { app, env } = viewsApp();
    const sec = fakeSection('section', { box: { enabled: false, min: null as null | number[] }, plane: { enabled: false, offset: 0 } });
    offs.push(sec.off);
    app.renderer.camera.position.set(3, 4, 5);
    app.renderer.controls!.target.set(1, 1, 1);
    app.selectIds!([1]);
    app.settings.overrides.userHides.add(3);
    app.settings.overrides.userPins.add(2);
    app.settings.xray = app.controller.settings.xray = false;
    sec.state.box.enabled = true;
    sec.state.box.min = [0, 0, 0];
    const v = captureView(app, 'Mine', { paramsEnv: env, ortho: true, exploded: true, preset: 'peelback', now: new Date('2026-03-04T00:00:00Z') });
    expect(v.camera).toEqual({ position: [3, 4, 5], target: [1, 1, 1], up: [0, 1, 0], fov: 45, ortho: true });
    expect(v.selection).toEqual(['G1']);
    expect(v.hides).toEqual({ mode: 'hide', ids: ['G3'] });
    expect(v.pins).toEqual(['G2']);
    expect(v.exploded).toBe(true);
    expect(v.preset).toBe('peelback');
    expect(v.params['xray']).toBe(false);
    expect(v.params['section']).toEqual({ box: { enabled: true, min: [0, 0, 0] }, plane: { enabled: false, offset: 0 } });
    for (const k of ['camera', 'overrides', 'selectionSets', 'classStyles', 'schema', 'model']) expect(k in v.params, k).toBe(false);
    expect(v.created).toBe('2026-03-04T00:00:00.000Z');
  });

  it('round-trips through JSON onto a reloaded model with other element ids, applying only changed sections', () => {
    const a = viewsApp();
    const sec = fakeSection('section', { box: { enabled: false }, plane: { enabled: false, offset: 0 } });
    offs.push(sec.off);
    a.app.selectIds!([0, 2]);
    a.app.settings.overrides.userHides.add(1);
    a.app.settings.overrides.userHides.add(2);
    a.app.settings.overrides.userHides.add(3); // 3 of 4 hidden: stored as an isolate of G0
    a.app.settings.sightlines.gamma = 2.5;
    sec.state.plane.enabled = true;
    sec.state.plane.offset = 1.5;
    const v = captureView(a.app, 'Iso', { paramsEnv: a.env });
    expect(v.hides).toEqual({ mode: 'show', ids: ['G0'] });
    const stored = parseViewsDocument(JSON.stringify({ schema: 'xray-views/1', model: 'building', views: [v] })).views[0]!;

    // A fresh app whose element ids are reversed (G0 is element 3 now), with the factory section state.
    sec.state.plane.enabled = false;
    sec.state.plane.offset = 0;
    const b = viewsApp(true);
    const factory = currentViewParams(b.app, b.env);
    const plan = planRestore(stored, b.app.controller.model, currentViewParams(b.app, b.env), factory);
    expect(Object.keys(plan.params).sort()).toEqual(['section', 'sightlines']);
    expect(plan.missing).toEqual([]);
    expect(plan.selection.sort()).toEqual([1, 3]); // G2 -> 1, G0 -> 3
    expect(plan.hides.sort()).toEqual([0, 1, 2]); // everything but G0 (element 3)
    const bad = applyPlan(b.app, plan, b.env);
    expect(bad).toEqual([]);
    expect(b.selects).toBe(1);
    expect(sec.state.plane).toEqual({ enabled: true, offset: 1.5 });
    expect(b.app.settings.sightlines.gamma).toBe(2.5);

    // Captured again on the reloaded model: the same view (ids, times and camera aside).
    const again = captureView(b.app, 'Iso', { paramsEnv: b.env });
    expect(again.selection.sort()).toEqual(stored.selection.sort());
    expect(again.hides).toEqual(stored.hides);
    expect(again.params).toEqual(stored.params);
    // Nothing differs any more: a second restore applies no section.
    expect(planRestore(stored, b.app.controller.model, currentViewParams(b.app, b.env), factory).params).toEqual({});
  });

  it('reports GlobalIds that the model lacks and keeps hidden elements out of the pins', () => {
    const { app, env } = viewsApp();
    const v = captureView(app, 'x', { paramsEnv: env });
    v.selection = ['G0', 'GONE'];
    v.pins = ['G1', 'G2', 'ALSO-GONE'];
    v.hides = { mode: 'hide', ids: ['G1', 'GONE'] };
    const plan = planRestore(v, app.controller.model, currentViewParams(app, env), null);
    expect(plan.missing).toEqual(['GONE', 'ALSO-GONE']);
    expect(plan.pins).toEqual([2]);
    expect(plan.selection).toEqual([0]);
  });

  it('a partial (shared) view resets what it does not name to the factory state', () => {
    const a = viewsApp();
    const factory = currentViewParams(a.app, a.env);
    a.app.settings.sightlines.gamma = 3;
    const v = captureView(a.app, 'S', { paramsEnv: a.env });
    const shared = shareView(v, factory);
    expect(shared.params).toEqual({ sightlines: { gamma: 3 } });
    // The receiver has changed something else meanwhile; the restore brings it back to the factory value.
    const b = viewsApp();
    b.app.settings.sightlines.alphaMin = 0.42;
    const plan = planRestore(shared, b.app.controller.model, currentViewParams(b.app, b.env), factory);
    applyPlan(b.app, plan, b.env);
    expect(b.app.settings.sightlines.gamma).toBe(3);
    expect(b.app.settings.sightlines.alphaMin).toBe((factory['sightlines'] as { alphaMin: number }).alphaMin);
    expect(mergeParams(factory, shared.params)).toEqual(v.params);
  });
});
