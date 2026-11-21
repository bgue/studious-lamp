import { describe, expect, it } from 'vitest';
import { FlyStore } from '../src/anim/store';
import { newKeyframe } from '../src/anim/flythrough';
import { MemoryStorage } from '../src/selectionSets';
import type { SavedView } from '../src/views/model';

const v = (name: string): SavedView => ({
  id: name,
  name,
  created: 'c',
  updated: 'u',
  camera: { position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0], fov: 50, ortho: false },
  selection: [],
  params: {},
});

describe('FlyStore', () => {
  it('stores under the identity key and not the model name, and loads it back', () => {
    const mem = new MemoryStorage();
    const s = new FlyStore(mem);
    s.load('building|120|abc', 'building');
    const f = s.create('Tour');
    s.add(f, v('one'));
    s.add(f, v('two'));
    expect([...mem.map.keys()]).toEqual(['xray.flythroughs.building|120|abc']);
    const t = new FlyStore(mem);
    t.load('building|120|abc', 'building');
    expect(t.list).toHaveLength(1);
    expect(t.active!.keyframes.map((k) => k.name)).toEqual(['one', 'two']);
    const other = new FlyStore(mem);
    other.load('building|121|zzz', 'building');
    expect(other.list).toHaveLength(0);
  });

  it('migrates the old keyframes once, keeps the old key, and does not migrate again', () => {
    const mem = new MemoryStorage();
    mem.setItem('xray.flythrough.building', JSON.stringify({ keyframes: [{ position: [0, 0, 5], target: [0, 0, 0], selection: [], toggles: {} }] }));
    const s = new FlyStore(mem);
    expect(s.load('building|10|h', 'building').migrated).toBe(true);
    expect(s.list.map((f) => f.name)).toEqual(['Imported']);
    expect(mem.getItem('xray.flythrough.building')).not.toBeNull();
    s.remove(s.list[0]!.id);
    const t = new FlyStore(mem);
    expect(t.load('building|10|h', 'building').migrated).toBe(false);
    expect(t.list).toHaveLength(0);
  });

  it('keeps several named fly-throughs with unique names and one active', () => {
    const s = new FlyStore(new MemoryStorage());
    s.load('k', 'm');
    const a = s.create('Tour');
    const b = s.create('Tour');
    expect(b.name).toBe('Tour 2');
    expect(s.active!.id).toBe(b.id);
    s.setActive(a.id);
    expect(s.active!.id).toBe(a.id);
    s.rename(a.id, 'Tour 2');
    expect(a.name).toBe('Tour 3');
    const c = s.duplicate(a.id)!;
    expect(c.id).not.toBe(a.id);
    s.remove(c.id);
    expect(s.list).toHaveLength(2);
  });

  it('adds, updates, moves and removes keyframes', () => {
    const s = new FlyStore(new MemoryStorage());
    s.load('k', 'm');
    const f = s.create('T');
    for (const n of ['a', 'b', 'c']) s.add(f, v(n));
    s.add(f, v('x'), 1);
    expect(f.keyframes.map((k) => k.name)).toEqual(['a', 'x', 'b', 'c']);
    expect(s.move(f, 0, 3)).toBe(true);
    expect(f.keyframes.map((k) => k.name)).toEqual(['x', 'b', 'c', 'a']);
    expect(s.move(f, 0, 0)).toBe(false);
    s.update(f, 0, { hold: -3, travel: 4, fadeFraction: 5, caption: { title: ' ', text: '' } });
    expect(f.keyframes[0]).toMatchObject({ hold: 0, travel: 4, fadeFraction: 1 });
    expect(f.keyframes[0]!.caption).toBeUndefined();
    s.update(f, 0, { travel: null, caption: { title: 'Hi' } });
    expect(f.keyframes[0]!.travel).toBeUndefined();
    expect(f.keyframes[0]!.caption).toEqual({ title: 'Hi' });
    s.removeKeyframe(f, 1);
    expect(f.keyframes).toHaveLength(3);
    s.clear(f);
    expect(f.keyframes).toHaveLength(0);
  });

  it('exports the active fly-through with captions and imports it as a new one', () => {
    const s = new FlyStore(new MemoryStorage());
    s.load('k', 'm');
    const f = s.create('T');
    s.add(f, newKeyframe(v('a')).view, undefined, { caption: { title: 'Secret title' } });
    const text = s.exportDoc(false);
    expect(text).toContain('Secret title');
    const t = new FlyStore(new MemoryStorage());
    t.load('k2', 'm');
    expect(t.importDoc(text)).toBe(1);
    expect(t.active!.keyframes[0]!.caption!.title).toBe('Secret title');
    expect(t.importDoc('nonsense')).toBe(0);
  });
});
