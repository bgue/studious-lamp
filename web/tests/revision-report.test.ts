// The revision report (design 3.7): CSV header and rows for fzk-v2, the decisions in the right columns, and the summary counts.
import { beforeAll, describe, expect, it } from 'vitest';
import type { ClassifyResult } from '../src/classify/types';
import { diffModels } from '../src/revision/diff';
import { REPORT_HEADER, reportFileNames, reportRows, revisionReportCsv, revisionSummaryMd } from '../src/revision/report';
import type { ReportInput } from '../src/revision/report';
import type { DiffEntry, ModelSnapshot, RevisionDecision, RevisionDiff } from '../src/revision/types';
import { fzk1, fzk2, loadIfc } from './revision-helpers';

let v1: ModelSnapshot, v2: ModelSnapshot;
let diff: RevisionDiff;

const res = (gid: string, disc: string, sub: string | null, div: string): ClassifyResult => ({
  id: gid, discipline: { code: disc, label: disc, confidence: 0.9, probabilities: { [disc]: 0.9 } },
  subDiscipline: sub ? { code: sub, label: sub, confidence: 0.9, probabilities: { [sub]: 0.9 } } : null,
  masterformat: { division: div, title: div, confidence: 0.9, probabilities: { [div]: 0.9 } }, buildingElement: 1, source: 'rules', needsReview: false,
});

beforeAll(async () => {
  v1 = (await loadIfc(fzk1(), { results: (g) => res(g, 'ARC', 'WALL', '06') })).snap;
  v2 = (await loadIfc(fzk2(), { results: (g) => res(g, 'STR', null, '05') })).snap;
  diff = diffModels(v1, v2);
}, 120000);

/** RFC 4180 parsing, enough for the report. */
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i]!;
    if (quoted) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else quoted = false; } else cell += c; }
    else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\r') { /* with the \n */ }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += c;
  }
  return rows;
}

const input = (extra: Partial<ReportInput> = {}): ReportInput => ({ base: v1, head: v2, diff, ...extra });
const col = (name: string): number => REPORT_HEADER.indexOf(name as (typeof REPORT_HEADER)[number]);
const rowOf = (rows: string[][], name: string): string[] => rows.find((r) => r[col('Name')] === name)!;
const entry = (name: string): DiffEntry => diff.entries.find((e) => (e.head ? v2.name[v2.globalId.indexOf(e.head)] : v1.name[v1.globalId.indexOf(e.base!)]) === name)!;

describe('csv', () => {
  it('has the header of the design and one row per listed element', () => {
    const rows = parseCsv(revisionReportCsv(input()));
    expect(rows[0]).toEqual([
      'Category', 'Flags', 'BaseGlobalId', 'HeadGlobalId', 'IfcClass', 'Name', 'Storey', 'MoveMm', 'Rotated', 'MatchScore', 'PropertyChanges', 'ClassifyAffected',
      'BaseDiscipline', 'BaseSubDiscipline', 'BaseDivision', 'HeadDiscipline', 'HeadSubDiscipline', 'HeadDivision',
      'Verdict', 'Unsure', 'Classification', 'AttachmentAction', 'Note', 'DecidedAt', 'DecidedBy',
    ]);
    expect(rows).toHaveLength(1 + 27);
    expect(rows.every((r) => r.length === 25)).toBe(true);
    expect(revisionReportCsv(input()).endsWith('\r\n')).toBe(true);
  });

  it('fills the rows of each category from the right model', () => {
    const rows = parseCsv(revisionReportCsv(input()));
    const move = rowOf(rows, 'Sparren-3');
    expect(move.slice(0, 2)).toEqual(['changed', 'placement']);
    expect(move[col('BaseGlobalId')]).toBe(move[col('HeadGlobalId')]);
    expect(Number(move[col('MoveMm')])).toBeGreaterThan(4.5);
    expect(Number(move[col('MoveMm')])).toBeLessThan(5.5);
    expect(move[col('Rotated')]).toBe('false');
    expect(move[col('Storey')]).toBe('Dachgeschoss');
    expect([move[col('BaseDiscipline')], move[col('BaseSubDiscipline')], move[col('BaseDivision')]]).toEqual(['ARC', 'WALL', '06']);
    expect([move[col('HeadDiscipline')], move[col('HeadSubDiscipline')], move[col('HeadDivision')]]).toEqual(['STR', '', '05']);
    expect(move[col('ClassifyAffected')]).toBe('false');

    const gone = rowOf(rows, 'EG-Fenster-6');
    expect(gone[0]).toBe('deleted');
    expect(gone[col('HeadGlobalId')]).toBe('');
    expect(gone[col('BaseGlobalId')]).not.toBe('');
    expect(gone[col('HeadDiscipline')]).toBe('');
    expect(gone[col('BaseDiscipline')]).toBe('ARC');
    expect(gone[col('Storey')]).toBe('Erdgeschoss');

    const added = rowOf(rows, 'Sparren-5 (copy)');
    expect(added[0]).toBe('new');
    expect(added[col('BaseGlobalId')]).toBe('');
    expect(added[col('BaseDiscipline')]).toBe('');
    expect(added[col('HeadDiscipline')]).toBe('STR');
    expect(added[col('ClassifyAffected')]).toBe('true');

    const re = rowOf(rows, 'Haustuer');
    expect(re[0]).toBe('rematched');
    expect(Number(re[col('MatchScore')])).toBeGreaterThanOrEqual(0.95);
    expect(re[col('BaseGlobalId')]).not.toBe(re[col('HeadGlobalId')]);

    const props = rowOf(rows, 'Wand-Int-ERDG-1');
    expect(props[col('PropertyChanges')]).toBe('Pset_WallCommon.ThermalTransmittance: 1.5 -> 0.9');
    expect(rowOf(rows, 'First')[col('Rotated')]).toBe('true');
    expect(rowOf(rows, 'Sparren-40')[1]).toBe('class');
  });

  it('records verdicts, unsure, classification, attachment action, note, time and reviewer; skipped and undecided otherwise', () => {
    const d = (e: DiffEntry, x: Partial<RevisionDecision>): RevisionDecision => ({ key: e.key, verdict: 'accepted', classification: 'kept', at: '2026-03-01T09:00:00.000Z', by: 'Ana', ...x });
    const a = entry('Sparren-3'), b = entry('Sparren-12'), c = entry('EG-Fenster-6'), s = entry('Dach-2');
    const decisions = {
      [a.key]: d(a, { unsure: true }),
      [b.key]: d(b, { verdict: 'rejected', classification: 'none', note: '=cmd|"x", y', by: 'Ben' }),
      [c.key]: d(c, { classification: 'none', attachments: 'resolve' }),
    };
    const rows = parseCsv(revisionReportCsv(input({ decisions, skipped: [s.key] })));
    const tail = (n: string): string[] => rowOf(rows, n).slice(col('Verdict'));
    expect(tail('Sparren-3')).toEqual(['accepted', 'yes', 'kept', '', '', '2026-03-01T09:00:00.000Z', 'Ana']);
    expect(tail('Sparren-12')).toEqual(['rejected', '', 'none', '', `'=cmd|"x", y`, '2026-03-01T09:00:00.000Z', 'Ben']); // quoted, and guarded against a formula
    expect(tail('EG-Fenster-6')[3]).toBe('resolve');
    expect(tail('Dach-2')[0]).toBe('skipped');
    expect(tail('First')[0]).toBe('undecided');
    expect(reportRows(input()).length).toBe(27);
  });

  it('names the files after the two models', () => {
    expect(reportFileNames('AC20-FZK-Haus.ifc', 'fzk v2 (final).ifc')).toEqual({ csv: 'revision-AC20-FZK-Haus-to-fzk-v2-final.csv', summary: 'revision-AC20-FZK-Haus-to-fzk-v2-final-summary.md' });
  });
});

