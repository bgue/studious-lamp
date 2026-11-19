// The issue report in the browser: the report model of the Issues tab's current list, the pictures (the snapshot of each issue and, for
// an issue whose sketch is tied to the model, its Plan and Section rendered through the derived-view switch), the PDF and the CSV.
//
// The Plan and Section pictures are rendered on the live canvas: for each issue the viewpoint is applied, the switch is put on Plan
// and on Section and the canvas is read in the same task. A copy of the canvas is laid over it for the whole run, so the view does
// not flicker, and the view you were in (camera, section, hides, look) is brought back at the end. Docs: docs-features/issues.md.

import type { IssuesController } from './controller';
import { isOpenStatus } from './controller';
import { buildReportModel, filterText, issuesCsv, reportFileName } from './reportModel';
import type { ReportModel } from './reportModel';
import { buildIssueReport } from './reportPdf';
import type { IssueImages, PageSize } from './reportPdf';
import type { ReportImage } from '../markup/report';
import { isSheetSet } from '../markup/model';
import type { BcfTopic, BcfViewpointRef } from '../bcf/model';

export interface ReportOptions {
  page: PageSize;
  /** Render a Plan and a Section for the issues whose sketch is tied to the model. */
  planSection: boolean;
  onProgress?: (text: string, done: number, total: number) => void;
}

export interface ReportResult {
  name: string;
  bytes: Uint8Array;
  issues: number;
  pages: number;
  /** How many pictures of each kind went into the file. */
  images: { snapshot: number; plan: number; section: number };
  ms: number;
}

interface ViewsApi {
  capture(name?: string): import('../views/model').SavedView;
  restoreView(v: import('../views/model').SavedView, o?: { animate?: boolean }): unknown;
}
const viewsApi = (): ViewsApi | null => (window as unknown as { __xrayViews?: ViewsApi }).__xrayViews ?? null;

/** The issues of the Issues tab's current list (status chip, search, this model) as a report model. */
export function reportModelOf(c: IssuesController, topics: readonly BcfTopic[] = c.visibleIssues()): ReportModel {
  const model = c.app.loaded?.model;
  const idOf = (g: string): number | undefined => model?.byGlobalId.get(g) ?? model?.byGlobalId.get(g.replace(/~\d+$/, ''));
  return buildReportModel({
    topics,
    modelName: c.app.modelName || 'model',
    ...(c.bcf.project.projectName ? { projectName: c.bcf.project.projectName } : {}),
    filter: filterText({ status: c.statusFilter, query: c.query }),
    date: new Date(),
    resolve: (g) => {
      const id = idOf(g);
      const e = id !== undefined ? model?.elements[id] : undefined;
      return e ? { name: e.name?.trim() || '', ifcClass: e.ifcClass } : null;
    },
    isOpen: isOpenStatus,
    tied: (t) => c.sketchesOf(t).some((s) => !isSheetSet(s) && c.views.tied(s)),
  });
}

export function issuesCsvOf(c: IssuesController): { name: string; text: string; issues: number } {
  const m = reportModelOf(c);
  return { name: reportFileName(m.modelName, m.date, 'csv'), text: issuesCsv(m), issues: m.issues.length };
}

const frame = (): Promise<void> => new Promise((res) => {
  let done = false;
  const go = (): void => { if (!done) { done = true; res(); } };
  requestAnimationFrame(go);
  setTimeout(go, 60);
});

/** Any image bytes (PNG or JPEG) as an RGB JPEG of at most `maxSide` pixels. Null when the browser cannot read them. */
export async function toJpeg(bytes: Uint8Array, mime: string, maxSide = 1100): Promise<ReportImage | null> {
  let bmp: ImageBitmap;
  try {
    bmp = await createImageBitmap(new Blob([bytes as Uint8Array<ArrayBuffer>], { type: mime }));
  } catch {
    return null;
  }
  try {
    return await canvasJpeg(bmp, bmp.width, bmp.height, maxSide);
  } finally {
    bmp.close?.();
  }
}

async function canvasJpeg(src: CanvasImageSource, w: number, h: number, maxSide: number): Promise<ReportImage | null> {
  if (!w || !h) return null;
  const s = Math.min(1, maxSide / Math.max(w, h));
  const cv = document.createElement('canvas');
  cv.width = Math.max(1, Math.round(w * s));
  cv.height = Math.max(1, Math.round(h * s));
  const g = cv.getContext('2d');
  if (!g) return null;
  g.fillStyle = '#e9edf2'; // under any transparent pixel
  g.fillRect(0, 0, cv.width, cv.height);
  g.drawImage(src, 0, 0, cv.width, cv.height);
  const blob = await new Promise<Blob | null>((res) => cv.toBlob(res, 'image/jpeg', 0.85));
  if (!blob) return null;
  return { bytes: new Uint8Array(await blob.arrayBuffer()), width: cv.width, height: cv.height };
}

/** A still copy of the canvas laid over it: what the user sees while the live view is switched for the pictures. */
function freezeCanvas(c: IssuesController): () => void {
  const src = c.app.canvas;
  const r = src.getBoundingClientRect();
  const cover = document.createElement('canvas');
  cover.width = src.width;
  cover.height = src.height;
  try {
    c.app.renderer.markDirty();
    c.app.renderer.render();
    cover.getContext('2d')?.drawImage(src, 0, 0);
  } catch {
    /* an empty cover is still better than a flicker */
  }
  cover.setAttribute('data-report-freeze', '');
  cover.style.cssText = `position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;z-index:15;pointer-events:auto;cursor:progress`;
  document.body.appendChild(cover);
  return () => cover.remove();
}

