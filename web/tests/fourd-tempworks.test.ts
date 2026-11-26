// Temporary works: rule parsing, geometry on a synthetic two-storey box, timelines from the activities, the plan round trip, the CLI flag.
import { describe, expect, it } from 'vitest';
import { buildPlan } from '../src/schedule/plan';
import { DAY, parseLocal } from '../src/schedule/planTime';
import { linkSchedule } from '../src/schedule/link';
import { DEFAULT_STYLE } from '../src/schedule/types';
import type { FourDPlan, TempWorksConfig, TempWorksGroup } from '../src/schedule/types';
import type { FourDElement, FourDModel } from '../src/schedule/model';
import { buildTempWorksGroups, fadeShare, generatePieces, groupPhase, groupProgress, parseTempWorks, pieceAlpha, resolveRules, TEMP_DEFAULTS } from '../src/schedule/tempworks';
import { parseConfig, serializeConfig } from '../src/map4d/scheduleConfig';
import { buildConfig, buildModel, buildSchedule } from './fourd-fixtures';

const L = (s: string): number => parseLocal(s)!;

describe('temporary works rules', () => {
  const ok: TempWorksConfig = { version: 1, rules: [
    { id: 's1', kind: 'scaffold', for: "class = 'IfcWall' and IsExternal = TRUE", erect: { daysBefore: 2, duration: 2 }, strike: { after: 'A500', daysAfter: 1 }, size: { lift: 2.5 } },
    { kind: 'falsework', for: "class = 'IfcSlab'", strike: { daysAfter: 10 } },
    { kind: 'formwork', for: "class = 'IfcWall'", erect: { activity: 'A310' } },
  ] };

  it('reads a valid section and keeps it as it is', () => {
    const r = parseTempWorks(JSON.parse(JSON.stringify(ok)));
    expect(r.problems).toEqual([]);
    expect(r.config).toEqual(ok);
    expect(parseTempWorks(JSON.stringify(ok)).config).toEqual(ok);
  });

  it('is versioned: a missing or other version, a non-list and non-JSON give no config', () => {
    expect(parseTempWorks({ rules: [] }).config).toBeNull();
    expect(parseTempWorks({ version: 2, rules: [] }).problems[0]).toContain('"version" must be 1');
    expect(parseTempWorks({ version: 1, rules: 'x' }).config).toBeNull();
    expect(parseTempWorks('{nope').config).toBeNull();
    expect(parseTempWorks(5).config).toBeNull();
  });

  it('leaves out rules that are wrong and says why', () => {
    const r = parseTempWorks({ version: 1, rules: [
      { kind: 'crane', for: 'x = 1' },
      { kind: 'scaffold', for: '' },
      { kind: 'scaffold', for: "class = " },
      { id: 'a', kind: 'scaffold', for: "class = 'IfcWall'" },
      { id: 'a', kind: 'formwork', for: "class = 'IfcWall'" },
      { kind: 'scaffold', for: "class = 'IfcWall'", size: { lift: -1 } },
      { kind: 'scaffold', for: "class = 'IfcWall'", erect: { daysBefore: 'two' } },
      { kind: 'falsework', for: "class = 'IfcSlab'", strike: { activity: '' } },
    ] });
    expect(r.config!.rules.map((x) => x.id)).toEqual(['a']);
    expect(r.problems.length).toBe(7);
    expect(r.problems.join('\n')).toMatch(/kind must be/);
    expect(r.problems.join('\n')).toMatch(/is used twice/);
    expect(r.problems.join('\n')).toMatch(/size\.lift/);
  });

  it('fills ids, names and the default sizes', () => {
    const rs = resolveRules(ok);
    expect(rs.map((r) => r.id)).toEqual(['s1', 'tw2', 'tw3']);
    expect(rs[0]!.size).toEqual({ ...TEMP_DEFAULTS, lift: 2.5 });
    expect(TEMP_DEFAULTS).toMatchObject({ offset: 0.3, width: 0.8, lift: 2, bay: 2.5, spacing: 1.2, thickness: 0.05 });
    expect(rs[1]!.name).toBe('Falsework');
  });

  it('is part of the .4d.json: read, kept and written again', () => {
    const cfg = { ...buildConfig(), temporaryWorks: ok };
    const back = parseConfig(serializeConfig(cfg));
    expect(back.problems).toEqual([]);
    expect(back.config!.temporaryWorks).toEqual(ok);
    const bad = parseConfig(JSON.stringify({ ...cfg, temporaryWorks: { version: 9, rules: [] } }));
    expect(bad.config!.temporaryWorks).toBeUndefined();
    expect(bad.problems.join()).toContain('temporaryWorks');
  });
});

