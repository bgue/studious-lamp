// Wave 7 fixes to the BCF markup and the shared overlay (bench/RESULTS-fixes-w7.md): reserved screen rects, element-local
// anchors that follow exploded elements, rectangle and freehand shapes, stable pin numbers, measurement units, the
// selection of annotated elements and the side file fields that carry them.

import { describe, expect, it } from 'vitest';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';
import { readZip } from '../src/bcf/zip';
import { emptyProject, newGuid, viewerToIfc } from '../src/bcf/model';
import type { BcfAnnotation, BcfSnapshotView, BcfTopic, BcfVersion, Vec3 } from '../src/bcf/model';
import { markupSelectionOf, parseSidecar, sidecarJson } from '../src/bcf/sidecar';
import { anchorPoint, annotationLines, layoutAnnotation, layoutPin, projectPoint, shapeFraction, shapePointWorld, viewProjection } from '../src/bcf/annotate';
import type { DrawOp, LayoutContext } from '../src/bcf/annotate';
import { freeSpot, insetRects, rectsOverlap, underReserved } from '../src/ui/reserved';
import type { Rect } from '../src/ui/reserved';
import { G1, G2 } from './bcf-helpers';

const W = 1000;
const H = 600;
function ctxFor(extra: Partial<LayoutContext> = {}): LayoutContext {
  const m = viewProjection([0, 0, 10], [0, 0, -1], [0, 1, 0], 60, W / H);
  return { width: W, height: H, shift: [0, 0, 0], project: (p) => projectPoint(m, W, H, p), scale: 1, ...extra };
}
const at = (v: Vec3): Vec3 => viewerToIfc(v, [0, 0, 0]);
const boxOf = (ops: DrawOp[]): Extract<DrawOp, { op: 'rect' }> => ops.find((o) => o.op === 'rect' && o.role === 'box') as Extract<DrawOp, { op: 'rect' }>;

describe('reserved rects (fix 2)', () => {
  const gizmo: Rect = { x: 860, y: 420, w: 130, h: 150 };
  const area: Rect = { x: 0, y: 0, w: W, h: H };

  it('leaves a free box where it is and moves a covered box to the nearest free side', () => {
    expect(freeSpot(100, 100, 40, 20, [gizmo], area)).toEqual({ x: 100, y: 100, moved: false });
    const s = freeSpot(900, 500, 60, 20, [gizmo], area)!;
    expect(s.moved).toBe(true);
    expect(rectsOverlap({ x: s.x - 30, y: s.y - 10, w: 60, h: 20 }, gizmo)).toBe(false);
    // nearest exit of a point 40 px inside the left side of the gizmo: to the left, not above
    expect(s.x).toBeLessThan(gizmo.x);
    expect(Math.abs(s.y - 500)).toBeLessThan(1e-9);
  });

  it('keeps clear of a status bar strip next to the gizmo and of the view edges, and honours maxShift', () => {
    const bar = insetRects(W, H, { top: 0, right: 0, bottom: 22, left: 0 });
    expect(bar).toEqual([{ x: 0, y: 578, w: 1000, h: 22 }]);
    const s = freeSpot(980, 590, 50, 20, [gizmo, ...bar], area)!;
    expect(s.x + 25).toBeLessThanOrEqual(W + 0.5);
    for (const r of [gizmo, ...bar]) expect(rectsOverlap({ x: s.x - 25, y: s.y - 10, w: 50, h: 20 }, r)).toBe(false);
    expect(freeSpot(925, 495, 20, 20, [gizmo], area, { maxShift: 10 })).toBeNull();
    expect(underReserved(900, 500, [gizmo])).toBe(true);
    expect(underReserved(10, 10, [gizmo])).toBe(false);
  });

  it('pushes a BCF pin under the gizmo beside it with a leader line, and a callout box out of it', () => {
    // Viewer point that projects into the gizmo box (bottom right)
    const ctx = ctxFor({ reserved: [gizmo] });
    const m = viewProjection([0, 0, 10], [0, 0, -1], [0, 1, 0], 60, W / H);
    const target = { x: 920, y: 500 };
    // unproject on the z = 0 plane: x_ndc = (920/1000)*2-1 ...; solve with the projector numerically
    const tanY = Math.tan(Math.PI / 6);
    const p: Vec3 = [((target.x / W) * 2 - 1) * tanY * (W / H) * 10, -((target.y / H) * 2 - 1) * tanY * 10, 0];
    const q = projectPoint(m, W, H, p);
    expect(q.x).toBeCloseTo(920, 3);
    const ops = layoutPin({ position: at(p) }, '4', ctx);
    expect(ops.every((o) => o.role === 'pin')).toBe(true);
    const head = ops.find((o) => o.op === 'circle' && o.r > 5) as Extract<DrawOp, { op: 'circle' }>;
    expect(rectsOverlap({ x: head.x - head.r, y: head.y - head.r, w: 2 * head.r, h: 2 * head.r }, gizmo)).toBe(false);
    const leader = ops.filter((o) => o.op === 'line') as Array<Extract<DrawOp, { op: 'line' }>>;
    expect(leader.length).toBe(2);
    expect(leader[0]!.x1).toBeCloseTo(920, 3);
    // without reserved rects the same pin is drawn in place, with no leader
    expect(layoutPin({ position: at(p) }, '4', ctxFor()).some((o) => o.op === 'line')).toBe(false);

    const a: BcfAnnotation = { guid: 'c', type: 'note', text: 'Under the cube', anchor: { kind: 'point', point: at(p) }, offset: [0, 0] };
    const box = boxOf(layoutAnnotation(a, ctx));
    expect(rectsOverlap(box, gizmo)).toBe(false);
    expect(layoutAnnotation(a, ctx).some((o) => o.op === 'line' && o.role === 'line')).toBe(true); // the note got a leader
  });
});

