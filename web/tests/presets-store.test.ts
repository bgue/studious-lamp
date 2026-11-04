// The preset list: JSON override merge, user preset persistence, export / import round trip, share encoding.
import { describe, expect, it } from 'vitest';
import { BUILTIN_PRESETS } from '../src/presets/builtin';
import {
  PRESETS_SCHEMA,
  decodePresetShare,
  encodePresetShare,
  findPreset,
  hashWithoutPreset,
  keyOf,
  mergeOverrides,
  normalizePreset,
  parsePresetsDocument,
  presetFromHash,
  presetShareUrl,
  serializePresets,
  slugify,
  uniqueId,
  uniqueName,
} from '../src/presets/model';
import type { Preset } from '../src/presets/model';
import { PRESETS_STORAGE_KEY, PresetStore } from '../src/presets/store';
import { MemoryStorage } from '../src/selectionSets';

const user = (name: string, params: Record<string, unknown> = { schema: 'xray-params/1', xray: false }): Preset => ({
  id: slugify(name), name, description: `${name}.`, group: 'My presets', base: 'current', params, builtIn: false,
});

describe('override merge', () => {
  const ov = (id: string, name: string): Preset => ({ id, name, description: 'Changed.', group: 'Review', base: 'defaults', params: { schema: 'xray-params/1', xray: true }, builtIn: false });

  it('replaces a built-in with the same id in place and appends new ids', () => {
    const out = mergeOverrides(BUILTIN_PRESETS, [ov('peelback', 'Peelback (office)'), ov('team-review', 'Team review')]);
    expect(out.length).toBe(BUILTIN_PRESETS.length + 1);
    expect(out.findIndex((p) => p.id === 'peelback')).toBe(BUILTIN_PRESETS.findIndex((p) => p.id === 'peelback'));
    expect(out.find((p) => p.id === 'peelback')).toMatchObject({ name: 'Peelback (office)', description: 'Changed.', builtIn: true });
    expect(out[out.length - 1]).toMatchObject({ id: 'team-review', builtIn: true });
    expect(out.map((p) => p.id).slice(0, 9)).toEqual(BUILTIN_PRESETS.slice(0, 9).map((p) => p.id));
    // the inputs are not mutated
    expect(BUILTIN_PRESETS.find((p) => p.id === 'peelback')!.name).toBe('Peelback');
  });

  it('is what the store lists', () => {
    const s = new PresetStore(null, [ov('plain', 'Plain screen')]);
    expect(s.get('plain')!.name).toBe('Plain screen');
    expect(s.list().length).toBe(BUILTIN_PRESETS.length);
  });
});

describe('user presets', () => {
  it('persist in localStorage xray.presets and come back in a new store', () => {
    const st = new MemoryStorage();
    const a = new PresetStore(st);
    const saved = a.add(user('Night review'));
    expect(st.getItem(PRESETS_STORAGE_KEY)).toContain('Night review');
    expect(JSON.parse(st.getItem(PRESETS_STORAGE_KEY)!).schema).toBe(PRESETS_SCHEMA);
    const b = new PresetStore(st);
    expect(b.userPresets().map((p) => p.name)).toEqual(['Night review']);
    expect(b.get(saved.id)).toMatchObject({ builtIn: false, group: 'My presets', params: { xray: false } });
    // built-ins are not stored
    expect(st.getItem(PRESETS_STORAGE_KEY)).not.toContain('Coordination');
  });

  it('rename, duplicate and delete', () => {
    const st = new MemoryStorage();
    const s = new PresetStore(st);
    const p = s.add(user('One'));
    expect(s.update(p.id, { name: 'Two', description: 'Edited.' })).toBe(true);
    expect(s.get(p.id)).toMatchObject({ name: 'Two', description: 'Edited.' });
    const d = s.duplicate(p.id)!;
    expect(d.id).not.toBe(p.id);
    expect(d.name).toBe('Two copy');
    const dc = s.duplicate('coordination')!;
    expect(dc).toMatchObject({ builtIn: false, name: 'Coordination copy' });
    expect(s.update('coordination', { name: 'x' })).toBe(false);
    expect(s.remove('coordination')).toBe(false);
    expect(s.remove(p.id)).toBe(true);
    expect(new PresetStore(st).userPresets().map((x) => x.name)).toEqual(['Two copy', 'Coordination copy']);
  });

  it('keep names and ids unique, also against built-ins', () => {
    const s = new PresetStore(null);
    const a = s.add(user('Plain'));
    expect(a.name).toBe('Plain (2)');
    expect(a.id).not.toBe('plain');
    expect(s.add(user('Plain')).name).toBe('Plain (3)');
    expect(uniqueName('a', new Set(['A']))).toBe('a (2)');
    expect(uniqueId('x', new Set(['x', 'x-2']))).toBe('x-3');
  });

  it('survive a broken or throwing storage', () => {
    const bad = { getItem: () => { throw new Error('no'); }, setItem: () => { throw new Error('no'); } };
    const s = new PresetStore(bad);
    expect(() => s.add(user('X'))).not.toThrow();
    const junk = new MemoryStorage();
    junk.setItem(PRESETS_STORAGE_KEY, '{not json');
    expect(new PresetStore(junk).userPresets()).toEqual([]);
  });

  it('notify listeners on change', () => {
    const s = new PresetStore(null);
    let n = 0;
    const off = s.onChange(() => void n++);
    const p = s.add(user('N'));
    s.remove(p.id);
    off();
    s.add(user('M'));
    expect(n).toBe(2);
  });
});

