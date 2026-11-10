// Pictures of an element for a decision model that reads images (d3-edge on its endpoint or in the browser with a vision graph; optionally Jev).
//
// Two pictures, as the person asked:
//   isolated  the element alone, fitted, axonometric (plus an optional plan), on a neutral background, with a scale bar. Style `render` is shaded
//             with edges; style `vector` is a simplified line drawing: silhouette and feature edges, black on white, no shading.
//   context   the element highlighted inside its own bounding box, expanded by a margin (25 % of its largest side, at least 0.5 m), with every
//             other element that touches that box drawn ghosted and grey and CLIPPED to the box (clipping planes of the off-screen render), and
//             the box outline drawn. The picture shows exactly the surroundings of the element within its box, and nothing beyond it.
//
// The maths (the box, which elements are inside it, the clipping planes, the frame, the silhouette edges, the note that tells the model what
// the pictures are) is pure and tested in Node. The drawing uses three.js on an off-screen canvas of its own, never the viewer's canvas.
// A picture is a data URL that goes into the request and into the drawer preview, and nowhere else: not into params, share links, saved
// views, presets or packed pages.

import {
  AmbientLight, BufferGeometry, Color, DirectionalLight, EdgesGeometry, LineBasicMaterial, LineSegments, Mesh, MeshBasicMaterial,
  MeshLambertMaterial, OrthographicCamera, Plane, Scene, Vector2, Vector3, WebGLRenderer,
} from 'three';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import type { ImageMode, ImageStyle } from './providers/d3Config';

/** Most elements drawn ghosted in the context picture (the nearest to the element first). */
export const MAX_CONTEXT = 120;
/** Extra room around the drawn box in the frame, as a share of its largest extent in the view. */
export const FRAME_MARGIN = 0.12;
/** The context box grows by at least this many metres on each side. */
export const MIN_MARGIN_M = 0.5;
/** A neighbour with more triangles than this is drawn with its crease edges only (no silhouette search), so a heavy model stays quick. */
export const SILHOUETTE_MAX_TRIANGLES = 30_000;

export interface ThumbSettings {
  mode: Exclude<ImageMode, 'off'>;
  style: ImageStyle;
  /** Add a plan view of the element alone to the isolated picture. */
  plan: boolean;
  /** Pixels, square. */
  size: number;
  /** Context box margin in percent of the largest side of the element (at least MIN_MARGIN_M). */
  margin: number;
}

export type Bounds6 = readonly [number, number, number, number, number, number];

export interface ThumbSource {
  /** Bounds [minx, miny, minz, maxx, maxy, maxz] of an element, or null when it has no geometry. */
  bounds(id: number): Bounds6 | null;
  /** Triangles of an element in world space (the caller disposes it), or null. */
  mesh(id: number): BufferGeometry | null;
  /** Every element id that may be in the box. */
  ids(): Iterable<number>;
}

export type PictureKind = 'isolated' | 'plan' | 'context';

export interface ThumbView {
  name: PictureKind;
  /** From the element towards the camera (unit). */
  dir: [number, number, number];
  up: [number, number, number];
}

const AXO: ThumbView = { name: 'isolated', dir: [0.577, 0.577, 0.577], up: [0, 1, 0] };
const PLAN: ThumbView = { name: 'plan', dir: [0, 1, 0], up: [0, 0, -1] };
const CONTEXT: ThumbView = { name: 'context', dir: AXO.dir, up: AXO.up };

/** The pictures of a set, in the order the model gets them: the isolated one first, its plan next, the context last. */
export function pictureKinds(s: Pick<ThumbSettings, 'mode' | 'plan'>): ThumbView[] {
  const out: ThumbView[] = [];
  if (s.mode === 'isolated' || s.mode === 'both') {
    out.push(AXO);
    if (s.plan) out.push(PLAN);
  }
  if (s.mode === 'context' || s.mode === 'both') out.push(CONTEXT);
  return out;
}

