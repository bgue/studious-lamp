// The signature cache: one decision per signature. In memory for Node; the browser persists it per model in localStorage,
// keyed by the model name, the schema hash and the model id, so a decision of another schema or model is never reused.

import type { RawDecision } from './calibrate';
import type { ClassifyResult } from './types';

/**
 * A stored decision: a result without the element id, the source and the review flag (both are set when it is used).
 * `raw` holds the raw scores (logits) of the model, so that calibration is applied when the decision is read and a change of
 * the temperatures re-scores without running the model. The other fields are the decision as the model gave it (T = 1).
 */
export type CachedDecision = Omit<ClassifyResult, 'id' | 'source' | 'needsReview' | 'signature'> & { raw?: RawDecision };

export interface SignatureCache {
  get(signature: string): CachedDecision | undefined;
  set(signature: string, d: CachedDecision): void;
  readonly size: number;
  /** Every stored decision with its signature (for calibration on the rules). */
  entries(): IterableIterator<[string, CachedDecision]>;
  clear(): void;
  /** Write to storage, when there is one. */
  flush(): void;
}

export class MemoryCache implements SignatureCache {
  protected readonly map = new Map<string, CachedDecision>();
  get(s: string): CachedDecision | undefined {
    return this.map.get(s);
  }
  set(s: string, d: CachedDecision): void {
    this.map.set(s, d);
  }
  get size(): number {
    return this.map.size;
  }
  entries(): IterableIterator<[string, CachedDecision]> {
    return this.map.entries();
  }
  clear(): void {
    this.map.clear();
  }
  flush(): void {
    /* memory only */
  }
}

export interface KeyValueStorage {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}

export const CACHE_PREFIX = 'xray.classify.cache.v1.';
const MAX_ENTRIES = 5000;

/** Storage key of a cache. `modelId` is the provider id and model, such as "jev:jev-1.13.0". */
export const cacheKey = (modelName: string, schemaHash: string, modelId: string): string => `${CACHE_PREFIX}${modelName}|${schemaHash}|${modelId}`;

export class StorageCache extends MemoryCache {
  private dirty = false;
  constructor(private readonly storage: KeyValueStorage | null, private readonly key: string) {
    super();
    try {
      const t = storage?.getItem(key);
      if (t) {
        const o = JSON.parse(t) as Record<string, CachedDecision>;
        for (const [k, v] of Object.entries(o)) if (v && typeof v === 'object' && 'discipline' in v) this.map.set(k, v);
      }
    } catch {
      /* a broken entry is an empty cache */
    }
  }
  override set(s: string, d: CachedDecision): void {
    super.set(s, d);
    this.dirty = true;
  }
  override clear(): void {
    super.clear();
    try {
      this.storage?.removeItem(this.key);
    } catch {
      /* ignore */
    }
    this.dirty = false;
  }
  override flush(): void {
    if (!this.dirty || !this.storage) return;
    this.dirty = false;
    while (this.map.size > MAX_ENTRIES) this.map.delete(this.map.keys().next().value as string);
    try {
      this.storage.setItem(this.key, JSON.stringify(Object.fromEntries(this.map)));
    } catch {
      /* quota or private mode: the cache stays in memory */
    }
  }
}
