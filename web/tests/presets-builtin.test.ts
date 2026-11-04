// The built-in presets: valid partial params documents, key order, keys that exist, the JSON override file.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { defaultViewModes, mergeBehind, mergePeel } from '../src/viewModes/config';
import { BUILTIN_PRESETS, KEYED_IDS } from '../src/presets/builtin';
import { GROUPS, normalizePreset, parsePresetsDocument } from '../src/presets/model';
import { defaultConfig } from '../src/plugins/cinematic';
import { PARAMS_SCHEMA, collectParams } from '../src/ui/params';
import { fakeApp } from './presets-helpers';

/** Sections of plugins that are not loaded in this test (they register their params section in install()). */
const ALLOWED_ABSENT = new Set(['viewModes', 'imaging', 'section', 'clearance', 'cinematic']);

const IMAGING_KEYS = ['style', 'palette', 'exposure', 'contrast', 'boneGlow', 'tissueEdges', 'mri'];
const MRI_KEYS = ['axis', 'thickness', 'position', 'scan', 'scanSpeed'];
const SECTION_KEYS = ['box', 'plane', 'caps', 'capColor'];
const CINEMATIC_KEYS = ['flyTo', 'reveal', 'dressing', 'bloom', 'edgeGlow', 'autoOrbit', 'sweep', 'grade'];

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

