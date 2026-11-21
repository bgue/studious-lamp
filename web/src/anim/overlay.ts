// The camera path of a fly-through drawn in 3D: a dashed line through the camera positions (the same spline the player flies) and a
// small camera marker at each keyframe. A light overlay (no depth test), shown while the Views tab is open with the fly-through
// section expanded, and never during playback or recording.

import {
  BufferGeometry,
  Float32BufferAttribute,
  Group,
  Line,
  LineBasicMaterial,
  LineDashedMaterial,
  LineSegments,
} from 'three';
import type { Scene } from 'three';
import type { CameraPose } from './score';
import { Spline3 } from './spline';
import type { P3 } from './spline';

const PER_SEGMENT = 20;

/** The points of the dashed line and the segments of the camera markers (pure: tested in tests/anim-overlay.test.ts). */
export function pathGeometry(poses: readonly CameraPose[], size: number): { line: number[]; markers: number[][] } {
  const line: number[] = [];
  if (poses.length >= 2) {
    const sp = new Spline3(poses.map((p) => p.position as P3));
    for (let i = 0; i < poses.length - 1; i++) {
      for (let k = 0; k < PER_SEGMENT; k++) {
        const p = sp.segmentAt(i, k / PER_SEGMENT);
        line.push(p[0], p[1], p[2]);
      }
    }
    const last = poses[poses.length - 1]!.position;
    line.push(last[0], last[1], last[2]);
  }
  const markers = poses.map((p) => {
    // A pyramid: the apex at the camera, the base `size` ahead along the view direction.
    const d: P3 = [p.target[0] - p.position[0], p.target[1] - p.position[1], p.target[2] - p.position[2]];
    const len = Math.hypot(...d) || 1;
    const f: P3 = [d[0] / len, d[1] / len, d[2] / len];
    const up: P3 = p.up ?? [0, 1, 0];
    // Right = f x up, up' = right x f.
    let r: P3 = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]];
    const rl = Math.hypot(...r) || 1;
    r = [r[0] / rl, r[1] / rl, r[2] / rl];
    const u: P3 = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
    const c = p.position;
    const base: P3 = [c[0] + f[0] * size, c[1] + f[1] * size, c[2] + f[2] * size];
    const w = size * 0.55;
    const h = size * 0.35;
    const corner = (sx: number, sy: number): P3 => [base[0] + r[0] * w * sx + u[0] * h * sy, base[1] + r[1] * w * sx + u[1] * h * sy, base[2] + r[2] * w * sx + u[2] * h * sy];
    const k = [corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1)];
    const seg: number[] = [];
    for (let i = 0; i < 4; i++) {
      const a = k[i]!;
      const b = k[(i + 1) % 4]!;
      seg.push(c[0], c[1], c[2], a[0], a[1], a[2]);
      seg.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
    return seg;
  });
  return { line, markers };
}

export class PathOverlay {
  private group: Group | null = null;
  private shown = false;
  private want = false;
  private suppressed = 0;
  private poses: CameraPose[] = [];
  private selected = -1;
  private size = 1;

  constructor(private readonly scene: Scene, private readonly redraw: () => void) {}

  get visible(): boolean {
    return this.shown;
  }

  set(poses: CameraPose[], size: number, selected: number): void {
    this.poses = poses;
    this.size = size;
    this.selected = selected;
    this.rebuild();
  }

  /** Show the overlay when `on` (and nothing suppresses it). */
  setWanted(on: boolean): void {
    if (on === this.want) return;
    this.want = on;
    this.rebuild();
  }

  /** Hide it for a moment (playback, recording, a thumbnail capture); call release() after. */
  suppress(): void {
    this.suppressed++;
    this.rebuild();
  }

  release(): void {
    this.suppressed = Math.max(0, this.suppressed - 1);
    this.rebuild();
  }

  private clear(): void {
    if (!this.group) return;
    this.scene.remove(this.group);
    this.group.traverse((o) => {
      const m = o as Line;
      m.geometry?.dispose();
      (m.material as { dispose?: () => void } | undefined)?.dispose?.();
    });
    this.group = null;
  }

  private rebuild(): void {
    const show = this.want && this.suppressed === 0 && this.poses.length > 0;
    this.clear();
    this.shown = show;
    if (show) {
      const g = pathGeometry(this.poses, this.size);
      const group = new Group();
      group.renderOrder = 999;
      if (g.line.length >= 6) {
        const geo = new BufferGeometry();
        geo.setAttribute('position', new Float32BufferAttribute(g.line, 3));
        const line = new Line(geo, new LineDashedMaterial({ color: 0xffb454, dashSize: this.size * 0.6, gapSize: this.size * 0.4, depthTest: false, transparent: true, opacity: 0.9 }));
        line.computeLineDistances();
        line.renderOrder = 999;
        line.frustumCulled = false;
        group.add(line);
      }
      g.markers.forEach((m, i) => {
        const geo = new BufferGeometry();
        geo.setAttribute('position', new Float32BufferAttribute(m, 3));
        const seg = new LineSegments(geo, new LineBasicMaterial({ color: i === this.selected ? 0xffffff : 0x3b9cff, depthTest: false, transparent: true, opacity: 0.95 }));
        seg.renderOrder = 1000;
        seg.frustumCulled = false;
        group.add(seg);
      });
      this.group = group;
      this.scene.add(group);
    }
    this.redraw();
  }

  dispose(): void {
    this.clear();
  }
}
