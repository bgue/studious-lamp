import { describe, expect, it } from 'vitest';
import { captureViewpoint, frameCamera, planViewpoint, visibilityHides } from '../src/bcf/plan';
import type { PlanContext } from '../src/bcf/plan';
import { dirViewerToIfc, ifcToViewer, viewerToIfc } from '../src/bcf/model';
import type { BcfViewpoint, Vec3 } from '../src/bcf/model';

const SHIFT: Vec3 = [10, 20, 3];
const guid = (i: number): string => `GUID${String(i).padStart(18, '0')}`; // 22 chars
const N = 10;
const classes = (i: number): string => (i === 8 ? 'IfcSpace' : i === 9 ? 'IfcOpeningElement' : 'IfcWall');
const byGuid = new Map<string, number>(Array.from({ length: N }, (_, i) => [guid(i), i] as [string, number]));

function ctx(over: Partial<PlanContext> = {}): PlanContext {
  return {
    shift: SHIFT, resolve: (g) => byGuid.get(g), count: N, classOf: classes, modelBounds: [-5, 0, -5, 5, 3, 5], fov: 45, aspect: 16 / 9, canClip: true, ...over,
  };
}
const vp = (over: Partial<BcfViewpoint> = {}): BcfViewpoint => ({ guid: 'g', camera: null, selection: [], visibility: null, coloring: [], clipping: [], lines: [], ...over });
const comps = (...ids: number[]): Array<{ ifcGuid: string }> => ids.map((i) => ({ ifcGuid: guid(i) }));

describe('visibility semantics', () => {
  const c = ctx();
  it('DefaultVisibility false hides everything except the exceptions', () => {
    const v = visibilityHides({ defaultVisibility: false, exceptions: comps(1, 2) }, c);
    expect(v.hide).toEqual([0, 3, 4, 5, 6, 7, 8, 9]);
  });
  it('DefaultVisibility true hides the exceptions', () => {
    const v = visibilityHides({ defaultVisibility: true, exceptions: comps(1, 2) }, c);
    expect(v.hide).toEqual([1, 2]);
  });
  it('unknown exception guids are counted, not applied', () => {
    const v = visibilityHides({ defaultVisibility: true, exceptions: [...comps(3), { ifcGuid: 'NOSUCHGUID0000000000AA' }, { authoringToolId: 'x' }] }, c);
    expect(v.hide).toEqual([3]);
    expect(v.unknown).toBe(2);
  });
  it('ViewSetupHints apply before exceptions: spaces and openings follow their flags', () => {
    const hidden = visibilityHides({ defaultVisibility: true, exceptions: [], hints: { spacesVisible: false, openingsVisible: false } }, c);
    expect(hidden.hide).toEqual([8, 9]);
    const shown = visibilityHides({ defaultVisibility: false, exceptions: comps(0), hints: { spacesVisible: true } }, c);
    expect(shown.hide).toEqual([1, 2, 3, 4, 5, 6, 7, 9]);
    // an exception overrides the hint (default true, space listed => hidden; default false, space listed => shown)
    expect(visibilityHides({ defaultVisibility: false, exceptions: comps(8), hints: { spacesVisible: false } }, c).hide).not.toContain(8);
  });
});

