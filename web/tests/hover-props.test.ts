// Property rules shared with tools/glb_common.py (ordering, cap, truncation, rounding, units) and the loader pass-through.
import { describe, expect, it } from 'vitest';
import {
  COMMON_QTY_NAMES, GROUP_ATTR, GROUP_COMMON, GROUP_OTHER, GROUP_QTY, PROPS_CAP, SI_SCALES, attributeEntries, clipString,
  finalizeProps, isBaseQtoSet, isCommonPset, normalizeNumber, propertyGroup, quantityGroup, roundSig, sanitizeProps,
} from '../src/model/ifcProps';
import type { PropEntry } from '../src/model/ifcProps';
import { buildModelData } from '../src/model/ifcImport';
import { parseModel } from '../src/model/loader';

const e = (key: string, value: string | number | boolean, group: number): PropEntry => ({ key, value, group });

describe('property groups', () => {
  it('recognises common psets and base quantity sets', () => {
    expect(isCommonPset('Pset_WallCommon')).toBe(true);
    expect(isCommonPset('Pset_WallCommonX')).toBe(false);
    expect(isCommonPset('Acme_Common')).toBe(false);
    expect(isBaseQtoSet('Qto_WallBaseQuantities')).toBe(true);
    expect(isBaseQtoSet('BaseQuantities')).toBe(true);
    expect(isBaseQtoSet('Qto_WallBaseQuantities2')).toBe(false);
  });
  it('mode decides what is kept', () => {
    expect(propertyGroup('Pset_WallCommon', 'common')).toBe(GROUP_COMMON);
    expect(propertyGroup('Acme', 'common')).toBeNull();
    expect(propertyGroup('Acme', 'all')).toBe(GROUP_OTHER);
    expect(propertyGroup('Pset_WallCommon', 'none')).toBeNull();
    expect(quantityGroup('Qto_WallBaseQuantities', 'NetVolume', 'common')).toBe(GROUP_QTY);
    expect(quantityGroup('Qto_WallBaseQuantities', 'Mystery', 'common')).toBeNull();
    expect(quantityGroup('Qto_WallBaseQuantities', 'Mystery', 'all')).toBe(GROUP_OTHER);
    expect(quantityGroup('Acme', 'Length', 'common')).toBeNull();
    expect(COMMON_QTY_NAMES.size).toBe(14);
  });
});

describe('finalizeProps', () => {
  it('orders attributes, common, quantities, others; keeps insertion order within a group', () => {
    const out = finalizeProps([
      e('Acme.X', 1, GROUP_OTHER), e('Qto_W.Length', 4, GROUP_QTY), e('Pset_WallCommon.B', true, GROUP_COMMON),
      e('Attr.Tag', 't', GROUP_ATTR), e('Pset_WallCommon.A', 'a', GROUP_COMMON), e('Qto_W.Width', 0.2, GROUP_QTY),
    ])!;
    expect(Object.keys(out)).toEqual(['Attr.Tag', 'Pset_WallCommon.B', 'Pset_WallCommon.A', 'Qto_W.Length', 'Qto_W.Width', 'Acme.X']);
  });
  it('caps at 24 and keeps the highest-priority groups', () => {
    const entries: PropEntry[] = [];
    for (let i = 0; i < 20; i++) entries.push(e(`Acme.P${i}`, i, GROUP_OTHER));
    for (let i = 0; i < 10; i++) entries.push(e(`Pset_XCommon.P${i}`, i, GROUP_COMMON));
    entries.push(e('Attr.ObjectType', 'o', GROUP_ATTR));
    const out = finalizeProps(entries)!;
    const keys = Object.keys(out);
    expect(keys.length).toBe(PROPS_CAP);
    expect(keys[0]).toBe('Attr.ObjectType');
    expect(keys.filter((k) => k.startsWith('Pset_XCommon')).length).toBe(10);
    expect(keys.filter((k) => k.startsWith('Acme')).length).toBe(13);
    expect(keys.at(-1)).toBe('Acme.P12');
  });
  it('first key wins and empty input gives undefined', () => {
    expect(finalizeProps([e('K', 1, GROUP_COMMON), e('K', 2, GROUP_COMMON)])).toEqual({ K: 1 });
    expect(finalizeProps([])).toBeUndefined();
  });
  it('truncates strings to 80 characters and leaves other values', () => {
    const out = finalizeProps([e('S', 'x'.repeat(200), GROUP_ATTR), e('N', 1.5, GROUP_ATTR), e('B', false, GROUP_ATTR)])!;
    expect((out.S as string).length).toBe(80);
    expect(out.N).toBe(1.5);
    expect(out.B).toBe(false);
    expect(clipString('€'.repeat(81)).length).toBe(80);
  });
});

