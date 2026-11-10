// Thumbnails of an element for a decision model that reads images (d3-edge on its endpoint, optionally Jev).
//
// What is drawn: the element, solid and highlighted; its neighbours, ghosted and grey, for context (the elements whose bounds lie within
// a margin of the element's bounds, at most 40, nearest first); nothing else. The view is orthographic and fitted to the element plus
// a margin, on a neutral background, with a scale bar. One to three views: plan, front elevation, axonometric.
//
// The maths (which neighbours, which frame, how long the scale bar is) is pure and tested in Node. The drawing uses three.js on an
// off-screen canvas of its own, never the viewer's canvas. A picture is a data URL that goes into the request and into the drawer
// preview, and nowhere else: not into params, share links, saved views, presets or packed pages.

import {
  AmbientLight, Box3, BufferGeometry, Color, DirectionalLight, EdgesGeometry, LineBasicMaterial, LineSegments, Mesh, MeshLambertMaterial, OrthographicCamera, Scene, Vector3, WebGLRenderer,
} from 'three';
import type { ImageMode } from './providers/d3Config';

export const MAX_NEIGHBOURS = 40;
/** Extra room around the element in the frame, as a share of its largest extent in the view. */
export const FRAME_MARGIN = 0.18;

export interface ThumbSettings {
  mode: Exclude<ImageMode, 'off'>;
  views: number;
  size: number;
}

export type Bounds6 = readonly [number, number, number, number, number, number];

export interface ThumbSource {
  /** Bounds [minx, miny, minz, maxx, maxy, maxz] of an element, or null when it has no geometry. */
  bounds(id: number): Bounds6 | null;
  /** Triangles of an element in world space (the caller disposes it), or null. */
  mesh(id: number): BufferGeometry | null;
  /** Every element id that may be a neighbour. */
  ids(): Iterable<number>;
}

export interface ThumbView {
  name: 'plan' | 'front' | 'axonometric';
  /** From the element towards the camera (unit). */
  dir: [number, number, number];
  up: [number, number, number];
}

const VIEWS: readonly ThumbView[] = [
  { name: 'plan', dir: [0, 1, 0], up: [0, 0, -1] },
  { name: 'front', dir: [0, 0, 1], up: [0, 1, 0] },
  { name: 'axonometric', dir: [0.577, 0.577, 0.577], up: [0, 1, 0] },
];
/** The views of a set: 1 plan, 2 plan and front, 3 plan, front and axonometric. */
export const viewsOf = (n: number): ThumbView[] => VIEWS.slice(0, Math.max(1, Math.min(3, Math.round(n))));

const emptyBounds = (b: Bounds6 | null): boolean => !b || b[3] < b[0] || b[4] < b[1] || b[5] < b[2] || b.some((x) => !Number.isFinite(x));

/** How far around the element a neighbour may lie: half its largest dimension, at least 0.5 m. */
export const neighbourMargin = (b: Bounds6): number => Math.max(0.5, 0.5 * Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]));

const gap = (a: Bounds6, b: Bounds6): number => {
  // Distance between two boxes: 0 when they overlap.
  const dx = Math.max(0, a[0] - b[3], b[0] - a[3]);
  const dy = Math.max(0, a[1] - b[4], b[1] - a[4]);
  const dz = Math.max(0, a[2] - b[5], b[2] - a[5]);
  return Math.hypot(dx, dy, dz);
};

/**
 * The elements whose bounds lie within `margin` of the bounds of `id`, nearest first (by box gap, then by distance of the centres), at most
 * `cap`. The element itself and elements without geometry are left out.
 */
export function neighbourIds(src: Pick<ThumbSource, 'bounds' | 'ids'>, id: number, o: { margin?: number; cap?: number } = {}): number[] {
  const me = src.bounds(id);
  if (emptyBounds(me)) return [];
  const m = o.margin ?? neighbourMargin(me!);
  const cap = o.cap ?? MAX_NEIGHBOURS;
  const c = [(me![0] + me![3]) / 2, (me![1] + me![4]) / 2, (me![2] + me![5]) / 2];
  const hits: Array<{ id: number; gap: number; d: number }> = [];
  for (const other of src.ids()) {
    if (other === id) continue;
    const b = src.bounds(other);
    if (emptyBounds(b)) continue;
    const g = gap(me!, b!);
    if (g > m) continue;
    const d = Math.hypot((b![0] + b![3]) / 2 - c[0]!, (b![1] + b![4]) / 2 - c[1]!, (b![2] + b![5]) / 2 - c[2]!);
    hits.push({ id: other, gap: g, d });
  }
  hits.sort((a, b) => a.gap - b.gap || a.d - b.d || a.id - b.id);
  return hits.slice(0, cap).map((h) => h.id);
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

/** The frame of one view: the 8 corners of the element bounds projected on the view's right and up axes, plus the margin. */
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
export const thumbKey = (s: ThumbSettings): string => `${s.mode}|${s.views}|${s.size}`;

// ---------------------------------------------------------------- drawing

export interface Thumb {
  view: ThumbView['name'];
  /** `data:image/webp;base64,...` (PNG when the browser cannot encode WebP). */
  dataUrl: string;
  width: number;
  height: number;
  /** Length of the scale bar in metres. */
  scaleBarM: number;
  /** Ids of the neighbours that were drawn. */
  neighbours: number[];
}

export interface ThumbSet {
  id: number;
  settings: ThumbSettings;
  thumbs: Thumb[];
  neighbours: number[];
}

const ELEMENT_COLOUR = 0xf0802a;
const NEIGHBOUR_COLOUR = 0x8f98a3;
const BACKGROUND = 0xeef1f5;

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
  renderer.setClearColor(new Color(BACKGROUND), 1);
  gl = { renderer, canvas, size };
  return gl;
}