describe('planViewpoint', () => {
  it('does not hide everything when no visible exception exists in the model', () => {
    const plan = planViewpoint(vp({ visibility: { defaultVisibility: false, exceptions: [{ ifcGuid: 'NOSUCHGUID0000000000AA' }] } }), ctx());
    expect(plan.hide).toBeNull();
    expect(plan.skipped.join(' ')).toMatch(/visibility/);
  });

  it('reports unknown selection guids and keeps the known ones', () => {
    const plan = planViewpoint(vp({ selection: [...comps(2, 4), { ifcGuid: 'NOSUCHGUID0000000000AA' }, { ifcGuid: guid(2) }] }), ctx());
    expect(plan.selection).toEqual([2, 4]);
    expect(plan.selectionUnknown).toBe(1);
    expect(plan.skipped.join(' ')).toContain('1 selected GlobalIds not in this model');
  });

  it('converts a perspective camera to viewer coordinates and aims at the model along the view', () => {
    const pos: Vec3 = [10 + 2, 20 - 15, 3 + 1.5]; // IFC: 15 m south of the shift, looking north (+Y)
    const plan = planViewpoint(vp({ camera: { kind: 'perspective', position: pos, direction: [0, 1, 0], up: [0, 0, 1], fov: 50, aspect: 16 / 9 } }), ctx());
    const c = plan.camera!;
    expect(c.position).toEqual(ifcToViewer(pos, SHIFT));
    expect(c.position[0]).toBeCloseTo(2, 12);
    expect(c.position[1]).toBeCloseTo(1.5, 12);
    expect(c.position[2]).toBeCloseTo(15, 12); // IFC y -15 -> viewer z +15
    // looking along IFC +Y = viewer -Z: the target lies at smaller z
    expect(c.target[2]).toBeLessThan(c.position[2]);
    expect(c.target[0]).toBeCloseTo(c.position[0], 9);
    expect(c.up.map((x) => x + 0)).toEqual([0, 1, 0]);
    expect(c.fov).toBe(50);
    expect(c.approximatedOrthogonal).toBe(false);
  });

  it('widens the field of view when the viewer is narrower than the viewpoint (BCF 3.0 AdjustToRatio)', () => {
    const cam = { kind: 'perspective' as const, position: [0, -10, 0] as Vec3, direction: [0, 1, 0] as Vec3, up: [0, 0, 1] as Vec3, fov: 45, aspect: 2 };
    const same = planViewpoint(vp({ camera: cam }), ctx({ aspect: 2 })).camera!;
    const narrow = planViewpoint(vp({ camera: cam }), ctx({ aspect: 1 })).camera!;
    expect(same.fov).toBe(45);
    const expected = (2 * Math.atan(Math.tan((45 * Math.PI) / 360) * 2) * 180) / Math.PI;
    expect(narrow.fov).toBeCloseTo(expected, 9);
  });

  it('approximates an orthogonal camera by a perspective camera showing the same vertical extent', () => {
    const plan = planViewpoint(vp({ camera: { kind: 'orthogonal', position: [10, 20 - 30, 3], direction: [0, 1, 0], up: [0, 0, 1], viewToWorldScale: 12 } }), ctx({ fov: 45 }));
    const c = plan.camera!;
    expect(c.approximatedOrthogonal).toBe(true);
    const dist = Math.hypot(c.target[0] - c.position[0], c.target[1] - c.position[1], c.target[2] - c.position[2]);
    expect(2 * dist * Math.tan((45 * Math.PI) / 360)).toBeCloseTo(12, 9);
    expect(plan.applied.join(' ')).toContain('orthographic approximated');
  });

  it('ClippingPlane Direction points into the clipped half-space; the renderer normal is the opposite', () => {
    const plan = planViewpoint(vp({ clipping: [{ location: [10, 20, 3 + 2.7], direction: [0, 0, 1] }] }), ctx());
    // IFC +Z (clipped: everything above 2.7 m) -> viewer +Y clipped -> kept normal is -Y
    expect(plan.clip).toHaveLength(1);
    expect(plan.clip[0]!.normal[0]).toBeCloseTo(0, 12);
    expect(plan.clip[0]!.normal[1]).toBeCloseTo(-1, 12);
    expect(plan.clip[0]!.normal[2]).toBeCloseTo(0, 12);
    expect(plan.clip[0]!.point[1]).toBeCloseTo(2.7, 12);
    // a point below the plane is on the kept side: (p - point) . normal >= 0
    const below = (0 - plan.clip[0]!.point[1]) * plan.clip[0]!.normal[1];
    expect(below).toBeGreaterThan(0);
    expect(planViewpoint(vp({ clipping: [{ location: [0, 0, 0], direction: [0, 0, 1] }] }), ctx({ canClip: false })).skipped.join(' ')).toMatch(/setClipPlanes/);
  });

  it('colours resolve to element ids and report the unknown ones', () => {
    const plan = planViewpoint(vp({ coloring: [{ color: 'FF8000', components: [...comps(1, 2), { ifcGuid: 'NOSUCHGUID0000000000AA' }] }] }), ctx());
    expect(plan.colors).toHaveLength(1);
    expect(plan.colors[0]!.ids).toEqual([1, 2]);
    expect(plan.colors[0]!.rgb[0]).toBeCloseTo(1, 12);
    expect(plan.colors[0]!.rgb[1]).toBeCloseTo(128 / 255, 12);
    expect(plan.colorUnknown).toBe(1);
  });
});

