// Simplified geometry write-back (design 2.5, experimental T5b): the body of an element is replaced by a triangle mesh. Pure, text level.
//   viewer frame (Y up, metres, origin shifted)  ->  IFC world (Z up, metres)  ->  file length unit  ->  the element's local frame.
// The element's ObjectPlacement, its other representations, its psets, type, material, containment, voids and fills are not touched.

import type { SchemaFamily } from './families';
import { argTexts, latin1Decode, refIds, replaceArg } from './removal';
import type { StepIndex } from './stepIndex';
import { LIST, NULLTXT, REF, entityLine, stepReal } from './stepText';

/** The mesh of one element as the cleanup simplification produces it (`CleanupPlan.replacements`): viewer frame, metres. */
export interface SimplifiedMesh {
  globalId: string;
  /** Express id in the source file the element came from. */
  expressId: number;
  positions: Float32Array;
  indices: Uint32Array;
}

export interface SimplifyFrame {
  /** `SceneModel.originShift`: IFC frame, metres. */
  shift: readonly [number, number, number];
  /** Metres per file length unit. */
  lengthScale: number;
}

/** Above this many triangles a 2X3 file gets about 5 lines per triangle: the dialog warns. */
export const BREP_WARN_TRIANGLES = 200_000;

// ---------------------------------------------------------------- text readers

const num = (s: string): number => parseFloat(s);
const numbers = (arg: string): number[] => (arg.match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g) ?? []).map(num);

const PREFIX: Record<string, number> = { EXA: 1e18, PETA: 1e15, TERA: 1e12, GIGA: 1e9, MEGA: 1e6, KILO: 1e3, HECTO: 1e2, DECA: 10, DECI: 0.1, CENTI: 0.01, MILLI: 0.001, MICRO: 1e-6, NANO: 1e-9, PICO: 1e-12, FEMTO: 1e-15, ATTO: 1e-18 };

/** Metres per file length unit, read from the project's unit assignment (SI prefix, or a conversion based unit); 1 when it cannot be told. */
export function lengthScaleOf(ix: StepIndex, bytes: Uint8Array): number {
  const text = (r: number): string => latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!);
  const rowOfArg = (args: string[], i: number): number => {
    const ids = refIds(args[i] ?? '');
    return ids.length ? ix.rowOf(ids[0]!) : -1;
  };
  let proj = -1;
  for (let r = 0; r < ix.count && proj < 0; r++) if (ix.typeOf(r) === 'IFCPROJECT') proj = r;
  if (proj < 0) return 1;
  const ua = rowOfArg(argTexts(text(proj)), 8);
  if (ua < 0) return 1;
  for (const id of refIds(argTexts(text(ua))[0] ?? '')) {
    const u = ix.rowOf(id);
    if (u < 0) continue;
    const t = ix.typeOf(u);
    const a = argTexts(text(u));
    if (t === 'IFCSIUNIT') {
      if (!/\.LENGTHUNIT\./i.test(a[1] ?? '')) continue;
      const pre = /\.([A-Z]+)\./i.exec(a[2] ?? '');
      return pre ? PREFIX[pre[1]!.toUpperCase()] ?? 1 : 1;
    }
    if (t === 'IFCCONVERSIONBASEDUNIT' || t === 'IFCCONVERSIONBASEDUNITWITHOFFSET') {
      if (!/\.LENGTHUNIT\./i.test(a[1] ?? '')) continue;
      const mwu = rowOfArg(a, 3);
      if (mwu < 0) continue;
      const m = argTexts(text(mwu));
      const value = numbers(m[0] ?? '')[0];
      const si = rowOfArg(m, 1);
      let base = 1;
      if (si >= 0 && ix.typeOf(si) === 'IFCSIUNIT') {
        const sa = argTexts(text(si));
        const pre = /\.([A-Z]+)\./i.exec(sa[2] ?? '');
        base = pre ? PREFIX[pre[1]!.toUpperCase()] ?? 1 : 1;
      }
      return value === undefined ? 1 : value * base;
    }
  }
  return 1;
}

