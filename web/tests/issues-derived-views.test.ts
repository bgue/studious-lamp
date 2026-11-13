// Derived views of a tied sketch: Plan and Section (src/issues/derivedViews.ts), their BCF viewpoints and the side file marker.

import { describe, expect, it } from 'vitest';
import { parseBcf } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';
import { dirIfcToViewer, emptyProject, ifcToViewer, newGuid } from '../src/bcf/model';
import type { BcfProject, BcfTopic, BcfViewpointRef, Vec3 } from '../src/bcf/model';
import type { Box6 } from '../src/bcf/plan';
import type { Attachment } from '../src/bcf/attach';
import {
  PLAN_ABOVE_CLEARANCE, PLAN_CUT_ABOVE_FLOOR, PLAN_JUST_ABOVE, attachmentTarget, derivePlan, deriveSection, derivedViewpoint, hintOf, horizontalNormal, isTied,
  planCutHeight, sketchIsTied, sketchTarget, storeyLevel, withDerivedViewpoints,
} from '../src/issues/derivedViews';
import type { DerivedInput, DerivedSource, TargetCtx } from '../src/issues/derivedViews';
import { sketchFromViewpoint } from '../src/issues/link';

const SHIFT: Vec3 = [6, 5, 3];
const IFC_A = 'AAAAAAAAAAAAAAAAAAAAAA';
const IFC_B = 'BBBBBBBBBBBBBBBBBBBBBB';
const close = (a: readonly number[], b: readonly number[], d = 1e-9): void => a.forEach((v, i) => expect(Math.abs(v - b[i]!), `${a} vs ${b}`).toBeLessThan(d));

/** A box centred on x, z with sizes, from y0 to y1 (viewer frame). */
const box = (cx: number, cz: number, sx: number, sz: number, y0: number, y1: number): Box6 => [cx - sx / 2, y0, cz - sz / 2, cx + sx / 2, y1, cz + sz / 2];

describe('plan cut height', () => {
  it('is the storey level plus 1.2 m for a target the cut passes through or lies below', () => {
    // a wall 0..3 m tall: cut like an architectural plan
    expect(planCutHeight({ target: box(0, 0, 8, 0.2, 0, 3), storeyY: 0 })).toBeCloseTo(PLAN_CUT_ABOVE_FLOOR, 9);
    // a slab below the cut
    expect(planCutHeight({ target: box(0, 0, 5, 5, -0.2, 0), storeyY: 0 })).toBeCloseTo(1.2, 9);
    // the level is the storey's, not the target's
    expect(planCutHeight({ target: box(0, 0, 8, 0.2, 3, 6), storeyY: 3 })).toBeCloseTo(4.2, 9);
  });

  it('is just above the top of a short target that straddles the cut', () => {
    const t = box(0, 0, 1, 1, 0.4, 1.4);
    expect(planCutHeight({ target: t, storeyY: 0 })).toBeCloseTo(1.4 + PLAN_JUST_ABOVE, 9);
  });

  it('is 0.3 m above the top of a target that lies wholly above the cut (ceiling MEP)', () => {
    const duct = box(2, 1, 6, 0.4, 2.5, 2.9);
    expect(planCutHeight({ target: duct, storeyY: 0 })).toBeCloseTo(2.9 + PLAN_ABOVE_CLEARANCE, 9);
  });

  it('takes the storey from the floors when it is not given: the highest floor at or below the target centre', () => {
    const floors = [0, 3, 6];
    expect(storeyLevel({ target: box(0, 0, 1, 1, 3.2, 3.6), floors })).toBe(3);
    expect(planCutHeight({ target: box(0, 0, 1, 1, 3.2, 3.6), floors })).toBeCloseTo(4.2, 9);
    // below every floor: the lowest; no floors at all: the base of the target
    expect(storeyLevel({ target: box(0, 0, 1, 1, -1, -0.5), floors })).toBe(0);
    expect(storeyLevel({ target: box(0, 0, 1, 1, 2, 2.5) })).toBe(2);
    expect(storeyLevel({ target: box(0, 0, 1, 1, 3.2, 3.6), floors, storeyY: 0 })).toBe(0);
  });
});

