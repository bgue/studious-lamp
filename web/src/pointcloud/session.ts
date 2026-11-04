// Parse + decimate pipeline. The same class runs inside the Web Worker (files over 5 MB) and inline on the main thread.

import { decimate } from './decimate';
import { parsePointCloud } from './readers';
import type { LoadInfo, PointCloudData, ProgressFn, Shown } from './types';

export class CloudSession {
  private data: PointCloudData | null = null;

  load(buffer: ArrayBuffer, name: string, onProgress?: ProgressFn): LoadInfo {
    const t0 = performance.now();
    const d = parsePointCloud(buffer, name, onProgress);
    this.data = d;
    return {
      name,
      format: d.format,
      originalCount: d.count,
      origin: d.origin,
      boundsMin: d.boundsMin,
      boundsMax: d.boundsMax,
      hasColor: !!d.colors,
      hasIntensity: !!d.intensity,
      hasClassification: !!d.classification && d.format !== 'ply' ? hasVariety(d.classification) : !!d.classification,
      intensityRange: d.intensityRange ?? null,
      warnings: d.warnings,
      parseMs: performance.now() - t0,
    };
  }

  decimate(budget: number, seed = 1): { shown: Shown; ms: number } {
    if (!this.data) throw new Error('no point cloud loaded');
    const t0 = performance.now();
    const shown = decimate(this.data, budget, seed);
    return { shown, ms: performance.now() - t0 };
  }

  /** Whether `shown` aliases the loaded arrays (so it must be copied before it is transferred away). */
  shares(shown: Shown): boolean {
    return !!this.data && shown.positions === this.data.positions;
  }

  dispose(): void {
    this.data = null;
  }
}

function hasVariety(c: Uint8Array): boolean {
  // LAS always carries a class byte; all zeros means "never classified", not worth a palette
  for (let i = 0; i < c.length; i++) if (c[i] !== c[0]) return true;
  return c[0] !== 0 && c[0] !== 1;
}
