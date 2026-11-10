// The classifier pipeline: rules, signature cache, the exact Jev request, response parsing, answer validation, review
// logic, backoff and abort. No real network: a stub fetch and the mock provider only.

import { describe, expect, it } from 'vitest';
import { buildInput, buildInputs, classByRules, classifyInputs, createJevProvider, createMockProvider, defaultSchema, MemoryCache, parseResponse, resolveRule, signatureOf } from '../src/classify';
import type { Answers, ClassifyInput, DecisionModel, Questions } from '../src/classify';
import { buildRequest } from '../src/classify/jevAdapter';
import { decodeAnswers } from '../src/classify/pipeline';
import { mainQuestions, subQuestions } from '../src/classify/questions';
import { computeNeedsReview, topMargin } from '../src/classify/review';
import { ProviderError } from '../src/classify/types';
import { buildState } from '../src/classify/state';
import { jsonResponse, sidecarModel } from './classify-helpers';

const schema = defaultSchema();

const input = (over: Partial<ClassifyInput> = {}): ClassifyInput => ({
  id: 'G1', ifcClass: 'IfcBuildingElementProxy', name: 'Unit 7', psets: { Attr: { ObjectType: 'Box:Generic' } }, ...over,
});

describe('rules', () => {
  it('place the classes of fzk-haus', () => {
    const m = sidecarModel('fzk-haus');
    const by = new Map<string, Set<string>>();
    for (const i of buildInputs(m)) {
      const h = classByRules(i)!;
      expect(resolveRule(h, schema, true), i.ifcClass).not.toBeNull();
      (by.get(i.ifcClass) ?? by.set(i.ifcClass, new Set()).get(i.ifcClass)!).add(`${h.discipline}/${h.subDiscipline}`);
    }
    expect([...by.get('IfcDoor')!]).toEqual(['ARC/DOR']);
    expect([...by.get('IfcWindow')!]).toEqual(['ARC/WIN']);
    expect([...by.get('IfcWallStandardCase')!]).toEqual(['ARC/WAL']);
    expect([...by.get('IfcBeam')!]).toEqual(['STR/BEM']);
    expect([...by.get('IfcSlab')!]).toEqual(['STR/SLB']);
    expect([...by.get('IfcStair')!]).toEqual(['ARC/STA']);
    expect([...by.get('IfcRailing')!]).toEqual(['ARC/STA']);
  });

  it('place the classes of synth5k, all with a final rule', () => {
    const m = sidecarModel('synth5k');
    const want: Record<string, string> = { IfcBeam: 'STR', IfcColumn: 'STR', IfcSlab: 'STR', IfcWall: 'ARC', IfcDuctSegment: 'MEC', IfcPipeSegment: 'PLB' };
    for (const i of buildInputs(m)) {
      const h = classByRules(i)!;
      expect(h.discipline, i.ifcClass).toBe(want[i.ifcClass]);
      expect(h.confidence, i.ifcClass).toBeGreaterThanOrEqual(0.85);
    }
  });

  it('send IfcWall to Structural only when LoadBearing is true', () => {
    const wall = (lb: boolean): ClassifyInput => input({ ifcClass: 'IfcWall', name: 'W', psets: { Pset_WallCommon: { LoadBearing: lb } } });
    expect(classByRules(wall(true))!.discipline).toBe('STR');
    expect(classByRules(wall(false))!.discipline).toBe('ARC');
    expect(classByRules(input({ ifcClass: 'IfcDuctSegment' }))!.discipline).toBe('MEC');
    for (const c of ['IfcBeam', 'IfcColumn', 'IfcFooting']) expect(classByRules(input({ ifcClass: c }))!.discipline).toBe('STR');
  });

  it('use the system name for a pipe, and stay weak without one', () => {
    expect(classByRules(input({ ifcClass: 'IfcPipeSegment', systems: ['Sprinkler zone 2'] }))!.discipline).toBe('FPR');
    expect(classByRules(input({ ifcClass: 'IfcPipeSegment', systems: ['Chilled water'] }))!.discipline).toBe('MEC');
    expect(classByRules(input({ ifcClass: 'IfcPipeSegment' }))!.confidence).toBeLessThan(0.85);
    expect(classByRules(input({ ifcClass: 'IfcPump' }))!.confidence).toBeLessThan(0.85);
  });

  it('map to the codes of another schema by rulesKey, and give no rule when the schema has no such discipline', () => {
    const s = JSON.parse(JSON.stringify(schema));
    s.disciplines = s.disciplines.filter((d: { code: string }) => d.code !== 'MEC');
    const h = classByRules(input({ ifcClass: 'IfcDuctSegment' }))!;
    expect(resolveRule(h, s, true)).toBeNull();
    const t = JSON.parse(JSON.stringify(schema));
    t.disciplines.find((d: { code: string }) => d.code === 'MEC').code = 'M';
    t.disciplines.find((d: { code: string }) => d.code === 'M').rulesKey = 'MEC';
    expect(resolveRule(h, t, true)!.discipline).toBe('M');
  });
});

