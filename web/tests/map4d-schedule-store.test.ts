// The schedule workflow's store (src/map4d/scheduleStore.ts): config, links and the XER bytes per model; the same work comes back; copies, not
// references; no IndexedDB means no persistence but no error. And the help keys the schedule panel uses.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { HELP } from '../src/ui/helpText';
import { MAX_STORED_XER, MemoryScheduleBackend, ScheduleStore } from '../src/map4d/scheduleStore';
import type { ScheduleRecord } from '../src/map4d/scheduleStore';
import { emptyConfig, setTradeQuery } from '../src/map4d/scheduleConfig';
import type { FourDLinks } from '../src/schedule/types';

const links: FourDLinks = { id: 'l1', model: { identity_key: 'k' }, schedule: { source_hash: 'h'.repeat(64), project: 'P' }, links: [{ id: 'ln-A1-build', activity: 'A1', role: 'build', elements: ['g'], status: 'accepted', source: 'suggested' }] };
const rec = (key: string): ScheduleRecord => ({
  schema: 'xray-4d-schedule/1', key, saved: '2027-01-01T00:00:00Z',
  config: setTradeQuery(emptyConfig(), 'CONC', "class = 'IfcSlab'"), links,
  file: { name: 'a.xer', hash: 'h'.repeat(64), project: 'P', bytes: new TextEncoder().encode('ERMHDR\t8.4').buffer as ArrayBuffer },
});

describe('schedule store', () => {
  it('keeps the config, the links and the file per model key, and returns copies', async () => {
    const s = new ScheduleStore(async () => new MemoryScheduleBackend());
    expect(await s.get('k')).toBeNull();
    expect(await s.put(rec('k'))).toBe(false);
    const a = await s.get('k');
    expect(a!.config!.tradeQueries).toEqual({ CONC: "class = 'IfcSlab'" });
    expect(a!.links!.links![0]!.status).toBe('accepted');
    expect(new TextDecoder().decode(a!.file!.bytes!)).toBe('ERMHDR\t8.4');
    a!.links!.links!.length = 0;
    expect((await s.get('k'))!.links!.links).toHaveLength(1);
    expect(await s.get('other')).toBeNull();
    await s.put({ ...rec('k'), config: null });
    expect((await s.get('k'))!.config).toBeNull();
    await s.delete('k');
    expect(await s.get('k')).toBeNull();
  });

  it('works without IndexedDB: it keeps the work in memory and says it is not persistent', async () => {
    const s = new ScheduleStore(async () => null);
    await s.init();
    expect(s.persistent).toBe(false);
    expect(await s.put(rec('k'))).toBe(false);
    expect((await s.get('k'))!.file!.name).toBe('a.xer');
  });

  it('survives a backend that fails', async () => {
    const bad = { persistent: true, get: async () => { throw new Error('x'); }, put: async () => { throw new Error('x'); }, delete: async () => { throw new Error('x'); } };
    const s = new ScheduleStore(async () => bad);
    expect(await s.get('k')).toBeNull();
    expect(await s.put(rec('k'))).toBe(false);
    await s.delete('k');
    expect(MAX_STORED_XER).toBeGreaterThan(1024 * 1024);
  });
});

describe('4D schedule help', () => {
  const dir = dirname(fileURLToPath(import.meta.url));
  it('has a help entry for every key the schedule panel uses', () => {
    const src = readFileSync(resolve(dir, '../src/map4d/schedulePanel.ts'), 'utf8');
    const keys = new Set<string>();
    for (const m of src.matchAll(/help\([^\n]*,\s*'([A-Za-z0-9 ]+)'\)/g)) keys.add(`4D tab/${m[1]}`);
    for (const m of src.matchAll(/\bbtn\([^\n]*?,\s*'([A-Za-z0-9 ]+)',\s*\(\)/g)) keys.add(`4D tab/${m[1]}`);
    for (const m of src.matchAll(/(?:select|num|check)\('([a-z ]+)'/g)) keys.add(`4D tab/Style ${m[1]}`);
    for (const m of src.matchAll(/section\('[A-Za-z ]+', '[a-z]+', (?:true|false), '([A-Za-z]+)'\)/g)) keys.add(`4D tab/Section ${m[1]}`);
    expect(keys.size).toBeGreaterThan(40);
    for (const k of keys) expect(HELP[k], k).toBeDefined();
  });
});
