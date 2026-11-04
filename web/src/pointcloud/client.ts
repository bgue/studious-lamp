// Main-thread side of the loader: runs the CloudSession in a Web Worker for files over WORKER_THRESHOLD bytes (with
// progress), inline otherwise, and inline when workers are unavailable (tests, single-file bundles).

import { CloudSession } from './session';
import type { LoadInfo, ProgressFn, Shown } from './types';
import type { WorkerIn } from './worker';
import { createCloudWorker } from './workerRuntime';

export const WORKER_THRESHOLD = 5 * 1024 * 1024;

export interface LoadResult {
  info: LoadInfo;
  shown: Shown;
  decimateMs: number;
  /** 'worker' or 'inline'. */
  mode: 'worker' | 'inline';
}

type WorkerOut =
  | { type: 'progress'; f: number; stage: string }
  | { type: 'loaded'; info: LoadInfo; shown: Shown; decimateMs: number }
  | { type: 'decimated'; shown: Shown; decimateMs: number }
  | { type: 'error'; message: string };

export class PointCloudLoader {
  private worker: Worker | null = null;
  private session: CloudSession | null = null;
  private pending: { resolve(m: WorkerOut): void; reject(e: Error): void; onProgress?: ProgressFn } | null = null;

  get mode(): 'worker' | 'inline' | 'none' {
    return this.worker ? 'worker' : this.session ? 'inline' : 'none';
  }

  async load(buffer: ArrayBuffer, name: string, opts: { budget: number; seed?: number; onProgress?: ProgressFn; inline?: boolean }): Promise<LoadResult> {
    this.dispose();
    const seed = opts.seed ?? 1;
    const wantWorker = !opts.inline && buffer.byteLength > WORKER_THRESHOLD && typeof Worker !== 'undefined';
    if (wantWorker) {
      try {
        const w = createCloudWorker();
        this.worker = w;
        w.onmessage = (e: MessageEvent<WorkerOut>) => this.onMessage(e.data);
        w.onerror = (e) => {
          const p = this.pending;
          this.pending = null;
          p?.reject(new Error(`point cloud worker failed: ${e.message || 'could not start'}`));
        };
        const copy = buffer.slice(0); // keep the caller's buffer intact for the inline fallback
        const m = await this.post({ type: 'load', buffer: copy, name, budget: opts.budget, seed }, [copy], opts.onProgress);
        if (m.type === 'loaded') return { info: m.info, shown: m.shown, decimateMs: m.decimateMs, mode: 'worker' };
      } catch (e) {
        if (e instanceof Error && !/worker failed/.test(e.message)) {
          this.dispose();
          throw e;
        }
        this.worker?.terminate();
        this.worker = null; // fall through to inline
      }
    }
    const s = (this.session = new CloudSession());
    await tick();
    const info = s.load(buffer, name, opts.onProgress);
    await tick();
    const r = s.decimate(opts.budget, seed);
    return { info, shown: r.shown, decimateMs: r.ms, mode: 'inline' };
  }

  /** Re-decimate the loaded cloud to another budget. */
  async decimate(budget: number, seed = 1): Promise<{ shown: Shown; decimateMs: number }> {
    if (this.worker) {
      const m = await this.post({ type: 'decimate', budget, seed }, []);
      if (m.type === 'decimated') return { shown: m.shown, decimateMs: m.decimateMs };
      throw new Error('unexpected worker reply');
    }
    if (!this.session) throw new Error('no point cloud loaded');
    const r = this.session.decimate(budget, seed);
    return { shown: r.shown, decimateMs: r.ms };
  }

  private post(msg: WorkerIn, transfer: Transferable[], onProgress?: ProgressFn): Promise<WorkerOut> {
    return new Promise((resolve, reject) => {
      this.pending = { resolve, reject, onProgress };
      this.worker!.postMessage(msg, transfer);
    });
  }

  private onMessage(m: WorkerOut): void {
    const p = this.pending;
    if (!p) return;
    if (m.type === 'progress') p.onProgress?.(m.f, m.stage);
    else if (m.type === 'error') {
      this.pending = null;
      p.reject(new Error(m.message));
    } else {
      this.pending = null;
      p.resolve(m);
    }
  }

  dispose(): void {
    if (this.worker) {
      this.worker.postMessage({ type: 'dispose' } satisfies WorkerIn);
      this.worker.terminate();
      this.worker = null;
    }
    this.session?.dispose();
    this.session = null;
    this.pending = null;
  }
}

const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0));