describe('signature cache and call counts', () => {
  it('needs tens of requests, not thousands, for synth5k when every element goes to the model', async () => {
    const inputs = buildInputs(sidecarModel('synth5k'));
    const p = createMockProvider();
    const { results, stats } = await classifyInputs(inputs, { schema, provider: p, rules: false });
    expect(results).toHaveLength(5000);
    expect(stats.signatures).toBeLessThan(30);
    expect(stats.calls).toBe(p.log.length);
    expect(stats.calls).toBeLessThanOrEqual(stats.signatures * 2);
    expect(stats.bySource.model).toBe(stats.signatures);
    expect(stats.bySource.model + stats.bySource.cache).toBe(5000);
    expect(stats.calls).toBeLessThan(60);
  });

  it('answers a repeat run from the cache without a request', async () => {
    const inputs = buildInputs(sidecarModel('fzk-haus'));
    const cache = new MemoryCache();
    const p1 = createMockProvider();
    const a = await classifyInputs(inputs, { schema, provider: p1, rules: false, cache });
    expect(a.stats.calls).toBeGreaterThan(0);
    const p2 = createMockProvider();
    const b = await classifyInputs(inputs, { schema, provider: p2, rules: false, cache });
    expect(p2.log).toHaveLength(0);
    expect(b.stats.calls).toBe(0);
    expect(b.stats.bySource.cache).toBe(inputs.length);
    expect(b.results.map((r) => r.discipline.code)).toEqual(a.results.map((r) => r.discipline.code));
  });

  it('shares one signature across elements with the same class, type and key properties', () => {
    const a = input({ id: 'A', name: 'Pump 1' });
    const b = input({ id: 'B', name: 'Pump 1' });
    const c = input({ id: 'C', name: 'Pump 1', psets: { Attr: { ObjectType: 'Box:Other' } } });
    expect(signatureOf(a)).toBe(signatureOf(b));
    expect(signatureOf(a)).not.toBe(signatureOf(c));
    // no type name: the name stem tells generic elements apart, digits do not
    const x = input({ id: 'X', name: 'Chair 12', psets: {} });
    const y = input({ id: 'Y', name: 'Chair 13', psets: {} });
    const z = input({ id: 'Z', name: 'Pump 13', psets: {} });
    expect(signatureOf(x)).toBe(signatureOf(y));
    expect(signatureOf(x)).not.toBe(signatureOf(z));
  });

  it('lets the rules decide first: no request for fzk-haus elements with a final rule', async () => {
    const inputs = buildInputs(sidecarModel('fzk-haus'));
    const p = createMockProvider();
    const { stats } = await classifyInputs(inputs, { schema, provider: p });
    expect(stats.bySource.rules).toBe(40);
    expect(stats.signatures).toBe(1); // the 42 IfcMember share one signature
    expect(stats.calls).toBeLessThanOrEqual(2);
    expect(stats.bySource.model + stats.bySource.cache).toBe(42);
  });

  it('keeps a manual result over everything', async () => {
    const inputs = buildInputs(sidecarModel('fzk-haus')).slice(0, 5);
    const manual = new Map([[inputs[0]!.id, { id: inputs[0]!.id, discipline: { code: 'GEN', label: 'x', confidence: 1, probabilities: { GEN: 1 } }, subDiscipline: null, masterformat: null, buildingElement: 1, source: 'manual' as const, needsReview: false }]]);
    const { results } = await classifyInputs(inputs, { schema, manual });
    expect(results[0]!.source).toBe('manual');
    expect(results[0]!.discipline.code).toBe('GEN');
  });
});

