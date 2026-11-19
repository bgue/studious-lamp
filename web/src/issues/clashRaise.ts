// Raise issues from the results of a check (penetrations, clearance): one issue per result, found again by check type plus the
// sorted GlobalId pair (clash.ts), so raising after a re-run adds only the new ones. Results the latest run no longer reports are
// marked "Not found in latest run" and can be closed in one go; they are never deleted. The work runs in small steps with a frame
// between them and reports progress, so the page stays responsive. The pure planning is in clash.ts. Docs: docs-features/issues.md.

import type { IssuesController } from './controller';
import { isOpenStatus } from './controller';
import { CLASH_CHECKS, FOUND_AGAIN_NOTE, MAX_BATCH, NOT_FOUND_NOTE, clashRef, countsOf, planClashRaise, topBySeverity } from './clash';
import type { ClashCheck, ClashCounts, ClashPlan, ClashResult, ExistingClash } from './clash';
import { frameCamera } from '../bcf/plan';
import { shapeFraction } from '../bcf/annotate';
import { nowIso, viewerToIfc } from '../bcf/model';
import type { BcfTopic, Vec3 } from '../bcf/model';
import { addMarkup, newMarkup } from '../markup/model';
import type { Attachment } from '../bcf/attach';

/** What a check lends to the raising: its results and whether it ran. Registered by the penetrations and clearance tools. */
export interface ClashSource {
  check: ClashCheck;
  /** Every result of the latest run (no filters), or null when the check has not run yet. */
  all(): ClashResult[] | null;
  /** The results the user means: the selected or filtered rows (all of them when nothing is chosen). */
  chosen(): ClashResult[];
  /** Whether the latest run could have found this pair (a run with another focus or scope says nothing about it). */
  inScope(a: string, b: string): boolean;
  /** Why raising is not possible now, or null. */
  disabledReason(): string | null;
  /** The source's results changed (a new run). */
  onChange(cb: () => void): () => void;
}

const sources = new Map<ClashCheck, ClashSource>();
export function registerClashSource(s: ClashSource): void {
  sources.set(s.check, s);
}
export function clashSource(check: ClashCheck): ClashSource | undefined {
  return sources.get(check);
}

/** Frames between steps: a frame, or 50 ms when the page is hidden and frames do not come. */
const frame = (): Promise<void> => new Promise((res) => {
  let done = false;
  const go = (): void => { if (!done) { done = true; res(); } };
  requestAnimationFrame(go);
  setTimeout(go, 50);
});

/** The issues of the loaded model that were raised from a check. */
export function existingClashes(c: IssuesController, check: ClashCheck): ExistingClash[] {
  const out: ExistingClash[] = [];
  for (const t of c.bcf.currentTopics) if (t.clash && t.clash.check === check) out.push({ topic: t.guid, ref: t.clash, open: isOpenStatus(t.topicStatus) });
  return out;
}

/** What raising would do now: counts of new, already raised and not found; null when the check has not run. */
export function previewClashes(c: IssuesController, src: ClashSource): ClashPlan | null {
  const all = src.all();
  if (!all) return null;
  return planClashRaise(src.check, existingClashes(c, src.check), all, src.chosen(), src.inScope);
}

export interface ClashReport {
  check: ClashCheck;
  counts: ClashCounts;
  /** Issue guids made now. */
  raised: string[];
  /** Results that could not be raised, with the reason. */
  failed: Array<{ title: string; error: string }>;
  /** Fresh results left out by the limit (top N by severity). */
  skipped: number;
  /** Old issues now marked "Not found in latest run", and old ones that came back. */
  flagged: number;
  backAgain: number;
  /** Issues not found in the latest run that are still open: offered for closing. */
  closable: number;
  cancelled: boolean;
}

export interface RaiseOptions {
  /** Raise only this many of the new results, the worst first. */
  limit?: number;
  /** Set `cancelled` to stop after the issue in hand. */
  signal?: { cancelled: boolean };
  onProgress?: (done: number, total: number) => void;
}

