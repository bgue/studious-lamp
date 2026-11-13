// The viewer side of attachments: build the inputs of the pure inference (src/bcf/surface.ts) from a camera and the BVH of
// the BcfController, for a shape drawn now (canvas pixels, rays of the live camera) or a stored shape (fractions, rays of its
// set camera: migration and the chip's Surface and Region choices). Shared by the markup tool and the BCF annotations.

import type { Camera } from 'three';
import { ifcToViewer } from '../bcf/model';
import type { BcfSnapshotView, Vec3 } from '../bcf/model';
import { shapePointWorld } from '../bcf/annotate';
import type { Attachment } from '../bcf/attach';
import { inferAttachment, projectRegion, projectSurface, projectSurfaceData } from '../bcf/surface';
import type { InferInput, Inference, Ray3 } from '../bcf/surface';
import type { BcfController } from '../bcf/controller';
import { cameraRay } from '../measure/geometry';
import { distToPolyline } from './geometry';
import type { Measurement } from '../measure/maths';
import { cloudBase, ellipsePoints, rectCorners } from './geometry';
import { boxCorners, ellipseInQuad } from './layout';

type Pt = ReadonlyArray<readonly [number, number]>;

/** The drawn path of a shape kind in pixels (or any 2D unit), and whether it is closed. `pts`: what the tool recorded. */
export function shapePath(kind: string, pts: Pt): { path: number[]; closed: boolean } {
  switch (kind) {
    case 'rect': case 'highlightBox': return { path: pts.length >= 4 ? boxCorners(pts).flat() : rectCorners(pts[0]!, pts[pts.length - 1]!), closed: true };
    case 'ellipse': return { path: pts.length >= 4 ? ellipseInQuad(boxCorners(pts), 56).flat() : ellipsePoints(pts[0]!, pts[pts.length - 1]!, 56), closed: true };
    case 'cloud': return { path: cloudBase(pts.length === 2 ? pts : pts), closed: true };
    case 'polygon': return { path: pts.flatMap((p) => [p[0], p[1]]), closed: true };
    default: return { path: pts.flatMap((p) => [p[0], p[1]]), closed: false };
  }
}

/** A candidate link under the shape: a measurement or a penetration. */
export interface HintSource {
  project: (p: Vec3) => { x: number; y: number; front: boolean };
  measurements: readonly Measurement[];
  measureLink: (m: Measurement) => NonNullable<Attachment['measurement']>;
  penetrations: ReadonlyArray<{ location: Vec3; mep: number; host: number }>;
  guidOfId: (id: number) => string | undefined;
}

/**
 * A measurement or penetration under the centre of the shape (path in pixels): a dimension line within 12 px of the centre,
 * or a penetration marker within 16 px. The nearest wins.
 */
export function findHint(path: ReadonlyArray<number>, closed: boolean, src: HintSource): InferInput['hint'] | undefined {
  if (path.length < 4) return undefined;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < path.length; i += 2) { x0 = Math.min(x0, path[i]!); x1 = Math.max(x1, path[i]!); y0 = Math.min(y0, path[i + 1]!); y1 = Math.max(y1, path[i + 1]!); }
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  // For an open line the middle of its path is the spot, not the middle of its box.
  const mid = closed ? [cx, cy] : [path[(Math.floor(path.length / 4)) * 2]!, path[Math.floor(path.length / 4) * 2 + 1]!];
  let bestD = Infinity;
  let hint: InferInput['hint'];
  for (const m of src.measurements) {
    const a = src.project(m.a as unknown as Vec3);
    const b = src.project(m.b as unknown as Vec3);
    if (!a.front || !b.front) continue;
    const d = distToPolyline(mid[0]!, mid[1]!, [a.x, a.y, b.x, b.y], false);
    if (d <= 12 && d < bestD) { bestD = d; hint = { measurement: src.measureLink(m) }; }
  }
  for (const r of src.penetrations) {
    const p = src.project(r.location);
    if (!p.front) continue;
    const d = Math.hypot(p.x - mid[0]!, p.y - mid[1]!);
    const mep = src.guidOfId(r.mep);
    const host = src.guidOfId(r.host);
    if (d <= 16 && d < bestD && mep && host) { bestD = d; hint = { penetration: { mep, host } }; }
  }
  return hint;
}

function baseInput(geo: BcfController, kind: string, shape: { path: number[]; closed: boolean }, rayAt: InferInput['rayAt']): InferInput {
  return {
    kind, path: shape.path, closed: shape.closed, rayAt, probe: (r) => geo.castRay(r),
    guidOf: (id) => geo.guidOfId(id), centreOf: (id) => geo.centreOfId(id), shift: geo.shift,
  };
}

/** Input for a shape drawn on the screen now: rays of the live camera through canvas pixels. */
export function screenInput(geo: BcfController, kind: string, screen: Pt, W: number, H: number, cam: Camera): InferInput {
  cam.updateMatrixWorld();
  const rayAt = (x: number, y: number): Ray3 => {
    const r = cameraRay(cam, (x / W) * 2 - 1, -((y / H) * 2 - 1));
    return { o: [r.origin.x, r.origin.y, r.origin.z], d: [r.direction.x, r.direction.y, r.direction.z] };
  };
  return baseInput(geo, kind, shapePath(kind, screen), rayAt);
}

/** Input for a stored shape: rays of its set camera through its fractions (canvas size W x H gives the pixel scale). */
export function fractionInput(geo: BcfController, kind: string, points: Pt, view: BcfSnapshotView, W: number, H: number): InferInput {
  const shift = geo.shift;
  const eye = ifcToViewer(view.position, shift);
  const rayAt = (x: number, y: number): Ray3 => {
    const w = shapePointWorld(view, shift, x / W, y / H, 1);
    const d: Vec3 = [w[0] - eye[0], w[1] - eye[1], w[2] - eye[2]];
    const l = Math.hypot(d[0], d[1], d[2]) || 1;
    return { o: eye, d: [d[0] / l, d[1] / l, d[2] / l] };
  };
  const px = points.map((p) => [p[0] * W, p[1] * H] as [number, number]);
  return baseInput(geo, kind, shapePath(kind, px), rayAt);
}

export { inferAttachment, projectRegion, projectSurface, projectSurfaceData };
export type { Inference };
