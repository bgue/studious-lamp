import { describe, expect, it } from 'vitest';
import { applySim, composeSim, denominatorOf, fitSimilarity, fromScale, invertSim, metresPerPoint, modelToSheet, placementStatus, sanitizePlacement, sheetToModel } from '../src/sheets/placement';
import type { PointPair, SheetPlacement, Similarity } from '../src/sheets/placement';

const truth: Similarity = { scale: 0.0352778, rotation: (20 * Math.PI) / 180, tx: 105.25, ty: -33.5 };
const pair = (s: [number, number]): PointPair => ({ sheet: s, model: applySim(truth, s) });
const near = (a: number, b: number, tol = 1e-9): void => expect(Math.abs(a - b)).toBeLessThanOrEqual(tol);

describe('similarity from point pairs', () => {
  it('two pairs give the exact transform', () => {
    const r = fitSimilarity([pair([80, 150]), pair([600, 520])]);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    near(r.transform.scale, truth.scale, 1e-12);
    near(r.transform.rotation, truth.rotation, 1e-12);
    near(r.transform.tx, truth.tx, 1e-8);
    near(r.transform.ty, truth.ty, 1e-8);
    expect(r.residual).toBeUndefined(); // two pairs leave nothing over
  });

  it('three exact pairs fit with a residual of zero', () => {
    const r = fitSimilarity([pair([80, 150]), pair([600, 520]), pair([100, 500])]);
    expect(r.ok && r.residual).toBeLessThan(1e-9);
  });

  it('least squares over noisy pairs finds the transform and reports the misfit in metres', () => {
    const noise: Array<[number, number]> = [[0.004, -0.002], [-0.003, 0.003], [0.002, 0.004], [-0.004, -0.003]];
    const pts: Array<[number, number]> = [[80, 150], [600, 520], [100, 500], [590, 160]];
    const pairs = pts.map((p, i) => { const q = pair(p); return { sheet: p, model: [q.model[0] + noise[i]![0], q.model[1] + noise[i]![1]] as [number, number] }; });
    const r = fitSimilarity(pairs);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    near(r.transform.scale / truth.scale, 1, 0.01);
    near(r.transform.rotation, truth.rotation, 0.01);
    expect(r.residual!).toBeGreaterThan(0.001);
    expect(r.residual!).toBeLessThan(0.006);
    expect(r.misfits).toHaveLength(4);
    // The residual is the root mean square of the misfits.
    near(r.residual!, Math.sqrt(r.misfits.reduce((a, b) => a + b * b, 0) / 4), 1e-12);
  });

  it('never mirrors: a mirrored pair set is fitted as a rotation, with a large misfit', () => {
    const mirrored: PointPair[] = [[0, 0], [100, 0], [0, 100]].map((p) => ({ sheet: p as [number, number], model: [p[0]! * 0.05, -p[1]! * 0.05] as [number, number] }));
    const r = fitSimilarity(mirrored);
    expect(r.ok && r.residual!).toBeGreaterThan(0.5);
  });

  it('refuses coincident points and too few pairs', () => {
    expect(fitSimilarity([pair([1, 1])]).ok).toBe(false);
    expect(fitSimilarity([pair([1, 1]), pair([1, 1])]).ok).toBe(false);
    expect(fitSimilarity([{ sheet: [0, 0], model: [1, 1] }, { sheet: [10, 0], model: [1, 1] }]).ok).toBe(false);
  });

  it('inverts and composes', () => {
    const p: [number, number] = [321.5, 77.25];
    const q = applySim(truth, p);
    const back = applySim(invertSim(truth), q);
    near(back[0], p[0], 1e-9);
    near(back[1], p[1], 1e-9);
    const t2: Similarity = { scale: 2, rotation: 0.3, tx: 4, ty: 5 };
    const c = composeSim(t2, truth);
    const direct = applySim(t2, applySim(truth, p));
    const via = applySim(c, p);
    near(via[0], direct[0], 1e-9);
    near(via[1], direct[1], 1e-9);
  });
});

