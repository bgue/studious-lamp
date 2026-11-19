// The revision report (design 3.7): a CSV with one row per changed element and a Markdown summary. Pure.
// `DecidedBy` is in the CSV as it is in the review log CSV: it is an explicit export by the user. It is in no setting, link, view or preset.

import type { ClassifyResult } from '../classify/types';
import { toCsv } from '../tools/csv';
import type { CsvCell } from '../tools/csv';
import { CATEGORIES, CHANGE_FLAGS } from './types';
import type { Category, DiffEntry, ModelSnapshot, PropValue, RevisionDecision, RevisionDiff } from './types';

export const REPORT_HEADER = [
  'Category', 'Flags', 'BaseGlobalId', 'HeadGlobalId', 'IfcClass', 'Name', 'Storey', 'MoveMm', 'Rotated', 'MatchScore', 'PropertyChanges', 'ClassifyAffected',
  'BaseDiscipline', 'BaseSubDiscipline', 'BaseDivision', 'HeadDiscipline', 'HeadSubDiscipline', 'HeadDivision',
  'Verdict', 'Unsure', 'Classification', 'AttachmentAction', 'Note', 'DecidedAt', 'DecidedBy',
] as const;

export interface ReportInput {
  base: ModelSnapshot;
  head: ModelSnapshot;
  diff: RevisionDiff;
  decisions?: Readonly<Record<string, RevisionDecision>>;
  skipped?: readonly string[];
  carried?: { commits: readonly string[]; results: number } | null;
  /** Bulk rules that were applied: id, label and how many elements each took. */
  bulk?: ReadonlyArray<{ id: string; label: string; count: number }>;
  generatedAt?: string;
}

const idx = (s: ModelSnapshot): Map<string, number> => new Map(s.globalId.map((g, i) => [g, i]));
const codes = (r: ClassifyResult | null | undefined): [string, string, string] => [r?.discipline.code ?? '', r?.subDiscipline?.code ?? '', r?.masterformat?.division ?? ''];
const val = (v: PropValue | undefined): string => (v === undefined ? '(none)' : String(v));
const round1 = (x: number): number => Math.round(x * 10) / 10;

const propText = (e: DiffEntry): string => (e.props ?? []).map((p) => `${p.key}: ${val(p.before)} -> ${val(p.after)}`).join('; ');

export function verdictOf(e: DiffEntry, d: RevisionDecision | undefined, skipped: ReadonlySet<string>): 'accepted' | 'rejected' | 'skipped' | 'undecided' {
  return d ? d.verdict : skipped.has(e.key) ? 'skipped' : 'undecided';
}

/** The listed entries (everything but unchanged) as report rows. */
export function reportRows(inp: ReportInput): CsvCell[][] {
  const bi = idx(inp.base), hi = idx(inp.head);
  const skipped = new Set(inp.skipped ?? []);
  return inp.diff.entries.map((e): CsvCell[] => {
    const b = e.base !== undefined ? bi.get(e.base) : undefined;
    const h = e.head !== undefined ? hi.get(e.head) : undefined;
    const s = h !== undefined ? inp.head : inp.base;
    const i = h ?? b!;
    const d = inp.decisions?.[e.key];
    const [bd, bs, bv] = codes(b !== undefined ? inp.base.results[b] : null);
    const [hd, hs, hv] = codes(h !== undefined ? inp.head.results[h] : null);
    return [
      e.category, e.flags.join(' '), e.base ?? '', e.head ?? '', s.ifcClass[i]!, s.name[i]!, s.storey[i]?.name ?? '',
      e.move !== undefined ? round1(e.move * 1000) : '', e.rotated === true, e.score !== undefined ? Math.round(e.score * 1000) / 1000 : '', propText(e), e.classifyAffected,
      bd, bs, bv, hd, hs, hv,
      verdictOf(e, d, skipped), d?.unsure === true ? 'yes' : '', d?.classification ?? '', d?.attachments ?? '', d?.note ?? '', d?.at ?? '', d?.by ?? '',
    ];
  });
}