describe('pictures with a request', () => {
  const inputs = buildInputs(sidecarModel('synth5k')).slice(0, 3);
  const seen: Array<{ state: Record<string, unknown>; images: readonly string[] | undefined }> = [];
  const spy: DecisionModel = { provider: 'spy', async decide(state, questions, signal, extra) { seen.push({ state, images: extra?.images }); return createMockProvider().decide(state, questions, signal, extra); } };

  it('sends the pictures with both requests of a signature and puts the note about them first in the state', async () => {
    seen.length = 0;
    const note = 'Picture 1: the element alone, a render, axonometric, with a scale bar. Picture 2: the element (orange) in its bounding box with nearby elements in grey.';
    await classifyInputs(inputs, { schema, provider: spy, rules: false, images: () => ({ images: ['data:image/webp;base64,AA', 'data:image/webp;base64,BB'], note }) });
    expect(seen.length).toBeGreaterThanOrEqual(2);
    for (const r of seen) {
      expect(r.images).toEqual(['data:image/webp;base64,AA', 'data:image/webp;base64,BB']);
      expect(Object.keys(r.state)[0]).toBe('pictures');
      expect(r.state['pictures']).toBe(note);
    }
  });
  it('still takes a plain list of pictures (no note, the state is unchanged)', async () => {
    seen.length = 0;
    await classifyInputs(inputs, { schema, provider: spy, rules: false, images: () => ['data:image/png;base64,AA'] });
    expect(seen.every((r) => r.images?.length === 1 && !('pictures' in r.state))).toBe(true);
  });
  it('puts the SVG geometry into the state as one line, legend first, and the note before it', async () => {
    seen.length = 0;
    await classifyInputs(inputs, { schema, provider: spy, rules: false, geometry: () => ({ legend: 'Geometry as SVG, metres.', svg: "<svg id='plan'/>\n<svg id='elev'/>" }), images: () => ({ images: ['data:image/png;base64,AA'], note: 'Picture 1: x.' }) });
    for (const r of seen) {
      expect(Object.keys(r.state).slice(0, 2)).toEqual(['pictures', 'geometry']);
      expect(r.state['geometry']).toBe("Geometry as SVG, metres. <svg id='plan'/> <svg id='elev'/>");
    }
  });
  it('goes on without the geometry when it cannot be made, and says so', async () => {
    seen.length = 0;
    const { stats } = await classifyInputs(inputs, { schema, provider: spy, rules: false, geometry: () => { throw new Error('no mesh'); } });
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((r) => !('geometry' in r.state))).toBe(true);
    expect(stats.errors.join(' ')).toMatch(/The geometry of an element could not be made, so it went out without it: no mesh/);
  });
  it('goes on with the text alone when the pictures cannot be made, and says so', async () => {
    seen.length = 0;
    const { stats } = await classifyInputs(inputs, { schema, provider: spy, rules: false, images: () => { throw new Error('no WebGL'); } });
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((r) => r.images === undefined && !('pictures' in r.state))).toBe(true);
    expect(stats.errors.join(' ')).toMatch(/Pictures of an element could not be made, so it went out as text only: no WebGL/);
  });
});

