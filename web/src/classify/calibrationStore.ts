// Fitted temperatures per model id (provider and model, as providerId() writes it), kept in localStorage. They are not secret and
// they are not part of the settings, share links, saved views or packed pages: a fit belongs to the browser that made it.

import type { KeyValueStorage } from './cache';
import { TEMPERATURE_KEYS } from './calibrate';
import type { StoredFit, Temperatures } from './calibrate';

export const CALIBRATION_STORAGE_KEY = 'xray.classify.calibration.v1';

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0;

export class FitStore {
  private map = new Map<string, StoredFit>();
  constructor(private readonly storage: KeyValueStorage | null) {
    try {
      const t = storage?.getItem(CALIBRATION_STORAGE_KEY);
      if (!t) return;
      const o = JSON.parse(t) as Record<string, unknown>;
      for (const [id, v] of Object.entries(o)) {
        if (!v || typeof v !== 'object') continue;
        const f = v as Partial<StoredFit>;
        const temps: Temperatures = {};
        for (const k of TEMPERATURE_KEYS) if (finite(f.temperatures?.[k])) temps[k] = f.temperatures![k]!;
        if (Object.keys(temps).length && typeof f.at === 'string') this.map.set(id, { temperatures: temps, n: f.n ?? {}, at: f.at, source: String(f.source ?? ''), ...(f.reports ? { reports: f.reports } : {}) });
      }
    } catch {
      /* a broken entry is an empty store */
    }
  }
  get(modelId: string): StoredFit | null {
    return this.map.get(modelId) ?? null;
  }
  set(modelId: string, fit: StoredFit): void {
    this.map.set(modelId, fit);
    this.persist();
  }
  remove(modelId: string): void {
    if (this.map.delete(modelId)) this.persist();
  }
  ids(): string[] {
    return [...this.map.keys()];
  }
  private persist(): void {
    try {
      this.storage?.setItem(CALIBRATION_STORAGE_KEY, JSON.stringify(Object.fromEntries(this.map)));
    } catch {
      /* quota or private mode: the fit stays in memory for this page */
    }
  }
}
