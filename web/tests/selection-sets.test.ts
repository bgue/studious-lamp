import { describe, expect, it } from 'vitest';
import {
  DEFAULT_SETS,
  MemoryStorage,
  addSet,
  defaultSetsFor,
  exportSets,
  globalIdsToIds,
  idsToGlobalIds,
  loadOrSeed,
  loadSets,
  mergeImported,
  parseImport,
  removeSet,
  renameSet,
  saveSets,
  storageKey,
  unionBounds,
  updateSet,
  uniqueName,
} from '../src/selectionSets';
import { modelOf } from './sidebar-model';

const storeys = [
  { id: 0, name: 'Level 0', elevation: 0 },
  { id: 1, name: 'Level 1', elevation: 3.5 },
];
const synth = modelOf(
  [
    { cls: 'IfcDuctSegment', name: 'Duct 0', storey: 0 }, // 0
    { cls: 'IfcDuctSegment', name: 'Duct 1', storey: 1 }, // 1
    { cls: 'IfcPipeSegment', name: 'Pipe riser L0', storey: 0 }, // 2
    { cls: 'IfcSlab', name: 'Slab', storey: 0 }, // 3
    { cls: 'IfcPipeSegment', name: 'Pipe', storey: 1 }, // 4
  ],
  storeys,
);

describe('globalId mapping', () => {
  it('round trips ids through globalIds, dedups and skips unknowns', () => {
    expect(idsToGlobalIds(synth, [3, 1, 3, 99])).toEqual(['G3', 'G1']);
    expect(globalIdsToIds(synth, ['G3', 'nope', 'G1'])).toEqual([3, 1]);
  });

  it('survives a reconversion that renumbers elements', () => {
    const gids = idsToGlobalIds(synth, [0, 4]);
    // Same elements, reversed id order and different ids.
    const rev = modelOf([...synth.elements].reverse().map((e) => ({ cls: e.ifcClass, name: e.name, storey: e.storey })), storeys);
    const revIds = rev.elements.map((e, i) => ({ gid: synth.elements[synth.elements.length - 1 - i]!.globalId, id: i }));
    rev.elements.forEach((e, i) => {
      e.globalId = revIds[i]!.gid;
    });
    rev.byGlobalId.clear();
    rev.elements.forEach((e) => rev.byGlobalId.set(e.globalId, e.id));
    expect(globalIdsToIds(rev, gids).sort()).toEqual([0, 4]); // ids 0 and 4 map to 4 and 0 in the reversed model
    expect(rev.elements[globalIdsToIds(rev, ['G0'])[0]!]!.name).toBe('Duct 0');
  });

  it('computes the union of bounds', () => {
    expect(unionBounds(synth, [])).toBeNull();
    expect(unionBounds(synth, [1, 3])).toEqual([1, 0, 0, 4, 1, 1]);
  });
});

describe('persistence', () => {
  it('uses the key xray.sets.<model> and round trips through a storage shim', () => {
    const st = new MemoryStorage();
    const sets = addSet([], 'Mine', ['G1', 'G2']);
    expect(saveSets(st, 'synth5k', sets)).toBe(true);
    expect(st.getItem('xray.sets.synth5k')).not.toBeNull();
    expect(storageKey('x')).toBe('xray.sets.x');
    expect(loadSets(st, 'synth5k')).toEqual(sets);
    expect(loadSets(st, 'other')).toBeNull();
  });

  it('ignores corrupt payloads and drops malformed entries', () => {
    const st = new MemoryStorage();
    st.setItem(storageKey('m'), '{not json');
    expect(loadSets(st, 'm')).toBeNull();
    st.setItem(storageKey('m'), JSON.stringify({ sets: [{ name: 'ok', globalIds: ['a'] }, { name: 3 }, null] }));
    expect(loadSets(st, 'm')).toEqual([{ name: 'ok', globalIds: ['a'] }]);
  });

  it('reports failure when storage throws', () => {
    const bad = { getItem: () => null, setItem: () => { throw new Error('quota'); } };
    expect(saveSets(bad, 'm', [])).toBe(false);
    expect(loadSets({ getItem: () => { throw new Error('x'); }, setItem: () => {} }, 'm')).toBeNull();
  });

  it('list operations: unique names, rename, update, remove', () => {
    let s = addSet([], 'A', ['G0']);
    s = addSet(s, 'A', ['G1']);
    expect(s.map((x) => x.name)).toEqual(['A', 'A 2']);
    expect(uniqueName(s, '  ')).toBe('Set');
    s = renameSet(s, 1, 'A'); // collides with index 0
    expect(s[1]!.name).toBe('A 2');
    s = renameSet(s, 1, 'B');
    s = updateSet(s, 0, ['G9']);
    expect(s[0]!.globalIds).toEqual(['G9']);
    s = removeSet(s, 0);
    expect(s.map((x) => x.name)).toEqual(['B']);
  });

  it('exports and imports JSON, merging by name', () => {
    const a = addSet(addSet([], 'One', ['G0']), 'Two', ['G1']);
    const text = exportSets('building', a);
    expect(JSON.parse(text).model).toBe('building');
    const back = parseImport(text)!;
    expect(back).toEqual(a);
    expect(parseImport('nope')).toBeNull();
    expect(parseImport(JSON.stringify([{ name: 'Bare', globalIds: [] }]))).toEqual([{ name: 'Bare', globalIds: [] }]);
    const merged = mergeImported(a, [{ name: 'Two', globalIds: ['G7'] }, { name: 'Three', globalIds: [] }]);
    expect(merged.map((s) => s.name)).toEqual(['One', 'Two', 'Three']);
    expect(merged[1]!.globalIds).toEqual(['G7']);
  });
});