// ---------------------------------------------------------------- a synthetic two-storey box

const el = (id: string, cls: string, name: string, storey: string, b: [number, number, number, number, number, number]): FourDElement => ({ globalId: id, ifcClass: cls, name, storey, props: {}, bbox: b });
/** 10 x 8 m, walls 0.3 m thick and 3 m high on two storeys (z 0..3, 3.3..6.3), a slab on top of each storey. */
function box(): FourDModel {
  const els: FourDElement[] = [];
  for (const [s, z0] of [['G', 0], ['U', 3.3]] as const) {
    els.push(el(`S-${s}`, 'IfcWall', `South ${s}`, s, [0, 0, z0, 10, 0.3, z0 + 3]));
    els.push(el(`N-${s}`, 'IfcWall', `North ${s}`, s, [0, 7.7, z0, 10, 8, z0 + 3]));
    els.push(el(`W-${s}`, 'IfcWall', `West ${s}`, s, [0, 0.3, z0, 0.3, 7.7, z0 + 3]));
    els.push(el(`E-${s}`, 'IfcWall', `East ${s}`, s, [9.7, 0.3, z0, 10, 7.7, z0 + 3]));
  }
  els.push(el('SLAB-G', 'IfcSlab', 'Ground slab', 'G', [0, 0, -0.3, 10, 8, 0]));
  els.push(el('SLAB-U', 'IfcSlab', 'Upper slab', 'U', [0, 0, 3, 10, 8, 3.3]));
  return { identityKey: 'box', name: 'box.ifc', elements: els, storeys: [{ name: 'G', elevation: 0 }, { name: 'U', elevation: 3.3 }] };
}

const tl = (id: string, task: string, from: string, to: string) => ({ globalId: id, intervals: [{ from: L(from), to: L(to), state: 'active' as const, task }, { from: L(to), to: Number.MAX_SAFE_INTEGER, state: 'complete' as const, task }] });
const timelines = () => [
  ...['S-G', 'N-G', 'W-G', 'E-G'].map((g) => tl(g, 'W1', '2027-03-08T08:00', '2027-03-12T17:00')),
  ...['S-U', 'N-U', 'W-U', 'E-U'].map((g) => tl(g, 'W2', '2027-03-22T08:00', '2027-03-26T17:00')),
  tl('SLAB-U', 'SL', '2027-03-15T08:00', '2027-03-16T17:00'),
];
const spans = new Map([['W1', { start: L('2027-03-08T08:00'), end: L('2027-03-12T17:00') }], ['W2', { start: L('2027-03-22T08:00'), end: L('2027-03-26T17:00') }], ['SL', { start: L('2027-03-15T08:00'), end: L('2027-03-16T17:00') }], ['FAC', { start: L('2027-04-12T08:00'), end: L('2027-04-16T17:00') }], ['STR', { start: L('2027-04-19T08:00'), end: L('2027-04-19T17:00') }]]);

const groupsOf = (rules: TempWorksConfig['rules']): TempWorksGroup[] => buildTempWorksGroups({ version: 1, rules }, { model: box(), elements: timelines(), spans }).groups;

