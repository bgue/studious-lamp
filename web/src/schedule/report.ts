// The link report: how well the schedule and the model are linked, what is left over, and the logic and spatial sanity checks
// of docs/design/4d-xer-animation.md section 8. `buildReport` makes plain data; `renderReportHtml` a self-contained page (inline
// CSS, no external assets). Pure.

import { equalsQuery } from '../query';
import type { FourDConfig, FourDLinks, Schedule, ScheduleTask } from './types';
import { bboxVolume, storeyOrder } from './model';
import type { FourDModel } from './model';
import { formatDate, isBuildType, isMilestone, parseLocal, plannedSpan } from './planTime';

export type CheckSeverity = 'error' | 'warning' | 'info';
export type CheckKind =
  | 'open-start' | 'open-finish' | 'actual-after-data-date' | 'out-of-sequence' | 'negative-float' | 'date-inversion' | 'built-before-support';

export interface ReportCheck { kind: CheckKind; severity: CheckSeverity; message: string; refs: string[] }

export interface CoverageRow { name: string; activities: number; activitiesLinked: number; elements: number }

export interface LinkReport {
  schedule: { project: string; sourceHash: string; dataDate?: string };
  model: { name: string; identityKey: string };
  linksId: string;
  coverage: {
    elements: {
      total: number; existing: number; considered: number; linked: number; tied: number; unlinked: number;
      byCount: number; volumeTotal: number; volumeLinked: number; byVolume: number;
    };
    activities: { total: number; linked: number; suggestedOnly: number; unlinked: number; ratio: number };
    byTrade: CoverageRow[];
    byWbs: CoverageRow[];
  };
  unlinkedElements: Array<{ ifcClass: string; storey: string | null; count: number; volume: number; query: string; globalIds: string[] }>;
  unlinkedActivities: Array<{ code: string; name: string; wbsPath: string; location?: string; trade?: string; zone?: string; hasSuggestion: boolean }>;
  ties: Array<{ element: string; name: string; candidates: Array<{ code: string; name: string }> }>;
  lowConfidence: Array<{ activity: string; name: string; confidence: number; source: string; status: string; elements: number; reasons: string[] }>;
  checks: ReportCheck[];
}

export interface ReportOptions {
  /** Links below this confidence, and every proposed link, are listed for review (default 0.6). */
  minConfidence?: number;
  config?: FourDConfig;
  /** Largest number of GlobalIds listed per unlinked group (default 20). */
  maxIds?: number;
}

const pct = (a: number, b: number): number => (b > 0 ? a / b : 1);

