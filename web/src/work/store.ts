// Where 3D sketches and issues live between sessions. In IndexedDB (database `xray-work`), one record per model, keyed the way
// markup/scope.ts groups items (identityKey). A record holds the sketches of that model, its issues (BCF topics, with their
// viewpoints, the snapshot images as bytes and the sketch links) and the metadata of the PDFs the issues refer to (never the PDF
// bytes: those stay in the sheets store). Nothing here goes anywhere else: not localStorage, not a URL or share link, not a saved
// view, a preset or a packed page. Without IndexedDB (a private window, a blocked profile, node) the store keeps nothing.
// Tested in tests/work-store.test.ts.

import type { BcfTopic } from '../bcf/model';
import type { MarkupSet, ModelIdentity } from '../markup/model';

export const WORK_DB = 'xray-work';
const DB_VERSION = 1;
const RECORDS = 'models';

/** A PDF an issue refers to: the bytes are found again by the SHA-256 in the sheets store. */
export interface WorkDocument {
  guid: string;
  filename: string;
  sha256: string;
  description?: string;
}

export interface WorkRecord {
  schema: 'xray-work/1';
  /** identityKey of the model. */
  key: string;
  model: ModelIdentity | null;
  saved: string;
  /** 3D sketches (sheet sketches are kept by the sheets store). */
  sets: MarkupSet[];
  /** Issues with their viewpoints; snapshots are bytes. `sketchId` of a viewpoint is the link to its sketch. */
  topics: BcfTopic[];
  documents: WorkDocument[];
}

export interface WorkBackend {
  readonly persistent: boolean;
  get(key: string): Promise<WorkRecord | null>;
  put(rec: WorkRecord): Promise<void>;
  delete(key: string): Promise<void>;
  keys(): Promise<string[]>;
}

function copy<T>(v: T): T {
  return structuredClone(v);
}

export class MemoryWorkBackend implements WorkBackend {
  readonly persistent = false;
  private readonly recs = new Map<string, WorkRecord>();
  async get(key: string): Promise<WorkRecord | null> { const r = this.recs.get(key); return r ? copy(r) : null; }
  async put(rec: WorkRecord): Promise<void> { this.recs.set(rec.key, copy(rec)); }
  async delete(key: string): Promise<void> { this.recs.delete(key); }
  async keys(): Promise<string[]> { return [...this.recs.keys()]; }
}

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((res, rej) => {
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error ?? new Error('IndexedDB request failed'));
  });
}

/** IndexedDB backend; null when IndexedDB is missing or cannot be opened. */
export async function openIdbWorkBackend(factory: IDBFactory | undefined = typeof indexedDB !== 'undefined' ? indexedDB : undefined): Promise<WorkBackend | null> {
  if (!factory) return null;
  let db: IDBDatabase;
  try {
    db = await new Promise<IDBDatabase>((res, rej) => {
      const o = factory.open(WORK_DB, DB_VERSION);
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
    async get(key) {
      const v = (await req(store('readonly').get(key))) as WorkRecord | undefined;
      return v && v.schema === 'xray-work/1' ? v : null;
    },
    async put(rec) {
      await req(store('readwrite').put(rec, rec.key));
    },
    async delete(key) {
      await req(store('readwrite').delete(key));
    },
    async keys() {
      return (await req(store('readonly').getAllKeys())).map(String);
    },
  };
}

export class WorkStore {
  private backend: WorkBackend = new MemoryWorkBackend();
  private ready: Promise<void> | null = null;

  constructor(private readonly open: () => Promise<WorkBackend | null> = () => openIdbWorkBackend()) {}

  /** Whether what is saved survives a reload. */
  get persistent(): boolean {
    return this.backend.persistent;
  }

  /** Open the backend (once). */
  init(): Promise<void> {
    this.ready ??= (async () => {
      const b = await this.open().catch(() => null);
      if (b) this.backend = b;
    })();
    return this.ready;
  }

  async get(key: string): Promise<WorkRecord | null> {
    await this.init();
    return this.backend.get(key).catch(() => null);
  }
  async put(rec: WorkRecord): Promise<boolean> {
    await this.init();
    try {
      await this.backend.put(rec);
      return this.backend.persistent;
    } catch {
      return false;
    }
  }
  async delete(key: string): Promise<void> {
    await this.init();
    await this.backend.delete(key).catch(() => undefined);
  }
  async keys(): Promise<string[]> {
    await this.init();
    return this.backend.keys().catch(() => []);
  }
}