describe('export and import', () => {
  it('round trip: export then import into an empty store gives the same presets', () => {
    const a = new PresetStore(null);
    a.add({ ...user('First'), actions: ['section.fitSelection'], base: 'defaults', params: { schema: 'xray-params/1', sightlines: { alphaMin: 0.2 } } });
    a.add(user('Second'));
    const text = a.exportJson(false, new Date('2026-01-01T00:00:00Z'));
    expect(JSON.parse(text)).toMatchObject({ schema: 'xray-presets/1', exportedAt: '2026-01-01T00:00:00.000Z' });
    const b = new PresetStore(null);
    const r = b.importJson(text);
    expect(r.errors).toEqual([]);
    expect(b.userPresets()).toEqual(a.userPresets());
  });

  it('import adds as user presets with fresh ids when they clash, and reports bad entries', () => {
    const s = new PresetStore(null);
    const doc = { schema: PRESETS_SCHEMA, presets: [{ id: 'coordination', name: 'Coordination', params: { xray: false } }, { name: 'No params' }, 5] };
    const r = s.importJson(JSON.stringify(doc));
    expect(r.added.length).toBe(1);
    expect(r.added[0]).toMatchObject({ builtIn: false, name: 'Coordination (2)' });
    expect(r.added[0]!.id).not.toBe('coordination');
    expect(r.errors.length).toBe(2);
    expect(s.get('coordination')!.builtIn).toBe(true);
  });

  it('rejects non-JSON and wrong documents without throwing', () => {
    expect(parsePresetsDocument('nope').errors[0]).toMatch(/not valid JSON/);
    expect(parsePresetsDocument({ schema: 'other/1', presets: [] }).errors).toContain('schema is not xray-presets/1');
    expect(parsePresetsDocument({}).presets).toEqual([]);
    expect(parsePresetsDocument([user('Bare')]).presets.length).toBe(1);
  });

  it('serialize and parse the built-ins unchanged', () => {
    expect(parsePresetsDocument(serializePresets(BUILTIN_PRESETS), true).presets).toEqual(BUILTIN_PRESETS);
  });

  it('drops action ids that are not plain ids', () => {
    const p = normalizePreset({ name: 'A', params: {}, actions: ['ok.id', 'bad id', '../x', 5] }, false)!;
    expect(p.actions).toEqual(['ok.id']);
  });
});

describe('share link', () => {
  const p: Preset = { ...user('Shared look', { schema: 'xray-params/1', sightlines: { alphaMin: 0.33 }, viewModes: { peel: { enabled: true } } }), actions: ['section.fitSelection'], base: 'defaults', description: 'Naïve text with ünïcode.' };

  it('encodes and decodes a preset', () => {
    const enc = encodePresetShare(p);
    expect(enc).toMatch(/^[A-Za-z0-9_-]+$/);
    const back = decodePresetShare(enc)!;
    expect(back).toMatchObject({ name: 'Shared look', description: p.description, base: 'defaults', actions: ['section.fitSelection'], builtIn: false });
    expect(back.params).toEqual(p.params);
  });

  it('reads #preset= from a hash, alone or next to p=, and removes it', () => {
    const enc = encodePresetShare(p);
    expect(presetFromHash(`#preset=${enc}`)!.name).toBe('Shared look');
    expect(presetFromHash(`#p=abc&preset=${enc}`)!.name).toBe('Shared look');
    expect(presetFromHash('#p=abc')).toBeNull();
    expect(hashWithoutPreset(`#preset=${enc}`)).toBe('');
    expect(hashWithoutPreset(`#p=abc&preset=${enc}`)).toBe('#p=abc');
  });

  it('returns null for garbage', () => {
    expect(decodePresetShare('%%%')).toBeNull();
    expect(decodePresetShare(btoa('{"a":1}'))).toBeNull();
    expect(decodePresetShare(btoa(JSON.stringify({ schema: PRESETS_SCHEMA, preset: { name: 'x' } })))).toBeNull();
    expect(presetFromHash('#preset=!!!')).toBeNull();
  });

  it('builds a url with the model query kept', () => {
    expect(presetShareUrl(p, { origin: 'http://h', pathname: '/', search: '?model=building' })).toMatch(/^http:\/\/h\/\?model=building#preset=/);
  });
});

describe('lookup and keys', () => {
  it('finds by id, by name ignoring case, and by key number', () => {
    const list = BUILTIN_PRESETS;
    expect(findPreset(list, 'peelback')!.id).toBe('peelback');
    expect(findPreset(list, 'HIDE BLOCKERS')!.id).toBe('hide-blockers');
    expect(findPreset(list, '3')!.id).toBe('behind-only');
    expect(findPreset(list, 'nope')).toBeUndefined();
  });

  it('keys 1 to 9 follow the list order', () => {
    expect(BUILTIN_PRESETS.map((_, i) => keyOf(i))).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', null, null, null]);
    const s = new PresetStore(null);
    s.add(user('Mine'));
    expect(s.list()[12]!.name).toBe('Mine');
    expect(s.list().slice(0, 9).map((p) => p.id)).toEqual(BUILTIN_PRESETS.slice(0, 9).map((p) => p.id));
  });
});
