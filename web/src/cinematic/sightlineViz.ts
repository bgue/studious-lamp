// Sightline visualisation: draw the Algorithm 2 sample rays (sample point -> camera) for a moment.
// The ray selection is pure (testable); SightlineViz owns the GPU objects and the fade.

import {
  BufferAttribute,
  BufferGeometry,
  Color,
  DoubleSide,
  LineSegments,
  Points,
  Ray,
  ShaderMaterial,
  Vector3,
} from 'three';
import type { Scene } from 'three';
import type { MergedGeometry } from '../model/merged';
import type { ElementId, GeometryProvider } from '../types';

export type RayStyle = 'lines' | 'dots' | 'both';
export type RayFilter = 'all' | 'blocked' | 'unblocked';

/** Length of an unblocked ray, metres. */
export const UNBLOCKED_LENGTH_M = 3;

export interface SightRay {
  /** Sample point on the focus surface. */
  from: Vector3;
  /** Unit direction toward the camera. */
  dir: Vector3;
  /** Distance from the sample point to the camera. */
  toCamera: number;
  blocked: boolean;
  /** Distance to the first occluder hit (null when unblocked or unknown). */
  hitDist: number | null;
}

/**
 * Filter by blocked state, then cap at `max` rays by an even stride over the filtered list (so the
 * kept rays are spread over all samples, not the first few).
 */
export function selectRays<T extends { blocked: boolean }>(rays: readonly T[], filter: RayFilter, max: number): T[] {
  const kept = filter === 'all' ? rays.slice() : rays.filter((r) => (filter === 'blocked' ? r.blocked : !r.blocked));
  const cap = Math.max(0, Math.floor(max));
  if (kept.length <= cap) return kept;
  if (cap === 0) return [];
  const out: T[] = [];
  for (let i = 0; i < cap; i++) out.push(kept[Math.floor(((i + 0.5) * kept.length) / cap)]!);
  return out;
}

/** Drawn length: up to the first occluder hit when known, else 3 m; never beyond the camera. */
export function rayLength(r: Pick<SightRay, 'blocked' | 'hitDist' | 'toCamera'>): number {
  const want = r.blocked && r.hitDist !== null ? r.hitDist : UNBLOCKED_LENGTH_M;
  return Math.max(0, Math.min(want, r.toCamera));
}

export interface RayQueries {
  /** True when the ray crosses an occluder (GeometryProvider.raycastAll non-empty). */
  blocked(origin: Vector3, dir: Vector3, dist: number): boolean;
  /** Distance to the nearest occluder hit, null for none. */
  firstHit(origin: Vector3, dir: Vector3, dist: number): number | null;
}

/**
 * Rays from every sample point to `camera`, classified with `q`. The first-hit distance is only
 * computed for the rays that survive the filter and the cap.
 */
export function buildSightRays(
  samples: readonly Vector3[],
  camera: Vector3,
  q: RayQueries,
  filter: RayFilter,
  max: number,
): SightRay[] {
  const rays: SightRay[] = [];
  for (const p of samples) {
    const dir = new Vector3().subVectors(camera, p);
    const toCamera = dir.length();
    if (toCamera < 1e-9) continue;
    dir.divideScalar(toCamera);
    rays.push({ from: p, dir, toCamera, blocked: q.blocked(p, dir, toCamera), hitDist: null });
  }
  const chosen = selectRays(rays, filter, max);
  for (const r of chosen) if (r.blocked) r.hitDist = q.firstHit(r.from, r.dir, r.toCamera);
  return chosen;
}

/** Queries over the geometry provider (blocked: raycastAll) and the merged BVH (first-hit distance). */
export function makeQueries(provider: GeometryProvider, merged: MergedGeometry, occluders: ReadonlySet<ElementId>): RayQueries {
  const ray = new Ray();
  return {
    blocked: (o, d, dist) => provider.raycastAll(o, d, dist, occluders).length > 0,
    firstHit: (o, d, dist) => {
      ray.origin.copy(o);
      ray.direction.copy(d);
      let best: number | null = null;
      for (const h of merged.bvh.raycast(ray, DoubleSide, 0, dist)) {
        if (h.faceIndex === undefined || h.faceIndex === null) continue;
        const id = merged.elementOfTriangle(h.faceIndex);
        if (id < 0 || !occluders.has(id)) continue;
        if (best === null || h.distance < best) best = h.distance;
      }
      return best;
    },
  };
}

