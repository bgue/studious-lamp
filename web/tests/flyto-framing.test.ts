import { describe, expect, it, afterEach } from 'vitest';
import { Box3, Vector3 } from 'three';
import { computeFlyView, DEFAULT_FRAMING, fitDistance, framing } from '../src/cinematic/flyto';
import { BLOOM_MAX, PULSE_LOW, PULSE_PERIOD_MS, pulseFactor } from '../src/plugins/cinematic';
import { DEFAULT_BLOOM } from '../src/cinematic/bloom';

const cam = { position: new Vector3(10, 10, 10), target: new Vector3(0, 0, 0), fovDeg: 50, aspect: 1.5 };
const cube = (s: number): Box3 => new Box3(new Vector3(-s / 2, -s / 2, -s / 2), new Vector3(s / 2, s / 2, s / 2));
const dist = (box: Box3, opts = {}): number => { const v = computeFlyView(box, cam, opts); return v.position.distanceTo(v.target); };

describe('fly-to framing', () => {
  afterEach(() => Object.assign(framing, DEFAULT_FRAMING));

  it('frames further back than the old default and never nearer than the closest distance', () => {
    const big = cube(10);
    const r = Math.sqrt(3) * 5;
    expect(dist(big)).toBeCloseTo(fitDistance(r, 50, 1.5, DEFAULT_FRAMING.margin), 6);
    expect(dist(big)).toBeGreaterThan(fitDistance(r, 50, 1.5, 1.35));
    expect(dist(cube(0.2))).toBeCloseTo(DEFAULT_FRAMING.minDistance, 6); // a small part keeps its surroundings
  });

  it('follows the controls', () => {
    const big = cube(10);
    const before = dist(big);
    framing.margin = DEFAULT_FRAMING.margin * 2;
    expect(dist(big)).toBeCloseTo(before * 2, 6);
    framing.minDistance = 0;
    const r = Math.sqrt(3) * 0.1;
    expect(dist(cube(0.2))).toBeCloseTo(fitDistance(r, 50, 1.5, framing.margin), 6);
  });

  it('leaves an explicit margin alone (whole-model views, Tab) and applies no closest distance to it', () => {
    const r = Math.sqrt(3) * 0.1;
    expect(dist(cube(0.2), { margin: 1.2 })).toBeCloseTo(fitDistance(r, 50, 1.5, 1.2), 6);
    expect(dist(cube(0.2), { margin: 1.2, minDistance: 2 })).toBeCloseTo(2, 6);
  });
});

describe('focus halo and pulse', () => {
  it('caps the halo at a quarter of the old 0.7', () => {
    expect(BLOOM_MAX).toBeCloseTo(0.175, 6);
    expect(DEFAULT_BLOOM.strength).toBe(BLOOM_MAX);
  });
  it('pulses gently between PULSE_LOW and 1', () => {
    expect(pulseFactor(0)).toBeCloseTo(1, 6);
    expect(pulseFactor(PULSE_PERIOD_MS / 2)).toBeCloseTo(PULSE_LOW, 6);
    expect(pulseFactor(PULSE_PERIOD_MS)).toBeCloseTo(1, 6);
    for (let t = 0; t < PULSE_PERIOD_MS; t += 97) {
      const f = pulseFactor(t);
      expect(f).toBeGreaterThanOrEqual(PULSE_LOW - 1e-9);
      expect(f).toBeLessThanOrEqual(1 + 1e-9);
    }
  });
});
