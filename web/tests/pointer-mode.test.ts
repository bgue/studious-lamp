import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_POINTER_MODE,
  NONE,
  POINTER_MODE_KEY,
  MOUSE_DOLLY,
  MOUSE_PAN,
  MOUSE_ROTATE,
  TOUCH_DOLLY_PAN,
  TOUCH_DOLLY_ROTATE,
  TOUCH_ROTATE,
  combineSelection,
  configureControls,
  loadPointerMode,
  parsePointerMode,
  savePointerMode,
  selectHowOf,
} from '../src/input/pointerMode';
import { MemoryStorage } from '../src/selectionSets';
import { PARAMS_SCHEMA, paramSectionNames } from '../src/ui/params';

describe('pointer mode state', () => {
  it('defaults to hand and parses only the two modes', () => {
    expect(DEFAULT_POINTER_MODE).toBe('hand');
    expect(parsePointerMode('arrow')).toBe('arrow');
    expect(parsePointerMode('hand')).toBe('hand');
    expect(parsePointerMode('select')).toBeNull();
    expect(parsePointerMode(3)).toBeNull();
  });

  it('is kept in storage, and survives a storage that throws', () => {
    const store = new MemoryStorage();
    expect(loadPointerMode(store)).toBe('hand');
    savePointerMode(store, 'arrow');
    expect(store.getItem(POINTER_MODE_KEY)).toBe('arrow');
    expect(loadPointerMode(store)).toBe('arrow');
    store.setItem(POINTER_MODE_KEY, 'junk');
    expect(loadPointerMode(store)).toBe('hand');
    const broken = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
    expect(loadPointerMode(broken)).toBe('hand');
    expect(() => savePointerMode(broken, 'arrow')).not.toThrow();
    expect(loadPointerMode(null)).toBe('hand');
  });

  it('is not part of the params document, a share link, a saved view, a preset or a packed page', () => {
    // No params section carries it: the section registry is what the params, the share link, the presets, the saved views
    // and the packed pages are made from.
    expect(paramSectionNames()).not.toContain('pointerMode');
    expect(paramSectionNames()).not.toContain('pointer');
    for (const file of ['../src/plugins/pointerMode.ts', '../src/input/pointerMode.ts']) {
      const text = readFileSync(fileURLToPath(new URL(file, import.meta.url)), 'utf8');
      expect(text, file).not.toMatch(/registerParamSection\(/);
      expect(text, file).not.toMatch(/from '\.\.\/ui\/params'/);
    }
    // The only place the key is written is localStorage.
    expect(POINTER_MODE_KEY).toBe('xray.pointerMode');
    expect(PARAMS_SCHEMA).toBe('xray-params/1');
  });
});

describe('orbit controls per mode', () => {
  const controls = () => ({ mouseButtons: { LEFT: -9 as number | null | undefined, MIDDLE: -9 as number | null | undefined, RIGHT: -9 as number | null | undefined }, touches: { ONE: -9 as number | null | undefined, TWO: -9 as number | null | undefined } });

  it('hand: left orbits, middle zooms, right pans, one finger orbits, two fingers zoom and pan', () => {
    const c = controls();
    configureControls(c, 'hand');
    expect(c.mouseButtons).toEqual({ LEFT: MOUSE_ROTATE, MIDDLE: MOUSE_DOLLY, RIGHT: MOUSE_PAN });
    expect(c.touches).toEqual({ ONE: TOUCH_ROTATE, TWO: TOUCH_DOLLY_PAN });
  });

  it('arrow: left and one finger leave the camera alone, the rest still move it', () => {
    const c = controls();
    configureControls(c, 'arrow');
    expect(c.mouseButtons.LEFT).toBe(NONE);
    expect(c.mouseButtons.MIDDLE).toBe(MOUSE_DOLLY);
    expect(c.mouseButtons.RIGHT).toBe(MOUSE_PAN);
    expect(c.touches.ONE).toBe(NONE);
    expect(c.touches.TWO).toBe(TOUCH_DOLLY_ROTATE);
    configureControls(c, 'hand'); // and back
    expect(c.mouseButtons.LEFT).toBe(MOUSE_ROTATE);
  });
});

describe('click and box selection modifiers', () => {
  it('Shift adds, Ctrl or Cmd toggles, nothing replaces', () => {
    expect(selectHowOf({})).toBe('replace');
    expect(selectHowOf({ shiftKey: true })).toBe('add');
    expect(selectHowOf({ ctrlKey: true })).toBe('toggle');
    expect(selectHowOf({ metaKey: true })).toBe('toggle');
    expect(selectHowOf({ ctrlKey: true, shiftKey: true })).toBe('toggle');
  });

  it('combines the picked ids with the selection', () => {
    expect(combineSelection([1, 2], [3, 4], 'replace')).toEqual([3, 4]);
    expect(combineSelection([1, 2], [2, 3], 'add').sort()).toEqual([1, 2, 3]);
    expect(combineSelection([1, 2], [2, 3], 'toggle').sort()).toEqual([1, 3]);
    expect(combineSelection([], [], 'replace')).toEqual([]);
  });
});
