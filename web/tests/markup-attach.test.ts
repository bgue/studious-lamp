// Attachments of markup shapes (src/bcf/attach.ts, surface.ts): inference on a synthetic scene of boxes, following an element
// in its local frame, the view-lock fade and pin, migration of old documents, and the BCF mapping (Lines, Components, side file).

import { describe, expect, it } from 'vitest';
import { newMarkup, parseMarkupDoc, buildMarkupDoc, needsAttach, attachmentOf, addMarkup, MARKUP_SCHEMA } from '../src/markup/model';
import type { MarkupSet } from '../src/markup/model';
import { VIEWLOCK, OcclusionCache, mostlyHidden, pickSamples, attachGuids, attachmentSegments, cleanAttachment, describeAttachment, regionEdges, viewLockState } from '../src/bcf/attach';
import type { Attachment } from '../src/bcf/attach';
import { SURFACE, densifyPath, inferAttachment, interiorSamples } from '../src/bcf/surface';
import type { InferInput, Probe, ProbeHit, Ray3 } from '../src/bcf/surface';
import { surfaceWorld, missingGuids, layoutMarkupFull } from '../src/markup/layout';
import { emptyProject, newGuid } from '../src/bcf/model';
import type { BcfAnnotation, BcfProject, BcfTopic, Vec3 } from '../src/bcf/model';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf, annotationLines } from '../src/bcf/write';
import { readZip } from '../src/bcf/zip';
import { parseSidecar, sidecarJson } from '../src/bcf/sidecar';
import { layoutAnnotation, projectPoint, viewProjection } from '../src/bcf/annotate';
import type { LayoutContext } from '../src/bcf/annotate';
import { G1, G2 } from './bcf-helpers';

// ---------------------------------------------------------------- a scene of boxes, a pinhole camera

interface Box { id: number; lo: Vec3; hi: Vec3 }
const W = 800;
const H = 500;
const EYE: Vec3 = [0, 0, 20];
const TAN = Math.tan((50 * Math.PI) / 360);

function rayAt(x: number, y: number): Ray3 {
  const nx = (x / W) * 2 - 1;
  const ny = -((y / H) * 2 - 1);
  const d: Vec3 = [nx * TAN * (W / H), ny * TAN, -1];
  const l = Math.hypot(...d);
  return { o: EYE, d: [d[0] / l, d[1] / l, d[2] / l] };
}

function boxProbe(boxes: Box[], skip: (id: number) => boolean = () => false): Probe {
  return (r): ProbeHit | null => {
    let best: ProbeHit | null = null;
    for (const b of boxes) {
      if (skip(b.id)) continue;
      let t0 = 0, t1 = Infinity, axis = -1, sign = 1;
      for (let a = 0; a < 3; a++) {
        const inv = 1 / (r.d[a]! || 1e-12);
        let ta = (b.lo[a]! - r.o[a]!) * inv, tb = (b.hi[a]! - r.o[a]!) * inv;
        let s = -1;
        if (ta > tb) { [ta, tb] = [tb, ta]; s = 1; }
        if (ta > t0) { t0 = ta; axis = a; sign = s; }
        t1 = Math.min(t1, tb);
        if (t0 > t1) { axis = -2; break; }
      }
      if (axis === -2 || axis < 0 || t0 > t1) continue;
      if (!best || t0 < best.distance) {
        const n: Vec3 = [0, 0, 0];
        n[axis] = sign;
        best = { point: [r.o[0] + r.d[0] * t0, r.o[1] + r.d[1] * t0, r.o[2] + r.d[2] * t0], normal: n, element: b.id, distance: t0 };
      }
    }
    return best;
  };
}

