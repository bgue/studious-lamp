import { describe, expect, it } from 'vitest';
import { allParentKeys, buildTree, defaultExpanded, elementPath, filterTree, flattenTree, truncate } from '../src/ui/treeModel';
import { modelOf } from './sidebar-model';

// Storeys listed out of elevation order on purpose.
const model = modelOf(
  [
    { cls: 'IfcSlab', name: 'Slab 10', storey: 1 }, // 0
    { cls: 'IfcSlab', name: 'Slab 2', storey: 1 }, // 1
    { cls: 'IfcDuctSegment', name: 'Duct A', storey: 0 }, // 2
    { cls: 'IfcDuctSegment', name: 'Duct B', storey: 0 }, // 3
    { cls: 'IfcBeam', name: 'Beam', storey: 0 }, // 4
    { cls: 'IfcPipeSegment', name: undefined, storey: null }, // 5 -> no storey, label falls back to globalId
    { cls: 'IfcWall', name: 'Orphan', storey: 99 }, // 6 -> unknown storey id, also "No storey"
  ],
  [
    { id: 1, name: 'Level 2', elevation: 3.5 },
    { id: 0, name: 'Level 1', elevation: 0 },
    { id: 2, name: 'Empty roof', elevation: 7 },
  ],
  [
    { name: 'Supply Air', elements: [2, 3] },
    { name: 'Ghost system', elements: [] },
  ],
);

