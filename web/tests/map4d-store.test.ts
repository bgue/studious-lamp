import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { HELP } from '../src/ui/helpText';
import { MapStore, MemoryMapBackend } from '../src/map4d/store';
import type { MapRecord } from '../src/map4d/store';
import { defaultLists } from '../src/map4d/values';

const rec = (key: string): MapRecord => ({ schema: 'xray-4d-map/1', key, model: null, saved: '2027-01-01T00:00:00Z', assignments: [{ id: 'a', element: 'g'.repeat(22), attribute: 'zone', value: 'A', status: 'accepted' }], values: defaultLists(), classTrade: { IfcSlab: 'CONC' } });

describe('map store', () => {
  it('keeps one record per model key and returns copies', async () => {
    const s = new MapStore(async () => new MemoryMapBackend());
    expect(await s.get('k')).toBeNull();
    await s.put(rec('k'));
    const a = await s.get('k');
    a!.assignments.length = 0;
    expect((await s.get('k'))!.assignments).toHaveLength(1);
    expect(await s.get('other')).toBeNull();
    await s.delete('k');
    expect(await s.get('k')).toBeNull();
  });
  it('works without IndexedDB (keeps in memory, reports not persistent)', async () => {
    const s = new MapStore(async () => null);
    await s.init();
    expect(s.persistent).toBe(false);
    expect(await s.put(rec('k'))).toBe(false);
  });
});

describe('4D help', () => {
  const dir = dirname(fileURLToPath(import.meta.url));
  it('has a help entry for every key the 4D panel and the Save IFC box use', () => {
    const src = readFileSync(resolve(dir, '../src/map4d/panel.ts'), 'utf8') + readFileSync(resolve(dir, '../src/plugins/ifcSave.ts'), 'utf8') + readFileSync(resolve(dir, '../src/plugins/map4d.ts'), 'utf8');
    const keys = new Set<string>();
    for (const m of src.matchAll(/'(4D tab\/[A-Za-z0-9 ]+)'/g)) keys.add(m[1]!);
    for (const m of src.matchAll(/help\(.*,\s*'([A-Za-z0-9 ]+)'\)/g)) keys.add(`4D tab/${m[1]}`);
    for (const m of src.matchAll(/\bbtn\([^\n]*?,\s*'([A-Za-z0-9 ]+)',\s*\(\)/g)) keys.add(`4D tab/${m[1]}`);
    for (const m of src.matchAll(/section\([^\n]*?'(?:Values|Assign|Suggest|Coverage)'/g)) keys.add(`4D tab/Section ${/'([A-Z][a-z]+)'$/.exec(m[0])![1]}`);
    keys.add('4D tab/Section Import and Export');
    keys.add('Right sidebar/4D tab');
    expect(keys.size).toBeGreaterThan(30);
    for (const k of keys) expect(HELP[k], k).toBeDefined();
  });
});