const emptyBounds = (b: Bounds6 | null): boolean => !b || b[3] < b[0] || b[4] < b[1] || b[5] < b[2] || b.some((x) => !Number.isFinite(x));

const size3 = (b: Bounds6): [number, number, number] => [b[3] - b[0], b[4] - b[1], b[5] - b[2]];

/** The margin of the context box: `percent` of the largest side of the element, at least 0.5 m. */
export const contextMargin = (b: Bounds6, percent: number): number => Math.max(MIN_MARGIN_M, (percent / 100) * Math.max(...size3(b)));

/** The bounding box of the element grown by the margin on every side: the box of the context picture. */
export function contextBox(b: Bounds6, percent: number): Bounds6 {
  const m = contextMargin(b, percent);
  return [b[0] - m, b[1] - m, b[2] - m, b[3] + m, b[4] + m, b[5] + m];
}

const gap = (a: Bounds6, b: Bounds6): number => {
  // Distance between two boxes: 0 when they overlap.
  const dx = Math.max(0, a[0] - b[3], b[0] - a[3]);
  const dy = Math.max(0, a[1] - b[4], b[1] - a[4]);
  const dz = Math.max(0, a[2] - b[5], b[2] - a[5]);
  return Math.hypot(dx, dy, dz);
};

/**
 * The elements whose bounds intersect `box` (touching counts), nearest to the element first (by box gap to the element, then by distance of
 * the centres), at most `cap`. The element itself and elements without geometry are left out.
 */
export function contextIds(src: Pick<ThumbSource, 'bounds' | 'ids'>, id: number, box: Bounds6, cap = MAX_CONTEXT): number[] {
  const me = src.bounds(id);
  if (emptyBounds(me)) return [];
  const c = [(me![0] + me![3]) / 2, (me![1] + me![4]) / 2, (me![2] + me![5]) / 2];
  const hits: Array<{ id: number; gap: number; d: number }> = [];
  for (const other of src.ids()) {
    if (other === id) continue;
    const b = src.bounds(other);
    if (emptyBounds(b)) continue;
    if (gap(box, b!) > 0) continue;
    const d = Math.hypot((b![0] + b![3]) / 2 - c[0]!, (b![1] + b![4]) / 2 - c[1]!, (b![2] + b![5]) / 2 - c[2]!);
    hits.push({ id: other, gap: gap(me!, b!), d });
  }
  hits.sort((a, b) => a.gap - b.gap || a.d - b.d || a.id - b.id);
  return hits.slice(0, cap).map((h) => h.id);
}

/** The 6 clipping planes of a box as [nx, ny, nz, constant]: a point is inside when n . p + constant >= 0 for all six (three.js Plane). */
export function boxPlanes(b: Bounds6): Array<[number, number, number, number]> {
  return [
    [1, 0, 0, -b[0]], [-1, 0, 0, b[3]],
    [0, 1, 0, -b[1]], [0, -1, 0, b[4]],
    [0, 0, 1, -b[2]], [0, 0, -1, b[5]],
  ];
}

export interface Frame {
  /** Half width of the orthographic frustum (the picture is square), in metres. */
  half: number;
  /** Centre of the frame in the view plane, in metres along the view's right and up axes. */
  cx: number;
  cy: number;
}

const cross = (a: readonly number[], b: readonly number[]): [number, number, number] => [a[1]! * b[2]! - a[2]! * b[1]!, a[2]! * b[0]! - a[0]! * b[2]!, a[0]! * b[1]! - a[1]! * b[0]!];
const norm = (a: readonly number[]): [number, number, number] => {
  const l = Math.hypot(a[0]!, a[1]!, a[2]!) || 1;
  return [a[0]! / l, a[1]! / l, a[2]! / l];
};
const dot = (a: readonly number[], b: readonly number[]): number => a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;

