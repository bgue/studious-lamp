// The ground-truth file of the process-plant sample (models/Process-Plant.truth.json, written by tools/make_process_plant_ifc.py):
// it parses, every code is in the default schema, it covers every element of the shipped sidecar, the IFC carries no trace of it,
// and the generator reproduces the committed IFC and truth file byte for byte (and fails loudly if a self-check breaks).

import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = (rel: string): string => fileURLToPath(new URL(rel, import.meta.url));
const read = (rel: string): string => readFileSync(here(rel), 'utf8');

interface TruthEntry { name: string; ifcClass: string; discipline: string; subDiscipline: string; division: string; alt?: { subDiscipline?: string[]; division?: string[] } }
interface Truth { format: string; model: string; generator: string; schema: string; convention: string; elements: Record<string, TruthEntry> }

const truth = JSON.parse(read('../../models/Process-Plant.truth.json')) as Truth;
const schema = JSON.parse(read('../public/classification/default-schema.json')) as {
  disciplines: Array<{ code: string; subDisciplines: Array<{ code: string }> }>;
  masterformat: { divisions: Array<{ division: string }> };
};
const sidecar = JSON.parse(read('../public/models/process-plant.json')) as { elements: Array<{ globalId: string; name: string; ifcClass: string }> };

describe('process-plant ground truth', () => {
  it('has the documented header and a convention text', () => {
    expect(truth.format).toBe('xray-truth/1');
    expect(truth.model).toBe('process-plant');
    expect(truth.generator).toBe('tools/make_process_plant_ifc.py --seed 1');
    expect(truth.schema).toBe('local:xray-throughline-aligned-default@1.0.0');
    expect(truth.convention.length).toBeGreaterThan(200);
    expect(Object.keys(truth).sort()).toEqual(['convention', 'elements', 'format', 'generator', 'model', 'schema']);
  });

  it('uses only codes of the default schema, with the sub-discipline inside its discipline', () => {
    const subs = new Map(schema.disciplines.map((d) => [d.code, new Set(d.subDisciplines.map((s) => s.code))]));
    const divisions = new Set(schema.masterformat.divisions.map((d) => d.division));
    for (const [gid, e] of Object.entries(truth.elements)) {
      const where = `${gid} ${e.name}`;
      expect(subs.has(e.discipline), `${where}: discipline ${e.discipline}`).toBe(true);
      expect(subs.get(e.discipline)!.has(e.subDiscipline), `${where}: ${e.discipline}/${e.subDiscipline}`).toBe(true);
      expect(divisions.has(e.division), `${where}: division ${e.division}`).toBe(true);
      for (const s of e.alt?.subDiscipline ?? []) expect(subs.get(e.discipline)!.has(s), `${where}: alt sub ${s}`).toBe(true);
      for (const d of e.alt?.division ?? []) expect(divisions.has(d), `${where}: alt division ${d}`).toBe(true);
      if (e.alt) {
        expect(Object.keys(e.alt).every((k) => k === 'subDiscipline' || k === 'division'), `${where}: alt keys`).toBe(true);
        expect((e.alt.subDiscipline?.length ?? 0) + (e.alt.division?.length ?? 0), `${where}: empty alt`).toBeGreaterThan(0);
      }
    }
  });

  it('covers every element of the sidecar, and nothing else, with the same name and class', () => {
    const ids = new Set(sidecar.elements.map((e) => e.globalId));
    expect(ids.size).toBe(sidecar.elements.length);
    expect(Object.keys(truth.elements).length).toBe(ids.size);
    for (const e of sidecar.elements) {
      const t = truth.elements[e.globalId];
      expect(t, `no truth for ${e.name}`).toBeDefined();
      expect(t!.name).toBe(e.name);
      expect(t!.ifcClass).toBe(e.ifcClass);
    }
  });

  it('labels the main equipment and the piping the way the design intends', () => {
    const by = (name: string): TruthEntry => Object.values(truth.elements).find((e) => e.name === name)!;
    expect(by('Pump P-101A')).toMatchObject({ discipline: 'PIP', subDiscipline: 'PMP', division: '43' });
    expect(by('Heat exchanger E-201')).toMatchObject({ discipline: 'PIP', subDiscipline: 'HTX', division: '42' });
    expect(by('Vessel V-301')).toMatchObject({ discipline: 'PIP', subDiscipline: 'VES', division: '43' });
    expect(by('Pipe 150-PR-1101-A1A spool 02')).toMatchObject({ discipline: 'PIP', subDiscipline: 'PRC', division: '40' });
    expect(by('Pipe 150-ST-1201-A1A spool 02')).toMatchObject({ discipline: 'PIP', subDiscipline: 'UTL', division: '40' });
    expect(by('Rack column RC-01A')).toMatchObject({ discipline: 'STR', subDiscipline: 'COL' });
    expect(by('Control building wall E')).toMatchObject({ discipline: 'STR', subDiscipline: 'WLS' });
    expect(by('Door D-02')).toMatchObject({ discipline: 'ARC', subDiscipline: 'DOR', division: '08' });
    const disciplines = new Set(Object.values(truth.elements).map((e) => e.discipline));
    expect([...disciplines].sort()).toEqual(['ARC', 'CIV', 'ELE', 'GEN', 'INS', 'PIP', 'STR']);
  });

  it('is not in the IFC (no pset, no name hint): the IFC is the classifier input', () => {
    const ifc = read('../../models/Process-Plant.ifc');
    expect(/truth|xray-truth|ground.?truth/i.test(ifc)).toBe(false);
    const gids = Object.keys(truth.elements);
    expect(gids.every((g) => ifc.includes(`'${g}'`))).toBe(true);
  });
});

describe('process-plant generator', () => {
  const python = spawnSync('python3', ['-c', 'import ifcopenshell, numpy'], { encoding: 'utf8' });
  const ready = python.status === 0;

  it.skipIf(!ready)('reproduces the committed IFC and truth file byte for byte, and its self-checks pass', () => {
    const dir = mkdtempSync(join(tmpdir(), 'pp-gen-'));
    try {
      const run = (name: string) => {
        const out = join(dir, `${name}.ifc`);
        const r = spawnSync('python3', [here('../../tools/make_process_plant_ifc.py'), '-o', out, '--seed', '1'], { encoding: 'utf8' });
        expect(r.status, r.stderr).toBe(0);
        expect(r.stderr).toMatch(/connectivity: 20 runs/);
        expect(r.stderr).toMatch(/0 overlaps/);
        return { ifc: readFileSync(out, 'utf8'), truth: readFileSync(join(dir, `${name}.truth.json`), 'utf8') };
      };
      const a = run('a');
      const b = run('b');
      expect(a.ifc).toBe(b.ifc);
      expect(a.truth).toBe(b.truth);
      expect(a.ifc).toBe(read('../../models/Process-Plant.ifc'));
      expect(a.truth).toBe(read('../../models/Process-Plant.truth.json'));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 60000);
});