const GUIDS = ['WALL', ...Array.from({ length: 24 }, (_v, i) => `P${i + 1}`)];
function input(boxes: Box[], kind: string, path: number[], closed: boolean, extra: Partial<InferInput> = {}): InferInput {
  return {
    kind, path, closed, rayAt, probe: boxProbe(boxes), guidOf: (id) => GUIDS[id], shift: [0, 0, 0],
    centreOf: (id) => { const b = boxes.find((x) => x.id === id)!; return [(b.lo[0] + b.hi[0]) / 2, (b.lo[1] + b.hi[1]) / 2, (b.lo[2] + b.hi[2]) / 2]; },
    ...extra,
  };
}
const wall: Box = { id: 0, lo: [-30, -30, -1], hi: [30, 30, 0] };
const rect = (x0: number, y0: number, x1: number, y1: number): number[] => [x0, y0, x1, y0, x1, y1, x0, y1];

describe('surface projection and attachment inference', () => {
  it('densifies long segments and thins to the ray budget', () => {
    const p = densifyPath([0, 0, 140, 0], false, 14);
    expect(p.length / 2).toBe(11);
    expect(densifyPath(rect(0, 0, 4000, 3000), true).length / 2).toBeLessThanOrEqual(SURFACE.maxPath);
    expect(interiorSamples(rect(0, 0, 300, 200)).length / 2).toBeLessThanOrEqual(SURFACE.maxInterior);
  });

  it('a rectangle drawn on one wall is attached as surface to that wall, lifted off it', () => {
    const r = inferAttachment(input([wall], 'rect', rect(200, 150, 500, 350), true));
    expect(r.attach.kind).toBe('surface');
    expect(r.attach.surface!.guids).toEqual(['WALL']);
    expect(r.info.rays).toBeGreaterThan(20);
    for (const p of r.attach.surface!.pts) {
      // IFC y is minus the viewer z: lifted along the wall normal, towards the camera, by 5 mm to 5 cm
      expect(-p.p[1]).toBeGreaterThan(0.004);
      expect(-p.p[1]).toBeLessThan(0.06);
      expect(p.l).toBeDefined();
    }
    expect(describeAttachment(r.attach, { classOf: () => 'IfcWall' }).text).toBe('Attached to: 1 wall');
  });

  it('a cloud over many elements at different depths becomes a region box around them', () => {
    // Twenty slabs side by side, each a little deeper: the outline itself runs over many elements.
    const boxes: Box[] = [wall];
    for (let i = 0; i < 20; i++) boxes.push({ id: i + 1, lo: [-15 + i * 1.5, -12, 1 + i * 0.4], hi: [-13.5 + i * 1.5, 12, 2.2 + i * 0.4] });
    const r = inferAttachment(input(boxes, 'cloud', rect(40, 60, 760, 440), true));
    expect(r.attach.kind).toBe('region');
    const reg = r.attach.region!;
    // IFC y is minus the viewer z: the slabs span about 12 m of depth
    expect(reg.max[1]! - reg.min[1]!).toBeGreaterThan(5);
    expect(reg.min[0]).toBeLessThan(-10);
    expect(regionEdges(reg)).toHaveLength(12);
  });

  it('a line over many elements that projects cleanly is surface; a rectangle in empty sky is view-locked', () => {
    const boxes: Box[] = [wall];
    for (let i = 0; i < 6; i++) boxes.push({ id: (i % 5) + 1, lo: [-6 + i * 2, -3, 1 + i], hi: [-5 + i * 2, 3, 1.8 + i] });
    const line = inferAttachment(input(boxes, 'line', [60, 250, 740, 250], false));
    expect(line.attach.kind).toBe('surface');
    const sky = inferAttachment(input([], 'rect', rect(200, 150, 500, 350), true));
    expect(sky.attach).toEqual({ kind: 'none' });
    expect(sky.info.reason).toMatch(/no hit/);
  });

  it('a spike across a silhouette snaps onto the surface of its neighbours and stays on its own ray', () => {
    // A 0.1 m thin rod in front of the wall: one ray of the line hits it, the others hit the wall.
    const rod: Box = { id: 1, lo: [-0.05, -5, 8], hi: [0.05, 5, 8.1] };
    const path = [100, 250, 700, 250];
    const r = inferAttachment(input([wall, rod], 'line', path, false));
    expect(r.attach.kind).toBe('surface');
    expect(r.attach.surface!.guids).toEqual(['WALL']);
    for (const p of r.attach.surface!.pts) expect(Math.abs(p.p[1])).toBeLessThan(0.06);
  });

  it('too many failed points: no surface mode', () => {
    // Half of the stroke is over sky.
    const half: Box = { id: 0, lo: [-30, -30, -1], hi: [0, 30, 0] };
    const r = inferAttachment(input([half], 'line', [40, 250, 760, 250], false));
    expect(r.attach.kind).toBe('none');
    expect(r.info.bad).toBeGreaterThan(SURFACE.maxBad);
  });

  it('a measurement or penetration under the shape wins over the surface', () => {
    const link = { kind: 'point' as const, a: [0, 0, 0] as Vec3, b: [1, 0, 0] as Vec3, distance: 1, label: '1.000 m' };
    const m = inferAttachment(input([wall], 'rect', rect(200, 150, 500, 350), true, { hint: { measurement: link } }));
    expect(m.attach.kind).toBe('measurement');
    expect(m.attach.surface).toBeDefined();
    const p = inferAttachment(input([wall], 'rect', rect(200, 150, 500, 350), true, { hint: { penetration: { mep: G1, host: G2 } } }));
    expect(p.attach.kind).toBe('penetration');
    expect(attachGuids(p.attach)).toEqual(expect.arrayContaining([G1, G2]));
  });

  it('respects hidden and click-through elements the way the probe does', () => {
    const front: Box = { id: 1, lo: [-30, -30, 5], hi: [30, 30, 6] };
    const hidden = inferAttachment({ ...input([wall, front], 'rect', rect(200, 150, 500, 350), true), probe: boxProbe([wall, front], (id) => id === 1) });
    expect(hidden.attach.surface!.guids).toEqual(['WALL']);
    const seen = inferAttachment(input([wall, front], 'rect', rect(200, 150, 500, 350), true));
    expect(seen.attach.surface!.guids).toEqual(['P1']);
  });
});

