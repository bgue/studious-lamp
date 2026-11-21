import { describe, expect, it } from 'vitest';
import { buildReport, renderReportHtml } from '../src/schedule/report';
import { linkSchedule } from '../src/schedule/link';
import { FourDTable } from '../src/schedule/model';
import { compile, parseQuery } from '../src/query';
import type { Schedule } from '../src/schedule/types';
import { buildConfig, buildModel, buildSchedule } from './fourd-fixtures';

const model = buildModel();
const config = buildConfig();
const mk = (schedule: Schedule = buildSchedule()) => { const links = linkSchedule(schedule, model, config, []); return { schedule, links, report: buildReport(schedule, links, model, { config }) }; };

describe('report: coverage', () => {
  const { report } = mk();
  it('elements by count and by bbox volume, existing excluded', () => {
    const e = report.coverage.elements;
    expect(e).toMatchObject({ total: 31, existing: 2, considered: 29, linked: 18, unlinked: 11, tied: 0 });
    expect(e.byCount).toBeCloseTo(18 / 29, 9);
    const vol = (ids: string[]): number => model.elements.filter((x) => ids.includes(x.globalId)).reduce((s, x) => s + (x.bbox![3] - x.bbox![0]) * (x.bbox![4] - x.bbox![1]) * (x.bbox![5] - x.bbox![2]), 0);
    const unlinked = ['DOOR1', 'DOOR2', 'DOOR3', 'DUCT1', 'FURN1', 'FURN2', 'PROXY1', 'ROOF1', 'STAIR1', 'WALLA1', 'WALLB1'];
    const total = vol(model.elements.filter((x) => !x.globalId.startsWith('OLD')).map((x) => x.globalId));
    expect(e.volumeTotal).toBeCloseTo(total, 2);
    expect(e.volumeLinked).toBeCloseTo(total - vol(unlinked), 2);
    expect(e.byVolume).toBeCloseTo((total - vol(unlinked)) / total, 3);
    expect(e.byVolume).not.toBeCloseTo(e.byCount, 2); // slabs are big: the two numbers differ
  });
  it('activities: building activities linked, unlinked and suggested only', () => {
    expect(report.coverage.activities).toMatchObject({ total: 12, linked: 9, unlinked: 3, suggestedOnly: 1 });
    expect(report.coverage.activities.ratio).toBeCloseTo(0.75);
  });
  it('by trade and by first WBS level', () => {
    const conc = report.coverage.byTrade.find((r) => r.name === 'CONC')!;
    expect(conc).toEqual({ name: 'CONC', activities: 4, activitiesLinked: 4, elements: 9 });
    expect(report.coverage.byTrade.find((r) => r.name === '(no trade)')!.activitiesLinked).toBe(1); // A500 windows
    const wbs = report.coverage.byWbs.find((r) => r.name === 'P')!;
    expect(wbs.activities).toBe(12);
    expect(wbs.elements).toBe(18);
  });
});

