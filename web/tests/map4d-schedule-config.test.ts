// The 4D configuration builder of the schedule workflow (src/map4d/scheduleConfig.ts): sources from the schedule, the value table, the trade
// queries, reading and writing `.4d.json`, and the guess for a schedule. Uses the FZK-Haus sample schedule.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseXer } from '../src/schedule/xer';
import {
  emptyConfig, guessConfig, parseConfig, serializeConfig, setExisting, setSource, setSplit, setStyle, setTradeQuery, setValueMap, sourceChoices, sourceKey, sourcesOf, tradeKeys, valueRows, wbsDepth,
} from '../src/map4d/scheduleConfig';
import { DEFAULT_STYLE } from '../src/schedule/types';

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const schedule = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const sampleText = readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8');

describe('sources the schedule offers', () => {
  it('lists the code types, the user fields and the WBS levels', () => {
    const keys = sourceChoices(schedule).map((c) => c.key);
    for (const k of ['code:Level', 'code:Phase', 'code:Trade']) expect(keys).toContain(k);
    expect(keys.filter((k) => k.startsWith('wbs:'))).toHaveLength(wbsDepth(schedule));
    expect(wbsDepth(schedule)).toBeGreaterThan(0);
  });

  it('sets one source per attribute without touching the config it was given', () => {
    const base = emptyConfig();
    const choice = sourceChoices(schedule).find((c) => c.key === 'code:Level')!;
    const next = setSource(base, 'location', choice);
    expect(sourcesOf(next, 'location')).toEqual([{ code: 'Level' }]);
    expect(sourcesOf(base, 'location')).toEqual([]);
    expect(sourcesOf(setSource(next, 'location', null), 'location')).toEqual([]);
    const zone = setSource(base, 'zone', sourceChoices(schedule).find((c) => c.key === 'wbs:0')!);
    expect(zone.schedule.zone).toEqual([{ wbsLevel: 0 }]);
    expect('zone' in setSource(zone, 'zone', null).schedule).toBe(false);
  });

  it('keeps a source from a file that the schedule does not offer (a pattern), so the drop-down can show it', () => {
    const cur = [{ wbsPattern: 'STR/(L\\d+)', group: 1 }];
    const choices = sourceChoices(schedule, cur);
    expect(choices.some((c) => c.key === sourceKey(cur[0]))).toBe(true);
  });

  it('guesses Level as location and Trade as trade, and keeps a source that is already set', () => {
    const g = guessConfig(schedule);
    expect(sourcesOf(g, 'location')).toEqual([{ code: 'Level' }]);
    expect(sourcesOf(g, 'trade')).toEqual([{ code: 'Trade' }]);
    expect(g.schedule.project).toBe('FZK-HAUS');
    const own = setSource(emptyConfig(), 'location', { key: 'code:Phase', label: '', source: { code: 'Phase' } });
    expect(sourcesOf(guessConfig(schedule, own), 'location')).toEqual([{ code: 'Phase' }]);
  });
});

describe('the value table', () => {
  const cfg = guessConfig(schedule);

  it('lists the distinct schedule values of building activities with their counts', () => {
    const rows = valueRows(schedule, cfg, 'location');
    expect(rows.map((r) => [r.schedule, r.count])).toEqual([['ALL', 10], ['DG', 11], ['EG', 14], ['SITE', 5]]);
    expect(rows.every((r) => r.count > 0 && r.model === '')).toBe(true);
    expect(valueRows(null, cfg, 'location')).toEqual([]);
    expect(valueRows(schedule, emptyConfig(), 'location')).toEqual([]);
  });

  it('maps a schedule value to a model value, and an empty text removes the row', () => {
    let c = setValueMap(cfg, 'location', 'EG', 'Erdgeschoss');
    c = setValueMap(c, 'location', 'DG', ' Dachgeschoss ');
    expect(c.values!.location).toEqual({ EG: 'Erdgeschoss', DG: 'Dachgeschoss' });
    expect(valueRows(schedule, c, 'location').map((r) => r.model)).toEqual(['', 'Dachgeschoss', 'Erdgeschoss', '']);
    c = setValueMap(setValueMap(c, 'location', 'EG', ''), 'location', 'DG', '');
    expect(c.values).toBeUndefined();
    expect(cfg.values).toBeUndefined();
  });

  it('keeps a table key that no activity uses, so it can be removed', () => {
    const c = setValueMap(cfg, 'location', '/^X(\\d)$/', 'Level $1');
    expect(valueRows(schedule, c, 'location').find((r) => r.schedule === '/^X(\\d)$/')).toMatchObject({ count: 0, model: 'Level $1' });
  });
});