export const revisionReportCsv = (inp: ReportInput): string => toCsv(REPORT_HEADER, reportRows(inp));

const stem = (n: string): string => n.replace(/\.(ifczip|ifc|zip)$/i, '').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'model';

export function reportFileNames(base: string, head: string): { csv: string; summary: string } {
  const b = `revision-${stem(base)}-to-${stem(head)}`;
  return { csv: `${b}.csv`, summary: `${b}-summary.md` };
}

const cell = (s: string | number): string => String(s).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
const table = (head: string[], rows: Array<Array<string | number>>): string => [`| ${head.join(' | ')} |`, `| ${head.map(() => '---').join(' | ')} |`, ...rows.map((r) => `| ${r.map(cell).join(' | ')} |`)].join('\n');

export function revisionSummaryMd(inp: ReportInput): string {
  const { diff, base, head } = inp;
  const o = diff.options;
  const skipped = new Set(inp.skipped ?? []);
  const bi = idx(base), hi = idx(head);
  const tally = { accepted: 0, rejected: 0, skipped: 0, undecided: 0 };
  const byStorey = new Map<string, Record<Category, number>>();
  for (const e of diff.entries) {
    tally[verdictOf(e, inp.decisions?.[e.key], skipped)]++;
    const h = e.head !== undefined ? hi.get(e.head) : undefined;
    const st = (h !== undefined ? head.storey[h] : base.storey[bi.get(e.base ?? '') ?? -1])?.name ?? '(no storey)';
    const row = byStorey.get(st) ?? byStorey.set(st, Object.fromEntries(CATEGORIES.map((c) => [c, 0])) as Record<Category, number>).get(st)!;
    row[e.category]++;
  }
  const lines: string[] = [];
  lines.push(`# Revision report: ${base.identity.name} to ${head.identity.name}`, '');
  if (inp.generatedAt) lines.push(`Generated ${inp.generatedAt}.`, '');
  lines.push('## Models', '', table(['', 'Name', 'Elements', 'GUID hash'], [['Base', base.identity.name, base.identity.elementCount, base.identity.guidHash], ['Head', head.identity.name, head.identity.elementCount, head.identity.guidHash]]), '');
  lines.push('## Thresholds', '', table(['Setting', 'Value'], [
    ['Same shape', `area within ${o.areaTol * 100} %, moments within ${o.momentTol * 100} %`],
    ['Moved', `centroid shift over ${o.moveTol * 1000} mm, or extent change over max(${o.extentTolAbs * 1000} mm, ${o.extentTolRel * 100} %)`],
    ['Rematch', `score at least ${o.matchMin}, margin at least ${o.matchMargin}, high from ${o.matchHigh}`],
    ['Properties compared', 'loaded properties only (attributes, common property sets, base quantities)'],
    ['Global offset removed', `${diff.offset.map((v) => round1(v * 1000) / 1000).join(', ')} m`],
  ]), '');
  lines.push('## Counts', '', table(['Category', 'Elements'], CATEGORIES.map((c) => [c, diff.counts[c]])), '');
  lines.push(table(['Flag', 'Elements'], CHANGE_FLAGS.map((f) => [f, diff.flagCounts[f]])), '');
  lines.push('## By storey', '', table(['Storey', ...CATEGORIES.filter((c) => c !== 'unchanged')], [...byStorey.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([k, v]) => [k, v.new, v.deleted, v.changed, v.rematched])), '');
  lines.push('## Decisions', '', table(['Verdict', 'Elements'], [['accepted', tally.accepted], ['rejected', tally.rejected], ['skipped', tally.skipped], ['undecided', tally.undecided]]), '');
  if (inp.bulk?.length) lines.push('## Bulk rules applied', '', table(['Rule', 'Elements'], inp.bulk.map((b) => [b.label, b.count])), '');
  if (inp.carried) lines.push('## Carried over', '', `${inp.carried.results} results and ${inp.carried.commits.length} commits came across from ${base.identity.name}.`, '');
  return lines.join('\n');
}