describe('report: leftovers', () => {
  const { report } = mk();
  it('unlinked elements grouped by class and storey, largest first', () => {
    expect(report.unlinkedElements.map((g) => `${g.ifcClass}|${g.storey}|${g.count}`)).toEqual([
      'IfcFurniture|Level 1|2', 'IfcWall|Level 1|2', 'IfcBuildingElementProxy|Level 2|1', 'IfcDoor|Level 1|1', 'IfcDoor|Level 2|1', 'IfcDoor|Level 3|1',
      'IfcDuctSegment|Level 1|1', 'IfcRoof|Level 3|1', 'IfcStair|null|1',
    ].sort((a, b) => Number(b.split('|')[2]) - Number(a.split('|')[2]) || a.localeCompare(b)));
  });
  it('each group has a criteria query that selects exactly the group', () => {
    const table = new FourDTable(model);
    let covered = 0;
    for (const g of report.unlinkedElements) {
      const c = compile(parseQuery(g.query), table);
      const hit: string[] = [];
      for (let r = 0; r < table.size; r++) if (c.test(r)) hit.push(model.elements[r]!.globalId);
      expect(hit.sort()).toEqual([...g.globalIds].sort());
      covered += hit.length;
    }
    expect(covered).toBe(report.coverage.elements.unlinked);
    expect(report.unlinkedElements.find((g) => g.ifcClass === 'IfcStair')!.query).toBe("class = 'IfcStair' AND storey IS NULL");
    expect(report.unlinkedElements.find((g) => g.ifcClass === 'IfcWall')!.query).toBe("class = 'IfcWall' AND storey = 'Level 1' AND NOT (name LIKE 'Old wall%')"); // leaves out the existing walls
  });
  it('activities with no elements, with their attributes and suggestion flag', () => {
    expect(report.unlinkedActivities.map((a) => a.code)).toEqual(['A110', 'A600', 'A720']);
    expect(report.unlinkedActivities.find((a) => a.code === 'A720')).toMatchObject({ hasSuggestion: true, wbsPath: 'P/FIT/L2' });
    expect(report.unlinkedActivities.find((a) => a.code === 'A110')!.hasSuggestion).toBe(false);
  });
  it('low-confidence and proposed links for review', () => {
    expect(report.lowConfidence).toHaveLength(1);
    expect(report.lowConfidence[0]).toMatchObject({ activity: 'A720', status: 'proposed', source: 'suggested', elements: 1 });
    expect(report.lowConfidence[0]!.reasons.length).toBeGreaterThan(0);
    const lowAttr = buildReport(buildSchedule(), linkSchedule(buildSchedule(), model, config, []), model, { minConfidence: 0.85 });
    expect(lowAttr.lowConfidence.map((l) => l.activity)).toContain('A300'); // attributes with two of three: 0.8
    expect(lowAttr.lowConfidence.map((l) => l.activity)).not.toContain('A210'); // three: 0.9
  });
  it('ties', () => {
    const s = buildSchedule();
    s.tasks.push({ ...s.tasks.find((t) => t.code === 'A400')!, id: 'id-A405', code: 'A405', name: 'L3 concrete frame' });
    const { report: r } = mk(s);
    expect(r.coverage.elements.tied).toBe(3);
    expect(r.ties).toHaveLength(3);
    expect(r.ties[0]!.candidates.map((c) => c.code)).toEqual(['A400', 'A405']);
    expect(r.ties[0]!.candidates[0]!.name).toBe('L3 slab');
    expect(r.ties.map((t) => t.name).sort()).toEqual(['Column A L3', 'Column B L3', 'Slab L3']);
  });
});