/** The frame of one view: the 8 corners of `b` projected on the view's right and up axes, plus the margin. */
export function fitFrame(b: Bounds6, v: ThumbView): Frame {
  const right = norm(cross(v.up, v.dir));
  const up = norm(cross(v.dir, right));
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const x of [b[0], b[3]]) for (const y of [b[1], b[4]]) for (const z of [b[2], b[5]]) {
    const p = [x, y, z];
    const px = dot(p, right);
    const py = dot(p, up);
    x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
  }
  const ext = Math.max(x1 - x0, y1 - y0, 0.05);
  return { half: (ext / 2) * (1 + 2 * FRAME_MARGIN), cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 };
}

/** A round length for the scale bar: 1, 2 or 5 times a power of ten, at most about a third of the picture width. */
export function scaleBarMetres(widthMetres: number): number {
  const target = widthMetres / 3;
  if (!(target > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(target)));
  for (const k of [5, 2, 1]) if (k * p <= target) return k * p;
  return p;
}

export const formatMetres = (m: number): string => (m >= 1 ? `${+m.toFixed(2)} m` : m >= 0.01 ? `${Math.round(m * 100)} cm` : `${Math.round(m * 1000)} mm`);

/** Hash of everything that changes a picture: the settings (the cache identity of a decision includes it). */
export const thumbKey = (s: ThumbSettings): string => `${s.mode}|${s.style}|${s.plan ? 'plan' : 'noplan'}|${s.size}|${s.margin}`;

/**
 * The note that tells the model what the pictures are, one sentence per picture in the order they are sent. The System One prompt puts the
 * pictures before the text of the request, so the note goes into the state ("pictures"). Short plain sentences.
 */
export function pictureNote(kinds: readonly PictureKind[], style: ImageStyle): string {
  const draw = style === 'vector' ? 'a line drawing' : 'a render';
  return kinds
    .map((k, i) => {
      const n = `Picture ${i + 1}:`;
      if (k === 'isolated') return `${n} the element alone, ${draw}, axonometric, with a scale bar.`;
      if (k === 'plan') return `${n} the element alone, ${draw}, seen from above.`;
      return style === 'vector'
        ? `${n} line drawing of the element (black) in its bounding box with nearby elements in grey.`
        : `${n} the element (orange) in its bounding box with nearby elements in grey.`;
    })
    .join(' ');
}

// ---------------------------------------------------------------- silhouette edges (the line drawing)

/**
 * Silhouette edges of a triangle mesh seen along `dir` (orthographic, from the element towards the camera): the edges between a face that looks at
 * the camera and one that looks away, and the edges that have a single face (open boundary). Vertices are matched by position (rounded to 1e-4).
 * Returns segments, 6 numbers each. Crease edges are not here: EdgesGeometry gives those.
 */
export function silhouetteSegments(position: ArrayLike<number>, index: ArrayLike<number> | null, dir: readonly [number, number, number]): Float32Array {
  const nv = Math.floor(position.length / 3);
  const tri = index ? Math.floor(index.length / 3) : Math.floor(nv / 3);
  const at = (t: number, k: number): number => (index ? index[t * 3 + k]! : t * 3 + k);
  // weld
  const weld = new Int32Array(nv);
  const seen = new Map<string, number>();
  for (let i = 0; i < nv; i++) {
    const key = `${Math.round(position[i * 3]! * 1e4)},${Math.round(position[i * 3 + 1]! * 1e4)},${Math.round(position[i * 3 + 2]! * 1e4)}`;
    const hit = seen.get(key);
    if (hit === undefined) { seen.set(key, i); weld[i] = i; } else weld[i] = hit;
  }
  const edges = new Map<number, { a: number; b: number; side: number; n: number; sil: boolean }>();
  const unit = nv + 1;
  for (let t = 0; t < tri; t++) {
    const i0 = at(t, 0), i1 = at(t, 1), i2 = at(t, 2);
    const ax = position[i0 * 3]!, ay = position[i0 * 3 + 1]!, az = position[i0 * 3 + 2]!;
    const ux = position[i1 * 3]! - ax, uy = position[i1 * 3 + 1]! - ay, uz = position[i1 * 3 + 2]! - az;
    const vx = position[i2 * 3]! - ax, vy = position[i2 * 3 + 1]! - ay, vz = position[i2 * 3 + 2]! - az;
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const len = Math.hypot(nx, ny, nz);
    if (!(len > 1e-12)) continue; // a degenerate triangle has no side
    const side = (nx * dir[0] + ny * dir[1] + nz * dir[2]) / len > 1e-6 ? 1 : -1;
    const w = [weld[i0]!, weld[i1]!, weld[i2]!];
    for (let k = 0; k < 3; k++) {
      const p = w[k]!, q = w[(k + 1) % 3]!;
      if (p === q) continue;
      const a = Math.min(p, q), b = Math.max(p, q);
      const key = a * unit + b;
      const e = edges.get(key);
      if (!e) edges.set(key, { a, b, side, n: 1, sil: false });
      else { e.n++; if (e.side !== side) e.sil = true; }
    }
  }
  const out: number[] = [];
  for (const e of edges.values()) {
    if (!(e.sil || e.n === 1)) continue;
    out.push(position[e.a * 3]!, position[e.a * 3 + 1]!, position[e.a * 3 + 2]!, position[e.b * 3]!, position[e.b * 3 + 1]!, position[e.b * 3 + 2]!);
  }
  return Float32Array.from(out);
}