describe('the Jev request', () => {
  it('has exactly this JSON for a sample element', () => {
    const i: ClassifyInput = {
      id: 'GID-DUCT-1', ifcClass: 'IfcFlowSegment', name: 'Supply 300x200',
      psets: { Attr: { ObjectType: 'Rectangular Duct:Standard', Tag: '' }, Pset_Custom: { Note: 'x'.repeat(500), Flow: 0.4 } },
      quantities: { Qto_X: { Length: 3.2 } },
      type: { ifcClass: 'IfcFlowSegmentType', name: 'Rectangular Duct:Standard', psets: {} },
      systems: ['Supply Air'],
      hierarchy: { path: [{ ifcClass: 'IfcBuildingStorey', name: 'Level 1', globalId: 's1' }], parents: [{ ifcClass: 'IfcWall', name: 'Wall A', psets: { Pset_WallCommon: { LoadBearing: false } } }] },
    };
    const req = buildRequest('jev-1.13.0', buildState(i), mainQuestions(schema));
    const wire = JSON.parse(JSON.stringify(req));
    expect(Object.keys(wire)).toEqual(['model', 'state', 'questions']);
    expect(wire.model).toBe('jev-1.13.0');
    expect(wire.state).toEqual({
      class: 'IfcFlowSegment',
      name: 'Supply 300x200',
      type: { class: 'IfcFlowSegmentType', name: 'Rectangular Duct:Standard' },
      psets: { Attr: { ObjectType: 'Rectangular Duct:Standard' }, Pset_Custom: { Flow: 0.4 } },
      quantities: { Qto_X: { Length: 3.2 } },
      systems: ['Supply Air'],
      hierarchy: ['IfcBuildingStorey: Level 1'],
      parents: [{ class: 'IfcWall', name: 'Wall A', psets: { Pset_WallCommon: { LoadBearing: false } } }],
      building_context: true,
    });
    expect(Object.keys(wire.questions)).toEqual(['discipline', 'building_element', 'masterformat']);
    const d = wire.questions.discipline;
    expect(d.type).toBe('choice');
    expect(Object.keys(d.criteria)).toEqual(schema.disciplines.map((x) => x.code));
    expect(d.criteria.MEC).toBe('Mechanical and HVAC. Heating, ventilation and air conditioning: ducts, air terminals, fans, air handling, chillers, boilers, hydronic piping.');
    expect(wire.questions.building_element).toEqual({ type: 'noul', instructions: 'This element is part of a building (not of a road, a bridge, a site utility or a process plant).' });
    const m = wire.questions.masterformat;
    expect(m.type).toBe('choice');
    expect(Object.keys(m.criteria)).toHaveLength(35);
    expect(m.criteria['23']).toMatch(/^Heating, Ventilating, and Air Conditioning \(HVAC\)\. /);
  });

  it('limits the sub-discipline question to the sub-codes of the discipline, or of the top 2 together', () => {
    const one = subQuestions(schema, ['MEC'])!;
    expect(Object.keys((one['sub_discipline'] as { criteria: object }).criteria)).toEqual(['DUC', 'TRM', 'EQP', 'HYD', 'ACC']);
    const two = subQuestions(schema, ['MEC', 'PLB'])!;
    expect(Object.keys((two['sub_discipline'] as { criteria: object }).criteria)).toContain('MEC/DUC');
    expect(Object.keys((two['sub_discipline'] as { criteria: object }).criteria)).toContain('PLB/SUP');
    expect(subQuestions(schema, ['GEN'])).toBeNull(); // one sub-code: nothing to ask
  });

  it('is sent with a bearer key and JSON headers, and without Authorization when there is no key', async () => {
    const seen: Array<{ url: string; headers: Record<string, string>; body: string }> = [];
    const fetchImpl = (async (url: string, init: RequestInit) => {
      seen.push({ url, headers: init.headers as Record<string, string>, body: String(init.body) });
      return jsonResponse(SAMPLE_RESPONSE);
    }) as unknown as typeof fetch;
    const q: Questions = SAMPLE_QUESTIONS;
    const withKey = createJevProvider({ endpoint: 'https://api.typesafe.ai/v1/systemone', model: 'jev-1.13.0', apiKey: () => 'sk-test-123', timeoutMs: 5000, fetchImpl });
    await withKey.decide({ class: 'IfcWall' }, q, new AbortController().signal);
    const noKey = createJevProvider({ endpoint: '/proxy/jev', model: 'jev-1.13.0', apiKey: () => null, timeoutMs: 5000, fetchImpl });
    await noKey.decide({ class: 'IfcWall' }, q, new AbortController().signal);
    expect(seen[0]!.url).toBe('https://api.typesafe.ai/v1/systemone');
    expect(seen[0]!.headers).toEqual({ 'Content-Type': 'application/json', Authorization: 'Bearer sk-test-123' });
    expect(JSON.parse(seen[0]!.body)).toEqual({ model: 'jev-1.13.0', state: { class: 'IfcWall' }, questions: q });
    expect(seen[1]!.url).toBe('/proxy/jev');
    expect(seen[1]!.headers).toEqual({ 'Content-Type': 'application/json' });
  });
});