describe('drawing scale, rotation and one pair', () => {
  it('1:100 is 35.28 mm of model per point', () => {
    near(metresPerPoint(100), 0.03527778, 1e-8);
    near(denominatorOf({ scale: metresPerPoint(50), rotation: 0, tx: 0, ty: 0 }), 50, 1e-9);
  });

  it('gives the same transform as two exact pairs', () => {
    const t: Similarity = { scale: metresPerPoint(100), rotation: (-35 * Math.PI) / 180, tx: 12, ty: 7 };
    const p: [number, number] = [200, 300];
    const r = fromScale(100, -35, { sheet: p, model: applySim(t, p) });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    near(r.transform.scale, t.scale, 1e-12);
    near(r.transform.tx, t.tx, 1e-9);
    near(r.transform.ty, t.ty, 1e-9);
    const q = applySim(r.transform, [600, 100]);
    const e = applySim(t, [600, 100]);
    near(q[0], e[0], 1e-9);
    near(q[1], e[1], 1e-9);
  });

  it('refuses a scale that is not a positive number', () => {
    expect(fromScale(0, 0, { sheet: [0, 0], model: [0, 0] }).ok).toBe(false);
    expect(fromScale(NaN, 0, { sheet: [0, 0], model: [0, 0] }).ok).toBe(false);
  });
});

describe('placing points', () => {
  const plan: SheetPlacement = { kind: 'manual', level: { elevation: 2.7 }, transform: truth, source: '2 points' };
  it('plan sheets lie in the horizontal plane at the level', () => {
    const p = sheetToModel(plan, [10, 20]);
    expect(p[2]).toBe(2.7);
    const xy = modelToSheet(plan, [p[0], p[1]]);
    near(xy[0], 10, 1e-9);
    near(xy[1], 20, 1e-9);
  });

  it('a vertical plane carries the sheet x along the plane and y up', () => {
    const el: SheetPlacement = { ...plan, plane: { normal: [0, -1, 0], point: [5, 10, 1] }, transform: { scale: 1, rotation: 0, tx: 0, ty: 0 } };
    const p = sheetToModel(el, [2, 3]);
    // normal -Y: the in-plane axis is (+1, 0): x grows east
    expect(p).toEqual([7, 10, 4]);
  });
});

describe('status and reading back', () => {
  it('says what is there', () => {
    expect(placementStatus(undefined)).toBe('Not placed');
    expect(placementStatus({ kind: 'geo', level: { elevation: 0 }, transform: truth, source: 'geo-PDF' })).toBe('Placed (geo)');
    expect(placementStatus({ kind: 'manual', level: { elevation: 0 }, transform: truth, source: 'x', residual: 0.0042 })).toBe('Placed (manual, ±4.2 mm)');
    expect(placementStatus({ kind: 'manual', level: { elevation: 0 }, transform: truth, source: 'x', residual: 0.0123 })).toBe('Placed (manual, ±12 mm)');
    expect(placementStatus({ kind: 'manual', level: { elevation: 0 }, transform: truth, source: 'x', drawingScale: 100 })).toBe('Placed (manual, scale 1:100)');
  });

  it('a stored placement is cleaned; junk is dropped', () => {
    const p: SheetPlacement = { kind: 'manual', level: { storeyGuid: 'abc', name: 'EG', elevation: 0 }, transform: truth, source: 'manual', residual: 0.002, pairs: [pair([1, 2]), pair([3, 4])] };
    const back = sanitizePlacement(JSON.parse(JSON.stringify(p)));
    expect(back).toEqual(p);
    expect(sanitizePlacement({ kind: 'geo', level: { elevation: 'x' }, transform: truth })).toBeUndefined();
    expect(sanitizePlacement({ kind: 'manual', level: { elevation: 0 }, transform: { scale: -1, rotation: 0, tx: 0, ty: 0 } })).toBeUndefined();
    expect(sanitizePlacement(null)).toBeUndefined();
    expect(sanitizePlacement({ kind: 'nope' })).toBeUndefined();
  });
});