describe('temporary works geometry (synthetic two-storey box)', () => {
  const rules: TempWorksConfig['rules'] = [{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall'" }];
  const groups = groupsOf(rules);
  const model = box();
  const pieces = generatePieces(groups, model);

  it('makes one scaffold group per storey from the walls it serves', () => {
    expect(groups.map((g) => [g.id, g.storey, g.elements.length, g.task])).toEqual([['TW-sc-1', 'G', 4, 'W1'], ['TW-sc-2', 'U', 4, 'W2']]);
  });

  it('counts bays, lifts and standards: 10 m and 7.4 m runs in 2.5 m bays, 3 m of wall in 2 m lifts', () => {
    for (const st of pieces.stats) {
      expect(st.runs).toBe(4);
      expect(st.bays).toBe(4 + 4 + 3 + 3); // 10 / 2.5 = 4; 7.4 / 2.5 -> 3
      expect(st.lifts).toBe(2);
      expect(st.standards).toBe((5 + 5 + 4 + 4) * 2);
      expect(st.pieces).toBe(st.standards + st.lifts * st.bays * 4); // two ledgers, a board and a guard per bay and lift
    }
    expect(pieces.count).toBe(2 * 148);
  });

  it('puts the standards 0.3 m and 1.1 m off the outer face, as tall as the lifts plus 1 m', () => {
    const south = groups[0]!.elements.indexOf('S-G');
    const north = groups[0]!.elements.indexOf('N-G');
    const stand = (run: number): Array<[number, number, number]> => { const out: Array<[number, number, number]> = []; for (let i = 0; i < pieces.count; i++) if (pieces.group[i] === 0 && pieces.kind[i] === 0 && pieces.run[i] === run) out.push([pieces.box[i * 6 + 1]!, pieces.box[i * 6 + 2]!, pieces.box[i * 6 + 5]!]); return out; };
    expect([...new Set(stand(south).map((p) => +p[0].toFixed(3)))].sort((a, b) => a - b)).toEqual([-1.1, -0.3]); // the wall face is y = 0
    expect([...new Set(stand(north).map((p) => +p[0].toFixed(3)))].sort((a, b) => a - b)).toEqual([8.3, 9.1]); // the wall face is y = 8
    expect(stand(south).every((p) => Math.abs(p[2] - 5) < 1e-6 && Math.abs(p[1] - 2.5) < 1e-6)).toBe(true);
  });

  it('builds the lifts bottom-up: the boards of lift 1 come before lift 2, standards first', () => {
    const order = (lift: number, kind: number): number[] => { const o: number[] = []; for (let i = 0; i < pieces.count; i++) if (pieces.group[i] === 0 && pieces.lift[i] === lift && pieces.kind[i] === kind) o.push(pieces.order[i]!); return o; };
    expect(Math.max(...order(1, 2))).toBeLessThan(Math.max(...order(2, 2)));
    expect(Math.max(...order(1, 2))).toBeLessThanOrEqual(Math.min(...order(2, 2)) + 1e-9);
    for (let i = 0; i < pieces.count; i++) if (pieces.kind[i] === 0) expect(pieces.order[i]).toBe(0);
    const boards: number[] = []; for (let i = 0; i < pieces.count; i++) if (pieces.group[i] === 0 && pieces.kind[i] === 2) boards.push(+pieces.box[i * 6 + 2]!.toFixed(3));
    expect([...new Set(boards)].sort((a, b) => a - b)).toEqual([2, 4]);
    expect(pieces.describe(pieces.range[0]![0] + 30)).toMatch(/^Temporary works: Scaffold, wall run W\d, lift [12]$/);
  });

  it('honours the size parameters of the rule', () => {
    const g = groupsOf([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and name = 'South G'", size: { offset: 0.5, width: 1, lift: 1.5, bay: 5 } }]);
    const p = generatePieces(g, model);
    expect(p.stats[0]).toMatchObject({ bays: 2, lifts: 2, standards: 6 });
    const ys = new Set<number>(); for (let i = 0; i < p.count; i++) if (p.kind[i] === 0) ys.add(+p.box[i * 6 + 1]!.toFixed(3));
    expect([...ys].sort((a, b) => a - b)).toEqual([-1.5, -0.5]);
  });

  it('falsework: props on a 1.2 m grid under the soffit down to the slab below, head beams on top, none inside walls', () => {
    const g = groupsOf([{ id: 'fw', kind: 'falsework', for: "class = 'IfcSlab' and name = 'Upper slab'" }]);
    expect(g.length).toBe(1);
    const p = generatePieces(g, model);
    expect(p.stats[0]).toMatchObject({ props: 42, pieces: 42 + 8 });
    for (let i = 0; i < p.count; i++) if (p.kind[i] === 4) {
      expect(p.box[i * 6 + 5]).toBeCloseTo(2.9, 5); // soffit 3.0 minus the 0.1 head beam, down to the ground slab top at 0
      expect(p.box[i * 6 + 2]).toBeCloseTo(1.45, 5);
    }
    const xs = new Set<number>(); for (let i = 0; i < p.count; i++) if (p.kind[i] === 4) xs.add(+p.box[i * 6]!.toFixed(3));
    const sorted = [...xs].sort((a, b) => a - b);
    expect(sorted[1]! - sorted[0]!).toBeCloseTo(1.2, 3);
    const heads: number[] = []; const props: number[] = [];
    for (let i = 0; i < p.count; i++) (p.kind[i] === 5 ? heads : props).push(p.order[i]!);
    expect(Math.min(...heads)).toBeGreaterThan(Math.max(...props)); // props, then the deck
  });

  it('formwork: 0.05 m panels on both faces of a wall, under the soffit and round the edges of a slab', () => {
    const w = generatePieces(groupsOf([{ id: 'fw', kind: 'formwork', for: "name = 'South G'" }]), model);
    expect(w.stats[0]!.panels).toBe(2 * 5); // 10 m in panels of at most 2.4 m
    const faces = new Set<number>(); for (let i = 0; i < w.count; i++) { faces.add(+w.box[i * 6 + 1]!.toFixed(3)); expect(w.box[i * 6 + 4]).toBeCloseTo(0.05, 6); }
    expect([...faces].sort((a, b) => a - b)).toEqual([-0.025, 0.325]);
    const s = generatePieces(groupsOf([{ id: 'fw', kind: 'formwork', for: "name = 'Upper slab'" }]), model);
    expect(s.stats[0]!.panels).toBe(5 * 4 + 5 * 2 + 4 * 2);
    const soffit = [...Array(s.count).keys()].filter((i) => Math.abs(s.box[i * 6 + 2]! - 2.975) < 1e-6);
    expect(soffit.length).toBe(20);
  });
});

describe('temporary works timelines', () => {
  const g = (rules: TempWorksConfig['rules']) => groupsOf(rules);

  it('erects before the served work and strikes after it, by default per kind', () => {
    const [a] = g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and storey = 'G'" }]);
    expect(a!.erect).toEqual({ from: L('2027-03-05T08:00'), to: L('2027-03-07T08:00') }); // 1 day before the start, taking 2
    expect(a!.strike.from).toBe(L('2027-03-12T17:00') + DAY); // 1 day after the end
    const [f] = g([{ id: 'fw', kind: 'falsework', for: "name = 'Upper slab'" }]);
    expect(f!.strike.from).toBe(L('2027-03-16T17:00') + 14 * DAY);
    const [m] = g([{ id: 'fm', kind: 'formwork', for: "name = 'Upper slab'" }]);
    expect(m!.strike.from).toBe(L('2027-03-16T17:00') + 3 * DAY);
  });

  it('takes the offsets of the rule, or ties them to other activities', () => {
    const [a] = g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and storey = 'G'", erect: { daysBefore: 3, duration: 1 }, strike: { after: 'FAC', daysAfter: 2, duration: 3 } }]);
    expect(a!.erect).toEqual({ from: L('2027-03-04T08:00'), to: L('2027-03-05T08:00') });
    expect(a!.strike).toEqual({ from: L('2027-04-16T17:00') + 2 * DAY, to: L('2027-04-16T17:00') + 5 * DAY });
    const [f] = g([{ id: 'fw', kind: 'falsework', for: "name = 'Upper slab'", erect: { activity: 'SL' }, strike: { activity: 'STR' } }]);
    expect(f!.erect).toEqual({ from: spans.get('SL')!.start, to: spans.get('SL')!.end });
    expect(f!.strike).toEqual({ from: spans.get('STR')!.start, to: spans.get('STR')!.end });
  });

  it('never strikes before it is up, and an unknown activity falls back to the served work', () => {
    const [a] = g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and storey = 'G'", strike: { activity: 'SL' } }]);
    expect(a!.strike.from).toBeGreaterThanOrEqual(a!.erect.to);
    const [b] = g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and storey = 'G'", strike: { after: 'NOPE', daysAfter: 0 } }]);
    expect(b!.strike.from).toBe(L('2027-03-12T17:00'));
  });

  it('splits by storey and by the activity that builds the elements, and skips elements with no work of their own', () => {
    const gs = g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall'" }, { id: 'x', kind: 'falsework', for: "name = 'Ground slab'" }]);
    expect(gs.filter((x) => x.rule === 'sc').map((x) => x.task)).toEqual(['W1', 'W2']);
    expect(gs.some((x) => x.rule === 'x')).toBe(false); // no timeline: it stood before the job
    expect(gs.map((x) => x.erect.from)).toEqual([...gs.map((x) => x.erect.from)].sort((p, q) => p - q));
  });

  it('a rule whose query matches nothing gives no group', () => {
    expect(g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcRoof'" }])).toEqual([]);
  });

  it('progress: 0, rising while erected, 1 in use, falling while struck, 0 after', () => {
    const [a] = g([{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and storey = 'G'" }]);
    expect(groupProgress(a!, a!.erect.from - 1)).toBe(0);
    expect(groupProgress(a!, (a!.erect.from + a!.erect.to) / 2)).toBeCloseTo(0.5, 6);
    expect(groupProgress(a!, a!.erect.to + 1)).toBe(1);
    expect(groupProgress(a!, (a!.strike.from + a!.strike.to) / 2)).toBeCloseTo(0.5, 6);
    expect(groupProgress(a!, a!.strike.to)).toBe(0);
    expect([a!.erect.from - 1, a!.erect.from + 1, a!.erect.to + 1, a!.strike.from + 1, a!.strike.to + 1].map((t) => groupPhase(a!, t))).toEqual(['before', 'erecting', 'in use', 'striking', 'gone']);
  });

  it('pieces fade in by their order, the first at the start and every one at the end', () => {
    for (const w of [fadeShare(undefined), fadeShare(0)]) {
      expect(pieceAlpha(0, 0, w)).toBe(0);
      expect(pieceAlpha(1, 1, w)).toBe(1);
      expect(pieceAlpha(0.5, 0.2, w)).toBeGreaterThanOrEqual(pieceAlpha(0.5, 0.8, w));
    }
    expect(fadeShare(0)).toBeLessThan(fadeShare(undefined));
  });
});

describe('temporary works in the plan', () => {
  const model = buildModel();
  const schedule = buildSchedule();
  const rules: TempWorksConfig = { version: 1, rules: [{ id: 'sc', kind: 'scaffold', for: "class = 'IfcWall' and name like 'Wall%'", strike: { after: 'A500', daysAfter: 1 } }, { id: 'fw', kind: 'falsework', for: "class = 'IfcSlab'" }] };
  const config = { ...buildConfig(), temporaryWorks: rules };
  const links = linkSchedule(schedule, model, config, []);
  const plan = buildPlan(schedule, links, model, { ...DEFAULT_STYLE }, { config });

  it('gets its own timeline per group from the activities of the elements it serves', () => {
    const groups = plan.temporaryWorks!.groups;
    expect(plan.temporaryWorks!.version).toBe(1);
    expect(groups.length).toBeGreaterThanOrEqual(4);
    for (const g of groups) {
      const starts = g.elements.map((id) => plan.elements.find((e) => e.globalId === id)!.intervals.find((i) => i.state === 'active')!);
      expect(g.erect.to).toBeLessThanOrEqual(Math.min(...starts.map((i) => i.from)));
      expect(g.strike.from).toBeGreaterThanOrEqual(g.erect.to);
      expect(g.size.lift).toBe(2);
    }
    const sc = groups.filter((g) => g.rule === 'sc');
    expect(sc.every((g) => g.strike.from === L('2027-02-19T17:00') + DAY)).toBe(true);
  });

  it('survives a JSON round trip unchanged', () => {
    const back = JSON.parse(JSON.stringify(plan)) as FourDPlan;
    expect(back.temporaryWorks).toEqual(plan.temporaryWorks);
    expect(back).toEqual(JSON.parse(JSON.stringify(plan)));
  });

  it('is left out with temporaryWorks: false, and without rules; the rest of the plan does not change', () => {
    const off = buildPlan(schedule, links, model, { ...DEFAULT_STYLE }, { config, temporaryWorks: false });
    expect(off.temporaryWorks).toBeUndefined();
    const none = buildPlan(schedule, links, model, { ...DEFAULT_STYLE }, { config: buildConfig() });
    expect(none.temporaryWorks).toBeUndefined();
    expect(off.elements).toEqual(none.elements);
    expect(off.tasks).toEqual(none.tasks);
    expect(off.milestones).toEqual(none.milestones);
  });
});