/** Free the off-screen renderer (when the drawer closes or a new model loads). */
export function disposeThumbRenderer(): void {
  gl?.renderer.dispose();
  gl = null;
}

function encode(canvas: HTMLCanvasElement): string {
  const webp = canvas.toDataURL('image/webp', 0.85);
  return webp.startsWith('data:image/webp') ? webp : canvas.toDataURL('image/png');
}

function drawLabel(src: HTMLCanvasElement, name: string, scaleBarM: number, half: number, size: number): HTMLCanvasElement {
  const out = document.createElement('canvas');
  out.width = size;
  out.height = size;
  const c = out.getContext('2d')!;
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
  c.fillText(name, 10, 8);
  return out;
}

/** Draw the thumbnails of one element. Throws when the element has no geometry or WebGL is not available. */
export function renderThumbs(src: ThumbSource, id: number, s: ThumbSettings): ThumbSet {
  const b = src.bounds(id);
  if (emptyBounds(b)) throw new Error('The element has no geometry, so there is nothing to draw.');
  const neighbours = s.mode === 'element+neighbours' ? neighbourIds(src, id) : [];
  const { renderer, canvas } = glFor(s.size);
  const disposables: BufferGeometry[] = [];
  const materials: Array<{ dispose(): void }> = [];
  const scene = new Scene();
  scene.add(new AmbientLight(0xffffff, 1.5));
  const sun = new DirectionalLight(0xffffff, 0.8);
  scene.add(sun);
  scene.add(sun.target);
  const add = (gid: number, solid: boolean): void => {
    const g = src.mesh(gid);
    if (!g) return;
    disposables.push(g);
    const mat = new MeshLambertMaterial(solid ? { color: ELEMENT_COLOUR, flatShading: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 } : { color: NEIGHBOUR_COLOUR, flatShading: true, transparent: true, opacity: 0.35, depthWrite: false });
    materials.push(mat);
    scene.add(new Mesh(g, mat));
    const eg = new EdgesGeometry(g, 30);
    disposables.push(eg);
    const lm = new LineBasicMaterial(solid ? { color: 0x3b1d08 } : { color: 0x6b7480, transparent: true, opacity: 0.4 });
    materials.push(lm);
    scene.add(new LineSegments(eg, lm));
  };
  for (const n of neighbours) add(n, false);
  add(id, true);
  const centre = new Vector3((b![0] + b![3]) / 2, (b![1] + b![4]) / 2, (b![2] + b![5]) / 2);
  const thumbs: Thumb[] = [];
  try {
    for (const v of viewsOf(s.views)) {
      const f = fitFrame(b!, v);
      const right = new Vector3(...norm(cross(v.up, v.dir)));
      const up = new Vector3(...norm(cross(v.dir, right.toArray())));
      // The frame centre is in view-plane metres: move the look-at point from the element centre to it.
      const cDot = new Vector3(dot(centre.toArray(), right.toArray()), dot(centre.toArray(), up.toArray()), 0);
      const target = centre.clone().addScaledVector(right, f.cx - cDot.x).addScaledVector(up, f.cy - cDot.y);
      const dist = Math.max(10, f.half * 20);
      const cam = new OrthographicCamera(-f.half, f.half, f.half, -f.half, 0.01, dist * 4);
      cam.up.set(...v.up);
      cam.position.copy(target).addScaledVector(new Vector3(...v.dir), dist);
      cam.lookAt(target);
      cam.updateMatrixWorld();
      sun.position.copy(target).addScaledVector(new Vector3(...norm([v.dir[0] + 0.3, v.dir[1] + 0.6, v.dir[2] + 0.2])), dist);
      sun.target.position.copy(target);
      renderer.render(scene, cam);
      const bar = scaleBarMetres(2 * f.half);
      const labelled = drawLabel(canvas, v.name, bar, f.half, s.size);
      thumbs.push({ view: v.name, dataUrl: encode(labelled), width: s.size, height: s.size, scaleBarM: bar, neighbours });
    }
  } finally {
    for (const g of disposables) g.dispose();
    for (const m of materials) m.dispose();
  }
  return { id, settings: s, thumbs, neighbours };
}

/** A box helper for tests and for callers that only have bounds. */
export const boundsBox = (b: Bounds6): Box3 => new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5]));