describe('plan view', () => {
  const model: Box6 = [-20, -1, -20, 20, 9, 20];

  it('is orthographic, looks straight down with north up and clips horizontally at the cut', () => {
    const v = derivePlan({ target: box(3, -2, 4, 0.3, 0, 3), storeyY: 0, model, aspect: 1.5 });
    expect(v.mode).toBe('plan');
    close(v.direction, [0, -1, 0]);
    close(v.up, [0, 0, -1]); // IFC north (+Y) is viewer -Z
    expect(v.target[0]).toBeCloseTo(3, 9);
    expect(v.target[2]).toBeCloseTo(-2, 9);
    expect(v.cutHeight).toBeCloseTo(1.2, 9);
    expect(v.clip).toHaveLength(1);
    close(v.clip[0]!.normal, [0, -1, 0]); // keeps what is below
    expect(v.clip[0]!.point[1]).toBeCloseTo(1.2, 9);
    // the camera stands above the cut and above the model
    expect(v.position[1]).toBeGreaterThan(model[4]);
    expect(v.position[1]).toBeGreaterThan(v.cutHeight!);
    expect(v.position[0]).toBeCloseTo(3, 9);
  });

  it('frames the target at 4 times its larger side, and at least 6 m across', () => {
    const big = derivePlan({ target: box(0, 0, 10, 2, 0, 1), storeyY: 0, aspect: 2 });
    expect(big.orthoHeight).toBeCloseTo(40, 9); // 4 x 10 across, landscape: the height is the span too
    const small = derivePlan({ target: box(0, 0, 0.5, 0.5, 0, 0.5), storeyY: 0, aspect: 2 });
    expect(small.orthoHeight).toBeCloseTo(6, 9);
    // portrait: the width is the narrow side, so the height grows to keep the span across
    const phone = derivePlan({ target: box(0, 0, 0.5, 0.5, 0, 0.5), storeyY: 0, aspect: 0.5 });
    expect(phone.orthoHeight).toBeCloseTo(12, 9);
  });

  it('puts the cut above a ceiling duct and looks at the cut level, not the duct', () => {
    const v = derivePlan({ target: box(0, 0, 6, 0.4, 2.5, 2.9), storeyY: 0, model, aspect: 1.6 });
    expect(v.cutHeight).toBeCloseTo(3.2, 9);
    expect(v.clip[0]!.point[1]).toBeCloseTo(3.2, 9);
    expect(v.target[1]).toBeLessThanOrEqual(3.2);
  });
});