/** Row-major 4x4. */
export type Mat4 = Float64Array;
const identity = (): Mat4 => Float64Array.from([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

function mul(a: Mat4, b: Mat4): Mat4 {
  const o = new Float64Array(16);
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[r * 4 + k]! * b[k * 4 + c]!;
    o[r * 4 + c] = s;
  }
  return o;
}

const norm = (v: number[]): number[] => {
  const l = Math.hypot(v[0]!, v[1]!, v[2]!);
  return l < 1e-12 ? [0, 0, 0] : [v[0]! / l, v[1]! / l, v[2]! / l];
};
const cross = (a: number[], b: number[]): number[] => [a[1]! * b[2]! - a[2]! * b[1]!, a[2]! * b[0]! - a[0]! * b[2]!, a[0]! * b[1]! - a[1]! * b[0]!];

/**
 * The matrix of an IfcAxis2Placement3D (or 2D) line: columns are the axes, then the location. Null when the line is something else.
 * Z = Axis (default 0 0 1); X = RefDirection made perpendicular to Z (default 1 0 0); Y = Z x X.
 */
function axisMatrix(ix: StepIndex, bytes: Uint8Array, row: number): Mat4 | null {
  const text = (r: number): string => latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!);
  const point = (arg: string | undefined): number[] | null => {
    const ids = refIds(arg ?? '');
    const r = ids.length ? ix.rowOf(ids[0]!) : -1;
    if (r < 0) return null;
    const n = numbers(argTexts(text(r))[0] ?? '');
    return [n[0] ?? 0, n[1] ?? 0, n[2] ?? 0];
  };
  const t = ix.typeOf(row);
  const a = argTexts(text(row));
  const loc = point(a[0]) ?? [0, 0, 0];
  let z = [0, 0, 1];
  let x = [1, 0, 0];
  if (t === 'IFCAXIS2PLACEMENT3D') {
    const ax = point(a[1]);
    const rd = point(a[2]);
    if (ax) z = norm(ax);
    if (rd) x = norm(rd);
  } else if (t === 'IFCAXIS2PLACEMENT2D') {
    const rd = point(a[1]);
    if (rd) x = norm(rd);
  } else return null;
  const d = x[0]! * z[0]! + x[1]! * z[1]! + x[2]! * z[2]!;
  x = norm([x[0]! - d * z[0]!, x[1]! - d * z[1]!, x[2]! - d * z[2]!]);
  if (x[0] === 0 && x[1] === 0 && x[2] === 0) return null;
  const y = cross(z, x);
  return Float64Array.from([x[0]!, y[0]!, z[0]!, loc[0]!, x[1]!, y[1]!, z[1]!, loc[1]!, x[2]!, y[2]!, z[2]!, loc[2]!, 0, 0, 0, 1]);
}

/** Local-to-world matrix of an IfcLocalPlacement chain, in file units. Null for any other placement (linear, grid) or a broken chain. */
export function placementMatrix(ix: StepIndex, bytes: Uint8Array, placementRow: number): Mat4 | null {
  let m = identity();
  let r = placementRow;
  for (let depth = 0; depth < 64 && r >= 0; depth++) {
    if (ix.typeOf(r) !== 'IFCLOCALPLACEMENT') return null;
    const a = argTexts(latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!));
    const relIds = refIds(a[1] ?? '');
    const rel = relIds.length ? ix.rowOf(relIds[0]!) : -1;
    const local = rel >= 0 ? axisMatrix(ix, bytes, rel) : identity();
    if (!local) return null;
    m = mul(local, m);
    const parentIds = refIds(a[0] ?? '');
    r = parentIds.length ? ix.rowOf(parentIds[0]!) : -1;
    if (parentIds.length && r < 0) return null;
  }
  return r >= 0 ? null : m;
}

/** Inverse of a rigid (rotation + translation) matrix. */
export function invertRigid(m: Mat4): Mat4 {
  const o = identity();
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) o[r * 4 + c] = m[c * 4 + r]!;
  for (let r = 0; r < 3; r++) o[r * 4 + 3] = -(o[r * 4]! * m[3]! + o[r * 4 + 1]! * m[7]! + o[r * 4 + 2]! * m[11]!);
  return o;
}

// ---------------------------------------------------------------- mesh

export interface LocalMesh {
  /** xyz per vertex in the element's local frame, file units. */
  points: Float64Array;
  /** Triangles into `points`, welded, degenerate ones dropped. */
  tris: Uint32Array;
  /** Every edge is shared by exactly two triangles. */
  closed: boolean;
  /** Bounds in IFC world metres [minx, miny, minz, maxx, maxy, maxz]. */
  worldBounds: [number, number, number, number, number, number];
}

