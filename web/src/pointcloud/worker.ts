// Web Worker: parse and decimate a point cloud off the main thread. Typed arrays are transferred.

import { CloudSession } from './session';
import type { Shown } from './types';

export type WorkerIn =
  | { type: 'load'; buffer: ArrayBuffer; name: string; budget: number; seed: number }
  | { type: 'decimate'; budget: number; seed: number }
  | { type: 'dispose' };

const session = new CloudSession();
const ctx = self as unknown as { postMessage(m: unknown, t?: Transferable[]): void; onmessage: ((e: MessageEvent<WorkerIn>) => void) | null };

function transferable(shown: Shown): { shown: Shown; list: Transferable[] } {
  const own = session.shares(shown);
  const s: Shown = {
    count: shown.count,
    positions: own ? shown.positions.slice() : shown.positions,
    colors: own && shown.colors ? shown.colors.slice() : shown.colors,
    intensity: own && shown.intensity ? shown.intensity.slice() : shown.intensity,
    classification: own && shown.classification ? shown.classification.slice() : shown.classification,
  };
  const list: Transferable[] = [s.positions.buffer];
  if (s.colors) list.push(s.colors.buffer);
  if (s.intensity) list.push(s.intensity.buffer);
  if (s.classification) list.push(s.classification.buffer);
  return { shown: s, list };
}

ctx.onmessage = (e) => {
  const m = e.data;
  try {
    if (m.type === 'load') {
      let last = 0;
      const info = session.load(m.buffer, m.name, (f, stage) => {
        const now = performance.now();
        if (now - last > 60) {
          last = now;
          ctx.postMessage({ type: 'progress', f, stage });
        }
      });
      ctx.postMessage({ type: 'progress', f: 1, stage: 'decimate' });
      const r = session.decimate(m.budget, m.seed);
      const t = transferable(r.shown);
      ctx.postMessage({ type: 'loaded', info, shown: t.shown, decimateMs: r.ms }, t.list);
    } else if (m.type === 'decimate') {
      const r = session.decimate(m.budget, m.seed);
      const t = transferable(r.shown);
      ctx.postMessage({ type: 'decimated', shown: t.shown, decimateMs: r.ms }, t.list);
    } else if (m.type === 'dispose') {
      session.dispose();
    }
  } catch (err) {
    ctx.postMessage({ type: 'error', message: err instanceof Error ? err.message : String(err) });
  }
};