describe('local frame: an attached shape follows its element', () => {
  const att: Attachment = {
    kind: 'surface',
    surface: { guids: ['WALL'], closed: false, pts: [{ e: 0, p: [1, 0, 0.02], l: [1, 0, 0.02] }, { e: 0, p: [2, 0, 0.02], l: [2, 0, 0.02] }] },
  };
  it('moves with the element frame and falls back to the IFC point without one', () => {
    const still = surfaceWorld(att.surface!, { shift: [0, 0, 0], element: () => ({ centre: [0, 0, 0], offset: [0, 0, 0] }) });
    // viewer frame: IFC (x, y, z) -> (x, z, -y)
    expect(still[0]!.map((v) => Math.abs(v) < 1e-12 ? 0 : v)).toEqual([1, 0.02, 0]);
    const moved = surfaceWorld(att.surface!, { shift: [0, 0, 0], element: () => ({ centre: [5, 0, 0], offset: [0, 0, 0] }) });
    expect(moved[0]![0]).toBeCloseTo(6);
    expect(moved[1]![0]).toBeCloseTo(7);
    const exploded = surfaceWorld(att.surface!, { shift: [0, 0, 0], element: () => ({ centre: [0, 0, 0], offset: [0, 3, 0] }) });
    expect(exploded[0]![1]).toBeCloseTo(3.02);
    const gone = surfaceWorld(att.surface!, { shift: [0, 0, 0] });
    expect(gone[1]![0]).toBe(2);
  });
  it('knows which GlobalIds a model lacks (the markup is then detached)', () => {
    expect(missingGuids(att, { element: (g) => (g === 'WALL' ? { centre: [0, 0, 0], offset: [0, 0, 0] } : null) })).toEqual([]);
    expect(missingGuids(att, { element: () => null })).toEqual(['WALL']);
    expect(describeAttachment(att, { missing: ['WALL'] })).toMatchObject({ attached: false, detached: true });
  });
});