describe('section view', () => {
  const model: Box6 = [-20, -1, -20, 20, 9, 20];

  it('cuts perpendicular to the longer horizontal side, looking along it', () => {
    const alongX = deriveSection({ target: box(0, 0, 8, 0.3, 0, 3), model, aspect: 1.6 });
    expect(alongX.basis).toBe('long-axis');
    close(alongX.direction.map(Math.abs), [1, 0, 0]);
    close(alongX.up, [0, 1, 0]);
    const alongZ = deriveSection({ target: box(0, 0, 0.3, 8, 0, 3), model, aspect: 1.6 });
    close(alongZ.direction.map(Math.abs), [0, 0, 1]);
  });

  it('keeps a limited depth box: a cut plane through the centroid and a back plane max(2 m, 2 x the depth) behind it', () => {
    const t = box(1, 2, 8, 0.3, 0, 3);
    const v = deriveSection({ target: t, model, aspect: 1.6 });
    const d = v.direction;
    expect(v.clip).toHaveLength(2);
    const [front, back] = v.clip;
    // front: through the centroid, keeps what is beyond it (along the view direction)
    close(front!.normal, d);
    close(front!.point, [1, 1.5, 2]);
    // back: 2 x the 8 m the target spans along the view direction, behind the cut; keeps what is in front of it
    expect(v.depth).toBeCloseTo(16, 9);
    close(back!.normal, d.map((x) => -x));
    close(back!.point, [1 + d[0] * 16, 1.5, 2 + d[2] * 16]);
    // a thin target gets at least 2 m
    const thin = deriveSection({ target: box(0, 0, 0.2, 0.2, 0, 0.2), model });
    expect(thin.depth).toBeCloseTo(2, 9);
  });

  it('looks from the side of the authored camera', () => {
    const t = box(0, 0, 8, 0.3, 0, 3);
    close(deriveSection({ target: t, hint: [1, 0, 0.2] }).direction, [1, 0, 0]);
    close(deriveSection({ target: t, hint: [-1, 0, 0.2] }).direction, [-1, 0, 0]);
    // the camera stands against the direction, so it sees the cut face
    const v = deriveSection({ target: t, hint: [-1, 0, 0], model });
    expect(v.position[0]).toBeGreaterThan(v.target[0]);
  });

  it('uses the long axis along the authored view for a square target', () => {
    const cube = box(0, 0, 1, 1, 0, 1);
    close(deriveSection({ target: cube, hint: [0.1, 0, -1] }).direction, [0, 0, -1]);
    close(deriveSection({ target: cube, hint: [1, 0, 0.1] }).direction, [1, 0, 0]);
  });

  it('is perpendicular to the horizontal part of a clearly horizontal surface normal, looking into the surface', () => {
    const wall = box(0, 0, 8, 0.3, 0, 3); // long in X, but the normal says Z
    const v = deriveSection({ target: wall, normal: [0.1, 0.05, 0.99], model });
    expect(v.basis).toBe('normal');
    const n = horizontalNormal([0.1, 0.05, 0.99])!;
    close(v.direction, [-n[0], 0, -n[2]]);
    expect(Math.abs(v.direction[2])).toBeGreaterThan(0.9);
  });

  it('falls back to the long axis for a floor, a ceiling or a missing normal', () => {
    expect(horizontalNormal([0, 1, 0])).toBeNull();
    expect(horizontalNormal([0.2, 0.9, 0.1])).toBeNull();
    expect(horizontalNormal(null)).toBeNull();
    expect(horizontalNormal([0, 0, 0])).toBeNull();
    expect(deriveSection({ target: box(0, 0, 8, 0.3, 0, 3), normal: [0, 1, 0] }).basis).toBe('long-axis');
  });

  it('frames the target with a margin and widens for a portrait screen', () => {
    const v = deriveSection({ target: box(0, 0, 0.3, 0.3, 0, 4), aspect: 2 });
    expect(v.orthoHeight).toBeCloseTo(12, 9); // 3 x the 4 m the target is tall
    const p = deriveSection({ target: box(0, 0, 0.3, 0.3, 0, 4), aspect: 0.5 });
    expect(p.orthoHeight).toBeCloseTo(24, 9);
    expect(deriveSection({ target: box(0, 0, 0.1, 0.1, 0, 0.1), aspect: 2 }).orthoHeight).toBeCloseTo(5, 9);
  });
});