describe('captureViewpoint', () => {
  const base = {
    shift: SHIFT, position: [1, 2, 3] as Vec3, target: [1, 2, -7] as Vec3, up: [0, 1, 0] as Vec3, fov: 45, aspect: 1.5,
    selection: [1, 2], count: N, globalId: guid, clip: [] as Array<{ normal: Vec3; point: Vec3 }>,
  };

  it('writes camera in IFC coordinates and puts the shorter list in Exceptions', () => {
    const few = captureViewpoint({ ...base, hidden: new Set([3, 4]) });
    expect(few.viewpoint.visibility).toEqual({ defaultVisibility: true, exceptions: comps(3, 4) });
    const many = captureViewpoint({ ...base, hidden: new Set([0, 1, 2, 3, 4, 5, 6]) });
    expect(many.viewpoint.visibility!.defaultVisibility).toBe(false);
    expect(many.viewpoint.visibility!.exceptions).toEqual(comps(7, 8, 9));
    const none = captureViewpoint({ ...base, hidden: new Set() });
    expect(none.viewpoint.visibility).toEqual({ defaultVisibility: true, exceptions: [] });
    const cam = few.viewpoint.camera!;
    expect(cam.position).toEqual(viewerToIfc(base.position, SHIFT));
    // viewer -Z is IFC +Y
    expect(cam.direction[0]).toBeCloseTo(0, 12);
    expect(cam.direction[1]).toBeCloseTo(1, 12);
    expect(cam.direction[2]).toBeCloseTo(0, 12);
    expect(cam.up).toEqual(dirViewerToIfc([0, 1, 0]));
    expect(few.viewpoint.selection).toEqual(comps(1, 2));
  });

  it('skips elements whose GlobalId is not a valid IfcGuid and counts them', () => {
    const r = captureViewpoint({ ...base, hidden: new Set(), selection: [1, 2], globalId: (i) => (i === 2 ? 'bad' : guid(i)) });
    expect(r.viewpoint.selection).toEqual(comps(1));
    expect(r.skippedIds).toBe(1);
  });

  it('captures clip planes with the BCF direction (clipped side)', () => {
    const r = captureViewpoint({ ...base, hidden: new Set(), clip: [{ normal: [0, -1, 0], point: [0, 2.7, 0] }] });
    expect(r.viewpoint.clipping).toHaveLength(1);
    expect(r.viewpoint.clipping[0]!.direction[2]).toBeCloseTo(1, 12); // keeps below, clips above: IFC +Z
    expect(r.viewpoint.clipping[0]!.location).toEqual(viewerToIfc([0, 2.7, 0], SHIFT));
  });

  it('capture then plan reproduces camera and clip planes in the viewer (round trip)', () => {
    const r = captureViewpoint({ ...base, hidden: new Set([4]), clip: [{ normal: [1, 0, 0], point: [2, 0, 0] }] });
    const plan = planViewpoint(r.viewpoint, ctx({ modelBounds: null }));
    const c = plan.camera!;
    for (let k = 0; k < 3; k++) expect(c.position[k]!).toBeCloseTo(base.position[k]!, 9);
    const dir = [c.target[0] - c.position[0], c.target[1] - c.position[1], c.target[2] - c.position[2]];
    const l = Math.hypot(...dir);
    expect(dir.map((x) => x / l)).toEqual([0, 0, -1].map((x) => expect.closeTo(x, 9)));
    expect(plan.clip[0]!.normal).toEqual([expect.closeTo(1, 9), expect.closeTo(0, 9), expect.closeTo(0, 9)]);
    expect(plan.hide).toEqual([4]);
    expect(plan.selection).toEqual([1, 2]);
  });
});

describe('frameCamera', () => {
  it('frames the box: all corners fit inside the view', () => {
    const box = [0, 0, 0, 4, 2, 6] as const;
    const f = frameCamera(box, 45, 16 / 9);
    const d = Math.hypot(f.position[0] - f.target[0], f.position[1] - f.target[1], f.position[2] - f.target[2]);
    const r = Math.hypot(4, 2, 6) / 2;
    expect(d).toBeGreaterThan(r);
    expect(f.target).toEqual([2, 1, 3]);
  });
});

describe('createTopics element aliases', () => {
  const els = [{ globalId: 'AAAAAAAAAAAAAAAAAAAAAA' }, { globalId: 'BBBBBBBBBBBBBBBBBBBBBB' }, { globalId: 'CCCCCCCCCCCCCCCCCCCCCC' }];
  it('globalIds wins, then elements (alias), then elementIds mapped through the model', async () => {
    const { topicGlobalIds, boxAround } = await import('../src/bcf/plan');
    expect(topicGlobalIds({ globalIds: ['X'], elements: ['Y'], elementIds: [0] }, els)).toEqual(['X']);
    expect(topicGlobalIds({ elements: ['Y'], elementIds: [0] }, els)).toEqual(['Y']);
    expect(topicGlobalIds({ elementIds: [2, 0, 9] }, els)).toEqual(['CCCCCCCCCCCCCCCCCCCCCC', 'AAAAAAAAAAAAAAAAAAAAAA']);
    expect(topicGlobalIds({}, els)).toEqual([]);
    expect(boxAround([1, 2, 3], [0, 0, 0, 1, 1, 1], 0.5)).toEqual([0, 0, 0, 1.5, 2.5, 3.5]);
  });
});