describe('view-locked display: fade and pin by camera angle', () => {
  const authored = { position: [0, 0, 20] as Vec3, direction: [0, 0, -1] as Vec3 };
  const at = (deg: number, dist = 0): { position: Vec3; direction: Vec3 } => ({
    position: [dist, 0, 20],
    direction: [Math.sin((deg * Math.PI) / 180), 0, -Math.cos((deg * Math.PI) / 180)],
  });
  it('is full near the authored view, fades smoothly, and is a pin past 25 degrees', () => {
    expect(viewLockState(at(0), authored, 100)).toMatchObject({ mode: 'full', alpha: 1, pinAlpha: 0 });
    expect(viewLockState(at(VIEWLOCK.fullAngle - 0.5), authored, 100).mode).toBe('full');
    const a15 = viewLockState(at(15), authored, 100);
    expect(a15.mode).toBe('fade');
    expect(a15.alpha).toBeGreaterThan(0.2);
    expect(a15.alpha).toBeLessThan(0.95);
    let prev = 1;
    for (let d = 10; d <= 25; d += 1) {
      const s = viewLockState(at(d), authored, 100);
      expect(s.alpha).toBeLessThanOrEqual(prev + 1e-9);
      prev = s.alpha;
    }
    expect(viewLockState(at(25), authored, 100)).toMatchObject({ mode: 'pin', alpha: 0, pinAlpha: 1 });
    expect(viewLockState(at(60), authored, 100).mode).toBe('pin');
  });
  it('also leaves the authored view when the eye moves a fraction of the scene away', () => {
    expect(viewLockState(at(0, 12), authored, 100).mode).toBe('full');
    expect(viewLockState(at(0, 30), authored, 100).mode).toBe('fade');
    expect(viewLockState(at(0, 60), authored, 100).mode).toBe('pin');
  });
  it('an orbit of 10 degrees about the model is still full and 25 degrees is a pin, whatever the distance', () => {
    const D = 80; // eye distance = scene scale
    const orbitTo = (deg: number): { position: Vec3; direction: Vec3 } => {
      const a = (deg * Math.PI) / 180;
      return { position: [-D * Math.sin(a), 0, D * Math.cos(a)], direction: [Math.sin(a), 0, -Math.cos(a)] };
    };
    const from = { position: [0, 0, D] as Vec3, direction: [0, 0, -1] as Vec3 };
    expect(viewLockState(orbitTo(9), from, D).mode).toBe('full');
    expect(viewLockState(orbitTo(15), from, D).mode).toBe('fade');
    expect(viewLockState(orbitTo(26), from, D).mode).toBe('pin');
  });
  it('has the settings pin only and hidden', () => {
    expect(viewLockState(at(0), authored, 100, 'pin only')).toMatchObject({ mode: 'pin', pinAlpha: 1, alpha: 0 });
    expect(viewLockState(at(0), authored, 100, 'hidden')).toMatchObject({ mode: 'hidden', alpha: 0, pinAlpha: 0 });
  });
});

