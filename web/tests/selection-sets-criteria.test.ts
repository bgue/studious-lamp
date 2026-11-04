// Criteria sets in the selection-set store: backward-compatible persistence, import/export and list operations.
import { describe, expect, it } from 'vitest';
import {
  MemoryStorage,
  addCriteriaSet,
  addSet,
  copySet,
  duplicateSet,
  exportSets,
  isCriteria,
  loadSets,
  mergeImported,
  parseImport,
  parseStored,
  saveSets,
  setQuery,
  updateSet,
} from '../src/selectionSets';

describe('criteria sets', () => {
  it('keeps old static payloads unchanged (no kind field is added)', () => {
    const st = new MemoryStorage();
    st.setItem('xray.sets.m', JSON.stringify({ version: 1, sets: [{ name: 'A', globalIds: ['G1'] }] }));
    const sets = loadSets(st, 'm')!;
    expect(sets).toEqual([{ name: 'A', globalIds: ['G1'] }]);
    saveSets(st, 'm', sets);
    expect(JSON.parse(st.getItem('xray.sets.m')!)).toEqual({ version: 1, sets: [{ name: 'A', globalIds: ['G1'] }] });
  });

  it('round trips kind and query through storage and export', () => {
    const sets = addCriteriaSet(addSet([], 'Static', ['G1']), 'Ext walls', '"Pset_WallCommon.IsExternal" = TRUE', ['G2', 'G3']);
    expect(isCriteria(sets[1]!)).toBe(true);
    expect(isCriteria(sets[0]!)).toBe(false);
    const st = new MemoryStorage();
    saveSets(st, 'm', sets);
    expect(loadSets(st, 'm')).toEqual(sets);
    expect(parseImport(exportSets('m', sets))).toEqual(sets);
  });

  it('accepts a hand-written criteria set without globalIds and drops a criteria kind without a query', () => {
    const list = parseStored(JSON.stringify([{ name: 'Q', kind: 'criteria', query: "class = 'IfcWall'" }, { name: 'Bad', kind: 'criteria' }]))!;
    expect(list).toEqual([{ name: 'Q', kind: 'criteria', query: "class = 'IfcWall'", globalIds: [] }]);
    expect(copySet({ name: 'S', globalIds: ['x'], kind: 'criteria' } as never)).toEqual({ name: 'S', globalIds: ['x'] });
  });

  it('turns a static set into a criteria set with setQuery and keeps the query on update and duplicate', () => {
    let sets = addSet([], 'A', ['G1']);
    sets = setQuery(sets, 0, 'id < 3', ['G0', 'G1', 'G2']);
    expect(sets[0]).toEqual({ name: 'A', globalIds: ['G0', 'G1', 'G2'], kind: 'criteria', query: 'id < 3' });
    sets = updateSet(sets, 0, ['G0']);
    expect(sets[0]!.query).toBe('id < 3');
    sets = duplicateSet(sets, 0);
    expect(sets.map((s) => s.name)).toEqual(['A', 'A copy']);
    expect(sets[1]).toMatchObject({ kind: 'criteria', query: 'id < 3' });
    expect(duplicateSet(sets, 0).map((s) => s.name)).toEqual(['A', 'A copy 2', 'A copy']);
  });

  it('imports criteria sets over same-named sets', () => {
    const merged = mergeImported([{ name: 'A', globalIds: ['x'] }], [{ name: 'A', globalIds: [], kind: 'criteria', query: 'id = 1' }]);
    expect(merged).toEqual([{ name: 'A', globalIds: [], kind: 'criteria', query: 'id = 1' }]);
  });
});
