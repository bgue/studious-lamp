// Class styles: alphaMax cap, alphaMin override, floor, colour, hidden; alias resolution and precedence.

import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { FLAG_FOCUS, FLAG_HIDDEN } from '../src/types';
import type { ClassStyles } from '../src/types';
import { createRenderState } from '../src/algo';
import { XrayController, defaultSettings } from '../src/controller';
import { mergeStyles, patternMatches, resolveStyleIndex, styleKeyCounts } from '../src/styles';
import { makeScene } from './boxProvider';

const DUCT = 0;
const SLAB = 1;
const STEEL = 2;
const COLUMN = 3;
const FAR_SLAB = 4;

const ALIASES = { Steel: ['IfcBeam:steel', 'IfcMember'] };

function build(styles: ClassStyles, aliases = ALIASES) {
  const scene = makeScene(
    [
      { cls: 'IfcDuctSegment', box: [0, 0, -0.3, 8, 0.7, 0.3], storey: 1, name: 'duct' },
      { cls: 'IfcSlab', box: [-1, 0.6, -3, 9, 0.85, 3], storey: 1, name: 'slab' },
      { cls: 'IfcBeam', box: [3.0, -0.8, -3, 3.4, -0.2, 3], storey: 1, name: 'steel beam' },
      { cls: 'IfcColumn', box: [20, -2.5, 3.3, 20.4, 0.6, 3.7], storey: 1, name: 'column' },
      { cls: 'IfcSlab', box: [30, 0.6, -3, 40, 0.85, 3], storey: 1, name: 'far slab' },
    ],
    { storeys: [{ id: 0, name: 'L0', elevation: -3.5 }, { id: 1, name: 'L1', elevation: 0 }] },
  );
  scene.model.elements[STEEL]!.material = 'Steel S355';
  scene.model.elements[SLAB]!.material = 'Concrete C30';
  const state = createRenderState(scene.model.elements.length);
  const settings = defaultSettings();
  settings.classStyles = styles;
  settings.materialAliases = aliases;
  const ctl = new XrayController(scene.model, scene.geometry, state, settings);
  return { ...scene, state, ctl };
}

const STYLES: ClassStyles = { Steel: { alphaMax: 0.8 }, IfcSlab: { alphaMin: 0.3 } };
const ABOVE = new Vector3(4, 0.85 + 6, 0);
const BELOW = new Vector3(3.2, -8, 0.1);

