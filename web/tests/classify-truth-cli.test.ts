// The truth-file checks of `npm run classify:truth` (tools/classify-truth.mjs) and their exit codes.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
// @ts-expect-error plain .mjs without types
import * as T from '../tools/classify-truth-lib.mjs';

const here = fileURLToPath(new URL('.', import.meta.url));
const schema = JSON.parse(readFileSync(resolve(here, '../public/classification/default-schema.json'), 'utf8'));
const ok = { discipline: 'PIP', subDiscipline: 'PRC', division: '40' };
const doc = (elements: Record<string, unknown>, format = 'xray-truth/1') => ({ format, elements });

describe('truth file validation', () => {
  it('accepts valid codes, alternates and cross-discipline pairs', () => {
    const r = T.validateTruth(doc({ a: ok, b: { ...ok, alt: { subDiscipline: ['UTL'], division: ['46'], discipline: ['MEC'], also: ['MEC/HYD'] } } }), schema);
    expect(r.errors).toEqual([]);
    expect(r.entries).toBe(2);
  });

  it('rejects unknown codes, a sub-discipline of another discipline, bad alternates, a wrong format and an empty file', () => {
    const bad = (e: Record<string, unknown>, format?: string) => T.validateTruth(doc(e, format), schema).errors;
    expect(bad({ a: { ...ok, discipline: 'XXX' } }).join()).toMatch(/unknown discipline/);
    expect(bad({ a: { ...ok, subDiscipline: 'HYD' } }).join()).toMatch(/unknown sub-discipline "HYD" for PIP/);
    expect(bad({ a: { ...ok, division: '99' } }).join()).toMatch(/unknown division/);
    expect(bad({ a: { ...ok, alt: { subDiscipline: ['HYD'] } } }).join()).toMatch(/alt sub-discipline/);
    expect(bad({ a: { ...ok, alt: { division: ['99'] } } }).join()).toMatch(/alt division/);
    expect(bad({ a: { ...ok, alt: { also: ['MEC/ZZZ'] } } }).join()).toMatch(/alt pair/);
    expect(bad({ a: ok }, 'other/1').join()).toMatch(/format/);
    expect(bad({}).join()).toMatch(/no entries/);
    expect(T.validateTruth({ format: 'xray-truth/1' }, schema).errors.join()).toMatch(/elements/);
    expect(T.validateTruth(null, schema).errors.length).toBe(1);
  });

  it('joins the truth with the model elements both ways', () => {
    const j = T.joinTruth(doc({ a: ok, b: ok }), ['a', 'c']);
    expect(j.withoutTruth).toEqual(['c']);
    expect(j.withoutElement).toEqual(['b']);
  });

  it('the shipped independent truth file is valid against the default schema', () => {
    const file = resolve(here, '../../models/independent/Water-Works.truth.json');
    const r = T.validateTruth(JSON.parse(readFileSync(file, 'utf8')), schema);
    expect(r.errors).toEqual([]);
    expect(r.entries).toBeGreaterThan(800);
  });
});

describe('classify:truth exit codes', () => {
  const cli = resolve(here, '../tools/classify-truth.mjs');
  const ifc = resolve(here, '../../models/independent/Water-Works.ifc');
  const dir = mkdtempSync(join(tmpdir(), 'classify-truth-test-'));
  const run = (args: string[]) => spawnSync('node', [cli, ...args], { encoding: 'utf8' });
  const write = (name: string, body: unknown) => { const f = join(dir, name); writeFileSync(f, typeof body === 'string' ? body : JSON.stringify(body)); return f; };

  it('64 without the required arguments, 2 for a truth file with unknown codes (before any conversion)', () => {
    expect(run([]).status).toBe(64);
    expect(run(['--ifc', ifc]).status).toBe(64);
    const r = run(['--ifc', ifc, '--truth', write('bad.json', doc({ a: { ...ok, discipline: 'XXX' } })), '--out', join(dir, 'o1')]);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/unknown discipline/);
    expect(run(['--ifc', ifc, '--truth', write('junk.json', 'not json'), '--out', join(dir, 'o2')]).status).toBe(2);
  });

  const hasIfcOpenShell = spawnSync('python3', ['-c', 'import ifcopenshell']).status === 0;
  it.skipIf(!hasIfcOpenShell)('2 for an element without a truth entry (after the conversion)', () => {
    const r = run(['--ifc', ifc, '--truth', write('one.json', doc({ onlyOne: ok })), '--out', join(dir, 'o3')]);
    expect(r.status).toBe(2);
    expect(r.stderr).toMatch(/elements without a truth entry/);
  }, 120_000);
});
