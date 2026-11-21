import { describe, expect, it } from 'vitest';
import { labelLines, parseFieldList, fieldText } from '../src/anim/hud/fields';
import type { HudElement } from '../src/anim/hud/fields';
import { nearestOnRect, overlaps, placeLabels } from '../src/anim/hud/place';
import type { LabelIn } from '../src/anim/hud/place';
import { DEFAULT_HUD, sanitizeHud } from '../src/anim/hud/settings';
import { fitText, wrapText } from '../src/anim/hud/text';
import { activeCues, anyItemAt, chaptersOf, clock, fadeAlpha, niceScale, scaleText } from '../src/anim/hud/timing';
import type { Score } from '../src/anim/score';
import { SCORE_SCHEMA } from '../src/anim/score';

const el: HudElement = { name: 'Wall 12', ifcClass: 'IfcWall', storey: 'Level 2', material: 'Concrete', globalId: '0abc', props: { 'Pset_WallCommon.FireRating': '2HR', 'Pset_WallCommon.IsExternal': true, 'Attr.PredefinedType': 'SOLIDWALL' } };

describe('label fields', () => {
  it('formats the built-in fields and properties', () => {
    expect(fieldText(el, 'name')).toBe('Wall 12');
    expect(fieldText(el, 'Class')).toBe('IfcWall');
    expect(fieldText(el, 'storey')).toBe('Level 2');
    expect(fieldText(el, 'globalid')).toBe('0abc');
    expect(fieldText(el, 'type')).toBe('SOLIDWALL');
    expect(fieldText(el, 'Pset_WallCommon.IsExternal')).toBe('Yes');
    expect(fieldText(el, 'pset_wallcommon.firerating')).toBe('2HR');
    expect(fieldText(el, 'Pset_X.Missing')).toBe('');
  });
  it('makes lines: values for the built-ins, "Prop: value" for properties, missing ones left out', () => {
    expect(labelLines(el, ['name', 'class', 'storey'])).toEqual(['Wall 12', 'IfcWall', 'Level 2']);
    expect(labelLines(el, ['name', 'Pset_WallCommon.FireRating', 'type', 'material'])).toEqual(['Wall 12', 'FireRating: 2HR', 'Type: SOLIDWALL', 'Concrete']);
    expect(labelLines({ ifcClass: 'IfcSlab', globalId: 'g' }, ['name', 'storey'])).toEqual(['IfcSlab']);
    expect(labelLines(el, [])).toEqual(['Wall 12', 'IfcWall', 'Level 2']);
  });
  it('parses a field list: commas, quotes, case of the built-ins, no duplicates, at most 8', () => {
    expect(parseFieldList('Name, "Pset_A.B" , class,name')).toEqual(['name', 'Pset_A.B', 'class']);
    expect(parseFieldList(' , ')).toEqual([]);
    expect(parseFieldList('a,b,c,d,e,f,g,h,i,j')).toHaveLength(8);
  });
});

describe('label placement', () => {
  const view = { w: 400, h: 300 };
  const tag = (key: number, x: number, y: number): LabelIn => ({ key, x, y, w: 80, h: 30 });

  it('puts a tag up-right of its anchor, with a leader gap', () => {
    const { placed, more } = placeLabels([tag(1, 100, 200)], view);
    expect(more).toBe(0);
    expect(placed[0]).toMatchObject({ x: 114, y: 156, ax: 100, ay: 200 });
  });
  it('moves a tag that would overlap an earlier one and never overlaps', () => {
    const items = [tag(1, 100, 100), tag(2, 105, 102), tag(3, 110, 104), tag(4, 112, 106)];
    const { placed } = placeLabels(items, view);
    expect(placed.length).toBeGreaterThanOrEqual(3);
    for (let i = 0; i < placed.length; i++) for (let j = i + 1; j < placed.length; j++) expect(overlaps(placed[i]!, placed[j]!)).toBe(false);
  });
  it('keeps tags inside the frame and off the anchor', () => {
    const { placed } = placeLabels([tag(1, 395, 5), tag(2, 3, 295)], view);
    for (const p of placed) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.x + p.w).toBeLessThanOrEqual(view.w);
      expect(p.y + p.h).toBeLessThanOrEqual(view.h);
      expect(p.ax >= p.x && p.ax <= p.x + p.w && p.ay >= p.y && p.ay <= p.y + p.h).toBe(false);
    }
  });
  it('avoids reserved rectangles and counts what does not fit', () => {
    const reserved = [{ x: 0, y: 0, w: 400, h: 300 }];
    const r = placeLabels([tag(1, 100, 100)], view, reserved);
    expect(r.placed).toHaveLength(0);
    expect(r.more).toBe(1);
  });
  it('caps at 12 and counts the rest as more', () => {
    const items = Array.from({ length: 20 }, (_, i) => tag(i, 20 + (i % 5) * 70, 40 + Math.floor(i / 5) * 60));
    const r = placeLabels(items, { w: 1000, h: 800 });
    expect(r.placed).toHaveLength(12);
    expect(r.more).toBe(8);
  });
  it('finds the nearest point of a rectangle', () => {
    expect(nearestOnRect({ x: 10, y: 10, w: 20, h: 10 }, 0, 0)).toEqual({ x: 10, y: 10 });
    expect(nearestOnRect({ x: 10, y: 10, w: 20, h: 10 }, 15, 50)).toEqual({ x: 15, y: 20 });
  });
});