describe('element-local anchors follow the element (fix 4)', () => {
  const frame = (offset: Vec3) => (g: string) => (g === G1 ? { centre: [1, 2, 3] as Vec3, offset } : null);

  it('places the anchor at the bounds centre plus the local offset, plus the explode offset', () => {
    const anchor = { point: at([9, 9, 9]), elementGuid: G1, local: [0.5, 0, 0] as Vec3 }; // IFC x = viewer x
    expect(anchorPoint(anchor, { shift: [0, 0, 0], element: frame([0, 0, 0]) })).toEqual({ p: [1.5, 2, 3], displaced: false });
    const moved = anchorPoint(anchor, { shift: [0, 0, 0], element: frame([0, 4, 0]) });
    expect(moved.p).toEqual([1.5, 6, 3]);
    expect(moved.displaced).toBe(true);
    // no local offset (older file): the stored point moves with the explode offset
    expect(anchorPoint({ point: at([9, 9, 9]), elementGuid: G1 }, { shift: [0, 0, 0], element: frame([0, 4, 0]) }).p).toEqual([9, 13, 9]);
    // unknown element or no element frame: the stored point
    expect(anchorPoint({ point: at([9, 9, 9]), elementGuid: G2, local: [1, 1, 1] }, { shift: [0, 0, 0], element: frame([0, 4, 0]) }).p).toEqual([9, 9, 9]);
  });

  it('draws an exploded callout at the moved element, without the occlusion fade', () => {
    const a: BcfAnnotation = { guid: 'x', type: 'callout', text: 'Duct', anchor: { kind: 'element', point: at([0, 0, 0]), elementGuid: G1, local: [0, 0, 0] }, offset: [0.1, -0.1] };
    const ctx = ctxFor({ occluded: () => true, element: (g) => (g === G1 ? { centre: [0, 0, 0], offset: [2, 0, 0] } : null) });
    const ops = layoutAnnotation(a, ctx);
    const dot = ops.find((o) => o.op === 'circle' && o.role === 'anchor') as Extract<DrawOp, { op: 'circle' }>;
    const plain = layoutAnnotation(a, ctxFor()).find((o) => o.op === 'circle' && o.role === 'anchor') as Extract<DrawOp, { op: 'circle' }>;
    expect(dot.x).toBeGreaterThan(plain.x + 50);
    expect(dot.dash).toBeUndefined(); // displaced: not tested against the undisplaced BVH
  });
});

