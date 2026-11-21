import { describe, expect, it } from 'vitest';
import { linkSchedule } from '../src/schedule/link';
import type { ActivityLink, Assignment, FourDConfig, FourDLinks } from '../src/schedule/types';
import { buildConfig, buildModel, buildSchedule, task } from './fourd-fixtures';

const run = (over: { config?: FourDConfig; assignments?: Assignment[]; schedule?: ReturnType<typeof buildSchedule>; model?: ReturnType<typeof buildModel>; opts?: Parameters<typeof linkSchedule>[4] } = {}): FourDLinks =>
  linkSchedule(over.schedule ?? buildSchedule(), over.model ?? buildModel(), over.config ?? buildConfig(), over.assignments ?? [], over.opts);
const link = (l: FourDLinks, code: string, role: 'build' | 'remove' = 'build'): ActivityLink | undefined => l.links!.find((x) => x.activity === code && x.role === role);
const els = (l: FourDLinks, code: string): string[] => [...(link(l, code)?.elements ?? [])].sort();

describe('linkSchedule: attributes tier', () => {
  const l = run();
  it('links by location, trade and zone, each optional', () => {
    expect(els(l, 'A300')).toEqual(['COLA2', 'COLB2', 'SLAB2']);       // level + trade
    expect(els(l, 'A310')).toEqual(['WALLA2', 'WALLB2']);
    expect(els(l, 'A400')).toEqual(['COLA3', 'COLB3', 'SLAB3']);
    expect(els(l, 'A410')).toEqual(['WALLA3', 'WALLB3']);
  });
  it('finds elements without a trade through tradeQueries', () => {
    expect(els(l, 'A320')).toEqual(['DUCT2']);
    expect(els(l, 'A420')).toEqual(['DUCT3']);
  });
  it('maps schedule values (regex key) before comparing: L01 -> Level 1', () => {
    expect(els(l, 'A200')).toContain('SLAB1');
    expect(link(l, 'A200')!.reasons!.join(' ')).toContain('Level 1 from code Level=L01');
  });
  it('the most specific activity wins: three attributes beat two', () => {
    expect(els(l, 'A210')).toEqual(['COLA1']);                         // level + trade + zone A
    expect(els(l, 'A200')).toEqual(['COLB1', 'SLAB1']);                // lost COLA1 to A210
    expect(link(l, 'A200')!.reasons!.join(' ')).toMatch(/1 candidate element\(s\) went to a more specific activity/);
  });
  it('writes source, confidence, status, reasons, rule and stable ids', () => {
    const a = link(l, 'A300')!;
    expect(a).toMatchObject({ id: 'ln-A300-build', role: 'build', source: 'attributes', status: 'accepted', rule: 'location=Level 2; trade=CONC' });
    expect(a.confidence).toBeCloseTo(0.8);
    expect(link(l, 'A210')!.confidence).toBeCloseTo(0.9);
    for (const x of l.links!) { expect(x.reasons!.length).toBeGreaterThan(0); expect(x.id).toMatch(/^ln-[A-Z0-9]+-(build|remove)/); }
    expect(new Set(l.links!.map((x) => x.id)).size).toBe(l.links!.length);
  });
  it('applies the split rule of the trade (and per-activity overrides)', () => {
    expect(link(l, 'A300')!.split).toBe('sweep_x');   // CONC
    expect(link(l, 'A310')!.split).toBe('none');      // '*' rule
    const cfg = buildConfig();
    cfg.activities!['A310'] = { split: 'by_name' };
    expect(link(run({ config: cfg }), 'A310')!.split).toBe('by_name');
  });
  it('milestones, LOE and WBS summaries never get elements, even with matching attributes', () => {
    const s = buildSchedule();
    s.tasks.push(task('M1', 'Slab milestone', { type: 'milestone', codes: { Level: 'L02', Trade: 'CONC' }, early: ['2027-02-01T08:00', '2027-02-01T08:00'] }));
    s.tasks.push(task('LOE1', 'Slab supervision', { type: 'loe', codes: { Level: 'L02', Trade: 'CONC' } }));
    s.tasks.push(task('W1', 'Slab summary', { type: 'wbsSummary', codes: { Level: 'L02', Trade: 'CONC' } }));
    const out = run({ schedule: s });
    for (const c of ['M1', 'LOE1', 'W1']) expect(link(out, c)).toBeUndefined();
    expect(out.unlinked_activities).not.toContain('M1');
    expect(els(out, 'A300')).toEqual(['COLA2', 'COLB2', 'SLAB2']);
  });
  it('an activity with no location, trade or zone claims nothing', () => {
    expect(link(l, 'A110')).toBeUndefined();
    expect(l.unlinked_activities).toContain('A110');
  });
});