/** Viewer positions -> IFC world metres: `p = ( v.x + s.x, -v.z + s.y, v.y + s.z )` (bcf/model.ts `viewerToIfc`). */
function toLocal(m: SimplifiedMesh, frame: SimplifyFrame, inv: Mat4): LocalMesh {
  const n = Math.floor(m.positions.length / 3);
  const key = new Map<string, number>();
  const map = new Uint32Array(n);
  const pts: number[] = [];
  const wb: LocalMesh['worldBounds'] = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  const s = frame.shift;
  for (let v = 0; v < n; v++) {
    const vx = m.positions[v * 3]!, vy = m.positions[v * 3 + 1]!, vz = m.positions[v * 3 + 2]!;
    const wx = vx + s[0], wy = -vz + s[1], wz = vy + s[2];
    for (let k = 0; k < 3; k++) {
      const w = [wx, wy, wz][k]!;
      if (w < wb[k]!) wb[k] = w;
      if (w > wb[k + 3]!) wb[k + 3] = w;
    }
    // file units, then the local frame
    const fx = wx / frame.lengthScale, fy = wy / frame.lengthScale, fz = wz / frame.lengthScale;
    const lx = inv[0]! * fx + inv[1]! * fy + inv[2]! * fz + inv[3]!;
    const ly = inv[4]! * fx + inv[5]! * fy + inv[6]! * fz + inv[7]!;
    const lz = inv[8]! * fx + inv[9]! * fy + inv[10]! * fz + inv[11]!;
    // weld on the float32 grid of the viewer (1e-5 m)
    const k = `${Math.round(vx * 1e5)},${Math.round(vy * 1e5)},${Math.round(vz * 1e5)}`;
    let id = key.get(k);
    if (id === undefined) {
      id = pts.length / 3;
      key.set(k, id);
      pts.push(lx, ly, lz);
    }
    map[v] = id;
  }
  const tris: number[] = [];
  const edges = new Map<number, number>();
  const V = pts.length / 3;
  for (let t = 0; t + 2 < m.indices.length; t += 3) {
    const a = map[m.indices[t]!]!, b = map[m.indices[t + 1]!]!, c = map[m.indices[t + 2]!]!;
    if (a === b || b === c || a === c) continue;
    tris.push(a, b, c);
    for (const [u, w] of [[a, b], [b, c], [c, a]] as const) {
      const e = Math.min(u, w) * V + Math.max(u, w);
      edges.set(e, (edges.get(e) ?? 0) + 1);
    }
  }
  let closed = tris.length > 0;
  for (const c of edges.values()) if (c !== 2) { closed = false; break; }
  return { points: Float64Array.from(pts), tris: Uint32Array.from(tris), closed, worldBounds: wb };
}

// ---------------------------------------------------------------- lines

const real3 = (x: number, y: number, z: number): string => `(${stepReal(+x.toPrecision(9))},${stepReal(+y.toPrecision(9))},${stepReal(+z.toPrecision(9))})`;

export interface RepLines {
  lines: string[];
  /** The new IfcShapeRepresentation and its single item. */
  repId: number;
  itemId: number;
  lastId: number;
}

/** The lines of a new Body representation (design 2.5), ids from `first`. */
export function repLines(family: SchemaFamily, ctx: number, first: number, mesh: LocalMesh): RepLines {
  let id = first;
  const lines: string[] = [];
  const nV = mesh.points.length / 3;
  const nT = mesh.tris.length / 3;
  if (family !== '2x3') {
    const pl = id++;
    lines.push(entityLine(pl, 'IFCCARTESIANPOINTLIST3D', [`(${Array.from({ length: nV }, (_, v) => real3(mesh.points[v * 3]!, mesh.points[v * 3 + 1]!, mesh.points[v * 3 + 2]!)).join(',')})`]));
    const fs = id++;
    const idx = Array.from({ length: nT }, (_, t) => `(${mesh.tris[t * 3]! + 1},${mesh.tris[t * 3 + 1]! + 1},${mesh.tris[t * 3 + 2]! + 1})`).join(',');
    lines.push(entityLine(fs, 'IFCTRIANGULATEDFACESET', [REF(pl), NULLTXT, mesh.closed ? '.T.' : '.F.', `(${idx})`, NULLTXT]));
    const rep = id++;
    lines.push(entityLine(rep, 'IFCSHAPEREPRESENTATION', [REF(ctx), "'Body'", "'Tessellation'", LIST([REF(fs)])]));
    return { lines, repId: rep, itemId: fs, lastId: id - 1 };
  }
  // IFC2X3: a faceted brep for a closed mesh, a shell based surface model for an open one
  const pts: number[] = [];
  for (let v = 0; v < nV; v++) {
    pts.push(id);
    lines.push(entityLine(id++, 'IFCCARTESIANPOINT', [real3(mesh.points[v * 3]!, mesh.points[v * 3 + 1]!, mesh.points[v * 3 + 2]!)]));
  }
  const faces: number[] = [];
  for (let t = 0; t < nT; t++) {
    const loop = id++;
    lines.push(entityLine(loop, 'IFCPOLYLOOP', [LIST([0, 1, 2].map((k) => REF(pts[mesh.tris[t * 3 + k]!]!)))]));
    const bound = id++;
    lines.push(entityLine(bound, 'IFCFACEOUTERBOUND', [REF(loop), '.T.']));
    const face = id++;
    lines.push(entityLine(face, 'IFCFACE', [LIST([REF(bound)])]));
    faces.push(face);
  }
  const shell = id++;
  const item = id++;
  if (mesh.closed) {
    lines.push(entityLine(shell, 'IFCCLOSEDSHELL', [LIST(faces.map(REF))]));
    lines.push(entityLine(item, 'IFCFACETEDBREP', [REF(shell)]));
  } else {
    lines.push(entityLine(shell, 'IFCOPENSHELL', [LIST(faces.map(REF))]));
    lines.push(entityLine(item, 'IFCSHELLBASEDSURFACEMODEL', [LIST([REF(shell)])]));
  }
  const rep = id++;
  lines.push(entityLine(rep, 'IFCSHAPEREPRESENTATION', [REF(ctx), "'Body'", mesh.closed ? "'Brep'" : "'SurfaceModel'", LIST([REF(item)])]));
  return { lines, repId: rep, itemId: item, lastId: id - 1 };
}