describe('buildTree', () => {
  const roots = buildTree(model);

  it('sorts storeys by elevation, No storey last, omits empty storeys, then Systems', () => {
    expect(roots.map((r) => r.label)).toEqual(['Level 1', 'Level 2', 'No storey', 'Systems']);
    expect(roots.map((r) => r.kind)).toEqual(['storey', 'storey', 'storey', 'systems']);
  });

  it('groups by class alphabetically with counts and ids', () => {
    const l1 = roots[0]!;
    expect(l1.children.map((c) => c.label)).toEqual(['IfcBeam', 'IfcDuctSegment']);
    expect(l1.children.map((c) => c.count)).toEqual([1, 2]);
    expect(l1.count).toBe(3);
    expect([...l1.ids].sort()).toEqual([2, 3, 4]);
    const duct = l1.children[1]!;
    expect(duct.ids).toEqual([2, 3]);
    expect(duct.children.map((c) => c.elementId)).toEqual([2, 3]);
  });

  it('sorts elements by natural name order', () => {
    const slabs = roots[1]!.children[0]!;
    expect(slabs.children.map((c) => c.label)).toEqual(['Slab 2', 'Slab 10']);
  });

  it('falls back to globalId for unnamed elements and truncates long labels', () => {
    const noStorey = roots[2]!;
    expect(noStorey.count).toBe(2);
    const pipe = noStorey.children.find((c) => c.label === 'IfcPipeSegment')!;
    expect(pipe.children[0]!.label).toBe('G5');
    expect(truncate('x'.repeat(100), 10)).toHaveLength(10);
    expect(truncate('short', 10)).toBe('short');
  });

  it('builds the Systems branch from relations and drops empty systems', () => {
    const sys = roots[3]!;
    expect(sys.children.map((c) => c.label)).toEqual(['Supply Air']);
    expect(sys.count).toBe(2);
    expect(sys.children[0]!.children.map((c) => c.elementId)).toEqual([2, 3]);
  });

  it('gives every node a unique key, even for elements shown in two branches', () => {
    const keys: string[] = [];
    const walk = (n: (typeof roots)[number]): void => {
      keys.push(n.key);
      n.children.forEach(walk);
    };
    roots.forEach(walk);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('omits the Systems root when the model has none', () => {
    const m = modelOf([{ cls: 'IfcSlab', storey: 0 }], [{ id: 0, name: 'L', elevation: 0 }]);
    expect(buildTree(m).map((r) => r.kind)).toEqual(['storey']);
  });
});

describe('flattenTree', () => {
  const roots = buildTree(model);

  it('creates rows only for expanded branches (storeys expanded by default, classes collapsed)', () => {
    const rows = flattenTree(roots, (k) => defaultExpanded(roots).has(k));
    // Level 1 + 2 classes, Level 2 + 1 class, No storey + 2 classes, Systems
    expect(rows.map((r) => r.node.kind)).toEqual([
      'storey', 'class', 'class', 'storey', 'class', 'storey', 'class', 'class', 'systems',
    ]);
    expect(rows.every((r) => r.node.kind !== 'element')).toBe(true);
    expect(rows.find((r) => r.node.kind === 'systems')!.expanded).toBe(false);
  });

  it('collapsed everything leaves only the roots', () => {
    expect(flattenTree(roots, () => false)).toHaveLength(4);
  });

  it('reports depth and expansion', () => {
    const all = allParentKeys(roots);
    const rows = flattenTree(roots, (k) => all.has(k));
    const el = rows.find((r) => r.node.elementId === 2 && r.node.key.startsWith('st:0'))!;
    expect(el.depth).toBe(2);
    expect(el.hasChildren).toBe(false);
    expect(rows.find((r) => r.node.kind === 'system')!.depth).toBe(1);
  });

  it('elementPath keys match the tree keys', () => {
    const p = elementPath(model, 2)!;
    const rows = flattenTree(roots, (k) => allParentKeys(roots).has(k));
    const keys = new Set(rows.map((r) => r.node.key));
    expect(keys.has(p.storey)).toBe(true);
    expect(keys.has(p.cls)).toBe(true);
    expect(keys.has(p.element)).toBe(true);
    expect(elementPath(model, 6)!.storey).toBe('st:none');
    expect(elementPath(model, 999)).toBeNull();
  });
});

describe('filterTree', () => {
  it('empty query returns the full tree', () => {
    expect(filterTree(model, '  ')).toEqual(buildTree(model));
  });

  it('matches by name, case-insensitively, keeping ancestors and counts of matches only', () => {
    const r = filterTree(model, 'DUCT a');
    expect(r.map((n) => n.label)).toEqual(['Level 1', 'Systems']);
    expect(r[0]!.count).toBe(1);
    expect(r[0]!.children.map((c) => c.label)).toEqual(['IfcDuctSegment']);
    expect(r[0]!.children[0]!.children.map((c) => c.elementId)).toEqual([2]);
  });

  it('matches by class substring', () => {
    const r = filterTree(model, 'slab');
    expect(r.map((n) => n.label)).toEqual(['Level 2']);
    expect(r[0]!.count).toBe(2);
  });

  it('matches by globalId', () => {
    const r = filterTree(model, 'g4');
    expect(r).toHaveLength(1);
    expect(r[0]!.ids).toEqual([4]);
  });

  it('returns nothing when nothing matches, and auto-expansion covers all ancestors', () => {
    expect(filterTree(model, 'zzz')).toEqual([]);
    const r = filterTree(model, 'duct');
    const rows = flattenTree(r, (k) => allParentKeys(r).has(k));
    expect(rows.filter((x) => x.node.kind === 'element').length).toBeGreaterThanOrEqual(2);
    // storey -> class -> element are all visible
    expect(rows.some((x) => x.node.kind === 'storey')).toBe(true);
    expect(rows.some((x) => x.node.kind === 'class')).toBe(true);
  });
});

describe('scale', () => {
  it('builds a 5,000 element tree quickly and creates no row for collapsed classes', () => {
    const specs = Array.from({ length: 5000 }, (_, i) => ({ cls: i % 2 ? 'IfcBeam' : 'IfcSlab', name: `E ${i}`, storey: i % 7 }));
    const m = modelOf(specs, Array.from({ length: 7 }, (_, i) => ({ id: i, name: `L${i}`, elevation: i })));
    const t0 = performance.now();
    const roots = buildTree(m);
    const rows = flattenTree(roots, (k) => defaultExpanded(roots).has(k));
    expect(performance.now() - t0).toBeLessThan(500);
    expect(rows).toHaveLength(7 + 14);
    expect(filterTree(m, 'e 4999').length).toBe(1);
  });
});