const SAMPLE_QUESTIONS: Questions = {
  discipline: { type: 'choice', instructions: 'Pick one.', criteria: { MEC: 'HVAC', PLB: 'Plumbing', ARC: 'Architecture' } },
  building_element: { type: 'noul', instructions: 'This element is part of a building.' },
  level: { type: 'score', instructions: 'How complete?', criteria: ['none', 'some', 'full'] },
};
const SAMPLE_RESPONSE = {
  model: 'jev-1.13.0',
  answers: {
    discipline: { type: 'choice', choice: 'MEC', confidence: 0.93, probabilities: { MEC: 0.93, PLB: 0.05, ARC: 0.02 } },
    building_element: { type: 'noul', noul: 0.97 },
    level: { type: 'score', score: 2, confidence: 0.8, legend: { '0': 'none', '1': 'some', '2': 'full' }, probabilities: { '0': 0.05, '1': 0.15, '2': 0.8 } },
  },
  usage: { input_tokens: 812, output_tokens: 6 },
};

describe('the Jev response', () => {
  it('parses a sample response of all three question types', () => {
    const a = parseResponse(SAMPLE_RESPONSE, SAMPLE_QUESTIONS);
    expect(a.model).toBe('jev-1.13.0');
    expect(a.answers['discipline']).toEqual({ type: 'choice', choice: 'MEC', confidence: 0.93, probabilities: { MEC: 0.93, PLB: 0.05, ARC: 0.02 } });
    expect(a.answers['building_element']).toEqual({ type: 'noul', noul: 0.97 });
    expect(a.answers['level']).toMatchObject({ type: 'score', score: 2, confidence: 0.8 });
    expect(a.usage).toEqual({ input_tokens: 812, output_tokens: 6 });
  });

  it('rejects answers that break the contract, with a plain message', () => {
    const bad = (mut: (r: any) => void): string => {
      const r = JSON.parse(JSON.stringify(SAMPLE_RESPONSE));
      mut(r);
      try {
        parseResponse(r, SAMPLE_QUESTIONS);
      } catch (e) {
        return (e as Error).message;
      }
      return '';
    };
    expect(bad((r) => (r.answers.discipline.choice = 'HVAC'))).toMatch(/not one of the options/);
    expect(bad((r) => delete r.answers.building_element)).toMatch(/no answer for "building_element"/);
    expect(bad((r) => (r.answers.discipline.confidence = 1.4))).toMatch(/confidence from 0 to 1/);
    expect(bad((r) => (r.answers.building_element.noul = -0.1))).toMatch(/probability from 0 to 1/);
    expect(bad((r) => (r.answers.discipline.probabilities.XXX = 0.1))).toMatch(/not one of the options/);
    expect(bad((r) => (r.answers.discipline.type = 'noul'))).toMatch(/expected "choice"/);
    expect(bad((r) => delete r.model)).toMatch(/no model id/);
    expect(bad((r) => (r.answers.level.score = 5))).toMatch(/outside the levels/);
  });

  it('checks every code against the schema, not only against the options', () => {
    const q = mainQuestions(schema);
    const main = (disc: string, div: string, building = 0.95): Answers => ({
      model: 'jev-1.13.0',
      answers: {
        discipline: { type: 'choice', choice: disc, confidence: 0.9, probabilities: { [disc]: 0.9 } },
        building_element: { type: 'noul', noul: building },
        masterformat: { type: 'choice', choice: div, confidence: 0.8, probabilities: { [div]: 0.8 } },
      },
    });
    expect(parseResponse(main('MEC', '23'), q).model).toBe('jev-1.13.0');
    expect(decodeAnswers(schema, main('MEC', '23'), null, ['MEC']).masterformat?.title).toBe('Heating, Ventilating, and Air Conditioning (HVAC)');
    expect(() => decodeAnswers(schema, main('ZZZ', '23'), null, ['ZZZ'])).toThrow(/not in the schema/);
    expect(() => decodeAnswers(schema, main('MEC', '99'), null, ['MEC'])).toThrow(/division "99"/);
    // not a building element: no MasterFormat division, whatever was answered
    expect(decodeAnswers(schema, main('CIV', '32', 0.03), null, ['CIV']).masterformat).toBeNull();
  });
});