describe('measurement units (fix 7)', () => {
  const m = (text: string): BcfAnnotation => ({
    guid: 'm', type: 'callout', text, offset: [0, -0.1],
    anchor: { kind: 'measurement', point: at([0, 0, 0]), measurement: { kind: 'point', a: at([-1, 0, 0]), b: at([1, 0, 0]), distance: 1.2346, label: '1.235 m' } },
  });
  it('shows the length in the unit of the measure tool, also for links whose text is the stored label', () => {
    expect(annotationLines(m(''), 'mm')).toEqual(['1235 mm']);
    expect(annotationLines(m('1.235 m'), 'mm')).toEqual(['1235 mm']);
    expect(annotationLines(m(''), 'm')).toEqual(['1.235 m']);
    expect(annotationLines(m('Gap to slab'), 'mm')).toEqual(['Gap to slab', '1235 mm']);
    const texts = layoutAnnotation(m(''), ctxFor({ units: 'mm' })).filter((o) => o.op === 'text').map((o) => (o as { text: string }).text);
    expect(texts).toEqual(['1235 mm']);
  });
});

describe('rectangle and freehand shapes (fix 5)', () => {
  const view: BcfSnapshotView = { position: at([0, 0, 10]), direction: at([0, 0, -1]), up: at([0, 1, 0]), fov: 60, aspect: W / H };

  it('maps view fractions to 3D and back', () => {
    for (const [u, v] of [[0.5, 0.5], [0.1, 0.9], [0.75, 0.2]] as Array<[number, number]>) {
      const p = shapePointWorld(view, [0, 0, 0], u, v, 7);
      const f = shapeFraction(view, [0, 0, 0], p);
      expect(f.u).toBeCloseTo(u, 9);
      expect(f.v).toBeCloseTo(v, 9);
      expect(f.depth).toBeCloseTo(7, 9);
    }
  });

  it('draws a rectangle straight from fractions in a snapshot, and through the camera in the live view', () => {
    const a: BcfAnnotation = { guid: 'r', type: 'rect', text: 'Here', anchor: { kind: 'point', point: at([0, 0, 0]) }, offset: [0, 0], shape: { points: [[0.25, 0.25], [0.5, 0.75]], depth: 10 } };
    const direct = layoutAnnotation(a, ctxFor({ shapeDirect: true }));
    const path = direct.find((o) => o.op === 'path' && o.fill) as Extract<DrawOp, { op: 'path' }>;
    expect(path.points).toEqual([250, 150, 500, 150, 500, 450, 250, 450]);
    expect(path.closed).toBe(true);
    const live = layoutAnnotation(a, ctxFor({ shapeView: view }));
    const lp = live.find((o) => o.op === 'path' && o.fill) as Extract<DrawOp, { op: 'path' }>;
    lp.points.forEach((v, i) => expect(v).toBeCloseTo(path.points[i]!, 6)); // the live camera is the viewpoint camera
    expect(boxOf(direct).y + boxOf(direct).h).toBeLessThanOrEqual(150); // label above the top-left corner
    // no camera to draw it with: nothing
    expect(layoutAnnotation(a, ctxFor())).toEqual([]);
    const fh: BcfAnnotation = { ...a, guid: 'f', type: 'freehand', text: '', shape: { points: [[0.1, 0.1], [0.2, 0.15], [0.3, 0.1]], depth: 5 } };
    const fo = layoutAnnotation(fh, ctxFor({ shapeDirect: true }));
    expect(fo.filter((o) => o.op === 'path').every((o) => !(o as { closed?: boolean }).closed)).toBe(true);
    expect(fo.some((o) => o.op === 'rect')).toBe(false);
  });
});

function topic(): BcfTopic {
  const vp = newGuid();
  return {
    guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title: 'T', labels: [], referenceLinks: [], creationDate: '2026-11-05T09:00:00Z', creationAuthor: 'me',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [], pinNumber: 7,
    pin: { position: [1, 2, 3], elementGuid: G1, local: [0.25, -0.5, 0] },
    viewpoints: [{
      guid: vp,
      data: { guid: vp, camera: { kind: 'perspective', position: [20, -10, 8], direction: [-0.8, 0.5, -0.3], up: [0, 0, 1], fov: 50, aspect: 1.5 }, selection: [{ ifcGuid: G2 }], visibility: null, coloring: [], clipping: [], lines: [] },
      annotations: [
        { guid: newGuid(), type: 'callout', text: 'c', anchor: { kind: 'element', point: [1, 1, 1], elementGuid: G1, local: [0, 0.1, 0] }, offset: [0.1, -0.1] },
        { guid: newGuid(), type: 'rect', text: 'area', anchor: { kind: 'point', point: [2, 2, 2] }, offset: [0, 0], shape: { points: [[0.1, 0.2], [0.4, 0.6]], depth: 12.5 } },
        { guid: newGuid(), type: 'freehand', text: '', anchor: { kind: 'point', point: [2, 2, 2] }, offset: [0, 0], shape: { points: [[0.1, 0.2], [0.15, 0.25], [0.2, 0.2]], depth: 9 } },
      ],
    }],
  };
}

