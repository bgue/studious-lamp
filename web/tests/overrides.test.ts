import { describe, expect, it } from 'vitest';
import { DEFAULT_OVERRIDES, FLAG_FOCUS, FLAG_HIDDEN, FLAG_PINNED, FLAG_SELECTED, HIDDEN, type OverrideSettings } from '../src/types';
import { applyRenderState, classify, computeFloors, createRenderState, smoothAlpha } from '../src/algo';
import { makeScene } from './boxProvider';

const { model, geometry } = makeScene([
  { cls: 'IfcDuctSegment', box: [0, 0, 0, 8, 0.3, 0.3] }, // 0 focus
  { cls: 'IfcSlab', box: [1, -0.1, -1, 2, 0.5, 1] }, // 1 host
  { cls: 'IfcColumn', box: [3, 0.4, 0, 3.4, 2, 0.4] }, // 2 near
  { cls: 'IfcWall', box: [5, 0.4, 0, 5.2, 2, 0.4] }, // 3 near
  { cls: 'IfcBeam', box: [6, 0.4, 0, 6.2, 2, 0.4] }, // 4 near
  { cls: 'IfcWall', box: [50, 0, 0, 51, 1, 1] }, // 5 far
]);
const cls = classify(model, geometry, [0]);

const ov = (p: Partial<OverrideSettings>): OverrideSettings => ({
  userPins: new Set(),
  userHides: new Set(),
  userPinFloor: 0.6,
  categoryFloors: {},
  projectPins: {},
  ...p,
});

describe('computeFloors (Algorithm 7)', () => {
  it('no rules: floor 0 for every occluder', () => {
    const f = computeFloors([1, 2, 3], model, ov({}));
    expect([...f.entries()]).toEqual([[1, 0], [2, 0], [3, 0]]);
  });
  it('default category floor applies to columns only', () => {
    const f = computeFloors([1, 2, 3], model, DEFAULT_OVERRIDES);
    expect(f.get(2)).toBe(0.5);
    expect(f.get(1)).toBe(0);
  });
  it('takes the max of category, project pin and user pin', () => {
    const o = ov({ categoryFloors: { IfcColumn: 0.5, IfcWall: 0.2 }, projectPins: { 2: 0.7, 3: 0.1 }, userPins: new Set([2, 3, 4]), userPinFloor: 0.6 });
    const f = computeFloors([2, 3, 4], model, o);
    expect(f.get(2)).toBe(0.7); // project pin beats category 0.5 and user pin 0.6
    expect(f.get(3)).toBe(0.6); // user pin beats category 0.2 and project 0.1
    expect(f.get(4)).toBe(0.6); // user pin alone
  });
  it('userHides beats every pin and category floor', () => {
    const o = ov({ categoryFloors: { IfcColumn: 0.9 }, projectPins: { 2: 0.9 }, userPins: new Set([2]), userHides: new Set([2]) });
    expect(computeFloors([2], model, o).get(2)).toBe(HIDDEN);
  });
  it('extraFloor hook joins the max and is bypassed by hides', () => {
    const o = ov({ userHides: new Set([4]) });
    const f = computeFloors([2, 3, 4], model, o, { extraFloor: (id) => (id === 3 ? 0.4 : 0.9) });
    expect(f.get(3)).toBe(0.4);
    expect(f.get(2)).toBe(0.9);
    expect(f.get(4)).toBe(HIDDEN);
  });
  it('floors are clamped to [0, 1]', () => {
    const f = computeFloors([2], model, ov({ projectPins: { 2: 3 } }));
    expect(f.get(2)).toBe(1);
  });
});

describe('floors in smoothAlpha and applyRenderState', () => {
  const targets = new Map([[1, 0.15], [2, 0.15], [3, 0.15], [4, 0.15]]);
  const settings = { alphaMax: 0.85, smoothingRate: 0.2 };

  it('alpha never settles below the floor', () => {
    const state = createRenderState(model.elements.length);
    const floors = new Map([[1, 0], [2, 0.5], [3, 0.6]]);
    for (let i = 0; i < 100; i++) smoothAlpha(state.alpha, targets, floors, settings, 'opaque', cls);
    expect(state.alpha[1]).toBeCloseTo(0.15, 3);
    expect(state.alpha[2]).toBeCloseTo(0.5, 3);
    expect(state.alpha[3]).toBeCloseTo(0.6, 3);
  });

  it('HIDDEN occluders keep their alpha and get FLAG_HIDDEN', () => {
    const state = createRenderState(model.elements.length);
    const o = ov({ userHides: new Set([3]), userPins: new Set([2]), projectPins: { 4: 0.3 } });
    const floors = computeFloors([1, 2, 3, 4], model, o);
    const alphas = smoothAlpha(state.alpha, targets, floors, settings, 'opaque', cls);
    expect(state.alpha[3]).toBe(1);
    expect(alphas.get(3)).toBe(1);
    state.flags[1] = FLAG_SELECTED;
    applyRenderState(state, cls, alphas, o, 'opaque');
    expect(state.flags[3]! & FLAG_HIDDEN).toBe(FLAG_HIDDEN);
    expect(state.flags[2]! & FLAG_PINNED).toBe(FLAG_PINNED);
    expect(state.flags[4]! & FLAG_PINNED).toBe(FLAG_PINNED);
    expect(state.flags[1]).toBe(FLAG_SELECTED); // selection preserved
    expect(state.flags[0]! & FLAG_FOCUS).toBe(FLAG_FOCUS);
  });

  it('Focus and Far are opaque; Far gets FLAG_HIDDEN only in hidden mode; flags are rebuilt each call', () => {
    const state = createRenderState(model.elements.length);
    state.alpha.fill(0.3);
    const alphas = smoothAlpha(state.alpha, targets, new Map(), settings, 'hidden', cls);
    applyRenderState(state, cls, alphas, ov({}), 'hidden');
    expect(state.alpha[0]).toBe(1);
    expect(state.alpha[5]).toBe(1);
    expect(state.flags[5]! & FLAG_HIDDEN).toBe(FLAG_HIDDEN);
    expect(state.flags[1]! & FLAG_HIDDEN).toBe(0);
    applyRenderState(state, cls, alphas, ov({}), 'opaque');
    expect(state.flags[5]! & FLAG_HIDDEN).toBe(0);
  });
});