describe('migration and the markup document', () => {
  const doc = (shape: object): string => JSON.stringify({
    schema: MARKUP_SCHEMA, generator: 'x', exportedAt: '2026-01-01T00:00:00Z', instructions: '', model: { name: 'm', elementCount: 1, guidCount: 1, guidHash: 'h' },
    sets: [{
      id: 's1', title: 'A', author: 'a', created: '2026-01-01T00:00:00Z', updated: '2026-01-01T00:00:00Z',
      view: { id: 'v', name: 'A', camera: { position: [0, 0, 1], target: [0, 0, 0] }, selection: [], created: '2026-01-01T00:00:00Z' },
      camera: { position: [0, 0, 10], direction: [0, 0, -1], up: [0, 1, 0], fov: 50, aspect: 1.6 }, nextNumber: 2,
      markups: [{ id: 'm1', number: 1, kind: 'cloud', colour: 'red', weight: 2, fill: false, text: '', status: 'open', author: 'a', created: '2026-01-01T00:00:00Z', comments: [], ...shape }],
    }],
  });
  const old = { shape: { points: [[0.2, 0.2], [0.5, 0.4]], depth: 12.3 } };

  it('reads an old document unchanged, flags its shapes for attaching, and keeps the fractions exactly', () => {
    const p = parseMarkupDoc(doc(old));
    expect(p.error).toBeUndefined();
    const m = p.sets[0]!.markups[0]!;
    expect(needsAttach(m)).toBe(true);
    expect(attachmentOf(m)).toEqual({ kind: 'none' });
    expect(m.shape).toEqual({ points: [[0.2, 0.2], [0.5, 0.4]], depth: 12.3 });
  });
  it('writes the attachment, reads it back equal, and treats a bad one as view-locked', () => {
    const att: Attachment = { kind: 'region', region: { min: [0, 0, 0], max: [1, 2, 3] } };
    const p = parseMarkupDoc(doc({ ...old, attach: att }));
    expect(p.sets[0]!.markups[0]!.attach).toEqual(att);
    expect(needsAttach(p.sets[0]!.markups[0]!)).toBe(false);
    const json = JSON.stringify(buildMarkupDoc(p.model!, p.sets));
    expect(parseMarkupDoc(json).sets[0]!.markups[0]!.attach).toEqual(att);
    const bad = parseMarkupDoc(doc({ ...old, attach: { kind: 'region' } }));
    expect(bad.sets[0]!.markups[0]!.attach).toEqual({ kind: 'none' });
    expect(cleanAttachment({ kind: 'bogus' })).toBeUndefined();
  });
  it('maps anchors one to one', () => {
    const c = newMarkup('callout', { author: 'a', anchor: { kind: 'element', point: [1, 2, 3], elementGuid: G1 } });
    expect(attachmentOf(c)).toEqual({ kind: 'elements', guids: [G1] });
    const t = newMarkup('text', { author: 'a', anchor: { kind: 'point', point: [1, 2, 3] } });
    expect(attachmentOf(t)).toEqual({ kind: 'point' });
    const set = { markups: [], nextNumber: 1, updated: '' } as unknown as MarkupSet;
    addMarkup(set, c);
    expect(set.markups).toHaveLength(1);
  });
});