describe('built-in presets', () => {
  it('are all valid presets with a one-sentence description and a known group', () => {
    expect(BUILTIN_PRESETS.length).toBeGreaterThanOrEqual(12);
    for (const p of BUILTIN_PRESETS) {
      expect(normalizePreset(p, true), p.id).not.toBeNull();
      expect(p.builtIn).toBe(true);
      expect((GROUPS as readonly string[]).includes(p.group), p.id).toBe(true);
      expect(p.description.length).toBeGreaterThan(20);
      expect(p.description.endsWith('.'), p.id).toBe(true);
      expect((p.description.match(/\./g) ?? []).length, `${p.id} is one sentence`).toBe(1);
      expect(p.params['schema']).toBe(PARAMS_SCHEMA);
    }
    expect(new Set(BUILTIN_PRESETS.map((p) => p.id)).size).toBe(BUILTIN_PRESETS.length);
    expect(new Set(BUILTIN_PRESETS.map((p) => p.name)).size).toBe(BUILTIN_PRESETS.length);
  });

  it('map the first nine to the keys 1 to 9 in the documented order', () => {
    expect(KEYED_IDS).toEqual(['coordination', 'hide-blockers', 'behind-only', 'peelback', 'peel-only', 'stacked-floors', 'radiograph', 'mri-scan', 'section-focus']);
    expect(BUILTIN_PRESETS.map((p) => p.id).slice(9)).toEqual(['presentation', 'clearance-review', 'plain']);
  });

  it('only use keys that exist in a collected params document, except the allow-listed plugin sections', () => {
    const f = fakeApp();
    const doc = collectParams(f.app, f.env) as Record<string, unknown>;
    for (const p of BUILTIN_PRESETS) {
      for (const [k, v] of Object.entries(p.params)) {
        if (k === 'schema') continue;
        if (ALLOWED_ABSENT.has(k)) continue;
        expect(k in doc, `${p.id}: ${k}`).toBe(true);
        if (isObj(v)) for (const sub of Object.keys(v)) expect(sub in (doc[k] as Record<string, unknown>), `${p.id}: ${k}.${sub}`).toBe(true);
        else expect(typeof v).toBe(typeof doc[k]);
      }
    }
  });

  it('use valid viewModes values (checked with the real validators)', () => {
    for (const p of BUILTIN_PRESETS) {
      const vm = p.params['viewModes'];
      if (!isObj(vm)) continue;
      const cfg = defaultViewModes();
      expect(mergeBehind(cfg.behind, vm['behind'], 'behind'), p.id).toEqual([]);
      expect(mergePeel(cfg.peel, vm['peel'], 'peel'), p.id).toEqual([]);
      expect(Object.keys(vm).filter((k) => k !== 'behind' && k !== 'peel'), p.id).toEqual([]);
    }
  });

  it('use the agreed imaging, section, cinematic and clearance shapes', () => {
    for (const p of BUILTIN_PRESETS) {
      const im = p.params['imaging'];
      if (isObj(im)) {
        for (const k of Object.keys(im)) expect(IMAGING_KEYS.includes(k), `${p.id}: imaging.${k}`).toBe(true);
        if (isObj(im['mri'])) for (const k of Object.keys(im['mri'])) expect(MRI_KEYS.includes(k), `${p.id}: imaging.mri.${k}`).toBe(true);
      }
      const sec = p.params['section'];
      if (isObj(sec)) for (const k of Object.keys(sec)) expect(SECTION_KEYS.includes(k), `${p.id}: section.${k}`).toBe(true);
      const cin = p.params['cinematic'];
      if (isObj(cin)) for (const k of Object.keys(cin)) expect(CINEMATIC_KEYS.includes(k), `${p.id}: cinematic.${k}`).toBe(true);
      const cl = p.params['clearance'];
      if (isObj(cl)) for (const k of Object.keys(cl)) expect(['enabled', 'tight', 'max'].includes(k), `${p.id}: clearance.${k}`).toBe(true);
    }
  });

  it('use cinematic keys of the real cinematic config', () => {
    const cfg = defaultConfig() as unknown as Record<string, unknown>;
    for (const p of BUILTIN_PRESETS) {
      const cin = p.params['cinematic'];
      if (!isObj(cin)) continue;
      for (const [k, v] of Object.entries(cin)) {
        expect(k in cfg, `${p.id}: cinematic.${k}`).toBe(true);
        if (isObj(v)) for (const sub of Object.keys(v)) expect(sub in (cfg[k] as Record<string, unknown>), `${p.id}: cinematic.${k}.${sub}`).toBe(true);
      }
    }
  });

  it('set what their descriptions promise', () => {
    const by = (id: string) => BUILTIN_PRESETS.find((p) => p.id === id)!;
    expect(by('hide-blockers').params['sightlines']).toMatchObject({ alphaMin: 0, layerWeighting: 'budget', occluderScope: 'all', farWeight: 1 });
    expect((by('hide-blockers').params['sightlines'] as { layerBudget: number }).layerBudget).toBeGreaterThanOrEqual(6);
    expect(by('behind-only').params['viewModes']).toEqual({ behind: { enabled: true, frontTreatment: 'cut + cap' } });
    expect(by('peelback').params['viewModes']).toEqual({ peel: { enabled: true, outside: 'x-ray' } });
    expect(by('peel-only').params['viewModes']).toMatchObject({ peel: { enabled: true, outside: 'solid' } });
    expect(by('stacked-floors').params['sightlines']).toMatchObject({ layerWeighting: 'front', layerFalloff: 0.3 });
    expect(by('radiograph').params['imaging']).toEqual({ style: 'radiograph', palette: 'classic' });
    expect(by('mri-scan').params['imaging']).toEqual({ style: 'mri', mri: { scan: true } });
    expect(by('section-focus').params['section']).toMatchObject({ box: { enabled: true, fit: 'selection' }, caps: true });
    expect(by('section-focus').actions).toEqual(['section.fitSelection']);
    expect(by('presentation').params['cinematic']).toMatchObject({ dressing: true, bloom: true, flyTo: true });
    expect(by('clearance-review').params['clearance']).toMatchObject({ enabled: true });
    expect(by('plain').params['xray']).toBe(false);
    expect(by('coordination').base).toBe('defaults');
  });
});

describe('public/xray.presets.json', () => {
  const text = readFileSync(new URL('../public/xray.presets.json', import.meta.url).pathname, 'utf8');
  it('is a valid xray-presets/1 document equal to the TS built-ins', () => {
    const { presets, errors } = parsePresetsDocument(text, true);
    expect(errors).toEqual([]);
    expect(presets).toEqual(BUILTIN_PRESETS);
  });
});