describe('what a sketch is tied to', () => {
  const boxes: Record<string, Box6> = {
    [IFC_A]: box(0, 0, 10, 0.3, 0, 3),
    [IFC_B]: box(0, 0, 0.4, 0.4, 0, 3),
  };
  const ctx: TargetCtx = {
    shift: SHIFT,
    elementBox: (g) => boxes[g] ?? null,
    storeyY: (g) => (g === IFC_A ? 0 : null),
  };

  it('ties surface, elements, measurement, penetration, region and point; not view-locked or foreign lines', () => {
    for (const kind of ['surface', 'elements', 'measurement', 'penetration', 'region', 'point'] as const) expect(isTied({ kind }), kind).toBe(true);
    expect(isTied({ kind: 'none' })).toBe(false);
    expect(isTied({ kind: 'lines', lines: [[[0, 0, 0], [1, 1, 1]]] })).toBe(false);
    expect(isTied(undefined)).toBe(false);
    expect(sketchIsTied([{ id: 'a', attach: { kind: 'none' } }])).toBe(false);
    expect(sketchIsTied([{ id: 'a', attach: { kind: 'none' } }, { id: 'b', attach: { kind: 'point' }, anchorPoint: [0, 0, 0] }])).toBe(true);
  });

  it('boxes an elements attachment from the elements and takes their storey', () => {
    const t = attachmentTarget({ kind: 'elements', guids: [IFC_A] }, null, ctx)!;
    expect(t.box).toEqual(boxes[IFC_A]);
    expect(t.storeyY).toBe(0);
    expect(t.normal).toBeNull();
  });

  it('boxes a surface attachment from the stroke and averages its normals (IFC to viewer)', () => {
    const a: Attachment = {
      kind: 'surface',
      surface: {
        guids: [IFC_A], closed: true,
        pts: [
          { e: 0, p: [6 + 1, 5 + 0, 3 + 1], n: [0, -1, 0] }, // IFC -Y is viewer +Z
          { e: 0, p: [6 + 3, 5 + 0, 3 + 2], n: [0, -1, 0] },
        ],
      },
    };
    const t = attachmentTarget(a, null, ctx)!;
    close(t.box, [1 - 0.15, 1 - 0.15, 0 - 0.15, 3 + 0.15, 2 + 0.15, 0 + 0.15], 1e-9);
    close(t.normal!, [0, 0, 1]);
    expect(t.storeyY).toBe(0);
    // a resolver moves the stroke with the element
    const moved = attachmentTarget(a, null, { ...ctx, resolveSurface: (s) => ({ ...s, pts: s.pts.map((p) => ({ ...p, p: [p.p[0] + 10, p.p[1], p.p[2]] as Vec3 })) }) })!;
    expect(moved.box[0]).toBeCloseTo(11 - 0.15, 9);
  });

  it('boxes a measurement by its end points, a region by its corners, a point around the anchor', () => {
    const m = attachmentTarget({ kind: 'measurement', measurement: { kind: 'point', a: [6, 5, 3], b: [9, 5, 3], distance: 3, label: '3 m' } }, null, ctx)!;
    expect(m.box[0]).toBeCloseTo(0 - 0.15, 9);
    expect(m.box[3]).toBeCloseTo(3 + 0.15, 9);
    const r = attachmentTarget({ kind: 'region', region: { min: [6, 5, 3], max: [8, 9, 5] } }, null, ctx)!;
    // IFC (x, y, z) -> viewer (x, z, -y): y 5..9 becomes z 0..-4
    close(r.box, [0, 0, -4, 2, 2, 0], 1e-9);
    const p = attachmentTarget({ kind: 'point' }, ifcPoint(1, 2, 3), ctx)!;
    close(ifcToViewer(ifcPoint(1, 2, 3), SHIFT), [p.box[0] + 0.25, p.box[1] + 0.25, p.box[2] + 0.25], 1e-9);
    expect(attachmentTarget({ kind: 'point' }, null, ctx)).toBeNull();
    expect(attachmentTarget({ kind: 'none' }, null, ctx)).toBeNull();
  });

  it('boxes a penetration by where the pipe meets its host', () => {
    const t = attachmentTarget({ kind: 'penetration', penetration: { mep: IFC_B, host: IFC_A } }, null, ctx)!;
    expect(t.box).toEqual(box(0, 0, 0.4, 0.3, 0, 3)); // the overlap of the two boxes
  });

  it('a sketch takes the union of its tied drawings, or only the selected one', () => {
    const marks = [
      { id: 'a', attach: { kind: 'elements', guids: [IFC_A] } as Attachment },
      { id: 'b', attach: { kind: 'elements', guids: [IFC_B] } as Attachment },
      { id: 'c', attach: { kind: 'none' } as Attachment },
    ];
    const both: Box6 = [-5, 0, -0.2, 5, 3, 0.2];
    expect(sketchTarget(marks, ctx)!.box).toEqual(both);
    expect(sketchTarget(marks, ctx, 'b')!.box).toEqual(boxes[IFC_B]);
    expect(sketchTarget(marks, ctx, 'c')!.box).toEqual(both); // not tied: the selection is ignored
    expect(sketchTarget([{ id: 'c', attach: { kind: 'none' } }], ctx)).toBeNull();
    expect(hintOf([0.6, 0.8, 0.8])).toEqual([0.6, 0, 0.8]);
    expect(hintOf([0, 1, 0])).toBeNull();
  });
});

function ifcPoint(x: number, y: number, z: number): Vec3 {
  return [x, y, z];
}

// ---------------------------------------------------------------- BCF export

