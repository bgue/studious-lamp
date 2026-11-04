// Pure parts of the hover card: property filter (glob, priority order) and card placement.
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_PROPERTY_FILTER, cardRows, contentToText, formatValue, globToRegExp, matchesGlob, parsePatterns, placeCard, propLabel, selectRows, subtitleOf,
} from '../src/ui/hoverCard';

const props = {
  'Attr.ObjectType': 'Wall:Brick',
  'Attr.Tag': 'W-1',
  'Pset_WallCommon.IsExternal': true,
  'Pset_WallCommon.LoadBearing': false,
  'Pset_WallCommon.FireRating': 'EI60',
  'Pset_WallCommon.Reference': 'R-1',
  'Qto_WallBaseQuantities.Length': 4,
  'Qto_WallBaseQuantities.Width': 0.2,
  'Qto_WallBaseQuantities.Height': 2.8,
  'Qto_WallBaseQuantities.NetVolume': 2.24,
  'Acme.Other': 'x',
};

describe('property filter', () => {
  it('parses comma separated patterns', () => {
    expect(parsePatterns(' a.b ,, *.c , ')).toEqual(['a.b', '*.c']);
    expect(parsePatterns('')).toEqual([]);
    expect(parsePatterns(DEFAULT_PROPERTY_FILTER).length).toBe(9);
  });
  it('matches globs over the whole key, case-insensitively, with literal dots', () => {
    expect(matchesGlob('Pset_WallCommon.IsExternal', '*.IsExternal')).toBe(true);
    expect(matchesGlob('Pset_WallCommon.IsExternal', '*.isexternal')).toBe(true);
    expect(matchesGlob('Pset_WallCommon.IsExternalX', '*.IsExternal')).toBe(false);
    expect(matchesGlob('Qto_WallBaseQuantities.Length', 'Qto*.Length')).toBe(true);
    expect(matchesGlob('Attr.ObjectType', 'Attr?ObjectType')).toBe(true);
    expect(matchesGlob('AttrXObjectType', 'Attr.ObjectType')).toBe(false);
    expect(matchesGlob('a(b)', 'a(b)')).toBe(true);
    expect(globToRegExp('x+*').test('x+yy')).toBe(true);
  });
  it('orders rows by pattern priority, then element order within a pattern, no duplicates', () => {
    const rows = selectRows(props, parsePatterns(DEFAULT_PROPERTY_FILTER), 99).map(([k]) => k);
    expect(rows).toEqual([
      'Attr.ObjectType', 'Pset_WallCommon.IsExternal', 'Pset_WallCommon.LoadBearing', 'Pset_WallCommon.FireRating', 'Pset_WallCommon.Reference',
      'Qto_WallBaseQuantities.Length', 'Qto_WallBaseQuantities.Width', 'Qto_WallBaseQuantities.Height', 'Qto_WallBaseQuantities.NetVolume',
    ]);
    expect(selectRows(props, ['Qto*', 'Qto_WallBaseQuantities.Width']).length).toBe(4);
    expect(selectRows(props, ['*.Reference', '*']).map(([k]) => k)[0]).toBe('Pset_WallCommon.Reference');
  });
  it('caps at the row limit and handles empty input', () => {
    expect(selectRows(props, parsePatterns(DEFAULT_PROPERTY_FILTER), 6).length).toBe(6);
    expect(selectRows(props, parsePatterns(DEFAULT_PROPERTY_FILTER), 0)).toEqual([]);
    expect(selectRows(undefined, ['*'])).toEqual([]);
    expect(selectRows(props, [], 3).map(([k]) => k)).toEqual(['Attr.ObjectType', 'Attr.Tag', 'Pset_WallCommon.IsExternal']);
    expect(selectRows(props, ['Nothing*'])).toEqual([]);
  });
});

describe('cardRows', () => {
  it('falls back to the first rows when the filter keeps nothing', () => {
    expect(cardRows(props, ['Nothing*'], 2).map(([k]) => k)).toEqual(['Attr.ObjectType', 'Attr.Tag']);
    expect(cardRows(props, ['Acme.*'], 2).map(([k]) => k)).toEqual(['Acme.Other']);
    expect(cardRows(props, ['Nothing*'], 0)).toEqual([]);
    expect(cardRows({}, [], 3)).toEqual([]);
  });
});

describe('card text', () => {
  it('labels and values', () => {
    expect(propLabel('Pset_WallCommon.IsExternal')).toBe('IsExternal');
    expect(propLabel('Plain')).toBe('Plain');
    expect(formatValue(true)).toBe('Yes');
    expect(formatValue(2.24)).toBe('2.24');
    expect(subtitleOf('IfcWall', undefined, 'Brick')).toBe('IfcWall · Brick');
    expect(subtitleOf('IfcWall', 'Level 1', '')).toBe('IfcWall · Level 1');
    expect(contentToText({ title: 'Wall', subtitle: 'IfcWall', rows: [['A.b', 1], ['A.c', false]], footer: 'x-ray: host' })).toBe('Wall\nIfcWall\nA.b: 1\nA.c: No\nx-ray: host');
  });
});

describe('placeCard', () => {
  const view = { w: 1000, h: 700 };
  const size = { w: 300, h: 150 };
  const clear = (p: { x: number; y: number }, at: { x: number; y: number }): boolean =>
    !(p.x >= at.x && p.x <= at.x + size.w && p.y >= at.y && p.y <= at.y + size.h);
  it('sits right of and below the pointer by default', () => {
    expect(placeCard({ x: 100, y: 100 }, size, view)).toEqual({ x: 116, y: 116 });
  });
  it('flips left near the right edge and up near the bottom', () => {
    const r = placeCard({ x: 900, y: 100 }, size, view);
    expect(r.x).toBe(900 - 16 - 300);
    const b = placeCard({ x: 100, y: 650 }, size, view);
    expect(b.y).toBe(650 - 16 - 150);
    const c = placeCard({ x: 990, y: 690 }, size, view);
    expect(c).toEqual({ x: 674, y: 524 });
  });
  it('stays on screen and clear of the pointer across the viewport', () => {
    for (let x = 0; x <= view.w; x += 50) {
      for (let y = 0; y <= view.h; y += 50) {
        const p = { x, y };
        const at = placeCard(p, size, view);
        expect(at.x).toBeGreaterThanOrEqual(6);
        expect(at.y).toBeGreaterThanOrEqual(6);
        expect(at.x + size.w).toBeLessThanOrEqual(view.w - 6);
        expect(at.y + size.h).toBeLessThanOrEqual(view.h - 6);
        expect(clear(p, at), `${x},${y}`).toBe(true);
      }
    }
  });
  it('keeps clear of the pointer in a tiny viewport when it can', () => {
    const at = placeCard({ x: 150, y: 100 }, size, { w: 320, h: 400 });
    expect(clear({ x: 150, y: 100 }, at)).toBe(true);
  });
});
