// Native vector geometry as text: compact SVG markup that goes into the `state` of a request, so a model that reads text (d3-edge in the browser or on the
// endpoint, Jev) reads the shape as tokens. No picture, no WebGL: pure and tested in Node.
//
//   isolated  the element alone, orthographic: plan and one elevation (across the longest horizontal axis), as simplified outlines (the convex hull of the
//             projected mesh, simplified by Douglas-Peucker; a round outline is a <circle>, a filled rectangle a <rect>). Class, predefined type and
//             size are attributes. Origin at the minimum corner of the element's bounding box, metres, IFC frame (X east, Y north, Z up; the viewer's y is up).
//   context   the same two views of the element's bounding box grown by the margin of the context picture, with every other element that touches the box
//             as an outline clipped to the box, in <g data-class data-tag>; the element is <g id='target'>. Neighbours: class and tag only, never a classification result.
//
// Attributes use single quotes: the state is JSON, so a double quote would cost an escape (a token) every time. Numbers have at most 2 decimals.

import { contextBox, contextIds } from './thumbs';
import type { Bounds6 } from './thumbs';

export const GEOMETRY_BUDGET_TOKENS = 1500;
export const MAX_GEOMETRY_NEIGHBOURS = 25;
/** A neighbour whose largest side is under this share of the box is left out. */
export const TINY_SHARE = 0.02;

export interface GeoMesh {
  position: ArrayLike<number>;
  index?: ArrayLike<number> | null;
}
export interface GeoInfo {
  ifcClass: string;
  tag?: string;
  predefined?: string;
}
export interface GeoSource {
  bounds(id: number): Bounds6 | null;
  mesh(id: number): GeoMesh | null;
  ids(): Iterable<number>;
  info(id: number): GeoInfo;
}
export interface GeometrySettings {
  /** Add the context picture's box with the elements around the element. */
  context: boolean;
  /** Context box margin, percent (as for the pictures). */
  margin: number;
  /** Most tokens of the markup (an estimate). */
  budget?: number;
}
export interface GeometrySet {
  id: number;
  /** The one-line legend that goes before the markup. */
  legend: string;
  /** The markup: one <svg> per view, one per line. */
  svg: string;
  /** Estimated tokens of legend and markup together. */
  tokens: number;
  /** Neighbours drawn. */
  neighbours: number;
  /** The same markup split into the <svg> elements (for the preview). */
  views: Array<{ name: string; svg: string }>;
}

/**
 * The markup dressed for the drawer preview only (the model reads the plain markup): a standalone SVG with outlines, a grey fill and the target in orange.
 * The styles are not part of what the model reads.
 */
export const previewSvg = (svg: string): string =>
  svg.replace('<svg ', "<svg xmlns='http://www.w3.org/2000/svg' ").replace(/(<svg [^>]*>)/, "$1<style>*{fill:#e3e6ea;stroke:#1b2430;stroke-width:1.4px;vector-effect:non-scaling-stroke}#target *{fill:#f0802a}</style>");

/** A cheap token estimate for markup: about 3 characters a token. */
export const estimateTokens = (text: string): number => Math.ceil(text.length / 3);

const fmt = (n: number): string => {
  const r = Math.round(n * 100) / 100;
  return String(Object.is(r, -0) ? 0 : r);
};

type P = [number, number];

// IFC frame from the viewer's: X = x, Y = -z, Z = y (the viewer has y up).
const toIfc = (x: number, y: number, z: number): [number, number, number] => [x, -z, y];
const boundsIfc = (b: Bounds6): Bounds6 => [b[0], -b[5], b[1], b[3], -b[2], b[4]];

/** Convex hull (monotone chain), counter-clockwise, no repeated first point. Points are rounded to 1 cm first. */
export function convexHull(pts: P[]): P[] {
  const seen = new Set<string>();
  const u: P[] = [];
  for (const p of pts) {
    const k = `${Math.round(p[0] * 100)},${Math.round(p[1] * 100)}`;
    if (!seen.has(k)) { seen.add(k); u.push([Math.round(p[0] * 100) / 100, Math.round(p[1] * 100) / 100]); }
  }
  if (u.length < 3) return u;
  u.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: P, a: P, b: P): number => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: P[] = [];
  for (const p of u) { while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, p) <= 0) lower.pop(); lower.push(p); }
  const upper: P[] = [];
  for (let i = u.length - 1; i >= 0; i--) { const p = u[i]!; while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, p) <= 0) upper.pop(); upper.push(p); }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

