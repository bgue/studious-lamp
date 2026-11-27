// The review walk's zoom resolution, its keys, Esc and the code filter. No browser: these are pure functions.

import { describe, expect, it } from 'vitest';
import { DEFAULT_REVIEW_ZOOM, nextReviewZoom, resolveZoom, roomOf, storeyBox, SURROUNDINGS, WIDE, REVIEW_ZOOMS } from '../src/classify/reviewZoom';
import type { Box6 } from '../src/classify/reviewZoom';
import { ESC_CLOSE_MS, escAction, filterCodes, walkKeyAction } from '../src/classify/walkKeys';
import { defaultDraft, toSettings, validateSettings } from '../src/classify/settings';

const box = (x: number, y: number, z: number, s = 1): Box6 => [x, y, z, x + s, y + s, z + s];

describe('review zoom', () => {
  it('defaults to With surroundings and cycles Close, With surroundings, Room, Storey', () => {
    expect(DEFAULT_REVIEW_ZOOM).toBe('surroundings');
    expect(REVIEW_ZOOMS).toEqual(['close', 'surroundings', 'room', 'storey']);
    expect(nextReviewZoom('close')).toBe('surroundings');
    expect(nextReviewZoom('storey')).toBe('close');
  });

  it('Close is the framing the walk always had: 1.6 for one element, 1.15 for a group, no closest distance', () => {
    expect(resolveZoom('close', [box(0, 0, 0)])).toMatchObject({ margin: 1.6, minDistance: 0, used: 'close' });
    expect(resolveZoom('close', [box(0, 0, 0), box(5, 0, 0)])).toMatchObject({ margin: 1.15, minDistance: 0 });
    expect(resolveZoom('close', [box(0, 0, 0), box(5, 0, 0)])!.box).toEqual([0, 0, 0, 6, 1, 1]);
  });

  it('With surroundings uses margin 2.5 and never goes nearer than 4 m', () => {
    const v = resolveZoom('surroundings', [box(0, 0, 0, 0.1)])!;
    expect(v).toMatchObject({ margin: SURROUNDINGS.margin, minDistance: SURROUNDINGS.minDistance, used: 'surroundings' });
    expect(SURROUNDINGS).toEqual({ margin: 2.5, minDistance: 4 });
  });

  it('Room frames the room box when one is known, else a wide margin around the element', () => {
    const room = box(-5, 0, -5, 10);
    expect(resolveZoom('room', [box(0, 0, 0)], { room })).toMatchObject({ box: room, used: 'room', minDistance: 0 });
    expect(resolveZoom('room', [box(0, 0, 0)], {})).toMatchObject({ used: 'wide', margin: WIDE.margin, minDistance: WIDE.minDistance });
    expect(resolveZoom('room', [box(0, 0, 0)], {})!.box).toEqual(box(0, 0, 0));
  });

  it('Storey frames the storey box, else the wide fallback', () => {
    const storey = box(-20, 0, -20, 40);
    expect(resolveZoom('storey', [box(0, 0, 0)], { storey, room: box(0, 0, 0, 5) })).toMatchObject({ box: storey, used: 'storey' });
    expect(resolveZoom('storey', [box(0, 0, 0)], { room: box(0, 0, 0, 5) })).toMatchObject({ used: 'wide' });
  });

  it('has nothing to frame without a target', () => {
    expect(resolveZoom('close', [])).toBeNull();
  });

  it('finds the smallest IfcSpace around the element centre, on the same storey', () => {
    const big = { bounds: box(-10, 0, -10, 20), storey: 0 };
    const small = { bounds: box(-2, 0, -2, 4), storey: 0 };
    const other = { bounds: box(-1, 0, -1, 2), storey: 1 };
    expect(roomOf(box(0, 0.2, 0, 0.2), 0, [big, small, other])).toEqual(small.bounds);
    expect(roomOf(box(8, 0.2, 8, 0.2), 0, [big, small])).toEqual(big.bounds);
    expect(roomOf(box(50, 0, 50), 0, [big, small])).toBeNull();
    expect(roomOf(box(0, 0, 0), null, [other])).toEqual(other.bounds); // no storey known: any space counts
  });

  it('builds the box of a storey from its elements', () => {
    const els = [{ storey: 1, bounds: box(0, 3, 0) }, { storey: 1, bounds: box(10, 3, 10) }, { storey: 2, bounds: box(0, 6, 0) }];
    expect(storeyBox(1, els)).toEqual([0, 3, 0, 11, 4, 11]);
    expect(storeyBox(null, els)).toBeNull();
  });
});