describe('needsReview', () => {
  const base = { discipline: { code: 'MEC', label: 'x', confidence: 0.9, probabilities: { MEC: 0.9, PLB: 0.05 } }, subDiscipline: null, masterformat: null, buildingElement: 0.97 };
  it('is false for a clear answer', () => expect(computeNeedsReview(base, 0.6)).toBe(false));
  it('is true below minConfidence', () => expect(computeNeedsReview({ ...base, discipline: { ...base.discipline, confidence: 0.5 } }, 0.6)).toBe(true));
  it('is true when the top 2 are close, even with a high confidence', () => {
    const r = { ...base, discipline: { ...base.discipline, confidence: 0.7, probabilities: { MEC: 0.7, PLB: 0.62 } } };
    expect(topMargin(r.discipline.probabilities)).toBeCloseTo(0.08);
    expect(computeNeedsReview(r, 0.6)).toBe(true);
    expect(computeNeedsReview(r, 0.6, 0.05)).toBe(false);
  });
  it('looks at the sub-discipline and the division too', () => {
    const sub = { code: 'DUC', label: 'x', confidence: 0.4, probabilities: { DUC: 0.4, EQP: 0.3 } };
    expect(computeNeedsReview({ ...base, subDiscipline: sub }, 0.6)).toBe(true);
    const mf = { division: '23', title: 't', confidence: 0.9, probabilities: { '23': 0.5, '22': 0.45 } };
    expect(computeNeedsReview({ ...base, masterformat: mf }, 0.6)).toBe(true);
  });
  it('is true when the building answer is undecided', () => expect(computeNeedsReview({ ...base, buildingElement: 0.55 }, 0.6)).toBe(true));
  it('marks model results through the pipeline', async () => {
    const p = createMockProvider({
      answer: (_s, q): Answers => 'sub_discipline' in q ? { model: 'm', answers: { sub_discipline: { type: 'choice', choice: 'ARC/WAL', confidence: 0.9, probabilities: { 'ARC/WAL': 0.9 } } } } : ({ model: 'm', answers: { discipline: { type: 'choice', choice: 'ARC', confidence: 0.45, probabilities: { ARC: 0.45, STR: 0.4 } }, building_element: { type: 'noul', noul: 0.9 }, masterformat: { type: 'choice', choice: '09', confidence: 0.9, probabilities: { '09': 0.9 } } } }),
    });
    const { results } = await classifyInputs([input()], { schema, provider: p, minConfidence: 0.6, rules: false });
    expect(results[0]!.needsReview).toBe(true);
  });
});