describe('trade queries, existing parts, split and style', () => {
  it('lists the trade values and sets and clears a query', () => {
    const cfg = guessConfig(schedule);
    const keys = tradeKeys(schedule, cfg);
    expect(keys).toContain('CONC-SLAB');
    let c = setTradeQuery(cfg, 'CONC-SLAB', " class = 'IfcSlab' ");
    expect(c.tradeQueries).toEqual({ 'CONC-SLAB': "class = 'IfcSlab'" });
    expect(tradeKeys(schedule, setTradeQuery(cfg, 'EXTRA', 'class = 1'))).toContain('EXTRA');
    c = setTradeQuery(c, 'CONC-SLAB', '');
    expect(c.tradeQueries).toBeUndefined();
    expect(setExisting(cfg, "storey = 'Site'").model.existing).toBe("storey = 'Site'");
    expect(setExisting(setExisting(cfg, 'a'), ' ').model.existing).toBeUndefined();
    expect(setSplit(cfg, '*', 'sweep_x').split).toEqual({ '*': 'sweep_x' });
    expect(setSplit(setSplit(cfg, '*', 'sweep_x'), '*', '').split).toBeUndefined();
  });

  it('changes the style by a patch and leaves the defaults alone', () => {
    const c = setStyle(emptyConfig(), { view: 'actual', unbuilt: 'ghost', window: { kind: 'lookahead', from: 'dataDate', weeks: 6 } });
    expect(c.style).toMatchObject({ view: 'actual', unbuilt: 'ghost', camera: 'director', length: 120 });
    expect(c.style.window).toEqual({ kind: 'lookahead', from: 'dataDate', weeks: 6 });
    expect(DEFAULT_STYLE.view).toBe('planned');
    expect(emptyConfig().style).toEqual(DEFAULT_STYLE);
  });
});

describe('the .4d.json file', () => {
  it('reads the FZK-Haus sample without a problem and writes it back the same', () => {
    const r = parseConfig(sampleText);
    expect(r.problems).toEqual([]);
    expect(r.config!.schedule.location).toEqual([{ code: 'Level' }]);
    expect(r.config!.values!.location).toEqual({ EG: 'Erdgeschoss', DG: 'Dachgeschoss' });
    expect(r.config!.style.length).toBe(90);
    expect(r.config!.tradeQueries!['WINDOWS']).toBe("class = 'IfcWindow'");
    const again = parseConfig(serializeConfig(r.config!));
    expect(again.config).toEqual(r.config);
  });

  it('refuses what is no configuration and lists the bad fields of one that is', () => {
    expect(parseConfig('{nope').config).toBeNull();
    expect(parseConfig('[]').config).toBeNull();
    expect(parseConfig({ schema: 'other/1' }).problems[0]).toMatch(/schema/);
    const r = parseConfig({ schema: 'xray-4d-config/1', schedule: { location: [{ code: 'Level' }, { nope: 1 }], trade: 'x' }, style: { view: 'sideways' }, split: { a: 'diagonal' }, tradeQueries: { a: 5 } });
    expect(r.config).not.toBeNull();
    expect(r.config!.schedule.location).toEqual([{ code: 'Level' }]);
    expect(r.config!.schedule.trade).toEqual([]);
    expect(r.config!.style.view).toBe('planned');
    expect(r.problems.length).toBeGreaterThanOrEqual(4);
  });
});
