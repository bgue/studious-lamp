// Where sheets live. In memory during the session, and in IndexedDB so a reload keeps them: the PDF bytes (one record per file,
// keyed by the SHA-256) and one small JSON record of the sheet documents, sheets, thumbnails and the sketches drawn on sheets.
// The bytes never go anywhere else: not localStorage, not a URL or share link, not a saved view or preset. Without IndexedDB
// (a private window, a blocked profile, node) the store works in memory only and says so.

import type { MarkupSet } from '../markup/model';
import type { Sheet, SheetDoc } from './model';
import { sanitizePlacement } from './placement';

export const DB_NAME = 'xray-sheets';
const DB_VERSION = 1;
const BYTES = 'bytes';
const META = 'meta';
const META_KEY = 'state';

/** What is saved besides the bytes. No PDF bytes in here (the leak test checks). */
export interface SheetsMeta {
  schema: 'xray-sheets/1';
  docs: SheetDoc[];
  sheets: Sheet[];
  /** Thumbnails by sheet id: small data:image/jpeg URLs. */
  thumbs: Record<string, string>;
  /** Sketches drawn on sheets (frame.kind sheet), including the read-only imported ones. */
  sets: MarkupSet[];
}

export interface ByteBackend {
  getBytes(key: string): Promise<Uint8Array | null>;
  putBytes(key: string, bytes: Uint8Array): Promise<void>;
  deleteBytes(key: string): Promise<void>;
  getMeta(): Promise<SheetsMeta | null>;
  putMeta(meta: SheetsMeta): Promise<void>;
  readonly persistent: boolean;
}

export class MemoryBackend implements ByteBackend {
  readonly persistent = false;
  private readonly bytes = new Map<string, Uint8Array>();
  private meta: SheetsMeta | null = null;
  async getBytes(key: string): Promise<Uint8Array | null> { return this.bytes.get(key) ?? null; }
  async putBytes(key: string, b: Uint8Array): Promise<void> { this.bytes.set(key, b); }
  async deleteBytes(key: string): Promise<void> { this.bytes.delete(key); }
  async getMeta(): Promise<SheetsMeta | null> { return this.meta ? (JSON.parse(JSON.stringify(this.meta)) as SheetsMeta) : null; }
  async putMeta(m: SheetsMeta): Promise<void> { this.meta = JSON.parse(JSON.stringify(m)) as SheetsMeta; }
}

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((res, rej) => {
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error ?? new Error('IndexedDB request failed'));
  });
}

/** IndexedDB backend; null when IndexedDB is missing or cannot be opened. */
export async function openIdbBackend(factory: IDBFactory | undefined = typeof indexedDB !== 'undefined' ? indexedDB : undefined): Promise<ByteBackend | null> {
  if (!factory) return null;
  let db: IDBDatabase;
  try {
    db = await new Promise<IDBDatabase>((res, rej) => {
      const o = factory.open(DB_NAME, DB_VERSION);
      o.onupgradeneeded = () => {
        o.result.createObjectStore(BYTES);
        o.result.createObjectStore(META);
      };
      o.onsuccess = () => res(o.result);
      o.onerror = () => rej(o.error ?? new Error('IndexedDB open failed'));
      o.onblocked = () => rej(new Error('IndexedDB blocked'));
    });
  } catch {
    return null;
  }
  const store = (name: string, mode: IDBTransactionMode): IDBObjectStore => db.transaction(name, mode).objectStore(name);
  return {
    persistent: true,
    async getBytes(key) {
      const v = (await req(store(BYTES, 'readonly').get(key))) as ArrayBuffer | Uint8Array | undefined;
      return v ? new Uint8Array(v instanceof Uint8Array ? v : v) : null;
    },
    async putBytes(key, bytes) {
      await req(store(BYTES, 'readwrite').put(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), key));
    },
    async deleteBytes(key) {
      await req(store(BYTES, 'readwrite').delete(key));
    },
    async getMeta() {
      const v = (await req(store(META, 'readonly').get(META_KEY))) as SheetsMeta | undefined;
      return v && v.schema === 'xray-sheets/1' ? v : null;
    },
    async putMeta(meta) {
      await req(store(META, 'readwrite').put(JSON.parse(JSON.stringify(meta)), META_KEY));
    },
  };
}

export class SheetStore {
  docs: SheetDoc[] = [];
  sheets: Sheet[] = [];
  thumbs = new Map<string, string>();
  private readonly cache = new Map<string, Uint8Array>();
  private backend: ByteBackend = new MemoryBackend();
  private ready: Promise<void> | null = null;

  constructor(private readonly open: () => Promise<ByteBackend | null> = () => openIdbBackend()) {}

  /** Whether the bytes survive a reload. */
  get persistent(): boolean {
    return this.backend.persistent;
  }

  /** Open the backend (once) and read the saved record. Returns the saved sketches for the caller to add to the session. */
  init(): Promise<SheetsMeta | null> {
    const run = async (): Promise<SheetsMeta | null> => {
      const b = await this.open().catch(() => null);
      if (b) this.backend = b;
      const meta = await this.backend.getMeta().catch(() => null);
      if (meta) {
        this.docs = meta.docs;
        this.sheets = meta.sheets.map((sh) => {
          const { placement, ...rest } = sh;
          const p = sanitizePlacement(placement);
          return p ? { ...rest, placement: p } : rest;
        });
        this.thumbs = new Map(Object.entries(meta.thumbs ?? {}));
      }
      return meta;
    };
    const p = run();
    this.ready = p.then(() => undefined);
    return p;
  }

  async whenReady(): Promise<void> {
    await this.ready;
  }

  doc(id: string): SheetDoc | undefined {
    return this.docs.find((d) => d.id === id);
  }
  sheet(id: string): Sheet | undefined {
    return this.sheets.find((s) => s.id === id);
  }

  async bytesOf(doc: SheetDoc): Promise<Uint8Array | null> {
    const c = this.cache.get(doc.bytesKey);
    if (c) return c;
    const b = await this.backend.getBytes(doc.bytesKey).catch(() => null);
    if (b) this.cache.set(doc.bytesKey, b);
    return b;
  }

  /** Keep the bytes (memory, and the backend when it can). */
  async putBytes(key: string, bytes: Uint8Array): Promise<boolean> {
    this.cache.set(key, bytes);
    try {
      await this.backend.putBytes(key, bytes);
      return this.backend.persistent;
    } catch {
      return false;
    }
  }

  async removeDoc(id: string): Promise<void> {
    const d = this.doc(id);
    if (!d) return;
    this.docs = this.docs.filter((x) => x.id !== id);
    for (const s of this.sheets.filter((x) => x.docId === id)) this.thumbs.delete(s.id);
    this.sheets = this.sheets.filter((x) => x.docId !== id);
    if (!this.docs.some((x) => x.bytesKey === d.bytesKey)) {
      this.cache.delete(d.bytesKey);
      await this.backend.deleteBytes(d.bytesKey).catch(() => undefined);
    }
  }

  async saveMeta(sets: readonly MarkupSet[]): Promise<void> {
    const meta: SheetsMeta = { schema: 'xray-sheets/1', docs: this.docs, sheets: this.sheets, thumbs: Object.fromEntries(this.thumbs), sets: sets.map((s) => JSON.parse(JSON.stringify(s)) as MarkupSet) };
    await this.backend.putMeta(meta).catch(() => undefined);
  }
}