function sourceTopic(): { topic: BcfTopic; ref: BcfViewpointRef } {
  const g = newGuid();
  const ref: BcfViewpointRef = {
    guid: g,
    sketchId: 's-1',
    data: {
      guid: g,
      camera: { kind: 'perspective', position: [10, -10, 8], direction: [-0.5, 0.7, -0.4], up: [0, 0, 1], fov: 50, aspect: 1.6 },
      selection: [{ ifcGuid: IFC_A }],
      visibility: { defaultVisibility: true, exceptions: [{ ifcGuid: IFC_B }] },
      coloring: [{ color: 'FF0000', components: [{ ifcGuid: IFC_A }] }],
      clipping: [],
      lines: [],
    },
    snapshotView: { position: [10, -10, 8], direction: [-0.5, 0.7, -0.4], up: [0, 0, 1], fov: 50, aspect: 1.6 },
    annotations: [{
      guid: newGuid(), type: 'freehand', text: '1. Clash', offset: [0.1, -0.1], anchor: { kind: 'point', point: [10, 0, 1] },
      shape: { points: [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.2]], depth: 10 },
      attach: { kind: 'surface', guids: [IFC_A], surface: { guids: [IFC_A], closed: true, pts: [{ e: 0, p: [6, 5, 4] }, { e: 0, p: [8, 5, 4] }, { e: 0, p: [8, 5, 5] }, { e: 0, p: [6, 5, 4] }] } },
    }],
  };
  const topic: BcfTopic = {
    guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title: 'Wall clash', labels: [], referenceLinks: [], creationDate: '2026-01-02T10:00:00Z', creationAuthor: 'Ana',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [], viewpoints: [ref],
  };
  return { topic, ref };
}

const WALL = box(0, 0, 8, 0.3, 0, 3);
function provider(t: BcfTopic, r: BcfViewpointRef): DerivedSource | null {
  if (!r.sketchId) return null;
  const input: DerivedInput = { target: WALL, storeyY: 0, model: [-20, -1, -20, 20, 9, 20], aspect: 1.6, hint: [1, 0, 0] };
  void t;
  return { sketch: r.sketchId, views: { plan: derivePlan(input), section: deriveSection(input) }, shift: SHIFT, aspect: 1.6 };
}

function projectOf(t: BcfTopic, version: '2.1' | '3.0'): BcfProject {
  const p = emptyProject(version);
  p.topics.push(t);
  return p;
}