describe('report: logic and spatial checks', () => {
  const kinds = (r: ReturnType<typeof buildReport>, k: string) => r.checks.filter((c) => c.kind === k);
  it('open ends: activities with no successor (a clean schedule has no open starts)', () => {
    const { report } = mk();
    expect(kinds(report, 'open-start')).toEqual([]);
    expect(kinds(report, 'open-finish')[0]!.refs).toEqual(['A320', 'A600', 'A720']);
    expect(kinds(report, 'open-finish')[0]).toMatchObject({ severity: 'warning', message: '3 activities have no successor (open end)' });
    const s = buildSchedule();
    s.relations = s.relations.filter((r) => r.taskId !== 'id-A310');
    expect(kinds(mk(s).report, 'open-start')[0]!.refs).toEqual(['A310']);
  });
  it('no checks about logic when the file has no relations', () => {
    const s = buildSchedule();
    s.relations = [];
    expect(kinds(mk(s).report, 'open-start')).toEqual([]);
  });
  it('actuals after the data date', () => {
    const s = buildSchedule();
    s.tasks.find((t) => t.code === 'A310')!.dates.actualStart = '2027-01-25T08:00';
    const r = mk(s).report;
    expect(kinds(r, 'actual-after-data-date')[0]).toMatchObject({ severity: 'error', refs: ['A310'] });
    expect(kinds(mk().report, 'actual-after-data-date')).toEqual([]);
  });
  it('out-of-sequence progress, negative float, date inversion', () => {
    const s = buildSchedule();
    const t = (c: string) => s.tasks.find((x) => x.code === c)!;
    t('A310').dates.actualStart = '2027-01-19T08:00';     // started while A300 (FS predecessor) has no actual finish
    t('A320').totalFloatHours = -8;
    t('A420').dates.earlyEnd = '2027-02-01T08:00';        // before its start Feb 8
    const r = mk(s).report;
    expect(kinds(r, 'out-of-sequence')[0]!.refs).toEqual(['A310']);
    expect(kinds(r, 'negative-float')[0]!.refs).toEqual(['A320']);
    expect(kinds(r, 'date-inversion')[0]).toMatchObject({ severity: 'error', refs: ['A420'] });
    expect(kinds(mk().report, 'out-of-sequence')).toEqual([]);
    expect(kinds(mk().report, 'negative-float')).toEqual([]);
  });
  it('no spatial finding in a sound schedule', () => {
    expect(kinds(mk().report, 'built-before-support')).toEqual([]);
  });
  it('an element built before the slab of the storey below is flagged, once per activity pair', () => {
    const s = buildSchedule();
    const a400 = s.tasks.find((x) => x.code === 'A400')!;
    a400.dates = { earlyStart: '2027-01-11T08:00', earlyEnd: '2027-01-15T17:00' };   // L3 frame before the L2 slab (Jan 18)
    const found = kinds(mk(s).report, 'built-before-support');
    expect(found).toHaveLength(1);
    expect(found[0]!.message).toContain("A400 'L3 slab' on Level 3 starts 2027-01-11, before the Level 2 slab (A300 'L2 slab') starts 2027-01-18: 3 elements");
    expect(found[0]!.refs.slice(0, 2)).toEqual(['A400', 'A300']);
  });
  it('uses plan position: a column away from the slab below is not compared with it', () => {
    const s = buildSchedule();
    s.tasks.find((x) => x.code === 'A400')!.dates = { earlyStart: '2027-01-11T08:00', earlyEnd: '2027-01-15T17:00' };
    const m = buildModel();
    // move the whole of L2's slab far away in plan: nothing is below the L3 elements any more
    m.elements.find((e) => e.globalId === 'SLAB2')!.bbox = [500, 500, 3.7, 520, 510, 4];
    const links = linkSchedule(s, m, config, []);
    const r = buildReport(s, links, m);
    expect(r.checks.filter((c) => c.kind === 'built-before-support')).toEqual([]);
  });
});

describe('report: HTML', () => {
  const s = buildSchedule();
  s.tasks.find((t) => t.code === 'A110')!.name = 'Mobilise <script>alert(1)</script> & "co"';
  const { report } = mk(s);
  const html = renderReportHtml(report);
  it('is a complete, self-contained page with no external assets and no scripts', () => {
    expect(html.startsWith('<!doctype html>')).toBe(true);
    expect(html).toContain('</html>');
    expect(html).not.toMatch(/https?:\/\//);
    expect(html).not.toMatch(/<script|<link|<img|src=|@import/);
    expect(html).toContain('<style>');
  });
  it('shows the numbers, the groups with their queries, and the checks', () => {
    expect(html).toContain('62.1%');                       // 18 / 29 by count
    expect(html).toContain('IfcFurniture');
    expect(html).toContain("<code>class = 'IfcFurniture' AND storey = 'Level 1'</code>");
    expect(html).toContain('A320, A600, A720');
    expect(html).toContain('4D link report');
    expect(html).toContain('fixture.ifc');
    expect(html).toContain('deadbeefcafe');
  });
  it('escapes names', () => {
    expect(html).toContain('Mobilise &lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;co&quot;');
  });
  it('renders an empty report', () => {
    const e = buildReport({ ...buildSchedule(), tasks: [], relations: [] }, { id: 'x', model: { identity_key: 'k' }, schedule: { source_hash: 'h', project: 'p' } }, { identityKey: 'k', name: 'm', elements: [] });
    const h = renderReportHtml(e);
    expect(h).toContain('None.');
    expect(e.coverage.elements.byCount).toBe(1);
  });
});
