// File selection rules of the "Open model" plugin (pure functions, no DOM).
import { describe, expect, it } from 'vitest';
import { LARGE_INPUT_BYTES, modelNameFor, planOpen, progressText } from '../src/plugins/fileLoader';

const f = (name: string, size = 1000) => ({ name, size });

describe('planOpen', () => {
  it('one ifc file', () => {
    const p = planOpen([f('Building-Structural.ifc')]);
    expect(p).toMatchObject({ kind: 'ifc', name: 'file:Building-Structural.ifc' });
  });

  it('several ifc files federate into one model named after the first', () => {
    const p = planOpen([f('a.ifc'), f('b.IFC'), f('c.ifczip')]);
    expect(p).toMatchObject({ kind: 'ifc', name: 'file:a.ifc +2 more' });
    if (p.kind === 'ifc') expect(p.ifc.map((x) => x.name)).toEqual(['a.ifc', 'b.IFC', 'c.ifczip']);
  });

  it('a glb picks up a same-basename json first, then any other json', () => {
    const p = planOpen([f('other.json'), f('house.json'), f('house.glb')]);
    expect(p.kind).toBe('glb');
    if (p.kind === 'glb') {
      expect(p.glb.name).toBe('house.glb');
      expect(p.sidecars.map((s) => s.name)).toEqual(['house.json', 'other.json']);
      expect(p.name).toBe('file:house.glb');
    }
  });

  it('mixed IFC and glb is an error with a clear message', () => {
    const p = planOpen([f('a.ifc'), f('b.glb')]);
    expect(p).toEqual({ kind: 'error', message: 'Cannot open IFC and glb files together; drop either IFC files or one glb' });
  });

  it('two glb files are an error', () => {
    expect(planOpen([f('a.glb'), f('b.glb')])).toMatchObject({ kind: 'error', message: expect.stringContaining('one glb file at a time') });
  });

  it('unsupported, json-only, empty and missing selections give a one-line message', () => {
    expect(planOpen([f('notes.txt')])).toEqual({ kind: 'error', message: 'Unsupported file type: notes.txt. Open .ifc, .ifczip or .glb files' });
    expect(planOpen([f('model.gltf'), f('x.obj')])).toMatchObject({ kind: 'error', message: expect.stringContaining('model.gltf, x.obj') });
    expect(planOpen([f('side.json')])).toMatchObject({ kind: 'error', message: expect.stringContaining('goes with its .glb') });
    expect(planOpen([f('empty.ifc', 0)])).toEqual({ kind: 'error', message: 'empty.ifc is empty' });
    expect(planOpen([])).toMatchObject({ kind: 'error' });
    for (const p of [planOpen([f('notes.txt')]), planOpen([f('a.ifc'), f('b.glb')])]) {
      if (p.kind === 'error') expect(p.message).not.toContain('\n');
    }
  });

  it('ignores extra unsupported files next to supported ones and reports them', () => {
    const p = planOpen([f('a.ifc'), f('readme.txt')]);
    expect(p).toMatchObject({ kind: 'ifc', ignored: ['readme.txt'] });
  });

  it('adds up the size so the 100 MB warning can fire', () => {
    const p = planOpen([f('a.ifc', 60 * 1048576), f('b.ifc', 50 * 1048576)]);
    expect(p.kind === 'ifc' && p.totalBytes > LARGE_INPUT_BYTES).toBe(true);
  });
});

describe('names and status text', () => {
  it('modelNameFor', () => {
    expect(modelNameFor(['x.ifc'])).toBe('file:x.ifc');
    expect(modelNameFor(['x.ifc', 'y.ifc'])).toBe('file:x.ifc +1 more');
  });

  it('progress strings', () => {
    expect(progressText({ phase: 'read', file: 'Building-Structural.ifc', bytes: 185185 })).toBe('Reading Building-Structural.ifc, 0.2 MB');
    expect(progressText({ phase: 'meshing', file: 'a.ifc', done: 120, total: 480 })).toBe('Meshing 120 of 480');
    expect(progressText({ phase: 'meshing', file: 'a.ifc', done: 1, total: 4 }, 3)).toBe('Meshing 1 of 4 (a.ifc)');
    expect(progressText({ phase: 'build' })).toBe('Building model');
  });
});