const BLOCKED_COLOR = new Color(1.0, 0.45, 0.12); // warm
const OPEN_COLOR = new Color(0.2, 0.75, 1.0); // cool
const PLAIN_COLOR = new Color(0.92, 0.92, 0.95); // colour-by-hit off

const VERT = /* glsl */ `
attribute vec3 rayColor;
attribute float rayT;
uniform float pointSize;
varying vec3 vRayColor;
varying float vRayT;
void main() {
  vRayColor = rayColor;
  vRayT = rayT;
  gl_PointSize = pointSize;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const FRAG = /* glsl */ `
uniform float opacity;
varying vec3 vRayColor;
varying float vRayT;
void main() {
  float a = opacity * mix(1.0, 0.35, vRayT);
  gl_FragColor = vec4(vRayColor * a, a); // premultiplied, raw colours like the xray shaders
}`;

function rayMaterial(pointSize: number): ShaderMaterial {
  return new ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: { opacity: { value: 1 }, pointSize: { value: pointSize } },
    transparent: true,
    premultipliedAlpha: true,
    depthTest: false,
    depthWrite: false,
  });
}

/** Draws a set of rays as lines and/or dots and fades them out. */
export class SightlineViz {
  private lines: LineSegments | null = null;
  private points: Points | null = null;
  private t0 = 0;
  private durationMs = 1500;
  count = 0;

  constructor(private readonly scene: Scene) {}

  get active(): boolean {
    return this.lines !== null || this.points !== null;
  }

  show(rays: readonly SightRay[], style: RayStyle, now: number, durationMs: number, colorByHit = true): void {
    this.clear();
    this.count = rays.length;
    if (rays.length === 0) return;
    this.t0 = now;
    this.durationMs = Math.max(1, durationMs);
    const n = rays.length;
    const lp = new Float32Array(n * 6);
    const lc = new Float32Array(n * 6);
    const lt = new Float32Array(n * 2);
    const pp = new Float32Array(n * 3);
    const pc = new Float32Array(n * 3);
    const pt = new Float32Array(n);
    const end = new Vector3();
    rays.forEach((r, i) => {
      const col = !colorByHit ? PLAIN_COLOR : r.blocked ? BLOCKED_COLOR : OPEN_COLOR;
      end.copy(r.from).addScaledVector(r.dir, rayLength(r));
      lp.set([r.from.x, r.from.y, r.from.z, end.x, end.y, end.z], i * 6);
      lc.set([col.r, col.g, col.b, col.r, col.g, col.b], i * 6);
      lt[i * 2] = 0;
      lt[i * 2 + 1] = 1;
      pp.set([r.from.x, r.from.y, r.from.z], i * 3);
      pc.set([col.r, col.g, col.b], i * 3);
    });
    if (style !== 'dots') {
      const g = new BufferGeometry();
      g.setAttribute('position', new BufferAttribute(lp, 3));
      g.setAttribute('rayColor', new BufferAttribute(lc, 3));
      g.setAttribute('rayT', new BufferAttribute(lt, 1));
      this.lines = new LineSegments(g, rayMaterial(1));
      this.lines.frustumCulled = false;
      this.lines.renderOrder = 20;
      this.lines.name = 'cinematic-sightlines';
      this.scene.add(this.lines);
    }
    if (style !== 'lines') {
      const g = new BufferGeometry();
      g.setAttribute('position', new BufferAttribute(pp, 3));
      g.setAttribute('rayColor', new BufferAttribute(pc, 3));
      g.setAttribute('rayT', new BufferAttribute(pt, 1));
      this.points = new Points(g, rayMaterial(6));
      this.points.frustumCulled = false;
      this.points.renderOrder = 21;
      this.points.name = 'cinematic-sightline-dots';
      this.scene.add(this.points);
    }
  }

  /** Fade; removes the objects when done. Returns true while something is still visible. */
  update(now: number): boolean {
    if (!this.active) return false;
    const k = (now - this.t0) / this.durationMs;
    if (k >= 1) {
      this.clear();
      return false;
    }
    const a = 1 - k;
    for (const o of [this.lines, this.points]) if (o) (o.material as ShaderMaterial).uniforms.opacity!.value = a;
    return true;
  }

  clear(): void {
    for (const o of [this.lines, this.points]) {
      if (!o) continue;
      this.scene.remove(o);
      o.geometry.dispose();
      (o.material as ShaderMaterial).dispose();
    }
    this.lines = this.points = null;
    this.count = 0;
  }
}