describe('side file fields (fixes 3, 4, 5, 6)', () => {
  it.each(['2.1', '3.0'] as BcfVersion[])('round trips pin number, local offsets, shapes and the markup selection (%s)', async (version) => {
    const p = emptyProject(version);
    const t = topic();
    p.topics.push(t);
    const back = await parseBcf(await writeBcf(p, version));
    const b = back.topics[0]!;
    expect(b.pinNumber).toBe(7);
    expect(b.pin).toEqual(t.pin);
    expect(b.viewpoints[0]!.annotations).toEqual(t.viewpoints[0]!.annotations);
    // G1 joined the written selection for other tools, and is recorded as markup only
    const sel = b.viewpoints[0]!.data!.selection.map((c) => c.ifcGuid);
    expect(sel.sort()).toEqual([G1, G2].sort());
    expect(b.viewpoints[0]!.markupSelection).toEqual([G1]);
    expect(markupSelectionOf(b.viewpoints[0]!)).toEqual([G1]);
  });

  it('keeps an element the author selected out of the markup selection', () => {
    const t = topic();
    t.viewpoints[0]!.data!.selection.push({ ifcGuid: G1 });
    t.viewpoints[0]!.markupSelection = [];
    expect(markupSelectionOf(t.viewpoints[0]!)).toEqual([]);
    const side = parseSidecar(sidecarJson(t, '2.1')!);
    expect(side.viewpoints.get(t.viewpoints[0]!.guid.toLowerCase())!.markupSelection).toEqual([]);
  });

  it('derives the markup selection for an older side file without the field', () => {
    const t = topic();
    const r = t.viewpoints[0]!;
    r.data!.selection.push({ ifcGuid: G1 }); // what the older writer put in the selection
    delete r.markupSelection;
    expect(markupSelectionOf(r)).toEqual([G1]);
    // the annotated element was all the selection had: it stays selected (nothing else would be)
    r.data!.selection = [{ ifcGuid: G1 }];
    expect(markupSelectionOf(r)).toEqual([]);
  });

  it('drops invalid shapes and pin numbers with a problem each', () => {
    const json = JSON.stringify({
      format: 'xray-bcf-markup', version: 1, frame: 'ifc', units: 'm', topic: 'x', pinNumber: -2,
      viewpoints: { v: { annotations: [
        { type: 'rect', text: '', anchor: { kind: 'point', point: [0, 0, 0] }, shape: { points: [[0, 0]], depth: 3 } },
        { type: 'freehand', text: '', anchor: { kind: 'point', point: [0, 0, 0] } },
        { type: 'rect', text: '', anchor: { kind: 'point', point: [0, 0, 0] }, shape: { points: [[0, 0], [1, 1]], depth: 3 } },
      ] } },
    });
    const s = parseSidecar(json);
    expect(s.pinNumber).toBeUndefined();
    expect(s.viewpoints.get('v')!.annotations).toHaveLength(1);
    expect(s.problems.length).toBe(3);
  });

  it('writes the snapshot of a viewpoint with only shapes burned (shapes count as markup)', async () => {
    const p = emptyProject('3.0');
    const t = topic();
    t.viewpoints[0]!.annotations = t.viewpoints[0]!.annotations!.filter((a) => a.type !== 'callout');
    t.viewpoints[0]!.snapshot = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1]);
    p.topics.push(t);
    let called = 0;
    const bytes = await writeBcf(p, '3.0', { composeSnapshot: async () => (called++, new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 2])) });
    expect(called).toBe(1);
    expect(readZip(bytes).some((e) => e.name.endsWith('-base.png'))).toBe(true);
  });
});
