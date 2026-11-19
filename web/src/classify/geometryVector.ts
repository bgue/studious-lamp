// A compact numeric shape descriptor of one element, as ONE line of text for the request state (`state.shape`).
// Pure and tested in Node: no DOM, no three.js. Every backend can use it, including the short-premise providers
// (decision, webllm), because it costs about 40 to 60 tokens and no markup. Setting: `geometryVector` (default off).
// Docs: docs-features/classify.md, "Shape as numbers".
//
// What the line says (viewer frame: y up; the output frame is IFC: X east, Y north, Z up; metres):
//   dims       the bounding box sides sorted, longest first, as "4.2 x 2.7 x 0.2 m"
//   volume     "volume 2.27 m3" and "surface 25.4 m2", from the mesh (left out for an open or empty mesh, or a huge one)
//   elongation longest side over the middle one (1 = compact, large = a bar); flatness: middle over the shortest (1 = not flat, large = a slab)
//   axis       the main axis of the mesh (principal component of its vertices; the longest box side when there is no mesh)
//              against up: "horizontal (90 deg from up)", "vertical (2 deg ...)" or "inclined"
//   plan       the direction of the longest horizontal axis in plan, 0 to 179 deg from east towards north
//   level      the box bottom and top above the storey elevation, "base 0.1 m above storey, top 2.9 m"
//   openings   the number of voids cut into the element, when the model says
// Anything that is not known is left out; a number is rounded to 2 significant decimals so equal shapes give equal text.

export type Box6 = readonly [number, number, number, number, number, number];
export interface ShapeMesh {
  position: ArrayLike<number>;
  index?: ArrayLike<number> | null;
}
export interface ShapeInput {
  /** [minx, miny, minz, maxx, maxy, maxz] in the viewer frame (y up), metres. */
  bounds: Box6;
  mesh?: ShapeMesh | null;
  /** Elevation of the element's storey, metres (same frame as the bounds), or null/absent when it has none. */
  storeyElevation?: number | null;
  /** Number of openings (voids) in the element, or null/absent when unknown. */
  openings?: number | null;
}
export interface ShapeVector {
  /** Box sides sorted longest first, metres. */
  dims: [number, number, number];
  volume: number | null;
  area: number | null;
  /** Longest over middle side. */
  elongation: number;
  /** Middle over shortest side. */
  flatness: number;
  /** Angle between the main axis and up, 0 to 90 degrees. */
  axisFromUp: number;
  /** 'vertical' under 20 degrees, 'horizontal' over 70, else 'inclined'. */
  axisKind: 'vertical' | 'horizontal' | 'inclined';
  /** Direction of the longest horizontal axis in plan, degrees from east (X) towards north (Y), 0 to 179. */
  planAngle: number;
  base: number | null;
  top: number | null;
  openings: number | null;
}

/** Meshes with more triangles than this get no volume or area (the line stays cheap). */
export const MAX_TRIANGLES = 200_000;
/** The mesh sample for the main axis: at most this many vertices. */
const MAX_AXIS_POINTS = 20_000;
export const VECTOR_TOKEN_ESTIMATE = 50;

const r2 = (n: number): number => {
  const r = Math.round(n * 100) / 100;
  return Object.is(r, -0) ? 0 : r;
};
/** Two significant decimals for a ratio: 1.56, 13, 120. */
const ratio = (n: number): number => (n >= 100 ? Math.round(n) : n >= 10 ? Math.round(n * 10) / 10 : r2(n));