describe('sub-discipline strategy', () => {
  const answers = (conf: number, runnerUp: string, subChoice?: string): ((s: unknown, q: Questions) => Answers) => (_s, q): Answers =>
    'sub_discipline' in q
      ? { model: 'm', answers: { sub_discipline: { type: 'choice', choice: subChoice ?? 'MEC/DUC', confidence: 0.8, probabilities: { [subChoice ?? 'MEC/DUC']: 0.8 } } } }
      : { model: 'm', answers: { discipline: { type: 'choice', choice: 'MEC', confidence: conf, probabilities: { MEC: conf, [runnerUp]: 1 - conf } }, building_element: { type: 'noul', noul: 0.95 }, masterformat: { type: 'choice', choice: '23', confidence: 0.9, probabilities: { '23': 0.9 } } } };

  it('asks over the chosen discipline when it is sure (2 requests)', async () => {
    const p = createMockProvider({ answer: answers(0.95, 'PLB', undefined) });
    const sure = (_s: unknown, q: Questions): Answers => {
      if ('sub_discipline' in q) {
        const opts = Object.keys((q['sub_discipline'] as { criteria: object }).criteria);
        expect(opts).toEqual(['DUC', 'TRM', 'EQP', 'HYD', 'ACC']);
        return { model: 'm', answers: { sub_discipline: { type: 'choice', choice: 'DUC', confidence: 0.9, probabilities: { DUC: 0.9 } } } };
      }
      return answers(0.95, 'PLB')(_s, q);
    };
    const r = await classifyInputs([input({ id: 'A' })], { schema, provider: createMockProvider({ answer: sure }), rules: false });
    expect(r.stats.calls).toBe(2);
    expect(r.results[0]!.subDiscipline!.code).toBe('DUC');
    expect(p.log).toHaveLength(0);
  });

  it('asks over the top 2 disciplines combined when unsure, and lets the sub-code break the tie', async () => {
    let subOptions: string[] = [];
    const p = createMockProvider({
      answer: (s, q) => {
        if ('sub_discipline' in q) subOptions = Object.keys((q['sub_discipline'] as { criteria: object }).criteria);
        return answers(0.5, 'PLB', 'PLB/SUP')(s, q);
      },
    });
    const r = await classifyInputs([input()], { schema, provider: p, minConfidence: 0.6, rules: false });
    expect(subOptions).toContain('MEC/DUC');
    expect(subOptions).toContain('PLB/SUP');
    expect(subOptions.every((o) => o.startsWith('MEC/') || o.startsWith('PLB/'))).toBe(true);
    expect(r.results[0]!.discipline.code).toBe('PLB');
    expect(r.results[0]!.subDiscipline!.code).toBe('SUP');
    expect(r.results[0]!.needsReview).toBe(true);
    expect(r.stats.calls).toBe(2);
  });

  it('keeps the model id of the answers with the result and in the stats', async () => {
    const p = createMockProvider({ model: 'jev-1.13.0' });
    const r = await classifyInputs(buildInputs(sidecarModel('fzk-haus')).slice(0, 3), { schema, provider: p, rules: false });
    expect(r.results.every((x) => x.model === 'jev-1.13.0')).toBe(true);
    expect(r.stats.models).toEqual({ 'jev-1.13.0': r.stats.calls });
  });
});