describe('linkSchedule: ties', () => {
  it('equal specificity is a tie: the element is not linked and is reported', () => {
    const s = buildSchedule();
    s.tasks.push(task('A405', 'L3 concrete frame', { codes: { Level: 'L03', Trade: 'CONC' }, early: ['2027-02-02T08:00', '2027-02-04T17:00'] }));
    const out = run({ schedule: s });
    expect(out.ties!.map((t) => t.element).sort()).toEqual(['COLA3', 'COLB3', 'SLAB3']);
    expect(out.ties![0]!.candidates).toEqual(['A400', 'A405']);
    expect(link(out, 'A400')).toBeUndefined();
    expect(link(out, 'A405')).toBeUndefined();
    expect(out.unlinked_elements).toContain('SLAB3');
    expect(out.unlinked_activities).toContain('A400');
  });
  it('a more specific third activity breaks the tie for its elements only', () => {
    const s = buildSchedule();
    s.tasks.push(task('A405', 'L3 concrete frame', { codes: { Level: 'L03', Trade: 'CONC' }, early: ['2027-02-02T08:00', '2027-02-04T17:00'] }));
    s.tasks.push(task('A406', 'L3 columns A', { codes: { Level: 'L03', Trade: 'CONC', Area: 'A' }, early: ['2027-02-02T08:00', '2027-02-04T17:00'] }));
    const out = run({ schedule: s });
    expect(els(out, 'A406')).toEqual(['COLA3']);
    expect(out.ties!.map((t) => t.element).sort()).toEqual(['COLB3', 'SLAB3']);
  });
});

describe('linkSchedule: property, native, override, existing, remove', () => {
  it('links by an id property, comma separated, exact code', () => {
    const m = buildModel();
    m.elements.find((e) => e.globalId === 'FURN1')!.props['Pset_4D.ActivityId'] = 'A720, a310';
    m.elements.find((e) => e.globalId === 'FURN2')!.props['Pset_4D.ActivityId'] = 'A720';
    const out = run({ model: m, opts: { idProperty: 'Pset_4D.ActivityId' } });
    expect(els(out, 'A720')).toEqual(['FURN2']);
    expect(link(out, 'A720')).toMatchObject({ source: 'property', confidence: 1, status: 'accepted' });
    // FURN1 is also named by A310 (property, rank equal to A720): a tie
    expect(out.ties!).toEqual([{ element: 'FURN1', candidates: ['A310', 'A720'] }]);
    // an activity with explicit elements does not also infer elements from its attributes
    expect(els(out, 'A310')).toEqual([]);
  });
  it('property beats attributes', () => {
    const m = buildModel();
    m.elements.find((e) => e.globalId === 'SLAB2')!.props['P.Id'] = 'A210';
    const out = run({ model: m, opts: { idProperty: 'p.id' } });
    expect(els(out, 'A210')).toEqual(['SLAB2']);
    expect(els(out, 'A300')).toEqual(['COLA2', 'COLB2']);
  });
  it('links native IfcTask assignments (a map GlobalId -> task codes)', () => {
    const out = run({ opts: { native: new Map([['ROOF1', ['A720']], ['STAIR1', ['nope']]]) } });
    expect(els(out, 'A720')).toEqual(['ROOF1']);
    expect(link(out, 'A720')!.source).toBe('native');
    expect(run({ opts: { native: { ROOF1: ['A720'] } } }).links!.find((x) => x.activity === 'A720')!.elements).toEqual(['ROOF1']);
  });
  it('overrides: a query or GlobalIds, ranking above the attributes', () => {
    const cfg = buildConfig();
    cfg.activities!['A110'] = { globalIds: ['ROOF1', 'MISSING'] };
    cfg.activities!['A720'] = { query: "class = 'IfcDoor' AND storey = 'Level 2'" };
    cfg.activities!['A310'] = { query: "globalId = 'WALLA2'" }; // replaces the attribute inference of A310
    const warnings: string[] = [];
    const out = run({ config: cfg, opts: { onWarning: (m) => warnings.push(m) } });
    expect(els(out, 'A110')).toEqual(['ROOF1']);
    expect(warnings.join('|')).toContain('MISSING');
    expect(els(out, 'A720')).toEqual(['DOOR2']);
    expect(link(out, 'A720')).toMatchObject({ source: 'override', confidence: 1, rule: "query:class = 'IfcDoor' AND storey = 'Level 2'" });
    expect(els(out, 'A310')).toEqual(['WALLA2']);
    expect(els(out, 'A500')).toEqual(['WIN1', 'WIN2', 'WIN3']);
  });
  it('an override beats a more general attribute claim', () => {
    const cfg = buildConfig();
    cfg.activities!['A110'] = { query: "globalId = 'SLAB2'" };
    const out = run({ config: cfg });
    expect(els(out, 'A110')).toEqual(['SLAB2']);
    expect(els(out, 'A300')).toEqual(['COLA2', 'COLB2']);
  });
  it('a bad override query warns and links nothing', () => {
    const cfg = buildConfig();
    cfg.activities!['A110'] = { query: 'class = ' };
    const w: string[] = [];
    const out = run({ config: cfg, opts: { onWarning: (m) => w.push(m) } });
    expect(link(out, 'A110')).toBeUndefined();
    expect(w.join()).toMatch(/not valid/);
  });
  it('existing elements (config.model.existing) are never built by attributes and are flagged', () => {
    const out = run();
    const old = out.model_elements!.find((e) => e.global_id === 'OLD1')!;
    expect(old.existing).toBe(true);
    expect(out.model_elements!.find((e) => e.global_id === 'SLAB1')!.existing).toBeUndefined();
    expect(out.unlinked_elements).not.toContain('OLD1');
    const cfg = buildConfig();
    cfg.schedule.location = [{ code: 'Level' }];
    const s = buildSchedule();
    s.tasks.push(task('A9', 'All level 1 trades', { codes: { Level: 'L01' } }));
    const o2 = run({ schedule: s });
    expect(els(o2, 'A9')).not.toContain('OLD1');
  });
  it('a remove role links existing elements as a remove link', () => {
    const out = run();
    expect(link(out, 'A600', 'remove')).toMatchObject({ id: 'ln-A600-remove', role: 'remove', status: 'accepted', source: 'override' });
    expect(link(out, 'A600', 'remove')!.elements).toEqual(['OLD1', 'OLD2']);
    expect(link(out, 'A600', 'build')).toBeUndefined();
    expect(out.unlinked_activities).toContain('A600'); // it builds nothing
  });
});

