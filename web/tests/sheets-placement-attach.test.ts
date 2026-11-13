import { describe, expect, it } from 'vitest';
import { cleanAttachment, attachGuids, isSpatial } from '../src/bcf/attach';
import { deriveSheetAttachment, regionAround } from '../src/sheets/attachSheet';
import { cutElement } from '../src/sheets/sectionCut';
import type { CutElement } from '../src/sheets/sectionCut';

/** A rectangular element cut, plan metres. */
function rect(guid: string, x0: number, y0: number, x1: number, y1: number): CutElement {
  const quad = [x0, y0, x1, y0, x1, y0, x1, y1, x1, y1, x0, y1, x0, y1, x0, y0];
  return cutElement(guid, quad)!;
}
// A small plan: a wall along the south, a wall along the east, a column, and a far wall.
const cut = [rect('wall-S', 0, 0, 6, 0.3), rect('wall-E', 5.7, 0, 6, 5), rect('col', 2, 2, 2.4, 2.4), rect('far', 20, 20, 24, 20.3)];
const level = { elevation: 2.7, top: 5.4 };
const sq = (x0: number, y0: number, x1: number, y1: number): number[] => [x0, y0, x1, y0, x1, y1, x0, y1];

describe('attachment of a shape on a placed sheet', () => {
  it('a cloud over one wall is attached to that wall', () => {
    const r = deriveSheetAttachment({ path: sq(1, -0.3, 3, 0.6), closed: true, cut, level });
    expect(r.attach.kind).toBe('elements');
    expect(r.attach.guids).toEqual(['wall-S']);
    expect(r.attach.surface!.pts).toHaveLength(4);
    expect(r.attach.surface!.pts[0]!.p[2]).toBeCloseTo(2.75, 6); // on the sheet's plane, a little above the level
    expect(attachGuids(r.attach)).toEqual(['wall-S']);
    expect(isSpatial(r.attach)).toBe(true);
    expect(cleanAttachment(JSON.parse(JSON.stringify(r.attach)))).toBeTruthy(); // it survives the storage rules
  });

  it('a shape around a corner takes both walls, and the column when it reaches it', () => {
    const r = deriveSheetAttachment({ path: sq(4, -0.5, 6.5, 1), closed: true, cut, level });
    expect(r.attach.kind).toBe('elements');
    expect([...r.attach.guids!].sort()).toEqual(['wall-E', 'wall-S']);
    const big = deriveSheetAttachment({ path: sq(-1, -1, 7, 6), closed: true, cut, level });
    expect([...big.attach.guids!].sort()).toEqual(['col', 'wall-E', 'wall-S']);
  });

  it('nothing under the shape gives a region: its bounds at the level, up to the storey top', () => {
    const r = deriveSheetAttachment({ path: sq(10, 10, 12, 11), closed: true, cut, level });
    expect(r.attach.kind).toBe('region');
    expect(r.attach.region!.min).toEqual([9.95, 9.95, 2.7]);
    expect(r.attach.region!.max).toEqual([12.05, 11.05, 5.4]);
    expect(r.found).toEqual([]);
    expect(cleanAttachment(r.attach)).toBeTruthy();
  });

  it('the storey height defaults to 3 m when the level above is unknown', () => {
    const a = regionAround(sq(0, 0, 1, 1), { elevation: 0 }, 0);
    expect(a.region!.max[2]).toBe(3);
  });

  it('a point on an element becomes `point` with that GlobalId; a point on nothing a small region', () => {
    const on = deriveSheetAttachment({ path: [3, 0.15], closed: false, anchored: true, cut, level });
    expect(on.attach.kind).toBe('point');
    expect(on.attach.guids).toEqual(['wall-S']);
    const near = deriveSheetAttachment({ path: [3, 0.38], closed: false, anchored: true, cut, level });
    expect(near.attach.guids).toEqual(['wall-S']); // within 0.1 m of the outline
    const off = deriveSheetAttachment({ path: [3, 3], closed: false, anchored: true, cut, level });
    expect(off.attach.kind).toBe('region');
    expect(off.attach.region!.min[0]).toBeCloseTo(2.5, 6);
  });

  it('a tiny closed shape is a point', () => {
    const r = deriveSheetAttachment({ path: sq(2.1, 2.1, 2.2, 2.2), closed: true, cut, level });
    expect(r.attach.kind).toBe('point');
    expect(r.attach.guids).toEqual(['col']);
  });

  it('a line along a wall is a surface of that wall; a line across empty floor is a region', () => {
    const along = deriveSheetAttachment({ path: [0.5, 0.15, 5, 0.15], closed: false, cut, level });
    expect(along.attach.kind).toBe('surface');
    expect(along.attach.surface!.guids).toEqual(['wall-S']);
    const across = deriveSheetAttachment({ path: [1, 3, 4, 4], closed: false, cut, level });
    expect(across.attach.kind).toBe('region');
  });

  it('a line that crosses a wall touches it', () => {
    const r = deriveSheetAttachment({ path: [3, -1, 3, 1], closed: false, cut, level });
    expect(r.attach.kind).toBe('surface');
    expect(r.attach.surface!.guids).toEqual(['wall-S']);
  });

  it('more than a dozen elements under an outline is a region, not a long list', () => {
    const many = Array.from({ length: 14 }, (_v, i) => rect(`e${i}`, i * 0.5, 30, i * 0.5 + 0.2, 31));
    const r = deriveSheetAttachment({ path: sq(-1, 29, 8, 32), closed: true, cut: many, level });
    expect(r.attach.kind).toBe('region');
    expect(r.found).toHaveLength(14);
  });

  it('no points is not attached', () => {
    expect(deriveSheetAttachment({ path: [], closed: true, cut, level }).attach.kind).toBe('none');
  });
});