/** Eigenvector of the largest eigenvalue of a symmetric 3x3 matrix (power iteration; enough for an axis), or null for a zero matrix. */
function principalAxis(c: number[][], skip: number[] | null): number[] | null {
  let v = skip ? [skip[1]! - skip[2]! * 0.3, skip[2]! * 0.7 - skip[0]!, skip[0]! * 0.2 - skip[1]!] : [1, 0.7, 0.3];
  if (skip) {
    // start orthogonal to the first axis so the iteration finds the next one
    const d = v[0]! * skip[0]! + v[1]! * skip[1]! + v[2]! * skip[2]!;
    v = v.map((x, i) => x - d * skip[i]!);
  }
  for (let k = 0; k < 40; k++) {
    let w = [c[0]![0]! * v[0]! + c[0]![1]! * v[1]! + c[0]![2]! * v[2]!, c[1]![0]! * v[0]! + c[1]![1]! * v[1]! + c[1]![2]! * v[2]!, c[2]![0]! * v[0]! + c[2]![1]! * v[1]! + c[2]![2]! * v[2]!];
    if (skip) {
      const d = w[0]! * skip[0]! + w[1]! * skip[1]! + w[2]! * skip[2]!;
      w = w.map((x, i) => x - d * skip[i]!);
    }
    const n = Math.hypot(w[0]!, w[1]!, w[2]!);
    if (n < 1e-12) return null;
    v = w.map((x) => x / n);
  }
  return v;
}

/** Principal axes (longest first) of the vertex cloud, or null when there are too few vertices. */
function meshAxes(mesh: ShapeMesh): { a1: number[]; a2: number[] | null } | null {
  const pos = mesh.position;
  const n = Math.floor(pos.length / 3);
  if (n < 3) return null;
  const step = Math.max(1, Math.ceil(n / MAX_AXIS_POINTS));
  let cx = 0, cy = 0, cz = 0, m = 0;
  for (let i = 0; i < n; i += step) { cx += pos[3 * i]!; cy += pos[3 * i + 1]!; cz += pos[3 * i + 2]!; m++; }
  cx /= m; cy /= m; cz /= m;
  const c = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let i = 0; i < n; i += step) {
    const x = pos[3 * i]! - cx, y = pos[3 * i + 1]! - cy, z = pos[3 * i + 2]! - cz;
    c[0]![0]! += x * x; c[0]![1]! += x * y; c[0]![2]! += x * z;
    c[1]![1]! += y * y; c[1]![2]! += y * z; c[2]![2]! += z * z;
  }
  c[1]![0] = c[0]![1]!; c[2]![0] = c[0]![2]!; c[2]![1] = c[1]![2]!;
  const a1 = principalAxis(c, null);
  if (!a1) return null;
  return { a1, a2: principalAxis(c, a1) };
}

/** Volume (divergence theorem, absolute) and surface area of a triangle mesh; null volume when it is not a plausible closed solid. */
export function meshVolumeArea(mesh: ShapeMesh, boxVolume: number): { volume: number | null; area: number | null } {
  const pos = mesh.position;
  const idx = mesh.index ?? null;
  const tris = idx ? Math.floor(idx.length / 3) : Math.floor(pos.length / 9);
  if (tris === 0 || tris > MAX_TRIANGLES) return { volume: null, area: null };
  let vol = 0, area = 0;
  for (let t = 0; t < tris; t++) {
    const ia = idx ? idx[3 * t]! : 3 * t, ib = idx ? idx[3 * t + 1]! : 3 * t + 1, ic = idx ? idx[3 * t + 2]! : 3 * t + 2;
    const ax = pos[3 * ia]!, ay = pos[3 * ia + 1]!, az = pos[3 * ia + 2]!;
    const bx = pos[3 * ib]!, by = pos[3 * ib + 1]!, bz = pos[3 * ib + 2]!;
    const cx = pos[3 * ic]!, cy = pos[3 * ic + 1]!, cz = pos[3 * ic + 2]!;
    const ux = bx - ax, uy = by - ay, uz = bz - az, vx = cx - ax, vy = cy - ay, vz = cz - az;
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    area += Math.hypot(nx, ny, nz) / 2;
    vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6;
  }
  const v = Math.abs(vol);
  // An open or inverted mesh gives a volume that is zero or larger than its own box: leave it out.
  const ok = v > 1e-6 && v <= boxVolume * 1.01 + 1e-9;
  return { volume: ok ? v : null, area: area > 0 ? area : null };
}

