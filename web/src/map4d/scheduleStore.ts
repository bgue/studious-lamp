// Where the schedule workflow keeps its work between sessions: IndexedDB database `xray-4d-schedule`, one record per model (the same key as
// the mapping store, src/map4d/store.ts): the 4D configuration, the links with their review state, and the XER file the links were made
// for (its bytes, so the links can be shown again after a reload). Nothing goes anywhere else. Without IndexedDB (a private window, node)
// the store keeps nothing. Tested in tests/map4d-schedule-store.test.ts.

import type { FourDConfig, FourDLinks } from '../schedule/types';

export const SCHEDULE_DB = 'xray-4d-schedule';
const DB_VERSION = 1;
const RECORDS = 'models';
/** XER files larger than this are not stored (the config and links are). */
export const MAX_STORED_XER = 24 * 1024 * 1024;

export interface ScheduleRecord {
  schema: 'xray-4d-schedule/1';
  key: string;
  saved: string;
  config: FourDConfig | null;
  links: FourDLinks | null;
  /** The schedule the links were made for. `bytes` is the file as it was read (any encoding). */
  file: { name: string; hash: string; project: string; bytes?: ArrayBuffer } | null;
}

export interface ScheduleBackend {
  readonly persistent: boolean;
  get(key: string): Promise<ScheduleRecord | null>;
  put(rec: ScheduleRecord): Promise<void>;
  delete(key: string): Promise<void>;
}

export class MemoryScheduleBackend implements ScheduleBackend {
  readonly persistent = false;
  private readonly recs = new Map<string, ScheduleRecord>();
  async get(key: string): Promise<ScheduleRecord | null> { const r = this.recs.get(key); return r ? structuredClone(r) : null; }
  async put(rec: ScheduleRecord): Promise<void> { this.recs.set(rec.key, structuredClone(rec)); }
  async delete(key: string): Promise<void> { this.recs.delete(key); }
}

const req = <T,>(r: IDBRequest<T>): Promise<T> => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error ?? new Error('IndexedDB request failed')); });

export async function openIdbScheduleBackend(factory: IDBFactory | undefined = typeof indexedDB !== 'undefined' ? indexedDB : undefined): Promise<ScheduleBackend | null> {
  if (!factory) return null;
  let db: IDBDatabase;
  try {
    db = await new Promise<IDBDatabase>((res, rej) => {
      const o = factory.open(SCHEDULE_DB, DB_VERSION);
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
    async get(key) { const v = (await req(store('readonly').get(key))) as ScheduleRecord | undefined; return v && v.schema === 'xray-4d-schedule/1' ? v : null; },
    async put(rec) { await req(store('readwrite').put(rec, rec.key)); },
    async delete(key) { await req(store('readwrite').delete(key)); },
  };
}

export class ScheduleStore {
  private backend: ScheduleBackend = new MemoryScheduleBackend();
  private ready: Promise<void> | null = null;
  constructor(private readonly open: () => Promise<ScheduleBackend | null> = () => openIdbScheduleBackend()) {}
  get persistent(): boolean { return this.backend.persistent; }
  init(): Promise<void> {
    this.ready ??= (async () => { const b = await this.open().catch(() => null); if (b) this.backend = b; })();
    return this.ready;
  }
  async get(key: string): Promise<ScheduleRecord | null> { await this.init(); return this.backend.get(key).catch(() => null); }
  async put(rec: ScheduleRecord): Promise<boolean> {
    await this.init();
    try { await this.backend.put(rec); return this.backend.persistent; } catch { return false; }
  }
  async delete(key: string): Promise<void> { await this.init(); await this.backend.delete(key).catch(() => undefined); }
}
