import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import {
  FlyPlayer,
  catmullRom,
  parseKeyframe,
  parseKeyframes,
  pickRecorderMime,
  sampleSpline,
  sampleSplineAt,
  serializeKeyframes,
} from '../src/cinematic/flythrough';
import type { Keyframe } from '../src/cinematic/flythrough';

const v = (x: number, y: number, z: number): Vector3 => new Vector3(x, y, z);
const close = (a: Vector3, b: Vector3, eps = 1e-9): void => {
  expect(a.distanceTo(b)).toBeLessThan(eps);
};

describe('Catmull-Rom', () => {
  it('hits p1 at t=0 and p2 at t=1', () => {
    const p = [v(0, 0, 0), v(1, 2, 3), v(4, 1, -2), v(6, 6, 6)] as const;
    close(catmullRom(p[0], p[1], p[2], p[3], 0), p[1]);
    close(catmullRom(p[0], p[1], p[2], p[3], 1), p[2]);
  });
  it('reproduces a straight uniform line exactly (linear precision)', () => {
    const a = catmullRom(v(0, 0, 0), v(1, 0, 0), v(2, 0, 0), v(3, 0, 0), 0.5);
    close(a, v(1.5, 0, 0));
  });
});

describe('sampleSpline over the whole path', () => {
  const three = [v(0, 0, 0), v(2, 5, 1), v(6, 1, -3)];
  const five = [v(0, 0, 0), v(1, 1, 0), v(3, 0, 2), v(4, 4, 4), v(9, 1, 1)];

  it('t = 0 is the first keyframe and t = 1 the last', () => {
    for (const pts of [three, five]) {
      close(sampleSpline(pts, 0), pts[0]!);
      close(sampleSpline(pts, 1), pts[pts.length - 1]!);
    }
  });
  it('t = 0.5 hits the middle keyframe (odd counts)', () => {
    close(sampleSpline(three, 0.5), three[1]!);
    close(sampleSpline(five, 0.5), five[2]!);
  });
  it('every keyframe is hit at its own parameter', () => {
    five.forEach((p, i) => close(sampleSpline(five, i / (five.length - 1)), p));
    five.forEach((p, i) => close(sampleSplineAt(five, i), p));
  });
  it('clamps t outside 0..1 and handles 0, 1 and 2 points', () => {
    close(sampleSpline(three, -1), three[0]!);
    close(sampleSpline(three, 2), three[2]!);
    expect(sampleSpline([], 0.5).toArray()).toEqual([0, 0, 0]);
    close(sampleSpline([v(1, 2, 3)], 0.7), v(1, 2, 3));
    close(sampleSpline([v(0, 0, 0), v(4, 0, 0)], 0.5), v(2, 0, 0));
  });
  it('is continuous across a keyframe', () => {
    const e = 1e-6;
    const before = sampleSplineAt(five, 2 - e);
    const after = sampleSplineAt(five, 2 + e);
    expect(before.distanceTo(after)).toBeLessThan(1e-4);
  });
});

describe('FlyPlayer', () => {
  const keys = [
    { position: [0, 0, 0] as [number, number, number], target: [0, 0, -5] as [number, number, number] },
    { position: [4, 0, 0] as [number, number, number], target: [4, 0, -5] as [number, number, number] },
    { position: [4, 4, 0] as [number, number, number], target: [4, 4, -5] as [number, number, number] },
  ];
  it('reaches keyframes in order, one per segment, and finishes at the last pose', () => {
    const p = new FlyPlayer(keys, 1000);
    expect(p.durationMs).toBe(2000);
    const pos = new Vector3();
    const tgt = new Vector3();
    let s = p.sample(5000, pos, tgt); // first call starts the clock
    expect(s.index).toBe(0);
    expect(p.reached(s)).toEqual([0]);
    expect(pos.toArray()).toEqual([0, 0, 0]);
    s = p.sample(5500, pos, tgt);
    expect(p.reached(s)).toEqual([]);
    expect(s.done).toBe(false);
    s = p.sample(6000, pos, tgt);
    expect(p.reached(s)).toEqual([1]);
    close(pos, v(4, 0, 0));
    close(tgt, v(4, 0, -5));
    s = p.sample(7500, pos, tgt);
    expect(s.done).toBe(true);
    expect(p.reached(s)).toEqual([2]);
    close(pos, v(4, 4, 0));
  });
  it('a long frame that skips a keyframe still reports it', () => {
    const p = new FlyPlayer(keys, 1000);
    const pos = new Vector3();
    const tgt = new Vector3();
    p.sample(0, pos, tgt); // starts the clock, but reached() is not called for it
    const s = p.sample(2500, pos, tgt);
    expect(p.reached(s)).toEqual([0, 1, 2]);
  });
  it('a single keyframe is done immediately', () => {
    const p = new FlyPlayer([keys[0]!], 1000);
    const s = p.sample(0, new Vector3(), new Vector3());
    expect(s.done).toBe(true);
    expect(p.reached(s)).toEqual([0]);
  });
});

describe('keyframe persistence', () => {
  const k: Keyframe = {
    position: [1, 2, 3],
    target: [4, 5, 6],
    selection: ['abc', 'def'],
    toggles: { bloom: true, ao: false, sweep: true },
    name: 'One',
  };
  it('round-trips through JSON', () => {
    const text = serializeKeyframes('building', [k, { ...k, selection: [], name: undefined }], 3);
    const back = parseKeyframes(text);
    expect(back).not.toBeNull();
    expect(back!.length).toBe(2);
    expect(back![0]).toEqual(k);
    expect(back![1]!.selection).toEqual([]);
    expect(JSON.parse(text).schema).toBe('xray-flythrough/1');
  });
  it('accepts a bare array, drops invalid entries, rejects garbage', () => {
    expect(parseKeyframes(JSON.stringify([k, { position: [1, 2], target: [0, 0, 0] }, 7, null]))!.length).toBe(1);
    expect(parseKeyframes('not json')).toBeNull();
    expect(parseKeyframes('{"a":1}')).toBeNull();
    expect(parseKeyframes(null)).toBeNull();
    expect(parseKeyframe({ position: [1, 2, NaN], target: [0, 0, 0] })).toBeNull();
  });
  it('ignores non-boolean toggle values and non-string ids', () => {
    const p = parseKeyframe({ position: [0, 0, 0], target: [0, 0, 1], selection: ['a', 3], toggles: { bloom: 'yes', ao: true } })!;
    expect(p.selection).toEqual(['a']);
    expect(p.toggles).toEqual({ ao: true });
  });
});

describe('recorder mime choice', () => {
  it('prefers vp9, then vp8, then plain webm', () => {
    expect(pickRecorderMime(() => true)).toBe('video/webm;codecs=vp9');
    expect(pickRecorderMime((t) => t !== 'video/webm;codecs=vp9')).toBe('video/webm;codecs=vp8');
    expect(pickRecorderMime((t) => t === 'video/webm')).toBe('video/webm');
    expect(pickRecorderMime(() => false)).toBeNull();
    expect(pickRecorderMime(undefined)).toBeNull();
  });
});