describe('linkSchedule: assignments', () => {
  it('accepted assignments give elements their location and trade; the rest are ignored', () => {
    const asg: Assignment[] = [
      { id: 'a1', element: 'STAIR1', attribute: 'location', value: 'Level 2', status: 'accepted' },
      { id: 'a2', element: 'STAIR1', attribute: 'trade', value: 'MAS', status: 'accepted' },
      { id: 'a3', element: 'FURN1', attribute: 'location', value: 'Level 2', status: 'proposed' },
      { id: 'a4', element: 'FURN1', attribute: 'trade', value: 'MAS', status: 'proposed' },
    ];
    const out = run({ assignments: asg });
    expect(els(out, 'A310')).toContain('STAIR1');
    expect(els(out, 'A310')).not.toContain('FURN1');
    expect(out.assignments).toEqual(asg);
    expect(out.model_elements!.find((e) => e.global_id === 'STAIR1')).toMatchObject({ location: 'Level 2', trade: 'MAS' });
  });
  it('an accepted assignment overrides the model property', () => {
    const out = run({ assignments: [{ id: 'a1', element: 'SLAB2', attribute: 'trade', value: 'MAS', status: 'accepted' }] });
    expect(els(out, 'A310')).toContain('SLAB2');
    expect(els(out, 'A300')).not.toContain('SLAB2');
  });
});

describe('linkSchedule: suggestions', () => {
  const out = run();
  it('proposes links for leftover activities from names and WBS tokens, with evidence', () => {
    const s = link(out, 'A720')!;
    expect(s).toMatchObject({ source: 'suggested', status: 'proposed', role: 'build' });
    expect(s.elements).toEqual(['DOOR2']);
    expect(s.confidence).toBeGreaterThan(0.6);
    expect(s.confidence).toBeLessThan(1);
    expect(s.reasons!.join(' | ')).toMatch(/IfcDoor from 'door'/);
    expect(s.reasons!.join(' | ')).toMatch(/storey 'Level 2' from 'level 2'/);
    expect(s.rule).toBe("class IN ('IfcDoor') AND storey IN ('Level 2')");
  });
  it('is never accepted automatically and never drives unlinked lists', () => {
    for (const l of out.links!) if (l.source === 'suggested') expect(l.status).toBe('proposed');
    expect(out.unlinked_activities).toContain('A720');
    expect(out.unlinked_elements).toContain('DOOR2');
  });
  it('can be switched off, and has a confidence floor', () => {
    expect(link(run({ opts: { suggest: false } }), 'A720')).toBeUndefined();
    expect(link(run({ opts: { minSuggestConfidence: 0.95 } }), 'A720')).toBeUndefined();
  });
  it('matches level words and numbers in several spellings, and class words alone with low confidence', () => {
    const s = buildSchedule();
    s.tasks.push(
      task('S1', 'Stair erection', { wbs: ['P', 'X'] }),
      task('S2', 'Doors', { wbs: ['P', 'X', 'L03'] }),
      task('S3', 'Fit-out 1st floor windows', {}),
    );
    const o = run({ schedule: s, config: { ...buildConfig(), activities: {} } });
    expect(link(o, 'S1')).toMatchObject({ elements: ['STAIR1'], status: 'proposed' });
    expect(link(o, 'S1')!.confidence).toBeLessThan(0.5);
    expect(link(o, 'S2')!.elements).toEqual(['DOOR3']);
    expect(link(o, 'S3')!.elements).toEqual(['WIN1']);
  });
  it('does not propose for an activity that already has links, a rejected or a proposed prior link', () => {
    const prior: ActivityLink[] = [{ id: 'ln-A720-build', activity: 'A720', role: 'build', elements: ['DOOR1'], status: 'rejected', source: 'suggested' }];
    const o = run({ opts: { priorLinks: prior } });
    expect(o.links!.filter((l) => l.activity === 'A720')).toEqual(prior);
  });
  it('suggestions skip elements other activities already build', () => {
    expect(link(out, 'A720')!.elements).not.toContain('WIN2');
  });
});