describe('BCF mapping: Lines, Components, side file', () => {
  const surf: Attachment = {
    kind: 'surface',
    surface: { guids: [G1], closed: true, pts: [{ e: 0, p: [1, 1, 0.5], l: [0.1, 0, 0] }, { e: 0, p: [2, 1, 0.5], l: [1.1, 0, 0] }, { e: 0, p: [2, 2, 0.5], l: [1.1, 1, 0] }] },
  };
  const reg: Attachment = { kind: 'region', region: { min: [0, 0, 0], max: [1, 1, 1] } };
  function project(): BcfProject {
    const p = emptyProject('2.1');
    const vg = newGuid();
    const anns: BcfAnnotation[] = [
      { guid: newGuid(), type: 'freehand', text: 'a', offset: [0, 0], anchor: { kind: 'point', point: [1, 1, 0.5] }, shape: { points: [[0.1, 0.1], [0.2, 0.2]], depth: 5 }, attach: surf },
      { guid: newGuid(), type: 'rect', text: 'b', offset: [0, 0], anchor: { kind: 'point', point: [0, 0, 0] }, shape: { points: [[0.3, 0.3], [0.5, 0.5]], depth: 5 }, attach: reg },
      { guid: newGuid(), type: 'rect', text: 'c', offset: [0, 0], anchor: { kind: 'point', point: [0, 0, 0] }, shape: { points: [[0.3, 0.3], [0.5, 0.5]], depth: 5 }, attach: { kind: 'none' } },
    ];
    const t: BcfTopic = {
      guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title: 'T', labels: [], referenceLinks: [], creationDate: '2026-11-04T09:00:00Z', creationAuthor: 'me',
      headerFiles: [], documentReferences: [], relatedTopics: [], comments: [],
      viewpoints: [{
        guid: vg,
        data: { guid: vg, camera: { kind: 'perspective', position: [20, -10, 8], direction: [-0.8, 0.5, -0.3], up: [0, 0, 1], fov: 50, aspect: 1.6 }, selection: [{ ifcGuid: G2 }], visibility: null, coloring: [], clipping: [], lines: [{ start: [9, 9, 9], end: [8, 8, 8] }] },
        annotations: anns,
      }],
    };
    p.topics.push(t);
    return p;
  }
  const bcfv = async (bytes: Uint8Array): Promise<string> => {
    const e = readZip(bytes).find((x) => x.name.endsWith('.bcfv'))!;
    return new TextDecoder().decode(await e.read());
  };

  it('writes surface and region shapes as 3D lines and the targets into the selection, merged with what is there', async () => {
    const src = project();
    const xml = await bcfv(await writeBcf(src, '2.1'));
    expect(xml).toContain('<Lines>');
    // foreign line + 3 closed path segments + 12 box edges
    expect((xml.match(/<Line>/g) ?? []).length).toBe(1 + 3 + 12);
    expect(xml).toContain(`IfcGuid="${G1}"`);
    expect(xml).toContain(`IfcGuid="${G2}"`);
    expect(annotationLines(src.topics[0]!.viewpoints[0]!)).toHaveLength(15);
    expect(attachmentSegments(reg)).toHaveLength(12);
  });

  it('round trips through our own writer and reader without doubling lines, and the side file is lossless', async () => {
    const src = project();
    const once = await writeBcf(src, '2.1');
    const back = await parseBcf(once);
    const bt = back.topics[0]!;
    const vp = bt.viewpoints[0]!;
    expect(vp.annotations!.map((a) => a.attach)).toEqual(src.topics[0]!.viewpoints[0]!.annotations!.map((a) => a.attach));
    expect(vp.data!.lines).toHaveLength(16);
    expect(vp.data!.selection.map((c) => c.ifcGuid)).toEqual(expect.arrayContaining([G1, G2]));
    // exporting the re-read project again does not double the lines
    const twice = await bcfv(await writeBcf(back, '2.1'));
    expect((twice.match(/<Line>/g) ?? []).length).toBe(16);
    // the side file text itself
    const side = sidecarJson(src.topics[0]!, '2.1')!;
    const read = parseSidecar(side);
    expect([...read.viewpoints.values()][0]!.annotations!.map((a) => a.attach)).toEqual([surf, reg, { kind: 'none' }]);
  });

  it('shows a foreign viewpoint line as a 3D world-line annotation without fractions', () => {
    const a: BcfAnnotation = { guid: 'x', type: 'freehand', text: '', offset: [0, 0], anchor: { kind: 'point', point: [0, 0, 0] }, attach: { kind: 'lines', lines: [[[0, 0, 0], [1, 0, 0]], [[1, 0, 0], [1, 1, 0]]] } };
    expect(annotationLines({ guid: 'v', data: null, annotations: [a] })).toEqual([]); // already in the viewpoint
    const eye: Vec3 = [3, -6, 4];
    const m = viewProjection(eye, [-0.3, 0.8, -0.4], [0, 1, 0], 50, 1.6);
    const ctx: LayoutContext = { width: 800, height: 500, shift: [0, 0, 0], scale: 1, project: (p) => projectPoint(m, 800, 500, p) };
    const ops = layoutAnnotation(a, ctx);
    expect(ops.filter((o) => o.op === 'line').length).toBeGreaterThanOrEqual(2);
    const rd = cleanAttachment(JSON.parse(JSON.stringify(a.attach)));
    expect(rd).toEqual(a.attach);
  });
});