// ---------------------------------------------------------------- drawing

export interface Thumb {
  view: PictureKind;
  /** What the picture shows, for the drawer. */
  label: string;
  /** `data:image/webp;base64,...` for a render (PNG when the browser cannot encode WebP), PNG for a line drawing (crisp lines). */
  dataUrl: string;
  width: number;
  height: number;
  /** Length of the scale bar in metres. */
  scaleBarM: number;
  /** Ids of the other elements that were drawn (context pictures). */
  neighbours: number[];
}

export interface ThumbSet {
  id: number;
  settings: ThumbSettings;
  thumbs: Thumb[];
  neighbours: number[];
  /** The note for the state (what each picture is). */
  note: string;
}

const ELEMENT_COLOUR = 0xf0802a;
const NEIGHBOUR_COLOUR = 0x8f98a3;
const BACKGROUND = 0xeef1f5;
const BOX_COLOUR = 0x2f6fd0;

interface Gl {
  renderer: WebGLRenderer;
  canvas: HTMLCanvasElement;
  size: number;
}
let gl: Gl | null = null;

function glFor(size: number): Gl {
  if (gl && gl.size === size) return gl;
  gl?.renderer.dispose();
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const renderer = new WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(size, size, false);
  renderer.autoClear = false;
  renderer.localClippingEnabled = true;
  gl = { renderer, canvas, size };
  return gl;
}

/** Free the off-screen renderer (when the drawer closes or a new model loads). */
export function disposeThumbRenderer(): void {
  gl?.renderer.dispose();
  gl = null;
}

function encode(canvas: HTMLCanvasElement, lossless: boolean): string {
  if (!lossless) {
    const webp = canvas.toDataURL('image/webp', 0.85);
    if (webp.startsWith('data:image/webp')) return webp;
  }
  return canvas.toDataURL('image/png');
}

function drawLabel(src: HTMLCanvasElement, text: string, scaleBarM: number, half: number, size: number, background: string): HTMLCanvasElement {
  const out = document.createElement('canvas');
  out.width = size;
  out.height = size;
  const c = out.getContext('2d')!;
  c.fillStyle = background;
  c.fillRect(0, 0, size, size);
  c.drawImage(src, 0, 0);
  const px = (scaleBarM / (2 * half)) * size;
  const y = size - 14;
  c.fillStyle = '#1b2430';
  c.fillRect(10, y - 1, px, 3);
  c.fillRect(10, y - 5, 2, 11);
  c.fillRect(10 + px - 2, y - 5, 2, 11);
  c.font = `${Math.max(10, Math.round(size / 32))}px sans-serif`;
  c.textBaseline = 'bottom';
  c.fillText(formatMetres(scaleBarM), 10, y - 7);
  c.textBaseline = 'top';
  c.fillText(text, 10, 8);
  return out;
}