/** The numbers of the shape, or null for an element with an empty box. */
export function describeShape(input: ShapeInput): ShapeVector | null {
  const b = input.bounds;
  const sx = b[3] - b[0], sy = b[4] - b[1], sz = b[5] - b[2];
  if (!(sx >= 0 && sy >= 0 && sz >= 0) || (sx === 0 && sy === 0 && sz === 0) || ![sx, sy, sz].every(Number.isFinite)) return null;
  const sides = [sx, sy, sz].sort((p, q) => q - p) as [number, number, number];
  const [L, M, S] = sides;
  const eps = 1e-6;
  const elongation = L / Math.max(M, eps);
  const flatness = M / Math.max(S, eps);

  // main axis (viewer frame) and the longest horizontal direction
  const axes = input.mesh ? meshAxes(input.mesh) : null;
  let axis: number[];
  let second: number[] | null = null;
  if (axes) {
    axis = axes.a1;
    second = axes.a2;
  } else {
    const e: Array<[number, number[]]> = [[sx, [1, 0, 0]], [sy, [0, 1, 0]], [sz, [0, 0, 1]]];
    e.sort((p, q) => q[0] - p[0]);
    axis = e[0]![1];
    second = e[1]![1];
  }
  const axisFromUp = (Math.acos(Math.min(1, Math.abs(axis[1]!))) * 180) / Math.PI;
  const kind: ShapeVector['axisKind'] = axisFromUp < 20 ? 'vertical' : axisFromUp > 70 ? 'horizontal' : 'inclined';
  // A vertical element has no direction in plan from its main axis: use the next axis (the long side of a wall's section).
  let dirv = kind === 'vertical' ? second ?? axis : axis;
  if (Math.hypot(dirv[0]!, dirv[2]!) < 1e-6) dirv = [1, 0, 0];
  // viewer (x, z) to IFC (X, Y) = (x, -z)
  let planAngle = (Math.atan2(-dirv[2]!, dirv[0]!) * 180) / Math.PI;
  planAngle = ((planAngle % 180) + 180) % 180;
  planAngle = Math.round(planAngle) % 180;

  const va = input.mesh ? meshVolumeArea(input.mesh, sx * sy * sz) : { volume: null, area: null };
  const elev = input.storeyElevation;
  const hasStorey = typeof elev === 'number' && Number.isFinite(elev);
  return {
    dims: sides,
    volume: va.volume,
    area: va.area,
    elongation,
    flatness,
    axisFromUp: Math.round(axisFromUp),
    axisKind: kind,
    planAngle,
    base: hasStorey ? b[1] - elev : null,
    top: hasStorey ? b[4] - elev : null,
    openings: typeof input.openings === 'number' && input.openings >= 0 ? input.openings : null,
  };
}

/** The one line for the state. No newline, so JSON does not escape it. Empty string for a null shape. */
export function shapeLine(v: ShapeVector | null): string {
  if (!v) return '';
  const parts: string[] = [`${v.dims.map(r2).join(' x ')} m sorted`];
  if (v.volume !== null) parts.push(`volume ${r2(v.volume)} m3`);
  if (v.area !== null) parts.push(`surface ${ratio(v.area)} m2`);
  parts.push(`elongation ${ratio(v.elongation)}`, `flatness ${ratio(v.flatness)}`);
  parts.push(`main axis ${v.axisKind} (${v.axisFromUp} deg from up)`);
  if (v.axisKind !== 'vertical' || v.elongation > 1.2 || v.flatness > 1.2) parts.push(`plan angle ${v.planAngle} deg`);
  if (v.base !== null && v.top !== null) parts.push(`base ${r2(v.base)} m above storey, top ${r2(v.top)} m`);
  if (v.openings !== null) parts.push(`${v.openings} opening${v.openings === 1 ? '' : 's'}`);
  return parts.join('; ');
}

/** Describe and format in one step. */
export const shapeText = (input: ShapeInput): string => shapeLine(describeShape(input));

/** A cheap token estimate for the line (about 3 characters a token, like the SVG). */
export const shapeTokens = (line: string): number => Math.ceil(line.length / 3);