describe('occlusion of attached outlines', () => {
  const wallBox: Box = { id: 0, lo: [-30, -30, -1], hi: [30, 30, 0] };
  it('classifies samples as hidden or visible from the first hit, ghosts passing', () => {
    // Camera behind the wall (z = -10) looks at points on its front face (z = 0.02): the wall hides them.
    const samples: Vec3[] = Array.from({ length: 20 }, (_v, i) => [i - 10, 0, 0.02]);
    const occ = (eye: Vec3, skip: (id: number) => boolean = () => false) => (p: Vec3): boolean => {
      const d = Math.hypot(p[0] - eye[0], p[1] - eye[1], p[2] - eye[2]);
      const h = boxProbe([wallBox], skip)({ o: eye, d: [(p[0] - eye[0]) / d, (p[1] - eye[1]) / d, (p[2] - eye[2]) / d] });
      return !!h && h.distance < d - Math.max(0.03, d * 0.003);
    };
    expect(mostlyHidden(samples, occ([0, 0, -10]))).toBe(true);
    expect(mostlyHidden(samples, occ([0, 0, 10]))).toBe(false);
    expect(mostlyHidden(samples, occ([0, 0, -10], () => true))).toBe(false); // a ghost or hidden occluder does not count
    // 5 of 12 hidden is not "mostly"
    expect(mostlyHidden(samples.slice(0, 12), (p) => p[0] < -5.5)).toBe(false);
    expect(mostlyHidden([], () => true)).toBe(false);
    expect(pickSamples(samples, 8)).toHaveLength(8);
    expect(pickSamples(samples.slice(0, 3), 8)).toHaveLength(3);
  });

  it('throttles the live test: at most every 150 ms after the camera moves', () => {
    let t = 0, cam = 'a', calls = 0, redraws = 0;
    const cache = new OcclusionCache(() => { calls++; return true; }, () => cam, () => redraws++, 150, () => t);
    const s: Vec3[] = [[0, 0, 0]];
    expect(cache.behind('k', s)).toBe(true);
    expect(calls).toBe(1);
    cache.behind('k', s);
    expect(calls).toBe(1); // camera still
    cam = 'b'; t = 50;
    cache.behind('k', s);
    expect(calls).toBe(1); // moved, but too soon
    t = 200;
    cache.behind('k', s);
    expect(calls).toBe(2);
  });

  it('draws a mostly hidden attached outline dashed and faint, and a visible one normally', () => {
    const m = newMarkup('cloud', { author: 'a', shape: { points: [[0.2, 0.2], [0.5, 0.4]], depth: 10 }, attach: {
      kind: 'surface', surface: { guids: ['W'], closed: true, pts: [[0, 0], [2, 0], [2, 2], [0, 2]].map(([x, z]) => ({ e: 0, p: [x!, 0, z!] as Vec3 })) },
    } });
    const m2 = viewProjection([1, 1, 8], [0, 0, -1], [0, 1, 0], 50, 1.6);
    const base = { width: 800, height: 500, shift: [0, 0, 0] as Vec3, scale: 1, project: (p: Vec3) => projectPoint(m2, 800, 500, p) };
    const shown = layoutMarkupFull(m, { ...base, occluded: () => false });
    expect(shown.behind).toBeUndefined();
    const hid = layoutMarkupFull(m, { ...base, occluded: () => true });
    expect(hid.behind).toBe(true);
    const shape = hid.ops.find((o) => o.op === 'path' && o.role === 'shape') as { alpha?: number; dash?: number[] };
    expect(shape.alpha).toBeCloseTo(0.35);
    expect(shape.dash).toBeDefined();
    expect(layoutMarkupFull(m, { ...base, occluded: () => true, behind: () => false }).behind).toBeUndefined();
  });
});