/** Douglas-Peucker on a closed polygon: split at the two farthest points, simplify both chains. */
export function simplifyPolygon(poly: P[], eps: number): P[] {
  if (poly.length <= 4) return poly;
  const dist = (p: P, a: P, b: P): number => {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const l = Math.hypot(dx, dy);
    return l < 1e-12 ? Math.hypot(p[0] - a[0], p[1] - a[1]) : Math.abs(dx * (a[1] - p[1]) - dy * (a[0] - p[0])) / l;
  };
  const chain = (pts: P[]): P[] => {
    if (pts.length <= 2) return pts;
    const a = pts[0]!, b = pts[pts.length - 1]!;
    let worst = -1, at = -1;
    for (let i = 1; i < pts.length - 1; i++) { const d = dist(pts[i]!, a, b); if (d > worst) { worst = d; at = i; } }
    if (worst <= eps) return [a, b];
    return [...chain(pts.slice(0, at + 1)).slice(0, -1), ...chain(pts.slice(at))];
  };
  let i0 = 0, i1 = 0, best = -1;
  for (let i = 0; i < poly.length; i++) for (let j = i + 1; j < poly.length; j++) {
    const d = Math.hypot(poly[i]![0] - poly[j]![0], poly[i]![1] - poly[j]![1]);
    if (d > best) { best = d; i0 = i; i1 = j; }
  }
  const first = poly.slice(i0, i1 + 1);
  const second = [...poly.slice(i1), ...poly.slice(0, i0 + 1)];
  return [...chain(first).slice(0, -1), ...chain(second).slice(0, -1)];
}

const area = (poly: P[]): number => {
  let a = 0;
  for (let i = 0; i < poly.length; i++) { const p = poly[i]!, q = poly[(i + 1) % poly.length]!; a += p[0] * q[1] - q[0] * p[1]; }
  return Math.abs(a) / 2;
};

/** Sutherland-Hodgman: a polygon clipped to the rectangle [x0, y0, x1, y1]. */
export function clipPolygon(poly: P[], r: readonly [number, number, number, number]): P[] {
  let out = poly;
  const edges: Array<{ inside: (p: P) => boolean; cut: (a: P, b: P) => P }> = [
    { inside: (p) => p[0] >= r[0], cut: (a, b) => [r[0], a[1] + ((b[1] - a[1]) * (r[0] - a[0])) / (b[0] - a[0])] },
    { inside: (p) => p[0] <= r[2], cut: (a, b) => [r[2], a[1] + ((b[1] - a[1]) * (r[2] - a[0])) / (b[0] - a[0])] },
    { inside: (p) => p[1] >= r[1], cut: (a, b) => [a[0] + ((b[0] - a[0]) * (r[1] - a[1])) / (b[1] - a[1]), r[1]] },
    { inside: (p) => p[1] <= r[3], cut: (a, b) => [a[0] + ((b[0] - a[0]) * (r[3] - a[1])) / (b[1] - a[1]), r[3]] },
  ];
  for (const e of edges) {
    const input = out;
    out = [];
    for (let i = 0; i < input.length; i++) {
      const cur = input[i]!, prev = input[(i + input.length - 1) % input.length]!;
      if (e.inside(cur)) { if (!e.inside(prev)) out.push(e.cut(prev, cur)); out.push(cur); } else if (e.inside(prev)) out.push(e.cut(prev, cur));
    }
    if (!out.length) return [];
  }
  return out;
}

/** One outline as an SVG element: a circle, a rectangle or a polygon. `ox`, `oy` is the origin, `h` the height of the view (the y axis points down). */
function shape(poly: P[], eps: number, canBeCircle: boolean, attrs: string): string {
  if (poly.length < 3) return '';
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of poly) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
  const w = x1 - x0, h = y1 - y0;
  if (w < 1e-6 || h < 1e-6) return '';
  if (canBeCircle && poly.length >= 10 && Math.abs(w - h) <= 0.04 * Math.max(w, h)) {
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, r = (w + h) / 4;
    if (poly.every((p) => Math.abs(Math.hypot(p[0] - cx, p[1] - cy) - r) <= 0.05 * r)) return `<circle ${attrs}cx='${fmt(cx)}' cy='${fmt(cy)}' r='${fmt(r)}'/>`;
  }
  if (area(poly) >= 0.97 * w * h) return `<rect ${attrs}x='${fmt(x0)}' y='${fmt(y0)}' width='${fmt(w)}' height='${fmt(h)}'/>`;
  const s = simplifyPolygon(poly, eps);
  return `<polygon ${attrs}points='${s.map((p) => `${fmt(p[0])},${fmt(p[1])}`).join(' ')}'/>`;
}

/** The projected hull of a mesh in the two views. Points are in the IFC frame relative to `origin` (min corner of the frame), y of each view points down. */
function viewsOf(mesh: GeoMesh, origin: [number, number, number], top: [number, number, number], along: 'x' | 'y'): { plan: P[]; elev: P[] } {
  const a = mesh.position;
  const n = Math.floor(a.length / 3);
  const plan: P[] = [];
  const elev: P[] = [];
  const step = n > 40000 ? Math.ceil(n / 40000) : 1;
  for (let i = 0; i < n; i += step) {
    const [X, Y, Z] = toIfc(a[i * 3]!, a[i * 3 + 1]!, a[i * 3 + 2]!);
    const x = X - origin[0], y = Y - origin[1], z = Z - origin[2];
    plan.push([x, top[1] - y]);
    elev.push([along === 'x' ? x : y, top[2] - z]);
  }
  return { plan: convexHull(plan), elev: convexHull(elev) };
}

/**
 * Build the markup of an element. Deterministic: the same model, element and settings give the same text. The budget is kept by dropping the
 * farthest neighbours first and then by simplifying harder.
 */
