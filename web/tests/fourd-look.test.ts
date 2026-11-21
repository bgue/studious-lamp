import { describe, expect, it } from 'vitest';
import { AHEAD_RGB, BEHIND_RGB, CRITICAL_RGB, GHOST_ALPHA, TINT_ACTIVE, fadeMs, hex, lookFor, toHex, tradeColour } from '../src/anim/fourd/look';
import type { LookInput } from '../src/anim/fourd/look';
import { DEFAULT_STYLE } from '../src/schedule/types';

const DAY = 86400000;
const base = (o: Partial<LookInput>): LookInput => ({ state: 'active', from: 0, to: 10 * DAY, t: 5 * DAY, style: { unbuilt: 'hidden', colours: {} }, secPerMs: 0, ...o });

describe('fade length', () => {
  it('is 10 % of the interval, but at most 0.6 s of video', () => {
    expect(fadeMs(0, 100 * DAY, 0)).toBe(10 * DAY);
    // 1 video second per day: 0.6 s is 0.6 days, shorter than 10 % of a 100 day interval
    expect(fadeMs(0, 100 * DAY, 1 / DAY)).toBeCloseTo(0.6 * DAY, 3);
    // a short interval: 10 % of it wins
    expect(fadeMs(0, 2 * DAY, 1 / (100 * DAY))).toBeCloseTo(0.2 * DAY, 3);
    expect(fadeMs(5, 5, 0)).toBe(1);
  });
});

describe('look per state', () => {
  it('future: hidden, or a faint ghost in a ghost view', () => {
    expect(lookFor(base({ state: 'future' })).hidden).toBe(true);
    const g = lookFor(base({ state: 'future', style: { unbuilt: 'ghost', colours: {} } }));
    expect(g.hidden).toBe(false);
    expect(g.alpha).toBe(GHOST_ALPHA);
  });

  it('active: fades in over the first 10 % of its interval, tinted in the trade colour with edge glow', () => {
    const task = { trade: 'Structure', critical: false };
    const start = lookFor(base({ t: 0, task }));
    expect(start.alpha).toBeLessThan(0.1);
    expect(start.until).toBe(1 * DAY);
    const mid = lookFor(base({ t: 0.5 * DAY, task }));
    expect(mid.alpha).toBeCloseTo(0.5, 6);
    const full = lookFor(base({ t: 2 * DAY, task }));
    expect(full.alpha).toBe(1);
    expect(full.tint).toEqual(hex(tradeColour('Structure')));
    expect(full.tintAmount).toBe(TINT_ACTIVE);
    expect(full.glow).toBe(1);
    expect(full.hidden).toBe(false);
    expect(full.until).toBeLessThan(2 * DAY); // static from here on: nothing to re-evaluate
  });

  it('active in a critical task: a red edge glow', () => {
    expect(lookFor(base({ t: 2 * DAY, task: { trade: 'Structure', critical: true } })).glow).toBe(2);
    expect(toHex(CRITICAL_RGB)).toBe('#ff2d2d');
  });

  it('uses style.colours over the default palette', () => {
    const l = lookFor(base({ t: 2 * DAY, task: { trade: 'Structure', critical: false }, style: { unbuilt: 'hidden', colours: { Structure: '#112233' } } }));
    expect(toHex(l.tint!)).toBe('#112233');
  });

  it('complete: no tint, no glow, opaque', () => {
    const l = lookFor(base({ state: 'complete' }));
    expect(l).toMatchObject({ hidden: false, alpha: 1, tint: null, tintAmount: 0, glow: 0 });
  });

  it('existing: visible and slightly desaturated', () => {
    const l = lookFor(base({ state: 'existing', from: -Infinity, to: Infinity }));
    expect(l.hidden).toBe(false);
    expect(l.tint).not.toBeNull();
    expect(l.tintAmount).toBeGreaterThan(0);
    expect(l.tintAmount).toBeLessThan(0.4);
  });

  it('removed: fades out red, then hidden', () => {
    const a = lookFor(base({ state: 'removed', t: 0.5 * DAY }));
    expect(a.hidden).toBe(false);
    expect(a.alpha).toBeCloseTo(0.5, 6);
    expect(a.tint![0]).toBeGreaterThan(a.tint![2]);
    expect(lookFor(base({ state: 'removed', t: 1 * DAY })).hidden).toBe(true);
  });

  it('behind: a red tint; ahead: a green flash that fades', () => {
    const b = lookFor(base({ state: 'behind' }));
    expect(b.tint).toEqual(BEHIND_RGB);
    expect(b.alpha).toBe(1);
    const f0 = lookFor(base({ state: 'ahead', t: 0 }));
    expect(f0.tint).toEqual(AHEAD_RGB);
    const f1 = lookFor(base({ state: 'ahead', t: 0.5 * DAY }));
    expect(f1.tintAmount).toBeLessThan(f0.tintAmount);
    expect(lookFor(base({ state: 'ahead', t: 1 * DAY })).tintAmount).toBe(0);
  });

  it('is a pure function of its input', () => {
    const i = base({ t: 0.3 * DAY, task: { trade: 'Services', critical: false } });
    expect(lookFor(i)).toEqual(lookFor({ ...i }));
  });
});

describe('trade colours', () => {
  it('maps trade names to a stable palette and falls back to a hash', () => {
    expect(tradeColour('Structure')).toBe(tradeColour('structure works'));
    expect(tradeColour('Plumbing')).not.toBe(tradeColour('Structure'));
    expect(tradeColour('Zzz')).toBe(tradeColour('Zzz'));
    expect(tradeColour(undefined)).toMatch(/^#[0-9a-f]{6}$/);
    expect(tradeColour('x', DEFAULT_STYLE.colours)).toMatch(/^#/);
  });
});