describe('class styles: alphaMax', () => {
  it('caps the steel beam at 0.8 with nothing selected; the slab stays at 1', () => {
    const { ctl, state } = build(STYLES);
    ctl.reclassify();
    ctl.settle();
    expect(state.alpha[STEEL]).toBeCloseTo(0.8, 6);
    expect(state.alpha[SLAB]).toBe(1);
    expect(state.alpha[COLUMN]).toBe(1);
  });

  it('caps with x-ray off', () => {
    const { ctl, state } = build(STYLES);
    ctl.settings.xray = false;
    ctl.reclassify();
    ctl.tick();
    expect(state.alpha[STEEL]).toBeCloseTo(0.8, 6);
    expect(state.alpha[SLAB]).toBe(1);
  });

  it('caps Far elements (class style, not alias) in both far modes', () => {
    const { ctl, state } = build({ IfcSlab: { alphaMax: 0.5 } });
    ctl.setSelection([DUCT]);
    ctl.updateSightlines(ABOVE);
    expect(ctl.bucketOf(FAR_SLAB)).toBe('far');
    ctl.settle();
    expect(state.alpha[FAR_SLAB]).toBeCloseTo(0.5, 6);
  });

  it('never lets the steel beam exceed 0.8, whatever the state', () => {
    const { ctl, state } = build(STYLES);
    const check = (): void => {
      expect(state.alpha[STEEL]!).toBeLessThanOrEqual(0.8 + 1e-6);
    };
    const run = (n: number): void => {
      for (let i = 0; i < n; i++) {
        ctl.tick();
        check();
      }
    };
    ctl.setSelection([]);
    run(5);
    ctl.setSelection([DUCT]);
    ctl.updateSightlines(ABOVE);
    run(40);
    ctl.updateSightlines(BELOW); // the beam now sits between camera and duct
    run(60);
    expect(state.alpha[STEEL]!).toBeLessThan(0.8);
    ctl.settings.farMode = 'hidden';
    ctl.touch();
    run(5);
    ctl.setSelection([]);
    run(60); // fading back to opaque is held at the cap
    expect(state.alpha[STEEL]).toBeCloseTo(0.8, 6);
    ctl.settings.xray = false;
    ctl.reclassify();
    run(3);
    expect(state.alpha[STEEL]).toBeCloseTo(0.8, 6);
  });

  it('converges when the cap is below the target', () => {
    const { ctl } = build(STYLES);
    ctl.setSelection([DUCT]);
    ctl.updateSightlines(ABOVE);
    expect(ctl.settle(300)).toBeLessThan(300);
    expect(ctl.converged).toBe(true);
  });

  it('exempts a selected (focus) element from an alias cap, but not from its own class style', () => {
    const alias = build(STYLES);
    alias.ctl.settings.classification.focusClasses.push('IfcBeam');
    alias.ctl.setSelection([STEEL]);
    alias.ctl.updateSightlines(ABOVE);
    alias.ctl.settle();
    expect(alias.state.flags[STEEL]! & FLAG_FOCUS).toBeTruthy();
    expect(alias.state.alpha[STEEL]).toBe(1);

    const own = build({ IfcBeam: { alphaMax: 0.6 } });
    own.ctl.settings.classification.focusClasses.push('IfcBeam');
    own.ctl.setSelection([STEEL]);
    own.ctl.updateSightlines(ABOVE);
    own.ctl.settle();
    expect(own.state.flags[STEEL]! & FLAG_FOCUS).toBeTruthy();
    expect(own.state.alpha[STEEL]).toBeCloseTo(0.6, 6);
  });

  it('setClassStyles takes effect and can be undone', () => {
    const { ctl, state } = build({});
    ctl.reclassify();
    ctl.settle();
    expect(state.alpha[STEEL]).toBe(1);
    ctl.setClassStyles(STYLES, ALIASES);
    ctl.settle();
    expect(state.alpha[STEEL]).toBeCloseTo(0.8, 6);
    ctl.setClassStyles({}, ALIASES);
    ctl.tick();
    expect(state.alpha[STEEL]).toBe(1);
  });
});