describe('default sets', () => {
  it('has a table entry for every sample model', () => {
    expect(Object.keys(DEFAULT_SETS).sort()).toEqual(['building', 'debris-demo', 'fzk-haus', 'plumbing', 'process-plant', 'synth5k']);
    expect(DEFAULT_SETS['building']!.map((d) => d.name)).toEqual(['Duct run', 'Roof beams']);
    expect(DEFAULT_SETS['fzk-haus']!.map((d) => d.name)).toEqual(['Rafters', 'Ground floor walls']);
    expect(DEFAULT_SETS['synth5k']!.map((d) => d.name)).toEqual(['Level 0 ducts', 'Risers']);
    expect(DEFAULT_SETS['plumbing']!.map((d) => d.name)).toEqual(['All pipes']);
    expect(DEFAULT_SETS['process-plant']!.map((d) => d.name)).toEqual(['Process piping', 'Pipe rack steel', 'Instruments', 'Foundations', 'Equipment', 'Cable tray', 'Battery-limit blinds']);
  });

  it('resolves synth5k rules: ducts on storey 0 and elements named riser', () => {
    const sets = defaultSetsFor(synth, 'synth5k');
    expect(sets.map((s) => s.name)).toEqual(['Level 0 ducts', 'Risers']);
    expect(sets[0]!.globalIds).toEqual(['G0']);
    expect(sets[1]!.globalIds).toEqual(['G2']);
  });

  it('resolves building and plumbing rules by class and drops rules that match nothing', () => {
    const m = modelOf(
      [
        { cls: 'IfcDuctSegment', storey: 0 },
        { cls: 'IfcAirTerminal', storey: 0 },
        { cls: 'IfcSlab', storey: 0 },
      ],
      storeys,
    );
    const sets = defaultSetsFor(m, 'building');
    expect(sets.map((s) => s.name)).toEqual(['Duct run']); // no beams -> "Roof beams" dropped
    expect(sets[0]!.globalIds).toEqual(['G0', 'G1']);
    expect(defaultSetsFor(m, 'plumbing')).toEqual([]);
    expect(defaultSetsFor(m, 'unknown-model')).toEqual([]);
  });

  it('resolves fzk-haus ground floor walls by storey name', () => {
    const m = modelOf(
      [
        { cls: 'IfcWallStandardCase', storey: 0 },
        { cls: 'IfcWallStandardCase', storey: 1 },
        { cls: 'IfcMember', storey: 1 },
        { cls: 'IfcWall', storey: null },
      ],
      [
        { id: 0, name: 'Erdgeschoss', elevation: 0 },
        { id: 1, name: 'Dachgeschoss', elevation: 2.7 },
      ],
    );
    const sets = defaultSetsFor(m, 'fzk-haus');
    expect(sets.find((s) => s.name === 'Ground floor walls')!.globalIds).toEqual(['G0']);
    expect(sets.find((s) => s.name === 'Rafters')!.globalIds).toEqual(['G2']);
  });

  it('seeds once per model: only when nothing is stored', () => {
    const st = new MemoryStorage();
    const first = loadOrSeed(st, synth, 'synth5k');
    expect(first).toHaveLength(2);
    expect(st.getItem(storageKey('synth5k'))).not.toBeNull();

    // User deletes everything: stays empty, no reseed.
    saveSets(st, 'synth5k', []);
    expect(loadOrSeed(st, synth, 'synth5k')).toEqual([]);

    // User edits: kept as is.
    const edited = addSet([], 'Custom', ['G3']);
    saveSets(st, 'synth5k', edited);
    expect(loadOrSeed(st, synth, 'synth5k')).toEqual(edited);

    // A model without defaults gets an empty saved list.
    expect(loadOrSeed(st, synth, 'upload')).toEqual([]);
    expect(st.getItem(storageKey('upload'))).not.toBeNull();
  });
});