const hex = (n: number): string => `#${n.toString(16).padStart(6, '0')}`;

/** Draw the pictures of one element. Throws when the element has no geometry or WebGL is not available. */
export function renderThumbs(src: ThumbSource, id: number, s: ThumbSettings): ThumbSet {
  const b = src.bounds(id);
  if (emptyBounds(b)) throw new Error('The element has no geometry, so there is nothing to draw.');
  const kinds = pictureKinds(s);
  const vector = s.style === 'vector';
  const bg = vector ? 0xffffff : BACKGROUND;
  const { renderer, canvas } = glFor(s.size);
  renderer.setClearColor(new Color(bg), 1);
  const box = contextBox(b!, s.margin);
  const others = kinds.some((k) => k.name === 'context') ? contextIds(src, id, box) : [];
  const planes = boxPlanes(box).map((p) => new Plane(new Vector3(p[0], p[1], p[2]), p[3]));
  const disposables: Array<{ dispose(): void }> = [];
  const materials: Array<{ dispose(): void }> = [];
  const geom = new Map<number, BufferGeometry | null>();
  const meshOf = (gid: number): BufferGeometry | null => {
    if (geom.has(gid)) return geom.get(gid) ?? null;
    const g = src.mesh(gid);
    if (g) disposables.push(g);
    geom.set(gid, g);
    return g;
  };
  const edgeCache = new Map<number, Float32Array>();
  const creases = (gid: number, g: BufferGeometry): Float32Array => {
    let e = edgeCache.get(gid);
    if (!e) {
      const eg = new EdgesGeometry(g, 30);
      e = Float32Array.from(eg.getAttribute('position').array as ArrayLike<number>);
      eg.dispose();
      edgeCache.set(gid, e);
    }
    return e;
  };
  const triangles = (g: BufferGeometry): number => (g.index ? g.index.count : g.getAttribute('position').count) / 3;
  const centreOf = (bb: Bounds6): Vector3 => new Vector3((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2);
  const thumbs: Thumb[] = [];
  try {
    for (const v of kinds) {
      const context = v.name === 'context';
      const target = context ? box : b!;
      const f = fitFrame(target, v);
      const scene = new Scene();
      const back = new Scene(); // the ghosts of the context: drawn first, the element is drawn over them with a fresh depth buffer
      const lights = (sc: Scene): DirectionalLight | null => {
        if (vector) return null;
        sc.add(new AmbientLight(0xffffff, 1.5));
        const sun = new DirectionalLight(0xffffff, 0.8);
        sc.add(sun);
        sc.add(sun.target);
        return sun;
      };
      const suns = [lights(back), lights(scene)];
      const res = new Vector2(s.size, s.size);
      const clip = context ? planes : [];

      const lineSet = (positions: Float32Array, colour: number, width: number, sc: Scene, clipped: boolean): void => {
        if (!positions.length) return;
        const lg = new LineSegmentsGeometry();
        lg.setPositions(positions);
        const lm = new LineMaterial({ color: colour, linewidth: width, worldUnits: false, resolution: res });
        if (clipped && clip.length) lm.clippingPlanes = clip;
        materials.push(lm);
        disposables.push(lg);
        const ls = new LineSegments2(lg, lm);
        ls.frustumCulled = false;
        sc.add(ls);
      };
      const addElement = (gid: number, sc: Scene, ghost: boolean): void => {
        const g = meshOf(gid);
        if (!g) return;
        if (vector) {
          // A white fill hides the lines behind the part. Nothing else.
          const fill = new MeshBasicMaterial({ color: 0xffffff, polygonOffset: true, polygonOffsetFactor: 1.5, polygonOffsetUnits: 1.5 });
          if (ghost && clip.length) fill.clippingPlanes = clip;
          materials.push(fill);
          sc.add(new Mesh(g, fill));
          const cr = creases(gid, g);
          const sil = !ghost || triangles(g) <= SILHOUETTE_MAX_TRIANGLES
            ? silhouetteSegments(g.getAttribute('position').array as ArrayLike<number>, g.index ? (g.index.array as ArrayLike<number>) : null, v.dir)
            : new Float32Array(0);
          const all = new Float32Array(cr.length + sil.length);
          all.set(cr);
          all.set(sil, cr.length);
          lineSet(all, ghost ? 0x8a929c : 0x000000, ghost ? 1.2 : 2, sc, ghost);
          return;
        }
        const mat = new MeshLambertMaterial(ghost
          ? { color: NEIGHBOUR_COLOUR, flatShading: true, transparent: true, opacity: 0.35, depthWrite: false }
          : { color: ELEMENT_COLOUR, flatShading: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
        if (ghost && clip.length) mat.clippingPlanes = clip;
        materials.push(mat);
        sc.add(new Mesh(g, mat));
        const eg = new EdgesGeometry(g, 30);
        disposables.push(eg);
        const lm = new LineBasicMaterial(ghost ? { color: 0x6b7480, transparent: true, opacity: 0.4 } : { color: 0x3b1d08 });
        if (ghost && clip.length) lm.clippingPlanes = clip;
        materials.push(lm);
        sc.add(new LineSegments(eg, lm));
      };
      const picked: number[] = [];
      if (context) {
        for (const n of others) if (meshOf(n)) { addElement(n, back, true); picked.push(n); }
        // The outline of the box: 12 edges.
        const [x0, y0, z0, x1, y1, z1] = box;
        const c = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]];
        const e = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
        const seg = new Float32Array(e.length * 6);
        e.forEach((pair, k) => { seg.set(c[pair[0]!]!, k * 6); seg.set(c[pair[1]!]!, k * 6 + 3); });
        lineSet(seg, BOX_COLOUR, 2, scene, false);
      }
      addElement(id, scene, false);

      const right = new Vector3(...norm(cross(v.up, v.dir)));
      const up = new Vector3(...norm(cross(v.dir, right.toArray())));
      const centre = centreOf(target);
      // The frame centre is in view-plane metres: move the look-at point from the centre of the framed box to it.
      const cDot = new Vector3(dot(centre.toArray(), right.toArray()), dot(centre.toArray(), up.toArray()), 0);
      const look = centre.clone().addScaledVector(right, f.cx - cDot.x).addScaledVector(up, f.cy - cDot.y);
      const dist = Math.max(10, f.half * 20);
      const cam = new OrthographicCamera(-f.half, f.half, f.half, -f.half, 0.01, dist * 4);
      cam.up.set(...v.up);
      cam.position.copy(look).addScaledVector(new Vector3(...v.dir), dist);
      cam.lookAt(look);
      cam.updateMatrixWorld();
      for (const sun of suns) {
        if (!sun) continue;
        sun.position.copy(look).addScaledVector(new Vector3(...norm([v.dir[0] + 0.3, v.dir[1] + 0.6, v.dir[2] + 0.2])), dist);
        sun.target.position.copy(look);
      }
      renderer.clear(true, true, true);
      if (context) renderer.render(back, cam);
      renderer.clearDepth();
      renderer.render(scene, cam);
      const bar = scaleBarMetres(2 * f.half);
      const text = v.name === 'plan' ? 'element, plan' : context ? 'element in its box' : 'element alone';
      const labelled = drawLabel(canvas, text, bar, f.half, s.size, hex(bg));
      thumbs.push({ view: v.name, label: text, dataUrl: encode(labelled, vector), width: s.size, height: s.size, scaleBarM: bar, neighbours: picked });
      scene.clear();
      back.clear();
    }
  } finally {
    for (const g of disposables) g.dispose();
    for (const m of materials) m.dispose();
  }
  const all = [...new Set(thumbs.flatMap((t) => t.neighbours))];
  return { id, settings: s, thumbs, neighbours: all, note: pictureNote(thumbs.map((t) => t.view), s.style) };
}
