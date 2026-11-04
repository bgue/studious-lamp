// Accumulates points into growable typed arrays, relative to the first point (see types.ts).

import type { PointCloudData, Vec3 } from '../types';
import { PointCloudError } from '../types';

export interface BuilderFields {
  color?: boolean;
  intensity?: boolean;
  classification?: boolean;
}

export class PointBuilder {
  count = 0;
  private cap: number;
  private pos: Float32Array;
  private col: Float32Array | null;
  private inten: Float32Array | null;
  private cls: Uint8Array | null;
  private ox = 0;
  private oy = 0;
  private oz = 0;
  private hasOrigin = false;
  private minX = Infinity;
  private minY = Infinity;
  private minZ = Infinity;
  private maxX = -Infinity;
  private maxY = -Infinity;
  private maxZ = -Infinity;
  readonly warnings: string[] = [];

  constructor(private readonly fields: BuilderFields, capacity = 1024) {
    this.cap = Math.max(16, capacity);
    this.pos = new Float32Array(this.cap * 3);
    this.col = fields.color ? new Float32Array(this.cap * 3) : null;
    this.inten = fields.intensity ? new Float32Array(this.cap) : null;
    this.cls = fields.classification ? new Uint8Array(this.cap) : null;
  }

  private grow(): void {
    const cap = this.cap * 2;
    const g = <T extends Float32Array | Uint8Array>(a: T, k: number): T => {
      const n = new (a.constructor as new (n: number) => T)(cap * k);
      n.set(a);
      return n;
    };
    this.pos = g(this.pos, 3);
    if (this.col) this.col = g(this.col, 3);
    if (this.inten) this.inten = g(this.inten, 1);
    if (this.cls) this.cls = g(this.cls, 1);
    this.cap = cap;
  }

  /** Add a point (source coordinates, double). Non-finite coordinates are skipped. Returns the index or -1. */
  add(x: number, y: number, z: number): number {
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return -1;
    if (!this.hasOrigin) {
      this.ox = x;
      this.oy = y;
      this.oz = z;
      this.hasOrigin = true;
    }
    if (this.count === this.cap) this.grow();
    const i = this.count++;
    this.pos[i * 3] = x - this.ox;
    this.pos[i * 3 + 1] = y - this.oy;
    this.pos[i * 3 + 2] = z - this.oz;
    if (x < this.minX) this.minX = x;
    if (y < this.minY) this.minY = y;
    if (z < this.minZ) this.minZ = z;
    if (x > this.maxX) this.maxX = x;
    if (y > this.maxY) this.maxY = y;
    if (z > this.maxZ) this.maxZ = z;
    return i;
  }

  /** Raw colour values of point i (any scale: it is normalised in finish()). */
  setColor(i: number, r: number, g: number, b: number): void {
    const c = this.col!;
    c[i * 3] = r;
    c[i * 3 + 1] = g;
    c[i * 3 + 2] = b;
  }

  setIntensity(i: number, v: number): void {
    this.inten![i] = v;
  }

  setClass(i: number, v: number): void {
    this.cls![i] = v;
  }

  finish(name: string, format: string): PointCloudData {
    if (this.count === 0) throw new PointCloudError(`No points found in ${name}`);
    const n = this.count;
    const out: PointCloudData = {
      name,
      format,
      count: n,
      origin: [this.ox, this.oy, this.oz] as Vec3,
      positions: this.pos.slice(0, n * 3),
      boundsMin: [this.minX, this.minY, this.minZ],
      boundsMax: [this.maxX, this.maxY, this.maxZ],
      warnings: this.warnings,
    };
    if (this.col) out.colors = normaliseColors(this.col.subarray(0, n * 3));
    if (this.inten) {
      out.intensity = this.inten.slice(0, n);
      let lo = Infinity;
      let hi = -Infinity;
      for (let i = 0; i < n; i++) {
        const v = out.intensity[i]!;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      out.intensityRange = [lo, hi];
    }
    if (this.cls) out.classification = this.cls.slice(0, n);
    return out;
  }
}

/** Raw colour values to bytes. Scale is detected from the maximum: <= 1 is 0..1, <= 255 is 8 bit, else 16 bit. */
export function normaliseColors(raw: Float32Array): Uint8Array {
  let max = 0;
  for (let i = 0; i < raw.length; i++) if (raw[i]! > max) max = raw[i]!;
  const scale = max <= 1.0000001 ? 255 : max <= 255.0000001 ? 1 : 255 / 65535;
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) {
    const v = Math.round(raw[i]! * scale);
    out[i] = v < 0 ? 0 : v > 255 ? 255 : v;
  }
  return out;
}