describe('numbers', () => {
  it('rounds reals to 4 significant digits', () => {
    expect(roundSig(1.234567)).toBe(1.235);
    expect(roundSig(0.000123456)).toBe(0.0001235);
    expect(roundSig(123456.7)).toBe(123500);
    expect(roundSig(0)).toBe(0);
  });
  it('keeps integers exact and converts measures to SI', () => {
    const mm = { ...SI_SCALES, length: 0.001, area: 1, volume: 1, mass: 0.001 };
    expect(normalizeNumber('IFCINTEGER', 12345, SI_SCALES)).toBe(12345);
    expect(normalizeNumber('IfcCountMeasure', 12345, SI_SCALES)).toBe(12345);
    expect(normalizeNumber('IFCLENGTHMEASURE', 4000, mm)).toBe(4);
    expect(normalizeNumber('IFCPOSITIVELENGTHMEASURE', 250, mm)).toBe(0.25);
    expect(normalizeNumber('IFCAREAMEASURE', 11.2, mm)).toBe(11.2);
    expect(normalizeNumber('IFCMASSMEASURE', 5000, mm)).toBe(5);
    expect(normalizeNumber('IFCREAL', 1234.5678, mm)).toBe(1235);
    expect(normalizeNumber('IFCREAL', Infinity, mm)).toBeNull();
  });
});

describe('attributes', () => {
  it('drops empty and NOTDEFINED values, keeps the order', () => {
    const out = attributeEntries({ objectType: 'Wall:A', tag: '', description: 'd', predefinedType: 'NOTDEFINED' });
    expect(out.map((x) => x.key)).toEqual(['Attr.ObjectType', 'Attr.Description']);
    expect(attributeEntries({ predefinedType: 'SOLIDWALL' }).map((x) => x.key)).toEqual(['Attr.PredefinedType']);
  });
});

describe('sidecar pass-through', () => {
  it('sanitizeProps keeps primitives only', () => {
    expect(sanitizeProps({ a: 1, b: 'x', c: true, d: { n: 1 }, e: null, f: NaN })).toEqual({ a: 1, b: 'x', c: true });
    expect(sanitizeProps(undefined)).toBeUndefined();
    expect(sanitizeProps([1])).toBeUndefined();
    expect(sanitizeProps({})).toBeUndefined();
  });
  it('the build writes props into the sidecar and parseModel passes them through; absence is tolerated', async () => {
    const box = (x: number): { positions: Float32Array; indices: Uint32Array } => ({
      positions: Float32Array.from([x, 0, 0, x + 1, 0, 0, x, 1, 0, x, 0, 1]),
      indices: Uint32Array.from([0, 1, 2, 0, 2, 3, 0, 3, 1, 1, 3, 2]),
    });
    const mk = (id: number, props?: Record<string, string | number | boolean>) => ({
      expressId: id, globalId: `g${id}`, ifcClass: 'IfcWall', name: `w${id}`, storeyExpressId: null, materialName: '', color: null, ...box(id), ...(props ? { props } : {}),
    });
    const built = buildModelData([{ fileName: 'a.ifc', schema: 'IFC4', elements: [mk(1, { 'Attr.Tag': 't', 'Pset_WallCommon.IsExternal': true }), mk(2)], storeys: [], voids: [], fills: [], ports: [], systems: [] }]);
    expect(built.sidecar.elements[0]!.props).toEqual({ 'Attr.Tag': 't', 'Pset_WallCommon.IsExternal': true });
    expect('props' in built.sidecar.elements[1]!).toBe(false);
    const { model } = await parseModel(built.glb, JSON.parse(JSON.stringify(built.sidecar)));
    expect(model.elements[0]!.props).toEqual({ 'Attr.Tag': 't', 'Pset_WallCommon.IsExternal': true });
    expect(model.elements[1]!.props).toBeUndefined();
    const { model: bare } = await parseModel(built.glb);
    expect(bare.elements.every((x) => x.props === undefined)).toBe(true);
  });
});
