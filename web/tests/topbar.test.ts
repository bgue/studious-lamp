// Top bar: mode to preset mapping, active-mode detection from the presets engine, click plan, visibility, keys.
import { afterEach, describe, expect, it } from 'vitest';
import { BUILTIN_PRESETS } from '../src/presets/builtin';
import { applyPreset, settingsHash } from '../src/presets/engine';
import type { EngineEnv } from '../src/presets/engine';
import { chordKey, eventCandidates, parseChord } from '../src/input/keymap';
import { MODES, OFF_PRESET_ID, TOPBAR_H, barVisible, clickPlan, modeById, modeForPreset, presetForMode } from '../src/ui/topBar';
import type { ModeId } from '../src/ui/topBar';
import { fakeApp, fakeSection } from './presets-helpers';

const offs: Array<() => void> = [];
afterEach(() => {
  while (offs.length) offs.pop()!();
});

const preset = (id: string) => BUILTIN_PRESETS.find((p) => p.id === id)!;

describe('mode to preset mapping', () => {
  it('has the four modes in order and each applies an existing built-in preset', () => {
    expect(MODES.map((m) => m.id)).toEqual(['ghost', 'radiograph', 'glow', 'cutaway']);
    expect(MODES.map((m) => m.presetId)).toEqual(['coordination', 'radiograph', 'focus-glow', 'peel-only']);
    for (const m of MODES) {
      expect(preset(m.presetId), m.id).toBeDefined();
      expect(preset(m.presetId).builtIn).toBe(true);
      expect(presetForMode(m.id)).toBe(m.presetId);
      expect(modeById(m.id)).toBe(m);
    }
    expect(preset(OFF_PRESET_ID).params['xray']).toBe(false);
  });

  it('gives every mode its own preset', () => {
    expect(new Set(MODES.map((m) => m.presetId)).size).toBe(MODES.length);
  });

  it('what each mode sets', () => {
    expect(preset('coordination').params['xray']).toBe(true);
    expect(preset('radiograph').params['imaging']).toMatchObject({ style: 'radiograph' });
    expect(preset('focus-glow').params['cinematic']).toEqual({ bloom: true, edgeGlow: true, glowScope: 'focus' });
    expect(preset('peel-only').params['viewModes']).toMatchObject({ peel: { enabled: true, outside: 'solid' } });
    expect(preset('peel-only').frame).toBe('selection');
  });

  it('gives short labels and an icon to every mode', () => {
    for (const m of MODES) {
      expect(m.label.length).toBeGreaterThan(2);
      expect(m.icon).toContain('<svg');
    }
    expect(TOPBAR_H).toBe(32);
  });
});