describe('summary', () => {
  it('states the models, thresholds, counts, storeys, decisions, bulk rules and the carry', () => {
    const a = entry('Sparren-3'), b = entry('Sparren-12');
    const md = revisionSummaryMd(input({
      generatedAt: '2026-03-01T10:00:00Z',
      decisions: { [a.key]: { key: a.key, verdict: 'accepted', classification: 'kept', at: 't', by: 'Ana', bulk: 'placement-moves' }, [b.key]: { key: b.key, verdict: 'rejected', classification: 'none', at: 't', by: 'Ana' } },
      skipped: [entry('Dach-2').key],
      bulk: [{ id: 'placement-moves', label: 'Accept placement-only moves up to 10 mm', count: 3 }],
      carried: { commits: ['c1~abc', 'c2~abc'], results: 52 },
    }));
    expect(md).toContain('# Revision report: AC20-FZK-Haus.ifc to fzk-v2.ifc');
    expect(md).toContain('| Base | AC20-FZK-Haus.ifc | 82 |');
    expect(md).toContain('| Head | fzk-v2.ifc | 81 |');
    expect(md).toMatch(/area within 0\.5 %, moments within 1 %/);
    expect(md).toMatch(/centroid shift over 1 mm/);
    expect(md).toContain('loaded properties only');
    for (const [k, n] of [['new', 3], ['deleted', 4], ['changed', 14], ['rematched', 6], ['unchanged', 58]] as const) expect(md).toContain(`| ${k} | ${n} |`);
    for (const [k, n] of [['geometry', 2], ['placement', 6], ['class', 1], ['type', 2], ['properties', 3], ['systems', 0]] as const) expect(md).toContain(`| ${k} | ${n} |`);
    expect(md).toContain('| accepted | 1 |');
    expect(md).toContain('| rejected | 1 |');
    expect(md).toContain('| skipped | 1 |');
    expect(md).toContain(`| undecided | ${27 - 2 - 1} |`);
    expect(md).toContain('| Accept placement-only moves up to 10 mm | 3 |');
    expect(md).toContain('52 results and 2 commits came across from AC20-FZK-Haus.ifc');
    // by storey: every listed element is in exactly one row
    const storeyRows = md.split('## By storey')[1]!.split('##')[0]!.split('\n').filter((l) => /^\| (Erdgeschoss|Dachgeschoss|\(no storey\))/.test(l));
    expect(storeyRows.length).toBeGreaterThanOrEqual(2);
    const total = storeyRows.reduce((n, l) => n + l.split('|').slice(2, 6).reduce((m, c) => m + Number(c), 0), 0);
    expect(total).toBe(27);
  });

  it('leaves out the sections that have nothing to say', () => {
    const md = revisionSummaryMd(input());
    expect(md).not.toContain('## Bulk rules applied');
    expect(md).not.toContain('## Carried over');
    expect(md).toContain('| undecided | 27 |');
  });
});
