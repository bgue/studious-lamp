// Where revision data lives (design 4): IndexedDB database `xray-revisions` (snapshots, sessions, ghosts), with a memory backend for
// node and private windows. Nothing here reaches localStorage, URL parameters, share links, saved views, presets or packed pages
// (tests/revision-store.test.ts checks). Without IndexedDB the store works in memory and says so (`persistent` is false).

import { identityKey } from '../markup/scope';
import { revisionCandidates, decodeSnapshot, nameStemOfFile, recordOf } from './snapshot';
import type { CandidateTarget, RevisionCandidate } from './snapshot';
import { parseSession } from './session';
import type { ModelSnapshot, RevisionSession, SnapshotRecord } from './types';

export const DB_NAME = 'xray-revisions';
export const DB_VERSION = 1;
const SNAPSHOTS = 'snapshots';
const SESSIONS = 'sessions';
const GHOSTS = 'ghosts';

/** Retention (4.1): the newest snapshots per name stem, and a total size; the oldest go first. */
export const DEFAULT_RETENTION = { perStem: 3, maxBytes: 300 * 1024 * 1024 } as const;
/** The wait before a session change is saved (4.2). */
export const SESSION_SAVE_DELAY_MS = 500;

export interface RevisionBackend {
  readonly persistent: boolean;
  putSnapshot(r: SnapshotRecord): Promise<void>;
  getSnapshot(key: string): Promise<SnapshotRecord | null>;
  listSnapshots(): Promise<SnapshotRecord[]>;
  deleteSnapshot(key: string): Promise<void>;
  putSession(s: RevisionSession): Promise<void>;
  getSession(key: string): Promise<unknown | null>;
  listSessions(): Promise<unknown[]>;
  deleteSession(key: string): Promise<void>;
  putGhosts(key: string, blob: Blob): Promise<void>;
  getGhosts(key: string): Promise<Blob | null>;
  deleteGhosts(key: string): Promise<void>;
}

const jsonCopy = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export class MemoryBackend implements RevisionBackend {
  readonly persistent = false;
  private readonly snaps = new Map<string, SnapshotRecord>();
  private readonly sessions = new Map<string, string>();
  private readonly ghosts = new Map<string, Blob>();
  async putSnapshot(r: SnapshotRecord): Promise<void> { this.snaps.set(r.key, r); }
  async getSnapshot(key: string): Promise<SnapshotRecord | null> { return this.snaps.get(key) ?? null; }
  async listSnapshots(): Promise<SnapshotRecord[]> { return [...this.snaps.values()]; }
  async deleteSnapshot(key: string): Promise<void> { this.snaps.delete(key); }
  async putSession(s: RevisionSession): Promise<void> { this.sessions.set(s.key, JSON.stringify(s)); }
  async getSession(key: string): Promise<unknown | null> { const t = this.sessions.get(key); return t ? (JSON.parse(t) as unknown) : null; }
  async listSessions(): Promise<unknown[]> { return [...this.sessions.values()].map((t) => JSON.parse(t) as unknown); }
  async deleteSession(key: string): Promise<void> { this.sessions.delete(key); }
  async putGhosts(key: string, b: Blob): Promise<void> { this.ghosts.set(key, b); }
  async getGhosts(key: string): Promise<Blob | null> { return this.ghosts.get(key) ?? null; }
  async deleteGhosts(key: string): Promise<void> { this.ghosts.delete(key); }
}

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((res, rej) => {
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error ?? new Error('IndexedDB request failed'));
  });
}

