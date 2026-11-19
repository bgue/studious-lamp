// Tile loading: a queue (nearest first, a few at a time), a memory cache with least-recently-used eviction, and a decoder. No three.js
// and no global fetch here (the fetcher is injected), so it is tested in Node. Nothing is requested until `request` is called, which
// the map layer does only while the map is on. Docs: docs-features/map.md.

export type TileImage = ImageBitmap | { width: number; height: number };

export interface TileEntry<T = TileImage> {
  key: string;
  state: 'loading' | 'ready' | 'error';
  image?: T;
  /** performance.now() of a failure, so a failed tile is asked again only after a pause. */
  failedAt?: number;
  /** For the layer: what it made from the image (a texture), disposed on eviction. */
  extra?: { dispose(): void } | null;
}

export type TileFetcher<T> = (url: string, signal: AbortSignal) => Promise<T>;

export interface TileCacheOptions<T> {
  fetcher: TileFetcher<T>;
  /** Most tiles kept (loaded ones; the oldest unused go first). */
  capacity?: number;
  /** Most requests in flight. */
  concurrency?: number;
  /** Milliseconds before a failed tile is asked again. */
  retryAfterMs?: number;
  now?: () => number;
  onChange?: () => void;
  onEvict?: (e: TileEntry<T>) => void;
}

interface Waiting { key: string; url: string; priority: number }

export class TileCache<T = TileImage> {
  readonly entries = new Map<string, TileEntry<T>>();
  /** Counts for tests and the status line. */
  stats = { requested: 0, loaded: 0, failed: 0, evicted: 0 };
  private readonly queue: Waiting[] = [];
  private inflight = 0;
  private abort = new AbortController();
  private readonly capacity: number;
  private readonly concurrency: number;
  private readonly retryAfterMs: number;
  private readonly now: () => number;

  constructor(private readonly o: TileCacheOptions<T>) {
    this.capacity = o.capacity ?? 256;
    this.concurrency = o.concurrency ?? 6;
    this.retryAfterMs = o.retryAfterMs ?? 15000;
    this.now = o.now ?? (() => performance.now());
  }

  /**
   * The entry for a key, and a request when it is not there (or failed a while ago). `priority`: lower is sooner. Touching an entry
   * makes it the most recently used.
   */
  request(key: string, url: string, priority = 0): TileEntry<T> {
    let e = this.entries.get(key);
    if (e) {
      // most recently used goes last
      this.entries.delete(key);
      this.entries.set(key, e);
      if (e.state === 'error' && this.now() - (e.failedAt ?? 0) >= this.retryAfterMs) {
        e.state = 'loading';
        this.enqueue(key, url, priority);
      } else if (e.state === 'loading') {
        const w = this.queue.find((q) => q.key === key);
        if (w) w.priority = Math.min(w.priority, priority);
      }
      return e;
    }
    e = { key, state: 'loading' };
    this.entries.set(key, e);
    this.enqueue(key, url, priority);
    return e;
  }

  get(key: string): TileEntry<T> | undefined {
    return this.entries.get(key);
  }

  private enqueue(key: string, url: string, priority: number): void {
    this.queue.push({ key, url, priority });
    this.pump();
  }

  private pump(): void {
    while (this.inflight < this.concurrency && this.queue.length) {
      let best = 0;
      for (let i = 1; i < this.queue.length; i++) if (this.queue[i]!.priority < this.queue[best]!.priority) best = i;
      const w = this.queue.splice(best, 1)[0]!;
      const e = this.entries.get(w.key);
      if (!e) continue; // evicted while it waited
      this.inflight++;
      this.stats.requested++;
      const signal = this.abort.signal;
      this.o.fetcher(w.url, signal).then((img) => {
        if (signal.aborted) return;
        e.state = 'ready';
        e.image = img;
        this.stats.loaded++;
      }, () => {
        if (signal.aborted) return;
        e.state = 'error';
        e.failedAt = this.now();
        this.stats.failed++;
      }).finally(() => {
        if (!signal.aborted) {
          this.inflight--;
          this.evict();
          this.o.onChange?.();
          this.pump();
        }
      });
    }
  }

  /** Drop the oldest finished entries beyond the capacity (never one that is still loading). */
  private evict(): void {
    if (this.entries.size <= this.capacity) return;
    for (const [k, e] of this.entries) {
      if (this.entries.size <= this.capacity) break;
      if (e.state === 'loading') continue;
      this.entries.delete(k);
      this.stats.evicted++;
      this.o.onEvict?.(e);
    }
  }

  /** Everything not in flight yet is dropped from the queue, and requests in flight are aborted (a provider change, the map turned off). */
  cancelAll(): void {
    this.abort.abort();
    this.abort = new AbortController();
    this.queue.length = 0;
    this.inflight = 0;
    for (const [k, e] of this.entries) if (e.state === 'loading') this.entries.delete(k);
  }

  /** Forget every tile (a provider change). */
  clear(): void {
    this.cancelAll();
    for (const e of this.entries.values()) this.o.onEvict?.(e);
    this.entries.clear();
  }

  get pending(): number {
    return this.queue.length + this.inflight;
  }
}

/** The browser fetcher: CORS request without credentials, decoded to an ImageBitmap. */
export function browserFetcher(): TileFetcher<ImageBitmap> {
  return async (url, signal) => {
    const r = await fetch(url, { mode: 'cors', credentials: 'omit', signal, referrerPolicy: 'strict-origin-when-cross-origin' });
    if (!r.ok) throw new Error(`tile ${r.status}`);
    const blob = await r.blob();
    return createImageBitmap(blob);
  };
}