describe('class styles: alphaMin and floor', () => {
  it('slab hosting the duct settles at max(target, 0.3), and the target uses the class alphaMin', () => {
    const base = build({});
    base.ctl.setSelection([DUCT]);
    base.ctl.updateSightlines(ABOVE);
    base.ctl.settle();
    const { ctl, state } = build(STYLES);
    ctl.setSelection([DUCT]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(ctl.bucketOf(SLAB)).toBe('host');
    const imp = ctl.result.importance.get(SLAB)!;
    expect(imp).toBeGreaterThan(0);
    const target = ctl.targets.get(SLAB)!;
    expect(target).toBeCloseTo(0.85 + (0.3 - 0.85) * imp, 6);
    expect(target).toBeGreaterThanOrEqual(0.3 - 1e-9);
    expect(state.alpha[SLAB]).toBeCloseTo(Math.max(target, 0.3), 2);
    // With the default alphaMin 0.15 the same slab would go lower than with the class override.
    const baseTarget = base.ctl.targets.get(SLAB)!;
    expect(baseTarget).toBeLessThanOrEqual(target + 1e-9);
  });

  it('a style floor replaces categoryFloors for its class; categoryFloors remains the fallback', () => {
    const a = build({ IfcSlab: { floor: 0.7 } });
    a.ctl.setSelection([DUCT]);
    a.ctl.updateSightlines(ABOVE);
    expect(a.ctl.floors.get(SLAB)).toBe(0.7);
    a.ctl.settle();
    expect(a.state.alpha[SLAB]!).toBeGreaterThanOrEqual(0.7 - 0.01);

    const b = build({});
    b.ctl.settings.overrides.categoryFloors['IfcSlab'] = 0.55;
    b.ctl.setSelection([DUCT]);
    expect(b.ctl.floors.get(SLAB)).toBe(0.55);

    const c = build({ IfcSlab: { floor: 0.2 } }); // style wins even when lower
    c.ctl.settings.overrides.categoryFloors['IfcSlab'] = 0.55;
    c.ctl.setSelection([DUCT]);
    expect(c.ctl.floors.get(SLAB)).toBe(0.2);
  });
});

describe('class styles: hidden and colour', () => {
  it('hidden sets FLAG_HIDDEN, including with x-ray off', () => {
    const { ctl, state } = build({ IfcColumn: { hidden: true } });
    ctl.reclassify();
    ctl.tick();
    expect(state.flags[COLUMN]! & FLAG_HIDDEN).toBeTruthy();
    expect(state.flags[SLAB]! & FLAG_HIDDEN).toBe(0);
    ctl.settings.xray = false;
    ctl.reclassify();
    ctl.tick();
    expect(state.flags[COLUMN]! & FLAG_HIDDEN).toBeTruthy();
  });

  it('colour lands in state.color and is restored when the style goes', () => {
    const { ctl, state, model } = build({ Steel: { color: [0.1, 0.2, 0.9] } });
    ctl.reclassify();
    ctl.tick();
    expect(Array.from(state.color.slice(STEEL * 3, STEEL * 3 + 3))).toEqual([
      Math.fround(0.1), Math.fround(0.2), Math.fround(0.9),
    ]);
    ctl.setClassStyles({}, ALIASES);
    ctl.tick();
    const b = model.elements[STEEL]!.color;
    expect(Array.from(state.color.slice(STEEL * 3, STEEL * 3 + 3))).toEqual([b[0], b[1], b[2]].map(Math.fround));
  });
});

describe('class styles: resolution', () => {
  const el = (ifcClass: string, material?: string) => ({ ifcClass, material });

  it('matches bare classes and Class:substring case-insensitively', () => {
    expect(patternMatches('IfcMember', el('IfcMember'))).toBe(true);
    expect(patternMatches('IfcMember', el('IfcBeam'))).toBe(false);
    expect(patternMatches('IfcBeam:steel', el('IfcBeam', 'STEEL S355'))).toBe(true);
    expect(patternMatches('IfcBeam:steel', el('IfcBeam', 'wood'))).toBe(false);
    expect(patternMatches('IfcBeam:steel', el('IfcBeam'))).toBe(false);
    expect(patternMatches('IfcBeam:steel', el('IfcColumn', 'steel'))).toBe(false);
  });

  it('element-level (ifcClass) entries win over alias entries, per field', () => {
    const model = { elements: [{ id: 0, globalId: 'a', ifcClass: 'IfcBeam', material: 'steel', color: [1, 1, 1, 1], bounds: [0, 0, 0, 1, 1, 1], storey: null }] } as never;
    const idx = resolveStyleIndex(model, { Steel: { alphaMax: 0.8, floor: 0.4 }, IfcBeam: { alphaMax: 0.5 } }, { Steel: ['IfcBeam:steel'] });
    expect(idx[0]).toMatchObject({ alphaMax: 0.5, floor: 0.4, alphaMaxOwn: 0.5 });
    const idx2 = resolveStyleIndex(model, { Steel: { alphaMax: 0.8 } }, { Steel: ['IfcBeam:steel'] });
    expect(idx2[0]).toMatchObject({ alphaMax: 0.8 });
    expect(idx2[0]!.alphaMaxOwn).toBeUndefined();
  });

  it('layers merge per field, later layers winning', () => {
    expect(mergeStyles({ A: { alphaMax: 0.8, floor: 0.1 } }, { A: { alphaMax: 0.6 } }, { B: { hidden: true } })).toEqual({
      A: { alphaMax: 0.6, floor: 0.1 },
      B: { hidden: true },
    });
  });

  it('lists classes present and only aliases that resolve to an element', () => {
    const { model } = build({});
    const keys = styleKeyCounts(model, { ...ALIASES, Timber: ['IfcBeam:timber'] });
    expect(keys.map((k) => k.key)).toEqual(['IfcBeam', 'IfcColumn', 'IfcDuctSegment', 'IfcSlab', 'Steel']);
    expect(keys.find((k) => k.key === 'IfcSlab')!.count).toBe(2);
    expect(keys.find((k) => k.key === 'Steel')!.count).toBe(1);
  });
});
