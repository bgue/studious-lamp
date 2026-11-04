// Shared shapes of the point cloud feature. Readers produce PointCloudData; the session decimates it into Shown.
//
// Precision: positions are stored as Float32 RELATIVE to `origin`, a double precision point of the source frame
// (the first valid point). The large offset of a georeferenced cloud therefore never enters a Float32.

export type Vec3 = [number, number, number];

export interface PointCloudData {
  name: string;
  /** 'las' | 'ply' | 'pcd' | 'xyz' | 'pts' | 'txt' */
  format: string;
  count: number;
  /** Source frame position (double) that `positions` are relative to. */
  origin: Vec3;
  /** 3 floats per point, source axes, relative to `origin`. */
  positions: Float32Array;
  /** 3 bytes per point (0..255). Absent when the file has no colour. */
  colors?: Uint8Array;
  /** One float per point, raw file values. */
  intensity?: Float32Array;
  /** One byte per point (ASPRS class codes for LAS). */
  classification?: Uint8Array;
  /** Source frame bounds (double). */
  boundsMin: Vec3;
  boundsMax: Vec3;
  intensityRange?: [number, number];
  warnings: string[];
}

/** The decimated points that are drawn. Same layout as PointCloudData. */
export interface Shown {
  count: number;
  positions: Float32Array;
  colors?: Uint8Array;
  intensity?: Float32Array;
  classification?: Uint8Array;
}

export interface LoadInfo {
  name: string;
  format: string;
  originalCount: number;
  origin: Vec3;
  boundsMin: Vec3;
  boundsMax: Vec3;
  hasColor: boolean;
  hasIntensity: boolean;
  hasClassification: boolean;
  intensityRange: [number, number] | null;
  warnings: string[];
  parseMs: number;
}

export type ProgressFn = (fraction: number, stage: string) => void;

export class PointCloudError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PointCloudError';
  }
}