// ---------------------------------------------------------------- the plan

export interface GeometryPlan {
  /** New lines, ids `first ..= lastId`. */
  lines: string[];
  lastId: number;
  /** `[product definition shape, old body]` rows: the shape lets go of the old body. */
  detach: Array<[number, number]>;
  /** Rows whose text changed: the shapes (new body in place of the old) and the layers that follow it. */
  rewrite: Map<number, string>;
  /** Rows the new lines refer to (surface styles of the old body). */
  pin: number[];
  /** Express ids that got a new body, with their bounds in IFC world metres (for the self-check). */
  applied: Array<{ expressId: number; globalId: string; bounds: LocalMesh['worldBounds']; triangles: number; closed: boolean }>;
  skipped: Array<{ expressId: number; globalId: string; reason: string }>;
  /** Triangles written in a 2X3 file (about 5 lines each). */
  brepTriangles: number;
}

const ARG = { ObjectPlacement: 5, Representation: 6 } as const;

/**
 * Plan the new bodies. An element keeps its original body, and is listed in `skipped`, when it has no body, a linear or grid placement,
 * a shared shape, or when the mesh is empty. `skip` lists elements the self-check found out of place.
 */
export function planGeometry(
  ix: StepIndex, bytes: Uint8Array, meshes: readonly SimplifiedMesh[], frame: SimplifyFrame, family: SchemaFamily, first: number,
  skip: ReadonlySet<number> = new Set(),
): GeometryPlan {
  const text = (r: number): string => latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!);
  const out: GeometryPlan = { lines: [], lastId: first - 1, detach: [], rewrite: new Map(), pin: [], applied: [], skipped: [], brepTriangles: 0 };
  let next = first;
  const seen = new Set<number>();
  for (const m of meshes) {
    const why = ((): string | null => {
      if (skip.has(m.expressId)) return 'its written bounds differ from the viewer bounds by more than 1 mm';
      if (seen.has(m.expressId)) return 'two replacements for one element';
      seen.add(m.expressId);
      return null;
    })();
    const skipIt = (reason: string): void => { out.skipped.push({ expressId: m.expressId, globalId: m.globalId, reason }); };
    if (why) { skipIt(why); continue; }
    const row = ix.rowOf(m.expressId);
    if (row < 0) { skipIt('not found in the source file'); continue; }
    const args = argTexts(text(row));
    const placeIds = refIds(args[ARG.ObjectPlacement] ?? '');
    const prodIds = refIds(args[ARG.Representation] ?? '');
    const pdsRow = prodIds.length ? ix.rowOf(prodIds[0]!) : -1;
    if (pdsRow < 0 || ix.typeOf(pdsRow) !== 'IFCPRODUCTDEFINITIONSHAPE') { skipIt('it has no product definition shape'); continue; }
    if (out.rewrite.has(pdsRow) || ix.invStart[pdsRow + 1]! - ix.invStart[pdsRow]! !== 1) { skipIt('its shape is shared with something else'); continue; }
    let mat: Mat4 | null = identity();
    if (placeIds.length) {
      const prow = ix.rowOf(placeIds[0]!);
      mat = prow >= 0 ? placementMatrix(ix, bytes, prow) : null;
    }
    if (!mat) { skipIt('its placement is not an IfcLocalPlacement chain (linear or grid placement)'); continue; }
    const pargs = argTexts(text(pdsRow));
    const reps = refIds(pargs[2] ?? '').map((id) => ix.rowOf(id)).filter((r) => r >= 0);
    const bodies = reps.filter((r) => ix.typeOf(r) === 'IFCSHAPEREPRESENTATION' && /^'Body'$/i.test((argTexts(text(r))[1] ?? '').trim()));
    if (bodies.length === 0) { skipIt('it has no Body representation'); continue; }
    const ctxIds = refIds(argTexts(text(bodies[0]!))[0] ?? '');
    if (ctxIds.length === 0) { skipIt('its Body representation has no context'); continue; }
    const lm = toLocal(m, frame, invertRigid(mat));
    if (lm.tris.length === 0) { skipIt('the replacement mesh has no triangles'); continue; }
    // the surface style of the first body item
    const items = refIds(argTexts(text(bodies[0]!))[3] ?? '').map((id) => ix.rowOf(id)).filter((r) => r >= 0);
    // The first body item's surface style; for a mapped item (type-shared geometry) the style of the first item of the mapped representation.
    let styles: { arg1: string; arg2: string; rows: number[] } | null = null;
    let cur = items.length ? items[0]! : -1;
    for (let depth = 0; depth < 4 && cur >= 0 && !styles; depth++) {
      for (let k = ix.invStart[cur]!; k < ix.invStart[cur + 1]!; k++) {
        const sr = ix.inv[k]!;
        if (ix.typeOf(sr) !== 'IFCSTYLEDITEM') continue;
        const sa = argTexts(text(sr));
        styles = { arg1: sa[1] ?? '$', arg2: sa[2] ?? '$', rows: refIds(sa[1] ?? '').map((id) => ix.rowOf(id)).filter((r) => r >= 0) };
        break;
      }
      if (styles || ix.typeOf(cur) !== 'IFCMAPPEDITEM') break;
      const src = ix.rowOf(refIds(argTexts(text(cur))[0] ?? '')[0] ?? -1);
      const mapped = src >= 0 ? ix.rowOf(refIds(argTexts(text(src))[1] ?? '')[0] ?? -1) : -1;
      const inner = mapped >= 0 ? ix.rowOf(refIds(argTexts(text(mapped))[3] ?? '')[0] ?? -1) : -1;
      cur = inner;
    }
    const rep = repLines(family, ctxIds[0]!, next, lm);
    out.lines.push(...rep.lines);
    next = rep.lastId + 1;
    if (styles) {
      out.lines.push(entityLine(next++, 'IFCSTYLEDITEM', [REF(rep.itemId), styles.arg1, styles.arg2]));
      out.pin.push(...styles.rows);
    }
    // the shape: the new body in place of the first old one, the other old bodies out
    const oldIds = new Set(bodies.map((r) => ix.id[r]!));
    let placed = false;
    const list = refIds(pargs[2] ?? '').flatMap((id) => (oldIds.has(id) ? (placed ? [] : ((placed = true), [rep.repId])) : [id]));
    out.rewrite.set(pdsRow, replaceArg(text(pdsRow), 2, LIST(list.map(REF))));
    for (const b of bodies) {
      out.detach.push([pdsRow, b]);
      // layers that listed the old body list the new one
      for (let k = ix.invStart[b]!; k < ix.invStart[b + 1]!; k++) {
        const lr = ix.inv[k]!;
        const t = ix.typeOf(lr);
        if (t !== 'IFCPRESENTATIONLAYERASSIGNMENT' && t !== 'IFCPRESENTATIONLAYERWITHSTYLE') continue;
        const cur = out.rewrite.get(lr) ?? text(lr);
        const la = argTexts(cur);
        const ai = 2;
        const ids = refIds(la[ai] ?? '');
        const had = ids.includes(ix.id[b]!);
        if (!had) continue;
        const swapped = ids.flatMap((id) => (id === ix.id[b]! ? (ids.includes(rep.repId) ? [] : [rep.repId]) : [id]));
        out.rewrite.set(lr, replaceArg(cur, ai, LIST(swapped.map(REF))));
      }
    }
    out.applied.push({ expressId: m.expressId, globalId: m.globalId, bounds: lm.worldBounds, triangles: lm.tris.length / 3, closed: lm.closed });
    if (family === '2x3') out.brepTriangles += lm.tris.length / 3;
  }
  out.lastId = next - 1;
  return out;
}