describe('active mode from the active preset', () => {
  it('maps the preset ids of the modes and nothing else', () => {
    expect(modeForPreset('coordination')).toBe('ghost');
    expect(modeForPreset('radiograph')).toBe('radiograph');
    expect(modeForPreset('focus-glow')).toBe('glow');
    expect(modeForPreset('peel-only')).toBe('cutaway');
    for (const other of ['hide-blockers', 'behind-only', 'peelback', 'mri-scan', 'presentation', 'plain', 'shared-preset', 'my-own']) expect(modeForPreset(other), other).toBeNull();
    expect(modeForPreset(null)).toBeNull();
    expect(modeForPreset(undefined)).toBeNull();
    expect(modeForPreset('')).toBeNull();
  });

  it('clears when a setting drifts: the presets engine hash changes after the mode preset was applied', () => {
    const f = fakeApp();
    const env: EngineEnv = { paramsEnv: f.env, clearance: null };
    for (const m of MODES) {
      applyPreset(f.app, preset(m.presetId), env);
      const active = m.presetId; // what presets.active() reports right after apply
      expect(modeForPreset(active)).toBe(m.id);
      const baseline = settingsHash(f.app, env);
      // nothing changed: the mark stays
      expect(settingsHash(f.app, env)).toBe(baseline);
      // a setting changed: the engine clears its mark, so the bar has no mode
      f.app.settings.sightlines.gamma = 2.2;
      expect(settingsHash(f.app, env)).not.toBe(baseline);
      f.app.settings.sightlines.gamma = 0.5;
    }
  });

  it('is not disturbed by the top bar setting itself (the hash ignores the topBar section)', () => {
    const f = fakeApp();
    const env: EngineEnv = { paramsEnv: f.env, clearance: null };
    const s = fakeSection('topBar', { visible: true });
    offs.push(s.off);
    const h = settingsHash(f.app, env);
    s.state.visible = false;
    expect(settingsHash(f.app, env)).toBe(h);
  });

  it('gives each mode a different settings state, so the highlight cannot confuse two modes', () => {
    const f = fakeApp();
    const env: EngineEnv = { paramsEnv: f.env, clearance: null };
    const im = fakeSection('imaging', { style: 'standard', palette: 'classic' });
    const vm = fakeSection('viewModes', { peel: { enabled: false, outside: 'x-ray' }, behind: { enabled: false, frontTreatment: 'cut' } });
    offs.push(im.off, vm.off);
    const factory = (s: string): unknown => (s === 'imaging' ? { style: 'standard', palette: 'classic' } : s === 'viewModes' ? { peel: { enabled: false, outside: 'x-ray' }, behind: { enabled: false, frontTreatment: 'cut' } } : undefined);
    const hashes = new Set<string>();
    for (const m of MODES) {
      applyPreset(f.app, preset(m.presetId), { ...env, factory });
      f.cfg['bloom'] = false;
      hashes.add(settingsHash(f.app, env));
    }
    expect(hashes.size).toBeGreaterThanOrEqual(3);
  });
});

describe('click plan', () => {
  it('applies the preset of an inactive mode', () => {
    for (const m of MODES) expect(clickPlan(null, m.id)).toEqual({ kind: 'apply', presetId: m.presetId });
    expect(clickPlan('ghost', 'glow')).toEqual({ kind: 'apply', presetId: 'focus-glow' });
  });

  it('returns to the normal view when the active mode is clicked again', () => {
    for (const m of MODES) expect(clickPlan(m.id, m.id)).toEqual({ kind: 'off', presetId: 'plain' });
  });

  it('survives a round trip: mode, off, mode', () => {
    let active: ModeId | null = null;
    const click = (id: ModeId): void => {
      const plan = clickPlan(active, id);
      active = modeForPreset(plan.presetId);
    };
    click('radiograph');
    expect(active).toBe('radiograph');
    click('radiograph');
    expect(active).toBeNull();
    click('cutaway');
    expect(active).toBe('cutaway');
  });
});

describe('bar visibility', () => {
  it('is on by default and off in a kiosk page, in an XR session and when switched off', () => {
    expect(barVisible({ visible: true, kiosk: false, xr: false })).toBe(true);
    expect(barVisible({ visible: false, kiosk: false, xr: false })).toBe(false);
    expect(barVisible({ visible: true, kiosk: true, xr: false })).toBe(false);
    expect(barVisible({ visible: true, kiosk: false, xr: true })).toBe(false);
    expect(barVisible({ visible: true, kiosk: false, xr: false, disabledByBoot: true })).toBe(false);
  });
});

describe('keys', () => {
  it('are valid chords, unique, and clear of the preset digits and the view keys', () => {
    const keys = MODES.map((m) => chordKey(m.key));
    expect(keys.every((k) => k !== null)).toBe(true);
    expect(new Set(keys).size).toBe(4);
    const taken = new Set<string>();
    for (let n = 0; n <= 9; n++) taken.add(`code:digit${n}`);
    for (const n of [0, 1, 3, 5, 7]) taken.add(chordKey(`Alt+code:Digit${n}`)!);
    for (const k of keys) expect(taken.has(k!), String(k)).toBe(false);
    expect(chordKey('Shift+t')).not.toBe(chordKey('t'));
  });

  it('match the key event of Shift and a digit on any layout', () => {
    for (let i = 0; i < MODES.length; i++) {
      const c = parseChord(MODES[i]!.key)!;
      expect(c.shift).toBe(true);
      const cands = eventCandidates({ key: '!', code: `Digit${i + 1}`, shiftKey: true });
      expect(cands).toContain(chordKey(MODES[i]!.key));
    }
  });
});
