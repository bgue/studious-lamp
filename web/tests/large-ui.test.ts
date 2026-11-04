// Pure parts of the large-model UI in plugins/fileLoader.ts: status texts for the new import phases, the Model stats line
// and the stage list of the `largeModel` drawer.
import { describe, expect, it } from 'vitest';
import { formatBytesMb, progressText, stageList, statsLine } from '../src/plugins/fileLoader';
import type { ModelInfo } from '../src/plugins/fileLoader';

describe('progress text', () => {
  it('names every stage with element counts', () => {
    expect(progressText({ phase: 'meshing', file: 'a.ifc', done: 120, total: 480 })).toBe('Meshing 120 of 480');
    expect(progressText({ phase: 'merge', done: 5000, total: 20000 })).toBe('Merging 5000 of 20000 elements');
    expect(progressText({ phase: 'edges', done: 100, total: 200 })).toBe('Edges 100 of 200 elements');
    expect(progressText({ phase: 'edges', done: 0, total: 60000, skipped: 'auto' })).toBe('Edges skipped (auto: over 50,000 elements)');
    expect(progressText({ phase: 'edges', done: 0, total: 10, skipped: 'none' })).toBe('Edges skipped (edges: none)');
    expect(progressText({ phase: 'bvh', percent: 45, triangles: 1_760_000 })).toBe('BVH 45% (1.76 M triangles)');
    expect(progressText({ phase: 'transfer' })).toBe('Transferring geometry');
    expect(progressText({ phase: 'upload', elements: 20000 })).toBe('Uploading 20000 elements');
    expect(progressText({ phase: 'build' })).toBe('Building model');
  });
});

describe('model stats', () => {
  const info: ModelInfo = {
    modelName: 'file:big.ifc', elements: 20000, triangles: 352000, vertices: 700000, edgeSegments: 324000, bufferBytes: 58 * 1048576,
    loadSeconds: 9.46, edgesSkipped: false, bvh: 'worker', options: { edges: 'auto', properties: 'common' }, stages: [],
  };

  it('formats the one-line readout', () => {
    expect(formatBytesMb(1572864)).toBe('1.5 MB');
    expect(statsLine(info)).toBe('20,000 elements, 352,000 triangles, 58.0 MB buffers, 9.5 s');
    expect(statsLine({ ...info, loadSeconds: null })).toBe('20,000 elements, 352,000 triangles, 58.0 MB buffers, load time n/a');
  });

  it('lists the stages of a load in pipeline order and drops the ones that did not run', () => {
    const rows = stageList({ readMs: 1200, openMs: 900, meshMs: 3000, relationsMs: 1800, releaseMs: 0, mergeMs: 100, edgesMs: 0, bvhMs: 600, handoffMs: 80, uploadMs: 700, totalMs: 9400 });
    expect(rows.map(([k]) => k)).toEqual([
      'Reading files', 'Opening IFC', 'Meshing', 'Relations and properties', 'Merging', 'BVH (worker)', 'Transfer and wrap', 'GPU upload to first frames', 'Total',
    ]);
    expect(rows[rows.length - 1]).toEqual(['Total', 9400]);
    expect(stageList({})).toEqual([]);
  });
});