export function buildGeometry(src: GeoSource, id: number, s: GeometrySettings): GeometrySet {
  const b = src.bounds(id);
  const mesh = src.mesh(id);
  if (!b || !mesh || b[3] < b[0]) throw new Error('The element has no geometry, so there is nothing to describe.');
  const budget = s.budget ?? GEOMETRY_BUDGET_TOKENS;
  const info = src.info(id);
  const eb = boundsIfc(b);
  const size: [number, number, number] = [eb[3] - eb[0], eb[4] - eb[1], eb[5] - eb[2]];
  const along: 'x' | 'y' = size[0] >= size[1] ? 'x' : 'y';
  const biggest = Math.max(...size, 0.05);
  const box = s.context ? contextBox(b, s.margin) : null;
  const near = box ? contextIds(src, id, box).filter((n) => {
    const nb = src.bounds(n);
    return nb && Math.max(nb[3] - nb[0], nb[4] - nb[1], nb[5] - nb[2]) >= TINY_SHARE * Math.max(box[3] - box[0], box[4] - box[1], box[5] - box[2]);
  }) : [];

  const attrs = (i: GeoInfo): string => `data-class='${i.ifcClass}'${i.tag ? ` data-tag='${i.tag.replace(/'/g, '')}'` : ''}`;
  const build = (cap: number, epsScale: number): { views: Array<{ name: string; svg: string }>; drawn: number } => {
    const out: Array<{ name: string; svg: string }> = [];
    const drawn = Math.min(cap, near.length);
    const eps = Math.max(0.01, 0.02 * biggest) * epsScale;
    // isolated: origin at the element's min corner
    const iso = viewsOf(mesh, [eb[0], eb[1], eb[2]], size, along);
    const horiz = along === 'x' ? size[0] : size[1];
    const head = `data-class='${info.ifcClass}'${info.predefined ? ` data-type='${info.predefined}'` : ''} data-size='${fmt(size[0])}x${fmt(size[1])}x${fmt(size[2])}'`;
    out.push({ name: 'plan', svg: `<svg id='plan' ${head} viewBox='0 0 ${fmt(size[0])} ${fmt(size[1])}'>${shape(iso.plan, eps, true, '')}</svg>` });
    out.push({ name: 'elevation', svg: `<svg id='elev' viewBox='0 0 ${fmt(horiz)} ${fmt(size[2])}'>${shape(iso.elev, eps, true, '')}</svg>` });
    if (box) {
      const bi = boundsIfc(box);
      const bsize: [number, number, number] = [bi[3] - bi[0], bi[4] - bi[1], bi[5] - bi[2]];
      const bhoriz = along === 'x' ? bsize[0] : bsize[1];
      const origin: [number, number, number] = [bi[0], bi[1], bi[2]];
      const rectPlan: [number, number, number, number] = [0, 0, bsize[0], bsize[1]];
      const rectElev: [number, number, number, number] = [0, 0, bhoriz, bsize[2]];
      const one = (view: 'plan' | 'elev'): string => {
        const rect = view === 'plan' ? rectPlan : rectElev;
        let body = '';
        for (const n of near.slice(0, drawn)) {
          const m = src.mesh(n);
          if (!m) continue;
          const v = viewsOf(m, origin, bsize, along)[view];
          const clipped = clipPolygon(v, rect);
          if (clipped.length < 3) continue;
          const el = shape(clipped, eps, clipped.length === v.length, '');
          if (el) body += `<g ${attrs(src.info(n))}>${el}</g>`;
        }
        const tv = viewsOf(mesh, origin, bsize, along)[view];
        const t = shape(clipPolygon(tv, rect), eps, true, '');
        body += `<g id='target'>${t}</g>`;
        return view === 'plan' ? `<svg id='ctx-plan' viewBox='0 0 ${fmt(bsize[0])} ${fmt(bsize[1])}'>${body}</svg>` : `<svg id='ctx-elev' viewBox='0 0 ${fmt(bhoriz)} ${fmt(bsize[2])}'>${body}</svg>`;
      };
      out.push({ name: 'context plan', svg: one('plan') });
      out.push({ name: 'context elevation', svg: one('elev') });
    }
    return { views: out, drawn };
  };

  const legend = box
    ? 'Geometry as SVG, metres, plan then elevation; first the element alone (origin at its bounding box corner), then the element in its bounding box with nearby elements (origin at the box corner); target element id=target.'
    : 'Geometry as SVG, metres, plan then elevation; the element alone (origin at its bounding box corner).';
  let cap = Math.min(MAX_GEOMETRY_NEIGHBOURS, near.length);
  let epsScale = 1;
  let r = build(cap, epsScale);
  const total = (): number => estimateTokens(legend) + estimateTokens(r.views.map((v) => v.svg).join('\n'));
  while (total() > budget && (cap > 0 || epsScale < 8)) {
    if (cap > 0) cap = Math.max(0, cap - 5);
    else epsScale *= 2;
    r = build(cap, epsScale);
  }
  const svg = r.views.map((v) => v.svg).join('\n');
  return { id, legend, svg, tokens: total(), neighbours: r.drawn, views: r.views };
}