export function buildReport(schedule: Schedule, links: FourDLinks, model: FourDModel, opts: ReportOptions = {}): LinkReport {
  const minConf = opts.minConfidence ?? 0.6;
  const maxIds = opts.maxIds ?? 20;
  const taskByCode = new Map(schedule.tasks.map((t) => [t.code, t]));
  const elByGid = new Map(model.elements.map((e) => [e.globalId, e]));
  const meta = new Map((links.model_elements ?? []).map((e) => [e.global_id, e]));
  const actMeta = new Map((links.activities ?? []).map((a) => [a.task_code, a]));
  const building = schedule.tasks.filter(isBuildType);

  // accepted links
  const linkedEls = new Set<string>();
  const taskOf = new Map<string, ScheduleTask>();
  const linkedTasks = new Set<string>();
  const removed = new Set<string>();
  for (const l of links.links ?? []) {
    if (l.status !== 'accepted') continue;
    if (l.role === 'remove') { l.elements.forEach((g) => removed.add(g)); continue; }
    if (l.elements.length) linkedTasks.add(l.activity);
    for (const g of l.elements) { linkedEls.add(g); const t = taskByCode.get(l.activity); if (t && !taskOf.has(g)) taskOf.set(g, t); }
  }
  const tied = new Set((links.ties ?? []).map((t) => t.element));
  const proposedTasks = new Set((links.links ?? []).filter((l) => l.status === 'proposed' && l.role === 'build' && l.elements.length).map((l) => l.activity));

  // elements
  const existing = new Set(model.elements.filter((e) => meta.get(e.globalId)?.existing).map((e) => e.globalId));
  const considered = model.elements.filter((e) => !existing.has(e.globalId));
  const consideredLinked = considered.filter((e) => linkedEls.has(e.globalId) || removed.has(e.globalId));
  const vol = (es: typeof considered): number => es.reduce((s, e) => s + bboxVolume(e.bbox), 0);
  const volumeTotal = vol(considered);
  const volumeLinked = vol(consideredLinked);
  const existingQuery = opts.config?.model.existing;
  const left = considered.filter((e) => !linkedEls.has(e.globalId) && !removed.has(e.globalId));

  // unlinked groups by class + storey
  const groups = new Map<string, { ifcClass: string; storey: string | null; els: typeof left }>();
  for (const e of left) {
    const key = `${e.ifcClass}\u0000${e.storey ?? ''}`;
    if (!groups.has(key)) groups.set(key, { ifcClass: e.ifcClass, storey: e.storey ?? null, els: [] });
    groups.get(key)!.els.push(e);
  }
  const unlinkedElements = [...groups.values()].map((g) => ({
    ifcClass: g.ifcClass, storey: g.storey, count: g.els.length, volume: round(vol(g.els)),
    query: `${equalsQuery('class', g.ifcClass)} AND ${equalsQuery('storey', g.storey)}${existingQuery && model.elements.some((e) => existing.has(e.globalId) && e.ifcClass === g.ifcClass && (e.storey ?? null) === g.storey) ? ` AND NOT (${existingQuery})` : ''}`,
    globalIds: g.els.slice(0, maxIds).map((e) => e.globalId),
  })).sort((a, b) => b.count - a.count || a.ifcClass.localeCompare(b.ifcClass) || String(a.storey).localeCompare(String(b.storey)));

  // activities
  const unlinkedTasks = building.filter((t) => !linkedTasks.has(t.code));
  const unlinkedActivities = unlinkedTasks.map((t) => {
    const a = actMeta.get(t.code);
    return { code: t.code, name: t.name, wbsPath: t.wbsPath.join('/'), ...(a?.location !== undefined ? { location: a.location } : {}), ...(a?.trade !== undefined ? { trade: a.trade } : {}), ...(a?.zone !== undefined ? { zone: a.zone } : {}), hasSuggestion: proposedTasks.has(t.code) };
  });

  // by trade and by first WBS level
  const elementsOfTask = new Map<string, number>();
  for (const l of links.links ?? []) if (l.status === 'accepted' && l.role === 'build') elementsOfTask.set(l.activity, (elementsOfTask.get(l.activity) ?? 0) + l.elements.length);
  const rows = (keyOf: (t: ScheduleTask) => string): CoverageRow[] => {
    const m = new Map<string, CoverageRow>();
    for (const t of building) {
      const k = keyOf(t);
      const r = m.get(k) ?? { name: k, activities: 0, activitiesLinked: 0, elements: 0 };
      r.activities++;
      if (linkedTasks.has(t.code)) r.activitiesLinked++;
      r.elements += elementsOfTask.get(t.code) ?? 0;
      m.set(k, r);
    }
    return [...m.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  };
  const byTrade = rows((t) => actMeta.get(t.code)?.trade ?? '(no trade)');
  const byWbs = rows((t) => t.wbsPath[0] ?? '(no WBS)');

  // ties
  const ties = (links.ties ?? []).map((t) => ({
    element: t.element, name: elByGid.get(t.element)?.name ?? '',
    candidates: t.candidates.map((c) => ({ code: c, name: taskByCode.get(c)?.name ?? '' })),
  }));

  const lowConfidence = (links.links ?? [])
    .filter((l) => l.status !== 'rejected' && l.status !== 'superseded' && (l.status === 'proposed' || (l.confidence ?? 1) < minConf))
    .map((l) => ({ activity: l.activity, name: taskByCode.get(l.activity)?.name ?? '', confidence: l.confidence ?? 1, source: l.source ?? '', status: l.status ?? '', elements: l.elements.length, reasons: l.reasons ?? [] }))
    .sort((a, b) => a.confidence - b.confidence || a.activity.localeCompare(b.activity));

  const checks = [...logicChecks(schedule), ...spatialChecks(schedule, links, model, taskOf)];

  return {
    schedule: { project: schedule.project.shortName, sourceHash: schedule.sourceHash, ...(schedule.project.dataDate ? { dataDate: schedule.project.dataDate } : {}) },
    model: { name: model.name, identityKey: model.identityKey },
    linksId: links.id,
    coverage: {
      elements: {
        total: model.elements.length, existing: existing.size, considered: considered.length, linked: consideredLinked.length,
        tied: considered.filter((e) => tied.has(e.globalId)).length, unlinked: left.length,
        byCount: pct(consideredLinked.length, considered.length), volumeTotal: round(volumeTotal), volumeLinked: round(volumeLinked), byVolume: pct(volumeLinked, volumeTotal),
      },
      activities: { total: building.length, linked: building.length - unlinkedTasks.length, suggestedOnly: unlinkedTasks.filter((t) => proposedTasks.has(t.code)).length, unlinked: unlinkedTasks.length, ratio: pct(building.length - unlinkedTasks.length, building.length) },
      byTrade, byWbs,
    },
    unlinkedElements, unlinkedActivities, ties, lowConfidence, checks,
  };
}

const round = (n: number): number => Math.round(n * 1000) / 1000;

// ---------------------------------------------------------------- logic checks

function logicChecks(schedule: Schedule): ReportCheck[] {
  const out: ReportCheck[] = [];
  const dd = parseLocal(schedule.project.dataDate);
  const byId = new Map(schedule.tasks.map((t) => [t.id, t]));
  const preds = new Map<string, typeof schedule.relations>();
  const hasSucc = new Set<string>();
  for (const r of schedule.relations) {
    if (!preds.has(r.taskId)) preds.set(r.taskId, []);
    preds.get(r.taskId)!.push(r);
    hasSucc.add(r.predecessorId);
  }
  const flag = (kind: CheckKind, severity: CheckSeverity, tasks: ScheduleTask[], message: (n: number) => string): void => {
    if (tasks.length) out.push({ kind, severity, message: message(tasks.length), refs: tasks.map((t) => t.code) });
  };
  const logicTasks = schedule.tasks.filter((t) => isBuildType(t) || isMilestone(t));
  if (schedule.relations.length) {
    flag('open-start', 'warning', logicTasks.filter((t) => !preds.has(t.id) && isBuildType(t)), (n) => `${n} activit${n === 1 ? 'y has' : 'ies have'} no predecessor (open start)`);
    flag('open-finish', 'warning', logicTasks.filter((t) => !hasSucc.has(t.id) && isBuildType(t)), (n) => `${n} activit${n === 1 ? 'y has' : 'ies have'} no successor (open end)`);
  }
  if (dd !== undefined) {
    flag('actual-after-data-date', 'error', schedule.tasks.filter((t) => {
      const s = parseLocal(t.dates.actualStart);
      const e = parseLocal(t.dates.actualEnd);
      return (s !== undefined && s > dd) || (e !== undefined && e > dd);
    }), (n) => `${n} activit${n === 1 ? 'y has' : 'ies have'} an actual date after the data date`);
  }
  const oos: ScheduleTask[] = [];
  for (const t of schedule.tasks) {
    if (!t.dates.actualStart) continue;
    for (const r of preds.get(t.id) ?? []) {
      const p = byId.get(r.predecessorId);
      if (!p) continue;
      if ((r.type === 'FS' && !p.dates.actualEnd) || (r.type === 'SS' && !p.dates.actualStart)) { oos.push(t); break; }
    }
  }
  flag('out-of-sequence', 'warning', oos, (n) => `${n} activit${n === 1 ? 'y' : 'ies'} started before ${n === 1 ? 'a' : ''} predecessor(s) allowed (out-of-sequence progress)`);
  flag('negative-float', 'warning', schedule.tasks.filter((t) => (t.totalFloatHours ?? 0) < 0), (n) => `${n} activit${n === 1 ? 'y has' : 'ies have'} negative float`);
  const inv = (a?: string, b?: string): boolean => { const x = parseLocal(a); const y = parseLocal(b); return x !== undefined && y !== undefined && y < x; };
  flag('date-inversion', 'error', schedule.tasks.filter((t) => inv(t.dates.earlyStart, t.dates.earlyEnd) || inv(t.dates.actualStart, t.dates.actualEnd) || inv(t.dates.targetStart, t.dates.targetEnd)),
    (n) => `${n} activit${n === 1 ? 'y finishes' : 'ies finish'} before ${n === 1 ? 'it starts' : 'they start'}`);
  return out;
}

// ---------------------------------------------------------------- spatial checks

/** An element that starts before the slab of the storey below it (matched by plan position when both have bboxes). */
function spatialChecks(schedule: Schedule, links: FourDLinks, model: FourDModel, taskOf: Map<string, ScheduleTask>): ReportCheck[] {
  const order = storeyOrder(model);
  const rank = new Map(order.map((s, i) => [s, i]));
  const slabsBy = new Map<number, typeof model.elements>();
  const existing = new Set((links.model_elements ?? []).filter((e) => e.existing).map((e) => e.global_id));
  for (const e of model.elements) {
    if (!e.ifcClass.startsWith('IfcSlab') || e.storey === undefined || !taskOf.has(e.globalId) || existing.has(e.globalId)) continue;
    const r = rank.get(e.storey);
    if (r === undefined) continue;
    if (!slabsBy.has(r)) slabsBy.set(r, []);
    slabsBy.get(r)!.push(e);
  }
  const startOf = (t: ScheduleTask): number | undefined => plannedSpan(t)?.start;
  const groups = new Map<string, { msg: string; refs: string[]; elements: string[] }>();
  for (const e of model.elements) {
    const t = taskOf.get(e.globalId);
    if (!t || e.storey === undefined || existing.has(e.globalId)) continue;
    const r = rank.get(e.storey);
    if (r === undefined || r === 0) continue;
    const slabs = (slabsBy.get(r - 1) ?? []).filter((s) => {
      if (!e.bbox || !s.bbox) return true;
      return e.bbox[0] < s.bbox[3] && e.bbox[3] > s.bbox[0] && e.bbox[1] < s.bbox[4] && e.bbox[4] > s.bbox[1];
    });
    if (!slabs.length) continue;
    const start = startOf(t);
    if (start === undefined) continue;
    let best: { slab: typeof model.elements[number]; task: ScheduleTask; start: number } | undefined;
    for (const s of slabs) {
      const st = taskOf.get(s.globalId)!;
      const ss = startOf(st);
      if (ss === undefined) continue;
      if (!best || ss < best.start) best = { slab: s, task: st, start: ss };
    }
    if (!best || best.task.code === t.code || start >= best.start) continue;
    const key = `${t.code}>${best.task.code}`;
    const g = groups.get(key) ?? { msg: `${t.code} '${t.name}' on ${e.storey} starts ${formatDate(start)}, before the ${order[r - 1]} slab (${best.task.code} '${best.task.name}') starts ${formatDate(best.start)}`, refs: [t.code, best.task.code], elements: [] };
    g.elements.push(e.globalId);
    groups.set(key, g);
  }
  return [...groups.values()].map((g) => ({
    kind: 'built-before-support' as const, severity: 'warning' as const,
    message: `${g.msg}: ${g.elements.length} element${g.elements.length === 1 ? '' : 's'}`,
    refs: [...g.refs, ...g.elements.slice(0, 10)],
  }));
}

// ---------------------------------------------------------------- HTML

const esc = (s: unknown): string => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const p1 = (x: number): string => `${(x * 100).toFixed(1)}%`;

/** A self-contained HTML page (inline CSS, no scripts, no external assets). */
export function renderReportHtml(r: LinkReport): string {
  const c = r.coverage;
  const table = (head: string[], rows: string[][]): string =>
    rows.length ? `<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((v) => `<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '<p class="none">None.</p>';
  const cov = (rows: CoverageRow[]): string => table(['Name', 'Activities', 'Linked', 'Elements'], rows.map((x) => [esc(x.name), String(x.activities), String(x.activitiesLinked), String(x.elements)]));
  const sev = (s: CheckSeverity): string => `<span class="sev ${s}">${s}</span>`;
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>4D link report: ${esc(r.model.name)} / ${esc(r.schedule.project)}</title>
<style>
:root{--bg:#fff;--fg:#1d2330;--mut:#5d6677;--line:#d9dde6;--card:#f5f7fa;--ok:#1a7f4b;--warn:#a15c00;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#14171d;--fg:#e6e9ef;--mut:#9aa3b2;--line:#2b303a;--card:#1c2028;--ok:#4cc38a;--warn:#e0a040;--err:#f2736b}}
body{font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:24px;max-width:1100px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}p.meta{color:var(--mut);margin:0}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:150px}
.card b{display:block;font-size:20px}.card span{color:var(--mut)}
table{border-collapse:collapse;width:100%;margin:6px 0}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mut);font-weight:600}
code{font:12px ui-monospace,monospace;background:var(--card);padding:1px 4px;border-radius:4px}.none{color:var(--mut)}
.sev{font-weight:600}.sev.error{color:var(--err)}.sev.warning{color:var(--warn)}.sev.info{color:var(--mut)}
</style></head><body>
<h1>4D link report</h1>
<p class="meta">Model ${esc(r.model.name)} (${esc(r.model.identityKey)}) &middot; schedule ${esc(r.schedule.project)}, hash ${esc(r.schedule.sourceHash.slice(0, 12))}${r.schedule.dataDate ? `, data date ${esc(r.schedule.dataDate)}` : ''} &middot; links ${esc(r.linksId)}</p>
<div class="cards">
<div class="card"><b>${p1(c.elements.byCount)}</b><span>elements linked (${c.elements.linked} of ${c.elements.considered})</span></div>
<div class="card"><b>${p1(c.elements.byVolume)}</b><span>by bbox volume (${c.elements.volumeLinked} of ${c.elements.volumeTotal} m3)</span></div>
<div class="card"><b>${p1(c.activities.ratio)}</b><span>activities linked (${c.activities.linked} of ${c.activities.total})</span></div>
<div class="card"><b>${c.elements.existing}</b><span>existing elements</span></div>
<div class="card"><b>${r.ties.length}</b><span>ties</span></div>
</div>
<h2>Coverage by trade</h2>${cov(c.byTrade)}
<h2>Coverage by WBS</h2>${cov(c.byWbs)}
<h2>Elements with no activity (${c.elements.unlinked})</h2>
${table(['Class', 'Storey', 'Elements', 'Volume m3', 'Query'], r.unlinkedElements.map((g) => [esc(g.ifcClass), esc(g.storey ?? '(none)'), String(g.count), String(g.volume), `<code>${esc(g.query)}</code>`]))}
<h2>Activities with no elements (${r.unlinkedActivities.length})</h2>
${table(['Activity', 'Name', 'WBS', 'Location', 'Trade', 'Zone', 'Suggestion'], r.unlinkedActivities.map((a) => [esc(a.code), esc(a.name), esc(a.wbsPath), esc(a.location ?? ''), esc(a.trade ?? ''), esc(a.zone ?? ''), a.hasSuggestion ? 'proposed' : '']))}
<h2>Ties (${r.ties.length})</h2>
${table(['Element', 'Name', 'Candidate activities'], r.ties.map((t) => [`<code>${esc(t.element)}</code>`, esc(t.name), t.candidates.map((x) => `${esc(x.code)} ${esc(x.name)}`).join('<br>')]))}
<h2>Links to review (${r.lowConfidence.length})</h2>
${table(['Activity', 'Name', 'Confidence', 'Source', 'Status', 'Elements', 'Reasons'], r.lowConfidence.map((l) => [esc(l.activity), esc(l.name), l.confidence.toFixed(2), esc(l.source), esc(l.status), String(l.elements), l.reasons.map(esc).join('<br>')]))}
<h2>Checks (${r.checks.length})</h2>
${table(['Severity', 'Check', 'Message', 'References'], r.checks.map((k) => [sev(k.severity), esc(k.kind), esc(k.message), k.refs.slice(0, 12).map(esc).join(', ') + (k.refs.length > 12 ? ` (+${k.refs.length - 12})` : '')]))}
</body></html>
`;
}