describe('linkSchedule: prior links', () => {
  it('keeps accepted manual links (they win over attributes) and passes others through', () => {
    const prior: ActivityLink[] = [
      { id: 'man-1', activity: 'A110', role: 'build', elements: ['SLAB2'], source: 'manual', confidence: 1, status: 'accepted', reviewed_by: 'sam', reviewed_at: '2027-01-02T00:00:00Z', reasons: ['picked in viewer'] },
      { id: 'agent-1', activity: 'A720', role: 'build', elements: ['DOOR1'], source: 'agent', confidence: 0.5, status: 'proposed' },
    ];
    const out = run({ opts: { priorLinks: prior } });
    expect(els(out, 'A110')).toEqual(['SLAB2']);
    expect(link(out, 'A110')).toMatchObject({ id: 'man-1', source: 'manual', reviewed_by: 'sam' });
    expect(els(out, 'A300')).toEqual(['COLA2', 'COLB2']);
    expect(out.links!.find((l) => l.id === 'agent-1')).toEqual(prior[1]);
  });
  it('keeps an accepted manual remove link', () => {
    const prior: ActivityLink[] = [{ id: 'm-rem', activity: 'A110', role: 'remove', elements: ['FURN1'], source: 'manual', status: 'accepted' }];
    const out = run({ opts: { priorLinks: prior } });
    expect(link(out, 'A110', 'remove')!.elements).toEqual(['FURN1']);
    expect(out.unlinked_elements).not.toContain('FURN1');
  });
});

describe('linkSchedule: dataset shape', () => {
  const out = run({ opts: { createdAt: '2027-01-20T00:00:00Z' } });
  it('fills the references, activities, elements and lists', () => {
    expect(out.model).toEqual({ identity_key: 'fixture|31|abcd', name: 'fixture.ifc' });
    expect(out.schedule).toEqual({ source_hash: 'deadbeefcafe0123', project: 'TOWER', data_date: '2027-01-20T08:00' });
    expect(out.created_at).toBe('2027-01-20T00:00:00Z');
    expect(out.activities).toHaveLength(15);
    expect(out.activities!.find((a) => a.task_code === 'A300')).toMatchObject({ name: 'L2 slab', wbs_path: 'P/STR/L2', activity_type: 'task', activity_status: 'active', location: 'Level 2', trade: 'CONC', critical: true, start: '2027-01-18T08:00', finish: '2027-01-22T17:00' });
    expect(out.activities!.find((a) => a.task_code === 'A310')!.critical).toBe(false);
    expect(out.model_elements).toHaveLength(31);
    expect(out.model_elements!.find((e) => e.global_id === 'COLA2')).toEqual({ global_id: 'COLA2', ifc_class: 'IfcColumn', name: 'Column A L2', storey: 'Level 2', location: 'Level 2', trade: 'CONC', zone: 'Zone A' });
    expect(out.unlinked_elements!.sort()).toEqual(['DOOR1', 'DOOR2', 'DOOR3', 'DUCT1', 'FURN1', 'FURN2', 'PROXY1', 'ROOF1', 'STAIR1', 'WALLA1', 'WALLB1']);
  });
  it('uses only the LinkML field names and no undefined values', () => {
    const json = JSON.parse(JSON.stringify(out));
    expect(Object.keys(json).sort()).toEqual(['activities', 'assignments', 'created_at', 'id', 'links', 'model', 'model_elements', 'schedule', 'tie' + 's', 'tool', 'unlinked_activities', 'unlinked_elements'].sort());
    for (const l of out.links!) for (const k of Object.keys(l)) expect(l[k as keyof ActivityLink]).not.toBeUndefined();
  });
  it('is deterministic', () => {
    expect(JSON.stringify(run())).toBe(JSON.stringify(run()));
  });
});
