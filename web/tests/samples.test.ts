// The Sample Projects menu: the labels, the availability in a single file, the entries of the menu, the names that old
// share links and saved views use, and the gzip-compressed IFC that the single file embeds. Pure: no DOM.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { SAMPLE_PROJECTS, UNAVAILABLE_HINT, inflateEmbedded, menuOptions, sampleAvailable, sampleMenu } from '../src/samples';
import type { BundleContents } from '../src/samples';

const read = (p: string): string => readFileSync(fileURLToPath(new URL(p, import.meta.url)), 'utf8');

/** Gzip with the web's CompressionStream (the same format the bundle writes with zlib). */
async function gzip(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes as Uint8Array<ArrayBuffer>]).stream().pipeThrough(new CompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
const toBase64 = (bytes: Uint8Array): string => btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(''));

// The `?model=` names of the app, as they were before the menu had labels. app.ts runs the viewer on import, so read its text.
const OLD_MODEL_NAMES = ['building', 'fzk-haus', 'plumbing', 'process-plant', 'synth5k', 'debris-demo', 'procedural'];

// What the default single file carries: the glb samples, the IFC sample, and no synth5k (it needs --all).
const SINGLE: BundleContents = { models: ['building', 'fzk-haus', 'plumbing', 'debris-demo', 'procedural'], ifc: ['process-plant'] };

describe('sample projects: names and labels', () => {
  it('keeps the ?model= names of the app, in the same order', () => {
    const src = read('../src/app.ts');
    const list = src.match(/MODEL_NAMES = \[([^\]]*)\]/)?.[1]?.match(/'([^']+)'/g)?.map((s) => s.slice(1, -1));
    expect(list).toEqual(OLD_MODEL_NAMES);
    expect(SAMPLE_PROJECTS.map((s) => s.name)).toEqual(OLD_MODEL_NAMES);
  });

  it('gives every sample a readable, unique label', () => {
    const labels = SAMPLE_PROJECTS.map((s) => s.label);
    expect(new Set(labels).size).toBe(labels.length);
    for (const l of labels) expect(l.trim().length).toBeGreaterThan(0);
    expect(SAMPLE_PROJECTS.find((s) => s.name === 'process-plant')!.label).toBe('Process plant');
    expect(SAMPLE_PROJECTS.find((s) => s.name === 'building')!.label).toBe('Building (Simple-Scene)');
  });
});

describe('sample projects: availability', () => {
  it('the served app (no bundle) loads every sample', () => {
    for (const s of SAMPLE_PROJECTS) expect(sampleAvailable(s.name, null)).toBe(true);
  });

  it('a single file loads what it carries, the procedural demo and nothing else', () => {
    expect(sampleAvailable('building', SINGLE)).toBe(true);
    expect(sampleAvailable('process-plant', SINGLE)).toBe(true);
    expect(sampleAvailable('procedural', SINGLE)).toBe(true);
    expect(sampleAvailable('synth5k', SINGLE)).toBe(false);
    expect(sampleAvailable('no-such-model', SINGLE)).toBe(false);
  });
});

describe('sample projects: the menu', () => {
  it('lists the samples in order with their labels when served', () => {
    const menu = sampleMenu(null);
    expect(menu.map((e) => e.value)).toEqual(OLD_MODEL_NAMES);
    expect(menu.every((e) => e.available)).toBe(true);
    expect(menu.find((e) => e.value === 'fzk-haus')!.label).toBe('FZK-Haus');
  });

  it('says why a sample is unavailable in a single file, in the same words everywhere', () => {
    const menu = sampleMenu(SINGLE);
    const synth = menu.find((e) => e.value === 'synth5k')!;
    expect(synth.available).toBe(false);
    expect(synth.label).toBe(`Synthetic 5k (${UNAVAILABLE_HINT})`);
    expect(menu.find((e) => e.value === 'process-plant')!.label).toBe('Process plant');
  });

  it('adds the models a bundle carries that are not samples, then the opened files', () => {
    const menu = sampleMenu({ models: ['packed-site'], ifc: [] }, ['Plan.ifc']);
    expect(menu.map((e) => e.value).slice(-2)).toEqual(['packed-site', 'Plan.ifc']);
    expect(menu.find((e) => e.value === 'Plan.ifc')!.label).toBe('Plan.ifc (opened file)');
    expect(menu.find((e) => e.value === 'packed-site')!.available).toBe(true);
  });

  it('keeps one entry per name, and every label distinct, so the menu loses nothing', () => {
    const menu = sampleMenu(SINGLE, ['building', 'Plan.ifc']);
    expect(new Set(menu.map((e) => e.value)).size).toBe(menu.length);
    const opts = menuOptions(menu);
    expect(Object.keys(opts).length).toBe(menu.length);
    expect(opts['FZK-Haus']).toBe('fzk-haus');
  });
});

describe('sample projects: the embedded IFC', () => {
  it('inflates a gzip-compressed sample back to the same bytes', async () => {
    const raw = new TextEncoder().encode('ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n'.repeat(50));
    const back = new Uint8Array(await inflateEmbedded(toBase64(await gzip(raw))));
    expect(back.length).toBe(raw.length);
    expect(back.every((b, i) => b === raw[i])).toBe(true);
  });

  it('the process-plant IFC embeds in well under the glb (about 4 MB), so the single file stays small', async () => {
    const ifc = new Uint8Array(readFileSync(fileURLToPath(new URL('../../models/Process-Plant.ifc', import.meta.url))));
    expect((await gzip(ifc)).length).toBeLessThan(1024 * 1024);
  });
});
