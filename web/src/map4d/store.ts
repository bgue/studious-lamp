// Where the assignments live between sessions: IndexedDB database `xray-4d-map`, one record per model, keyed by the model identity
// (markup/scope.ts identityKey), like the work store. Nothing here goes anywhere else: not localStorage, not a URL, a share link, a saved
// view or a packed page. Without IndexedDB (a private window, node) the store keeps nothing. Tested in tests/map4d-store.test.ts.

import type { Assignment } from '../schedule/types';
import type { ModelIdentity } from '../markup/model';
import type { ValueLists } from './values';

export const MAP_DB = 'xray-4d-map';
const DB_VERSION = 1;
const RECORDS = 'models';

export interface MapRecord {
  schema: 'xray-4d-map/1';
  /** identityKey of the model. */
  key: string;
  model: ModelIdentity | null;
  saved: string;
  assignments: Assignment[];
  values: ValueLists;
  /** The class-to-trade table in use (a copy the person may have edited). */
  classTrade: Record<string, string>;
}

export interface MapBackend {
  readonly persistent: boolean;
  get(key: string): Promise<MapRecord | null>;
  put(rec: MapRecord): Promise<void>;
  delete(key: string): Promise<void>;
}

export class MemoryMapBackend implements MapBackend {
  readonly persistent = false;
  private readonly recs = new Map<string, MapRecord>();
  async get(key: string): Promise<MapRecord | null> { const r = this.recs.get(key); return r ? structuredClone(r) : null; }
  async put(rec: MapRecord): Promise<void> { this.recs.set(rec.key, structuredClone(rec)); }
  async delete(key: string): Promise<void> { this.recs.delete(key); }
}

const req = <T,>(r: IDBRequest<T>): Promise<T> => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error ?? new Error('IndexedDB request failed')); });

export async function openIdbMapBackend(factory: IDBFactory | undefined = typeof indexedDB !== 'undefined' ? indexedDB : undefined): Promise<MapBackend | null> {
  if (!factory) return null;
  let db: IDBDatabase;
  try {
    db = await new Promise<IDBDatabase>((res, rej) => {
      const o = factory.open(MAP_DB, DB_VERSION);
      o.onupgradeneeded = () => { o.result.createObjectStore(RECORDS); };
      o.onsuccess = () => res(o.result);
      o.onerror = () => rej(o.error ?? new Error('IndexedDB open failed'));
      o.onblocked = () => rej(new Error('IndexedDB blocked'));
    });
  } catch {
    return null;
  }
  const store = (mode: IDBTransactionMode): IDBObjectStore => db.transaction(RECORDS, mode).objectStore(RECORDS);
  return {
    persistent: true,
    async get(key) { const v = (await req(store('readonly').get(key))) as MapRecord | undefined; return v && v.schema === 'xray-4d-map/1' ? v : null; },
    async put(rec) { await req(store('readwrite').put(rec, rec.key)); },
    async delete(key) { await req(store('readwrite').delete(key)); },
  };
}

export class MapStore {
  private backend: MapBackend = new MemoryMapBackend();
  private ready: Promise<void> | null = null;
  constructor(private readonly open: () => Promise<MapBackend | null> = () => openIdbMapBackend()) {}
  get persistent(): boolean { return this.backend.persistent; }
  init(): Promise<void> {
    this.ready ??= (async () => { const b = await this.open().catch(() => null); if (b) this.backend = b; })();
    return this.ready;
  }
  async get(key: string): Promise<MapRecord | null> { await this.init(); return this.backend.get(key).catch(() => null); }
  async put(rec: MapRecord): Promise<boolean> {
    await this.init();
    try { await this.backend.put(rec); return this.backend.persistent; } catch { return false; }
  }
  async delete(key: string): Promise<void> { await this.init(); await this.backend.delete(key).catch(() => undefined); }
}