describe('backoff and abort', () => {
  const sleeps: number[] = [];
  const sleep = async (ms: number): Promise<void> => void sleeps.push(ms);
  const goodAnswer = (_s: unknown, q: Questions): Answers => createMockProviderAnswer(q);

  function createMockProviderAnswer(q: Questions): Answers {
    const out: Answers['answers'] = {};
    for (const [n, x] of Object.entries(q)) {
      if (x.type === 'choice') {
        const k = Object.keys(x.criteria)[0]!;
        out[n] = { type: 'choice', choice: k, confidence: 0.95, probabilities: { [k]: 0.95 } };
      } else out[n] = { type: 'noul', noul: 0.95 };
    }
    return { model: 'jev-1.13.0', answers: out };
  }

  it('retries 429 and 5xx with Retry-After, then exponential delays, and counts one call per decision', async () => {
    sleeps.length = 0;
    let n = 0;
    const fetchImpl = (async (_u: string, init: RequestInit) => {
      n++;
      const body = JSON.parse(String(init.body)) as { questions: Questions };
      if (n === 1) return jsonResponse({ error: 'slow down' }, 429, { 'retry-after': '2' });
      if (n === 2) return jsonResponse({ error: 'oops' }, 503);
      return jsonResponse(goodAnswer(null, body.questions));
    }) as unknown as typeof fetch;
    const provider = createJevProvider({ endpoint: '/x', model: 'jev-1.13.0', apiKey: () => null, timeoutMs: 5000, fetchImpl });
    const r = await classifyInputs([input()], { schema, provider, rules: false, retry: { sleep, jitter: 0 } });
    expect(sleeps.slice(0, 2)).toEqual([2000, 1000]); // Retry-After 2 s, then base 500 x 2^1
    expect(r.stats.calls).toBe(2); // main + sub; the 2 retries are not counted
    expect(n).toBe(4);
    expect(r.results).toHaveLength(1);
  });

  it('gives up after the retries and falls back to the weak rule with needsReview', async () => {
    sleeps.length = 0;
    const fetchImpl = (async () => jsonResponse({ error: 'down' }, 500)) as unknown as typeof fetch;
    const provider = createJevProvider({ endpoint: '/x', model: 'jev-1.13.0', apiKey: () => null, timeoutMs: 5000, fetchImpl });
    const pipe = input({ ifcClass: 'IfcPipeSegment', name: 'Pipe 1' });
    const r = await classifyInputs([pipe], { schema, provider, retry: { sleep, jitter: 0, retries: 2 } });
    expect(sleeps).toHaveLength(2);
    expect(r.results[0]!.source).toBe('rules');
    expect(r.results[0]!.needsReview).toBe(true);
    expect(r.stats.errors[0]).toMatch(/HTTP 500/);
  });

  it('does not retry a 401 and does not leak the key into the message', async () => {
    sleeps.length = 0;
    const fetchImpl = (async () => jsonResponse({ error: 'bad key sk-secret-999' }, 401)) as unknown as typeof fetch;
    const provider = createJevProvider({ endpoint: '/x', model: 'jev-1.13.0', apiKey: () => 'sk-secret-999', timeoutMs: 5000, fetchImpl });
    const r = await classifyInputs([input()], { schema, provider, rules: false, retry: { sleep, jitter: 0 } });
    expect(sleeps).toHaveLength(0);
    expect(r.stats.failed).toBe(1);
    expect(JSON.stringify(r.stats.errors)).not.toContain('sk-secret-999');
    expect(r.stats.errors[0]).toMatch(/rejected the credentials/);
  });

  it('redacts the key from a network error', async () => {
    const fetchImpl = (async () => { throw new TypeError('Failed to fetch https://x?k=sk-secret-999'); }) as unknown as typeof fetch;
    const provider = createJevProvider({ endpoint: '/x', model: 'm', apiKey: () => 'sk-secret-999', timeoutMs: 5000, fetchImpl });
    await expect(provider.decide({}, SAMPLE_QUESTIONS, new AbortController().signal)).rejects.toThrow(/CORS/);
    await provider.decide({}, SAMPLE_QUESTIONS, new AbortController().signal).catch((e: Error) => expect(e.message).not.toContain('sk-secret-999'));
  });

  it('stops at once on abort, in a request and in a backoff wait', async () => {
    const ctl = new AbortController();
    const hang: DecisionModel = {
      provider: 'test',
      decide: (_s, _q, signal) => new Promise((_res, rej) => signal.addEventListener('abort', () => rej(new DOMException('Aborted', 'AbortError')))),
    };
    const inputs = buildInputs(sidecarModel('fzk-haus'));
    const run = classifyInputs(inputs, { schema, provider: hang, rules: false, signal: ctl.signal, concurrency: 3 });
    setTimeout(() => ctl.abort(), 20);
    const r = await run;
    expect(r.stats.aborted).toBe(true);
    expect(r.results.length).toBeLessThan(inputs.length);
    expect(r.stats.calls).toBeLessThanOrEqual(3);

    // abort while waiting to retry
    const ctl2 = new AbortController();
    const always429: DecisionModel = { provider: 'test', decide: async () => { throw new ProviderError('busy', 429, 60_000, true); } };
    const run2 = classifyInputs([input()], { schema, provider: always429, rules: false, signal: ctl2.signal });
    setTimeout(() => ctl2.abort(), 20);
    const r2 = await run2;
    expect(r2.stats.aborted).toBe(true);
    expect(r2.stats.failed).toBe(0);
  });

  it('builds inputs from the viewer model: psets, quantities, storey and systems', () => {
    const m = sidecarModel('synth5k');
    const pipe = m.elements.find((e) => e.ifcClass === 'IfcPipeSegment')!;
    const i = buildInput(m, pipe.id)!;
    expect(i.id).toBe(pipe.globalId);
    expect(i.systems).toEqual(['Domestic Water']);
    expect(i.hierarchy!.path[0]!.ifcClass).toBe('IfcBuildingStorey');
    expect(Object.keys(i.quantities ?? {}).every((k) => /^Qto_/.test(k))).toBe(true);
    expect(buildInput(m, pipe.globalId)!.id).toBe(pipe.globalId);
  });
});