/** IndexedDB backend; null when IndexedDB is missing, blocked or cannot be opened. */
export async function openIdbBackend(factory: IDBFactory | undefined = typeof indexedDB !== 'undefined' ? indexedDB : undefined): Promise<RevisionBackend | null> {
  if (!factory) return null;
  let db: IDBDatabase;
  try {
    db = await new Promise<IDBDatabase>((res, rej) => {
      const o = factory.open(DB_NAME, DB_VERSION);
      o.onupgradeneeded = () => {
        const d = o.result;
        d.createObjectStore(SNAPSHOTS, { keyPath: 'key' }).createIndex('name', 'name');
        d.createObjectStore(SESSIONS, { keyPath: 'key' }).createIndex('headKey', 'headKey');
        d.createObjectStore(GHOSTS);
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
    putSnapshot: async (r) => { await req(store(SNAPSHOTS, 'readwrite').put(r)); },
    getSnapshot: async (k) => ((await req(store(SNAPSHOTS, 'readonly').get(k))) as SnapshotRecord | undefined) ?? null,
    listSnapshots: async () => (await req(store(SNAPSHOTS, 'readonly').getAll())) as SnapshotRecord[],
    deleteSnapshot: async (k) => { await req(store(SNAPSHOTS, 'readwrite').delete(k)); },
    putSession: async (s) => { await req(store(SESSIONS, 'readwrite').put({ ...s, headKey: identityKey(s.head) })); },
    getSession: async (k) => ((await req(store(SESSIONS, 'readonly').get(k))) as unknown) ?? null,
    listSessions: async () => (await req(store(SESSIONS, 'readonly').getAll())) as unknown[],
    deleteSession: async (k) => { await req(store(SESSIONS, 'readwrite').delete(k)); },
    putGhosts: async (k, b) => { await req(store(GHOSTS, 'readwrite').put(b, k)); },
    getGhosts: async (k) => ((await req(store(GHOSTS, 'readonly').get(k))) as Blob | undefined) ?? null,
    deleteGhosts: async (k) => { await req(store(GHOSTS, 'readwrite').delete(k)); },
  };
}

/** IndexedDB when it opens, else memory. */
export async function openRevisionBackend(factory?: IDBFactory | null): Promise<RevisionBackend> {
  const idb = factory === null ? null : await openIdbBackend(factory);
  return idb ?? new MemoryBackend();
}

export class RevisionStore {
  readonly retention: { perStem: number; maxBytes: number };

  constructor(readonly backend: RevisionBackend = new MemoryBackend(), retention: Partial<{ perStem: number; maxBytes: number }> = {}) {
    this.retention = { ...DEFAULT_RETENTION, ...retention };
  }

  /** False when the data is kept for this session only (no IndexedDB). */
  get persistent(): boolean {
    return this.backend.persistent;
  }

  // -------- snapshots

  /** Encode, store, then evict by the retention rules. A snapshot that an open session refers to is not evicted. */
  async saveSnapshot(s: ModelSnapshot): Promise<SnapshotRecord> {
    const rec = await recordOf(s);
    await this.backend.putSnapshot(rec);
    await this.evict();
    return rec;
  }

  /** The record fields (the body is a Blob handle: it is read only by loadSnapshot). */
  records(): Promise<SnapshotRecord[]> {
    return this.backend.listSnapshots();
  }

  async loadSnapshot(key: string): Promise<ModelSnapshot | null> {
    const r = await this.backend.getSnapshot(key);
    return r ? decodeSnapshot(r.body) : null;
  }

  /** Stored snapshots that the model just opened may be a revision of (3.1). */
  async candidates(now: CandidateTarget): Promise<RevisionCandidate[]> {
    return revisionCandidates(await this.records(), now);
  }

  /** Drop snapshots beyond the retention. Returns the keys that were removed. */
  async evict(): Promise<string[]> {
    const protectedKeys = new Set<string>();
    for (const s of await this.sessions()) if (s.status === 'open') { protectedKeys.add(identityKey(s.base)); protectedKeys.add(identityKey(s.head)); }
    const all = (await this.backend.listSnapshots()).sort((a, b) => (a.savedAt < b.savedAt ? 1 : a.savedAt > b.savedAt ? -1 : 0)); // newest first
    const drop = new Set<string>();
    const perStem = new Map<string, number>();
    for (const r of all) {
      const stem = nameStemOfFile(r.name) || r.name;
      const n = (perStem.get(stem) ?? 0) + 1;
      perStem.set(stem, n);
      if (n > this.retention.perStem && !protectedKeys.has(r.key)) drop.add(r.key);
    }
    let total = all.filter((r) => !drop.has(r.key)).reduce((n, r) => n + r.size, 0);
    for (let i = all.length - 1; i >= 0 && total > this.retention.maxBytes; i--) {
      const r = all[i]!;
      if (drop.has(r.key) || protectedKeys.has(r.key)) continue;
      drop.add(r.key);
      total -= r.size;
    }
    for (const k of drop) await this.backend.deleteSnapshot(k);
    return [...drop];
  }

  // -------- sessions

  async saveSession(s: RevisionSession): Promise<void> {
    await this.backend.putSession(s);
  }

  async loadSession(key: string): Promise<RevisionSession | null> {
    const raw = await this.backend.getSession(key);
    return raw ? parseSession(raw).session : null;
  }

  async sessions(): Promise<RevisionSession[]> {
    const out: RevisionSession[] = [];
    for (const raw of await this.backend.listSessions()) { const p = parseSession(raw).session; if (p) out.push(p); }
    return out;
  }

  /** The open session whose head is this model (newest first), for "Resume revision review". Null when there is none. */
  async openSessionFor(head: Parameters<typeof identityKey>[0]): Promise<RevisionSession | null> {
    const k = identityKey(head);
    const list = (await this.sessions()).filter((s) => s.status === 'open' && identityKey(s.head) === k);
    list.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
    return list[0] ?? null;
  }

  async deleteSession(key: string): Promise<void> {
    await this.backend.deleteSession(key);
    await this.backend.deleteGhosts(key);
  }
}

/**
 * Saves a session `delayMs` after its last change (500 ms), and at once on `flush()` (call it on visibilitychange and pagehide).
 * Timers are injectable for tests.
 */
export class SessionSaver {
  private timer: unknown = null;
  private pending = false;
  private chain: Promise<void> = Promise.resolve();
  /** Resolves with an Error text when the last save failed (the UI says the walk is kept in memory only). */
  lastError: string | null = null;

  constructor(
    private readonly store: RevisionStore,
    private readonly get: () => RevisionSession | null,
    private readonly o: { delayMs?: number; setTimer?: (fn: () => void, ms: number) => unknown; clearTimer?: (t: unknown) => void } = {},
  ) {}

  schedule(): void {
    this.pending = true;
    const clear = this.o.clearTimer ?? ((t: unknown) => clearTimeout(t as ReturnType<typeof setTimeout>));
    if (this.timer !== null) clear(this.timer);
    const set = this.o.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
    this.timer = set(() => { this.timer = null; void this.flush(); }, this.o.delayMs ?? SESSION_SAVE_DELAY_MS);
  }

  flush(): Promise<void> {
    if (this.timer !== null) { (this.o.clearTimer ?? ((t: unknown) => clearTimeout(t as ReturnType<typeof setTimeout>)))(this.timer); this.timer = null; }
    if (!this.pending) return this.chain;
    this.pending = false;
    const s = this.get();
    if (!s) return this.chain;
    this.chain = this.chain.then(() => this.store.saveSession(s)).then(() => { this.lastError = null; }, (e: unknown) => { this.lastError = e instanceof Error ? e.message : String(e); });
    return this.chain;
  }
}