/** The canvas as it is now, as a JPEG of at most `maxSide` pixels (rendered and read in the same task). */
async function liveJpeg(c: IssuesController, maxSide: number): Promise<ReportImage | null> {
  const r = c.app.renderer;
  r.markDirty();
  r.render();
  const src = c.app.canvas;
  const cv = document.createElement('canvas');
  cv.width = src.width;
  cv.height = src.height;
  const g = cv.getContext('2d');
  if (!g) return null;
  g.drawImage(src, 0, 0);
  return canvasJpeg(cv, cv.width, cv.height, maxSide);
}

async function snapshotOf(c: IssuesController, t: BcfTopic): Promise<ReportImage | null> {
  const ref = t.viewpoints.find((v) => v.snapshot && !v.derived);
  if (!ref?.snapshot) return null;
  const mime = ref.snapshotMime ?? 'image/png';
  // With drawings on the viewpoint the picture has them burned in, as the issue's detail shows it.
  let bytes: Uint8Array = ref.snapshot;
  let m: string = mime;
  if (ref.annotations?.length) {
    const burned = await c.bcf.composeSnapshot(t, ref).catch(() => null);
    if (burned) { bytes = burned; m = ref.snapshotMime ?? 'image/png'; }
  }
  return toJpeg(bytes, m);
}

/** The issues of a list whose sketch is tied to the model: the topic, its sketch and the viewpoint of that sketch. */
function tiedSketches(c: IssuesController, topics: readonly BcfTopic[]): Array<{ topic: BcfTopic; set: import('../markup/model').MarkupSet; vp: BcfViewpointRef }> {
  const out: Array<{ topic: BcfTopic; set: import('../markup/model').MarkupSet; vp: BcfViewpointRef }> = [];
  for (const topic of topics) {
    for (const set of c.sketchesOf(topic)) {
      if (isSheetSet(set) || !c.views.tied(set)) continue;
      const vp = topic.viewpoints.find((v) => v.sketchId === set.id);
      if (vp) { out.push({ topic, set, vp }); break; }
    }
  }
  return out;
}

/**
 * Render the Plan and the Section of each tied issue. The live view is covered by a copy of itself meanwhile and put back after.
 * Returns the pictures by issue guid.
 */
export async function renderDerivedImages(c: IssuesController, topics: readonly BcfTopic[], onProgress?: (done: number, total: number) => void): Promise<Map<string, { plan?: ReportImage; section?: ReportImage }>> {
  const out = new Map<string, { plan?: ReportImage; section?: ReportImage }>();
  const list = tiedSketches(c, topics);
  if (!list.length || !c.app.loaded) return out;
  const views = viewsApi();
  const keep = views?.capture('before report');
  const keepActive = c.markup.activeId;
  const unfreeze = freezeCanvas(c);
  let lastSet: string | null = null;
  try {
    for (let i = 0; i < list.length; i++) {
      const { topic, set, vp } = list[i]!;
      onProgress?.(i, list.length);
      if (vp.data) c.bcf.applyViewpoint(topic.guid, vp.guid);
      const got: { plan?: ReportImage; section?: ReportImage } = {};
      for (const mode of ['plan', 'section'] as const) {
        if (!c.views.apply(set.id, mode)) continue;
        lastSet = set.id;
        try { c.app.controller.settle(); } catch { /* a test double without settle */ }
        await frame();
        await frame();
        const im = await liveJpeg(c, 640);
        if (im) got[mode] = im;
      }
      if (vp.data) c.bcf.clearViewpoint(true);
      if (got.plan || got.section) out.set(topic.guid, got);
    }
    onProgress?.(list.length, list.length);
  } finally {
    try { if (lastSet) c.views.apply(lastSet, '3d'); } catch { /* the view is put back below */ }
    try { c.bcf.clearViewpoint(true); } catch { /* nothing applied */ }
    if (keep) views?.restoreView(keep, { animate: false });
    c.markup.activeId = keepActive;
    c.app.renderer.markDirty();
    c.markup.emit(true);
    await frame();
    unfreeze();
  }
  return out;
}

/** The PDF of the Issues tab's current list. */
export async function makeIssueReport(c: IssuesController, o: ReportOptions): Promise<ReportResult> {
  const t0 = performance.now();
  const topics = c.visibleIssues();
  const model = reportModelOf(c, topics);
  const images = new Map<string, IssueImages>();
  const count = { snapshot: 0, plan: 0, section: 0 };
  const say = o.onProgress ?? (() => undefined);
  for (let i = 0; i < topics.length; i++) {
    say(`Pictures ${i + 1} / ${topics.length}`, i, topics.length);
    const im = await snapshotOf(c, topics[i]!);
    if (im) { images.set(topics[i]!.guid, { snapshot: im }); count.snapshot++; }
    if (i % 5 === 4) await frame();
  }
  if (o.planSection && c.app.loaded) {
    const derived = await renderDerivedImages(c, topics, (d, n) => say(`Plan and Section ${d} / ${n}`, d, n));
    for (const [guid, d] of derived) {
      const e = images.get(guid) ?? {};
      if (d.plan) { e.plan = d.plan; count.plan++; }
      if (d.section) { e.section = d.section; count.section++; }
      images.set(guid, e);
    }
  }
  say('Writing the PDF', topics.length, topics.length);
  const bytes = buildIssueReport(model, images, { page: o.page, author: c.markup.author.trim() });
  return { name: reportFileName(model.modelName, model.date, 'pdf'), bytes, issues: topics.length, pages: pageCountOf(bytes), images: count, ms: Math.round(performance.now() - t0) };
}

/** The page count written in the file's page tree. */
function pageCountOf(bytes: Uint8Array): number {
  const s = String.fromCharCode(...bytes.subarray(0, 4096)); // the page tree is the second object
  const m = /\/Type \/Pages \/Count (\d+)/.exec(s);
  return m ? Number(m[1]) : 0;
}