describe('review zoom setting', () => {
  it('is in the settings, saved with them, and checked on load', () => {
    expect(validateSettings(undefined).settings.reviewZoom).toBe('surroundings');
    expect(validateSettings({ reviewZoom: 'room' }).settings.reviewZoom).toBe('room');
    const bad = validateSettings({ reviewZoom: 'far' });
    expect(bad.settings.reviewZoom).toBe('surroundings');
    expect(bad.errors[0]).toMatch(/reviewZoom must be one of close, surroundings, room, storey/);
    expect(toSettings({ ...defaultDraft(), reviewZoom: 'storey' }).reviewZoom).toBe('storey');
  });
});

describe('walk keys', () => {
  const act = (key: string, shift = false) => walkKeyAction({ key, shift });
  it('1 confirms, 2 is the runner-up, 3 to 9 are candidates', () => {
    expect(act('1')).toEqual({ action: 'confirm' });
    expect(act('2')).toEqual({ action: 'candidate', rank: 2 });
    expect(act('9')).toEqual({ action: 'candidate', rank: 9 });
    expect(act('0')).toBeNull();
  });
  it('keeps the old keys and adds F, Z and Q', () => {
    expect(act('Enter')?.action).toBe('confirm');
    expect(act('Y')?.action).toBe('confirm');
    expect(act('e')?.action).toBe('correct');
    expect(act('n')?.action).toBe('skip');
    expect(act('N', true)?.action).toBe('skip-other');
    expect(act('ArrowRight')?.action).toBe('skip');
    expect(act('ArrowLeft')?.action).toBe('back');
    expect(act('?')?.action).toBe('unsure');
    expect(act('u')?.action).toBe('undo');
    expect(act('a')?.action).toBe('scope');
    expect(act(']')?.action).toBe('step-next');
    expect(act('f')?.action).toBe('frame');
    expect(act('Z')?.action).toBe('zoom');
    expect(act('q')?.action).toBe('close');
    expect(act('Escape')).toBeNull(); // Esc has its own rules
  });
});

describe('Esc', () => {
  const now = 100_000;
  it('leaves Correct first', () => {
    expect(escAction({ editing: true, focus: 'field', armedAt: null, now })).toBe('leave-edit');
    expect(escAction({ editing: true, focus: 'walk', armedAt: now - 10, now })).toBe('leave-edit');
  });
  it('brings the focus back to the walk when it is in a field or elsewhere, and does not close', () => {
    expect(escAction({ editing: false, focus: 'field', armedAt: null, now })).toBe('focus-walk');
    expect(escAction({ editing: false, focus: 'elsewhere', armedAt: now - 10, now })).toBe('focus-walk');
  });
  it('closes only on a second Esc within 1.5 s', () => {
    expect(escAction({ editing: false, focus: 'walk', armedAt: null, now })).toBe('arm');
    expect(escAction({ editing: false, focus: 'walk', armedAt: now - 500, now })).toBe('close');
    expect(escAction({ editing: false, focus: 'walk', armedAt: now - ESC_CLOSE_MS, now })).toBe('close');
    expect(escAction({ editing: false, focus: 'walk', armedAt: now - ESC_CLOSE_MS - 1, now })).toBe('arm');
    expect(ESC_CLOSE_MS).toBe(1500);
  });
});

describe('code filter', () => {
  const list = [{ code: 'PLB', label: 'Plumbing' }, { code: 'MEC', label: 'Mechanical' }, { code: 'ELE', label: 'Electrical' }];
  it('keeps what matches the code or the label, every word', () => {
    expect(filterCodes(list, 'plum').map((x) => x.code)).toEqual(['PLB']);
    expect(filterCodes(list, 'cal').map((x) => x.code)).toEqual(['MEC', 'ELE']);
    expect(filterCodes(list, 'mec cal').map((x) => x.code)).toEqual(['MEC']);
    expect(filterCodes(list, '').length).toBe(3);
  });
  it('keeps the current code visible', () => {
    expect(filterCodes(list, 'plum', 'ELE').map((x) => x.code)).toEqual(['PLB', 'ELE']);
  });
});