describe('derived viewpoints in the BCF export', () => {
  it('writes an orthogonal camera with ViewToWorldScale and planes whose Direction points into the cut-away half', () => {
    const { ref } = sourceTopic();
    const d = provider(sourceTopic().topic, ref)!;
    const vp = derivedViewpoint(d.views.plan!, ref, { shift: SHIFT, aspect: 1.6 });
    expect(vp.camera?.kind).toBe('orthogonal');
    expect(vp.camera?.viewToWorldScale).toBeCloseTo(d.views.plan!.orthoHeight, 9);
    expect(vp.camera?.aspect).toBe(1.6);
    // plan looks down: IFC direction (0, 0, -1); up is IFC +Y (north)
    close(vp.camera!.direction, [0, 0, -1], 1e-9);
    close(vp.camera!.up, [0, 1, 0], 1e-9);
    // one plane at the cut: location in IFC (z = 1.2 + shift z), Direction = up (the cut-away half is above)
    expect(vp.clipping).toHaveLength(1);
    expect(vp.clipping[0]!.location[2]).toBeCloseTo(1.2 + SHIFT[2], 9);
    close(vp.clipping[0]!.direction, [0, 0, 1], 1e-9);
    // the same components as the source viewpoint
    expect(vp.selection.map((c) => c.ifcGuid)).toEqual([IFC_A]);
    expect(vp.visibility?.exceptions.map((c) => c.ifcGuid)).toEqual([IFC_B]);
    expect(vp.coloring[0]!.color).toBe('FF0000');
    // the drawing's elements join the selection like in the source, and its attached outline shows as 3D lines
    expect(vp.lines.length).toBeGreaterThan(0);
    const sec = derivedViewpoint(d.views.section!, ref, { shift: SHIFT, aspect: 1.6 });
    expect(sec.clipping).toHaveLength(2);
    // the cut-away halves: in front of the cut (against the view direction) and beyond the back plane
    const viewDir = dirIfcToViewer(sec.camera!.direction);
    const front = dirIfcToViewer(sec.clipping[0]!.direction);
    const back = dirIfcToViewer(sec.clipping[1]!.direction);
    close(front, viewDir.map((x) => -x), 1e-9);
    close(back, viewDir, 1e-9);
  });

  it.each(['2.1', '3.0'] as const)('adds Plan and Section after the source viewpoint, marked in the side file (%s)', async (version) => {
    const { topic, ref } = sourceTopic();
    const out = withDerivedViewpoints(projectOf(topic, version), provider);
    expect(out.topics[0]!.viewpoints.map((r) => r.derived?.kind ?? 'source')).toEqual(['source', 'plan', 'section']);
    // the stored project is not changed
    expect(topic.viewpoints).toHaveLength(1);
    const back = await parseBcf(await writeBcf(out, version));
    const t = back.topics[0]!;
    expect(t.viewpoints).toHaveLength(3);
    const g = (s: string): string => (version === '3.0' ? s.toLowerCase() : s);
    const [src, plan, section] = t.viewpoints;
    expect(src!.derived).toBeUndefined();
    expect(plan!.derived).toEqual({ kind: 'plan', sketch: 's-1', of: g(ref.guid) });
    expect(section!.derived).toEqual({ kind: 'section', sketch: 's-1', of: g(ref.guid) });
    for (const r of [plan!, section!]) {
      expect(r.data?.camera?.kind).toBe('orthogonal');
      expect(r.data?.camera?.viewToWorldScale).toBeGreaterThan(0);
      expect(r.data!.clipping.length).toBeGreaterThan(0);
      expect(r.data!.selection.map((c) => c.ifcGuid)).toEqual([IFC_A]);
      expect(r.annotations).toBeUndefined();
    }
    expect(plan!.data!.clipping).toHaveLength(1);
    expect(section!.data!.clipping).toHaveLength(2);
    // BCF 3.0 carries the aspect ratio of an orthogonal camera, 2.1 has no place for it
    if (version === '3.0') expect(plan!.data!.camera!.aspect).toBeCloseTo(1.6, 6);
  });

  it('opens without a sketch of its own: derived viewpoints never become sketches', async () => {
    const { topic } = sourceTopic();
    const back = await parseBcf(await writeBcf(withDerivedViewpoints(projectOf(topic, '2.1'), provider), '2.1'));
    const t = back.topics[0]!;
    const cam = { position: [0, 0, 10] as Vec3, direction: [0, 0, -1] as Vec3, up: [0, 1, 0] as Vec3, fov: 45, aspect: 1.6 };
    for (const r of t.viewpoints.filter((x) => x.derived)) {
      expect(sketchFromViewpoint(t, r, { author: 'x', shift: SHIFT, camera: cam })).toBeNull();
      expect(sketchFromViewpoint(t, r, { author: 'x', shift: SHIFT, camera: cam, empty: true })).toBeNull();
      expect(r.sketchId).toBeUndefined();
    }
    // the source viewpoint still becomes its sketch
    const src = t.viewpoints.find((r) => !r.derived)!;
    expect(sketchFromViewpoint(t, src, { author: 'x', shift: SHIFT, camera: cam })).not.toBeNull();
  });

  it('exports again without doubling the derived viewpoints, and keeps their guids', async () => {
    const { topic } = sourceTopic();
    const first = await parseBcf(await writeBcf(withDerivedViewpoints(projectOf(topic, '3.0'), provider), '3.0'));
    const t = first.topics[0]!;
    // the file knows the sketch id; the viewer that opened it has its own ids: the provider needs the source's `sketchId`
    for (const r of t.viewpoints) if (!r.derived) r.sketchId = 's-2';
    const ids = t.viewpoints.map((r) => r.guid);
    const again = withDerivedViewpoints(first, provider);
    expect(again.topics[0]!.viewpoints).toHaveLength(3);
    expect(again.topics[0]!.viewpoints.map((r) => r.guid)).toEqual(ids);
    expect(again.topics[0]!.viewpoints[1]!.derived?.sketch).toBe('s-2');
    // a viewer with no sketch for the source keeps the derived viewpoints as they are
    for (const r of t.viewpoints) delete r.sketchId;
    const kept = withDerivedViewpoints(first, provider);
    expect(kept.topics[0]!.viewpoints.map((r) => r.guid)).toEqual(ids);
    expect(kept).toBe(first);
  });

  it('leaves a topic without a tied sketch alone', () => {
    const { topic, ref } = sourceTopic();
    delete ref.sketchId;
    const p = projectOf(topic, '2.1');
    expect(withDerivedViewpoints(p, provider)).toBe(p);
  });
});