function sketchRect(c: IssuesController, topic: BcfTopic, r: ClashResult): void {
  const vp = topic.viewpoints[0];
  if (!vp) return;
  const set = c.sketchForViewpoint(topic, vp);
  if (!set) return;
  const view = c.bcf.shapeView(vp);
  if (!view) return;
  const shift = c.bcf.shift;
  const b = r.region;
  let u0 = 1, v0 = 1, u1 = 0, v1 = 0;
  let depth = 0;
  for (let i = 0; i < 8; i++) {
    const p: Vec3 = [i & 1 ? b[3] : b[0], i & 2 ? b[4] : b[1], i & 4 ? b[5] : b[2]];
    const f = shapeFraction(view, shift, p);
    u0 = Math.min(u0, f.u); u1 = Math.max(u1, f.u);
    v0 = Math.min(v0, f.v); v1 = Math.max(v1, f.v);
    depth += f.depth / 8;
  }
  // Inside the picture, and not smaller than a thumb.
  const clamp = (x: number): number => Math.min(0.97, Math.max(0.03, x));
  [u0, u1, v0, v1] = [clamp(u0), clamp(u1), clamp(v0), clamp(v1)];
  if (u1 - u0 < 0.05) { const m = (u0 + u1) / 2; u0 = clamp(m - 0.025); u1 = clamp(m + 0.025); }
  if (v1 - v0 < 0.05) { const m = (v0 + v1) / 2; v0 = clamp(m - 0.025); v1 = clamp(m + 0.025); }
  let attach: Attachment;
  if (r.attach.kind === 'penetration') attach = { kind: 'penetration', penetration: { mep: r.a, host: r.b } };
  else {
    attach = {
      kind: 'measurement',
      measurement: { kind: 'element', a: viewerToIfc(r.attach.pointA, shift), b: viewerToIfc(r.attach.pointB, shift), distance: r.attach.distanceM, label: r.attach.label, elementGuids: [r.a, r.b] },
    };
  }
  const author = c.markup.author.trim() || 'unknown';
  addMarkup(set, newMarkup('rect', { author, text: r.check === 'penetration' ? 'Penetration' : r.attach.kind === 'measurement' ? r.attach.label : 'Clearance', shape: { points: [[u0, v0], [u1, v1]], depth: Math.max(0.1, depth) }, attach, colour: 'red' }));
}

/** One result as an issue: title, both GlobalIds, a camera on the pair, a pin, the labels, and a sketch tied to the pair. */
export function raiseOne(c: IssuesController, r: ClashResult): BcfTopic {
  const bcf = c.bcf;
  const app = c.app;
  const cam = app.renderer.camera;
  const camera = frameCamera(r.region, cam.fov, cam.aspect);
  const topic = bcf.createTopic({
    title: r.title, description: r.description, type: 'Clash', priority: r.priority, labels: ['clash', r.check],
    globalIds: [r.a, r.b], camera, pin: r.location, snapshot: true,
  });
  topic.clash = clashRef(r.check, r.a, r.b);
  sketchRect(c, topic, r);
  c.markup.emit();
  c.syncAll();
  bcf.touch(topic);
  return topic;
}

/**
 * Raise the chosen results of a check. `limit` keeps only the worst N of the new ones. Old issues that the run no longer reports
 * get the "Not found in latest run" note (once); old ones that are reported again get a "Found again" note.
 */
export async function raiseClashes(c: IssuesController, src: ClashSource, o: RaiseOptions = {}): Promise<ClashReport> {
  const why = src.disabledReason();
  if (why) throw new Error(why);
  const plan = previewClashes(c, src);
  if (!plan) throw new Error('Run the check first');
  const counts = countsOf(plan);
  const todo = o.limit !== undefined ? topBySeverity(plan.fresh, o.limit) : topBySeverity(plan.fresh, plan.fresh.length);
  const report: ClashReport = { check: src.check, counts, raised: [], failed: [], skipped: plan.fresh.length - todo.length, flagged: 0, backAgain: 0, closable: plan.toClose.length, cancelled: false };
  const total = todo.length;
  o.onProgress?.(0, total);
  await c.batch(async () => {
    for (let i = 0; i < todo.length; i++) {
      if (o.signal?.cancelled) { report.cancelled = true; break; }
      const r = todo[i]!;
      try {
        report.raised.push(raiseOne(c, r).guid);
      } catch (e) {
        report.failed.push({ title: r.title, error: e instanceof Error ? e.message : String(e) });
      }
      o.onProgress?.(i + 1, total);
      await frame();
    }
  });
  // Notes on the old issues.
  for (const e of plan.toFlag) {
    const t = c.bcf.topic(e.topic);
    if (!t?.clash) continue;
    t.clash.missing = nowIso();
    c.bcf.addComment(t.guid, NOT_FOUND_NOTE);
    report.flagged++;
  }
  for (const e of plan.backAgain) {
    const t = c.bcf.topic(e.topic);
    if (!t?.clash) continue;
    delete t.clash.missing;
    c.bcf.addComment(t.guid, FOUND_AGAIN_NOTE);
    report.backAgain++;
  }
  if (report.raised.length) c.bcf.selectedTopic = null;
  c.bcf.setStatus(`${src.check}: ${report.raised.length} issue${report.raised.length === 1 ? '' : 's'} raised, ${counts.already} already raised, ${counts.resolved} not found in the latest run`);
  c.emit();
  return report;
}

/** Close the issues of a check that the latest run does not report any more (and that are still open). Returns how many. */
export function closeNotFound(c: IssuesController, src: ClashSource): number {
  const plan = previewClashes(c, src);
  if (!plan) return 0;
  let n = 0;
  for (const e of plan.toClose) {
    const t = c.bcf.topic(e.topic);
    if (!t) continue;
    c.bcf.setTopicStatus(t.guid, 'Closed');
    n++;
  }
  if (n) c.bcf.setStatus(`${n} issue${n === 1 ? '' : 's'} closed: not found in the latest ${src.check} run`);
  return n;
}

export { CLASH_CHECKS, MAX_BATCH };
