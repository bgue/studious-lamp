// The manual location of a model, kept per model in IndexedDB (not localStorage, not a URL, not a share link, a saved view or a
// preset). A backend interface so tests run on a memory one; the IndexedDB one is used in the browser, and when IndexedDB is not
// there (a private window, blocked storage) the location lives in memory for the page. Docs: docs-features/map.md.

import type { ManualLocation } from './geo';
import { validLatLon } from './geo';

export interface LocationBackend {
  get(model: string): Promise<ManualLocation | null>;
  put(model: string, loc: ManualLocation): Promise<void>;
  delete(model: string): Promise<void>;
}

export class MemoryLocationBackend implements LocationBackend {
  readonly map = new Map<string, ManualLocation>();
  async get(model: string): Promise<ManualLocation | null> { return this.map.get(model) ?? null; }
  async put(model: string, loc: ManualLocation): Promise<void> { this.map.set(model, { ...loc }); }
  async delete(model: string): Promise<void> { this.map.delete(model); }
}

const DB_NAME = 'xray-map';
const STORE = 'locations';

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
}

export class IdbLocationBackend implements LocationBackend {
  private db: Promise<IDBDatabase> | null = null;
  constructor(private readonly factory: IDBFactory) {}

  private open(): Promise<IDBDatabase> {
    if (!this.db) {
      this.db = new Promise((res, rej) => {
        const r = this.factory.open(DB_NAME, 1);
        r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains(STORE)) r.result.createObjectStore(STORE); };
        r.onsuccess = () => res(r.result);
        r.onerror = () => rej(r.error);
        r.onblocked = () => rej(new Error('blocked'));
      });
    }
    return this.db;
  }

  async get(model: string): Promise<ManualLocation | null> {
    const db = await this.open();
    const v = await req(db.transaction(STORE, 'readonly').objectStore(STORE).get(model));
    return clean(v);
  }
  async put(model: string, loc: ManualLocation): Promise<void> {
    const db = await this.open();
    await req(db.transaction(STORE, 'readwrite').objectStore(STORE).put({ lat: loc.lat, lon: loc.lon, rotation: loc.rotation }, model));
  }
  async delete(model: string): Promise<void> {
    const db = await this.open();
    await req(db.transaction(STORE, 'readwrite').objectStore(STORE).delete(model));
  }
}

function clean(v: unknown): ManualLocation | null {
  const r = v as Partial<ManualLocation> | undefined;
  if (!r || typeof r !== 'object' || !validLatLon(r.lat, r.lon)) return null;
  return { lat: r.lat as number, lon: r.lon as number, rotation: typeof r.rotation === 'number' && Number.isFinite(r.rotation) ? r.rotation : 0 };
}

/** The store of the page: IndexedDB when it works, else memory. Errors never reach the caller: a failed read is "nothing stored". */
export class LocationStore {
  private fallback = new MemoryLocationBackend();
  constructor(private backend: LocationBackend) {}

  async get(model: string): Promise<ManualLocation | null> {
    const local = await this.fallback.get(model); // what this page set is the newest
    if (local) return local;
    try { return await this.backend.get(model); } catch { return null; }
  }
  async set(model: string, loc: ManualLocation): Promise<void> {
    await this.fallback.put(model, loc);
    try { await this.backend.put(model, loc); } catch { /* kept in memory for this page */ }
  }
  async clear(model: string): Promise<void> {
    await this.fallback.delete(model);
    try { await this.backend.delete(model); } catch { /* ignore */ }
  }
}

export function browserLocationStore(): LocationStore {
  let backend: LocationBackend;
  try {
    backend = typeof indexedDB !== 'undefined' && indexedDB ? new IdbLocationBackend(indexedDB) : new MemoryLocationBackend();
  } catch {
    backend = new MemoryLocationBackend();
  }
  return new LocationStore(backend);
}