describe('text', () => {
  const m = (s: string): number => s.length * 10;
  it('wraps at word boundaries and cuts long words', () => {
    expect(wrapText(m, 'aaa bbb ccc ddd', 70)).toEqual(['aaa bbb', 'ccc ddd']);
    expect(wrapText(m, 'abcdefghij', 40)).toEqual(['abcd', 'efgh', 'ij']);
    expect(wrapText(m, 'one\ntwo', 100)).toEqual(['one', 'two']);
    expect(wrapText(m, '', 100)).toEqual([]);
  });
  it('fits with an ellipsis', () => {
    expect(fitText(m, 'short', 100)).toBe('short');
    expect(m(fitText(m, 'a very long label', 80))).toBeLessThanOrEqual(80);
    expect(fitText(m, 'a very long label', 80).endsWith('…')).toBe(true);
  });
});

const score = (cues: Score['cues'], extra: Partial<Score> = {}): Score => ({ schema: SCORE_SCHEMA, duration: 10, cues, ...extra });

describe('timing: fades and active cues', () => {
  it('fades in and out over 0.3 s and is 0 outside', () => {
    expect(fadeAlpha(-0.1, 1, 4)).toBe(0);
    expect(fadeAlpha(1, 1, 4)).toBe(0);
    expect(fadeAlpha(1.15, 1, 4)).toBeCloseTo(0.5, 5);
    expect(fadeAlpha(2.5, 1, 4)).toBe(1);
    expect(fadeAlpha(3.85, 1, 4)).toBeCloseTo(0.5, 5);
    expect(fadeAlpha(4.5, 1, 4)).toBe(0);
  });
  it('shrinks the fade of a short item and shows nothing for a zero length', () => {
    expect(fadeAlpha(1.1, 1, 1.2)).toBeCloseTo(1, 5);
    expect(fadeAlpha(1.05, 1, 1.2)).toBeCloseTo(0.5, 5);
    expect(fadeAlpha(1, 1, 1)).toBe(0);
  });
  it('lists the cues of a kind that are on, with their index and alpha', () => {
    const s = score([
      { kind: 'caption', at: 0, dur: 2, title: 'A' },
      { kind: 'label', at: 1, dur: 2, elements: { all: true }, fields: ['name'] },
      { kind: 'caption', at: 3, dur: 2, title: 'B' },
    ]);
    expect(activeCues(s, 'caption', 1).map((x) => [x.index, x.alpha])).toEqual([[0, 1]]);
    expect(activeCues(s, 'caption', 3.5).map((x) => x.index)).toEqual([2]);
    expect(activeCues(s, 'caption', 2.5)).toEqual([]);
    expect(anyItemAt(s, 1.5)).toBe(true);
    expect(anyItemAt(s, 2.5)).toBe(true);
    expect(anyItemAt(s, 5.5)).toBe(false);
  });
});

describe('timing: chapters, clock, scale', () => {
  it('uses the arrival at each keyframe for a fly-through', () => {
    const s = score(
      [
        { kind: 'view', at: 0, dur: 0, state: { camera: { position: [0, 0, 0], target: [0, 0, 1] } } },
        { kind: 'view', at: 0, dur: 3, state: { camera: { position: [0, 0, 0], target: [0, 0, 1] } } },
        { kind: 'view', at: 4, dur: 2, state: { camera: { position: [0, 0, 0], target: [0, 0, 1] } } },
        { kind: 'caption', at: 3, dur: 1, title: 'x' },
      ],
      { source: { kind: 'keyframes' } },
    );
    expect(chaptersOf(s)).toEqual([0, 3, 6]);
  });
  it('uses the start of each caption and label for a script, merges close marks and drops the ones past the end', () => {
    const s = score([
      { kind: 'caption', at: 2, dur: 1, title: 'a' },
      { kind: 'label', at: 2.1, dur: 1, elements: { all: true }, fields: [] },
      { kind: 'caption', at: 5, dur: 1, title: 'b' },
      { kind: 'hover', at: 6, dur: 1, elements: { all: true } },
      { kind: 'caption', at: 12, dur: 1, title: 'late' },
    ]);
    expect(chaptersOf(s)).toEqual([2, 5]);
  });
  it('writes clock text and picks round scale lengths', () => {
    expect(clock(0)).toBe('0:00');
    expect(clock(65.9)).toBe('1:05');
    expect(scaleText(5)).toBe('5 m');
    expect(scaleText(2000)).toBe('2 km');
    expect(scaleText(0.2)).toBe('20 cm');
    const n = niceScale(20)!; // 20 px per metre: 5 m is 100 px
    expect(n.metres).toBe(5);
    expect(n.px).toBe(100);
    const far = niceScale(0.3)!;
    expect(far.metres).toBe(200);
    expect(niceScale(0)).toBeNull();
  });
});

describe('HUD settings', () => {
  it('has defaults with the progress bar on and the rest off, and repairs bad data', () => {
    expect(DEFAULT_HUD).toEqual({ progress: true, compass: false, scaleBar: false, labelSize: 12, captionPosition: 'bottom' });
    expect(sanitizeHud(null)).toEqual(DEFAULT_HUD);
    expect(sanitizeHud({ progress: false, compass: 'yes', labelSize: 400, captionPosition: 'left' })).toEqual({ ...DEFAULT_HUD, progress: false, labelSize: 28 });
    expect(sanitizeHud({ labelSize: 3, captionPosition: 'top', scaleBar: true }).labelSize).toBe(9);
  });
});
