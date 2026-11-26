import { describe, expect, it } from 'vitest';
import { PerspectiveCamera } from 'three';
import type { HudFrame } from '../src/anim/hud';
import { ScoreHudLayer } from '../src/anim/hud/layer';
import type { HudSource } from '../src/anim/hud/layer';
import { makeProjector } from '../src/anim/hud/project';
import { DEFAULT_HUD, defaultHud, isDefaultHud, sanitizeHud } from '../src/anim/hud/settings';
import type { HudSettings } from '../src/anim/hud/settings';
import { buildDemoPlan } from '../src/anim/fourd/demoPlan';
import type { DemoModel } from '../src/anim/fourd/demoPlan';
import { fourdViewAt, isoDate, isoWeek, parsePlanDate, scheduleCueAt, viewAt } from '../src/anim/fourd/live';
import { clearPlans, registerPlan } from '../src/anim/fourd/plans';
import type { Score } from '../src/anim/score';
import { SCORE_SCHEMA } from '../src/anim/score';

class FakeCtx {
  font = '10px sans-serif';
  fillStyle: unknown = '';
  strokeStyle: unknown = '';
  lineWidth = 1;
  globalAlpha = 1;
  textBaseline = '';
  lineJoin = '';
  texts: Array<{ text: string; x: number; y: number; alpha: number }> = [];
  rects: Array<{ x: number; y: number; w: number; h: number; style: unknown }> = [];
  strokeStyles: unknown[] = [];
  lines: Array<[number, number]> = [];
  strokes = 0;
  arcs = 0;
  save(): void {}
  restore(): void {}
  scale(): void {}
  measureText(text: string): { width: number } {
    const m = /(\d+(?:\.\d+)?)px/.exec(this.font);
    return { width: text.length * (m ? Number(m[1]) : 10) * 0.55 };
  }
  fillText(text: string, x: number, y: number): void {
    this.texts.push({ text, x, y, alpha: this.globalAlpha });
  }
  fill(): void {}
  stroke(): void {
    this.strokes++;
    this.strokeStyles.push(this.strokeStyle);
  }
  fillRect(x: number, y: number, w: number, h: number): void {
    this.rects.push({ x, y, w, h, style: this.fillStyle });
  }
  beginPath(): void {}
  closePath(): void {}
  moveTo(x: number, y: number): void {
    this.lines.push([x, y]);
  }
  lineTo(x: number, y: number): void {
    this.lines.push([x, y]);
  }
  arcTo(): void {}
  arc(): void {
    this.arcs++;
  }
  has(text: string | RegExp): boolean {
    return this.texts.some((t) => (typeof text === 'string' ? t.text === text : text.test(t.text)));
  }
}

const classes = ['IfcSlab', 'IfcWall', 'IfcColumn', 'IfcDuctSegment', 'IfcCovering', 'IfcWindow'];
const model: DemoModel = {
  name: 'T',
  storeys: [{ id: 0, name: 'L1', elevation: 0 }, { id: 1, name: 'L2', elevation: 3 }, { id: 2, name: 'L3', elevation: 6 }],
  elements: Array.from({ length: 120 }, (_, i) => ({ globalId: `e${i}`, ifcClass: classes[i % classes.length]!, storey: i % 3, bounds: [i, 0, 0, i + 1, 1, 1] })),
};
const plan = buildDemoPlan(model, { seconds: 20 });
const score = (cueAt = 2, dur = 20, total = 30): Score => ({ schema: SCORE_SCHEMA, duration: total, cues: [{ at: cueAt, dur, kind: 'schedule4d', plan }] });

const source: HudSource = {
  elementIds: () => [],
  element: () => null,
  bounds: () => null,
  card: () => null,
  camera: () => ({ focus: [0, 0, -20], right: [1, 0, 0], distance: 20 }),
  northDeg: () => 0,
};
function frame(t: number, w = 900, h = 500, duration = 30): HudFrame {
  const cam = new PerspectiveCamera(50, w / h, 0.1, 1000);
  cam.updateMatrixWorld();
  return { t, duration, width: w, height: h, pixelRatio: 1, project: makeProjector(cam, w, h), recording: false };
}
function draw(sc: Score, t: number, st: Partial<HudSettings> = {}, w = 900, h = 500): { ctx: FakeCtx; layer: ScoreHudLayer } {
  const layer = new ScoreHudLayer(source, () => ({ ...DEFAULT_HUD, ...st }));
  layer.setScore(sc);
  const ctx = new FakeCtx();
  layer.draw(ctx as never, frame(t, w, h, sc.duration));
  return { ctx, layer };
}

describe('dates', () => {
  it('formats the plan date and the ISO week', () => {
    expect(isoDate(Date.UTC(2027, 2, 14, 8))).toBe('2027-03-14');
    expect(isoWeek(Date.UTC(2027, 0, 1))).toEqual({ week: 53, year: 2026 });
    expect(isoWeek(Date.UTC(2027, 0, 4))).toEqual({ week: 1, year: 2027 });
    expect(isoWeek(Date.UTC(2027, 2, 14))).toEqual({ week: 10, year: 2027 });
    expect(isoWeek(Date.UTC(2026, 11, 31))).toEqual({ week: 53, year: 2026 });
    expect(parsePlanDate('2027-03-14T08:00')).toBe(Date.UTC(2027, 2, 14, 8));
    expect(parsePlanDate('2027-03-14')).toBe(Date.UTC(2027, 2, 14));
    expect(Number.isNaN(parsePlanDate('soon'))).toBe(true);
  });
});

describe('the 4D view at a moment', () => {
  it('finds the running schedule4d cue and its plan (inline or by name)', () => {
    expect(scheduleCueAt(score(), 1)).toBeNull();
    expect(scheduleCueAt(score(), 2)!.plan).toBe(plan);
    expect(scheduleCueAt(score(), 22)).not.toBeNull();
    expect(scheduleCueAt(score(), 22.5)).toBeNull();
    clearPlans();
    const named: Score = { schema: SCORE_SCHEMA, duration: 10, cues: [{ at: 0, dur: 10, kind: 'schedule4d', plan: { name: 'p' } }] };
    expect(scheduleCueAt(named, 5)).toBeNull();
    registerPlan('p', plan);
    expect(scheduleCueAt(named, 5)!.plan).toBe(plan);
    clearPlans();
  });

  it('the date follows the time map, % complete rises, actual stops at the data date', () => {
    const a = fourdViewAt(score(), 2)!.view;
    const b = fourdViewAt(score(), 12)!.view;
    const c = fourdViewAt(score(), 22)!.view;
    expect(a.date < b.date && b.date < c.date).toBe(true);
    expect(a.plannedPct).toBe(0);
    expect(b.plannedPct).toBeGreaterThan(a.plannedPct);
    expect(c.plannedPct).toBeCloseTo(100, 0);
    expect(a.actualPct).toBeDefined();
    expect(c.actualPct).toBeUndefined();
    expect(a.week).toBeGreaterThan(0);
    expect(fourdViewAt(score(), 1)).toBeNull();
  });

  it('lists the current activities, the biggest first, at most 5, with trade colours', () => {
    let seen = 0;
    for (let p = 0; p <= 1; p += 0.05) {
      const v = viewAt(plan, p, 20);
      expect(v.activities.length).toBeLessThanOrEqual(5);
      for (let i = 1; i < v.activities.length; i++) expect(v.activities[i - 1]!.elements).toBeGreaterThanOrEqual(v.activities[i]!.elements);
      for (const r of v.activities) expect(r.colour).toMatch(/^#[0-9a-f]{6}$/);
      seen = Math.max(seen, v.activities.length);
      expect(v.moreActivities).toBeGreaterThanOrEqual(0);
    }
    expect(seen).toBeGreaterThanOrEqual(2);
  });

  it('holds a milestone caption for the milestone hold and not otherwise', () => {
    const m = plan.milestones[0]!;
    // the film reaches the first milestone at this cue progress
    let at = -1;
    for (let p = 0; p <= 1; p += 0.0005) if (viewAt(plan, p, 20).milestone) { at = p; break; }
    expect(at).toBeGreaterThan(0);
    const v = viewAt(plan, at + 0.0005, 20);
    expect(v.milestone!.name).toBe(m.name);
    expect(viewAt(plan, 0, 20).milestone).toBeNull();
    // gone after hold (1 s of a 20 s cue = 0.05) plus a margin
    expect(viewAt(plan, at + 0.08, 20).milestone?.name).not.toBe(m.name);
    // the caption fades in and out
    const mid = viewAt(plan, at + 0.025, 20).milestone!;
    expect(mid.alpha).toBe(1);
  });

  it('puts the data date on the cue', () => {
    const v = viewAt(plan, 0.5, 20);
    expect(v.dataDate).not.toBeNull();
    expect(v.dataDate!).toBeGreaterThan(0.3);
    expect(v.dataDate!).toBeLessThan(0.9);
    expect(viewAt({ ...plan, schedule: { ...plan.schedule, dataDate: undefined } } as never, 0.5, 20).dataDate).toBeNull();
  });
});

describe('the HUD layer draws the 4D items', () => {
  it('draws the date and week instead of the m:ss clock, and the % complete', () => {
    const { ctx, layer } = draw(score(), 12);
    const v = fourdViewAt(score(), 12)!.view;
    expect(ctx.has(v.date)).toBe(true);
    expect(ctx.has(`Week ${v.week} · ${v.weekYear}`)).toBe(true);
    expect(ctx.has(/^Planned \d+\.\d %/)).toBe(true);
    expect(ctx.has(/Actual \d+\.\d %/)).toBe(true);
    expect(ctx.has(/^\d:\d\d \/ \d:\d\d$/)).toBe(false); // no m:ss clock
    expect(ctx.has(`${v.date}  W${String(v.week).padStart(2, '0')}`)).toBe(true); // the date replaces it on the progress bar
    const d = layer.last!.fourd!;
    expect(d.date).toBe(v.date);
    expect(d.panel).not.toBeNull();
    expect(d.actualPct).not.toBeNull();
  });

  it('keeps the m:ss clock without a schedule cue and outside the schedule cue', () => {
    const sc: Score = { schema: SCORE_SCHEMA, duration: 30, cues: [{ at: 5, dur: 5, kind: 'caption', title: 'Hi' }] };
    const { ctx, layer } = draw(sc, 6);
    expect(ctx.has(/^\d:\d\d \/ \d:\d\d$/)).toBe(true);
    expect(layer.last!.fourd).toBeNull();
    const out = draw(score(), 27);
    expect(out.ctx.has(/^\d:\d\d \/ \d:\d\d$/)).toBe(true);
  });

  it('draws the S-curve with the planned line, the actual line and a marker', () => {
    const { ctx, layer } = draw(score(), 12);
    const c = layer.last!.fourd!.curve!;
    expect(c.plannedPoints).toBe(plan.progress.length);
    expect(c.actualPoints).toBeGreaterThan(0);
    expect(c.rect.x + c.rect.w).toBeLessThanOrEqual(900);
    expect(c.marker.x).toBeGreaterThanOrEqual(c.rect.x);
    expect(c.marker.x).toBeLessThanOrEqual(c.rect.x + c.rect.w);
    expect(ctx.arcs).toBeGreaterThan(0);
    expect(ctx.has('S-curve')).toBe(true);
    // the curve lines were drawn: far more path points than the panels alone
    expect(ctx.lines.length).toBeGreaterThan(plan.progress.length);
    expect(ctx.strokeStyles.filter((s) => s === '#8fb4ff').length).toBeGreaterThan(0);
    expect(ctx.strokeStyles.filter((s) => s === '#ffb347').length).toBeGreaterThan(0);
  });

  it('draws no actual line when the plan has no actuals', () => {
    const bare = buildDemoPlan(model, { seconds: 20, actual: false });
    const sc: Score = { schema: SCORE_SCHEMA, duration: 30, cues: [{ at: 2, dur: 20, kind: 'schedule4d', plan: bare }] };
    const { ctx, layer } = draw(sc, 12);
    expect(layer.last!.fourd!.curve!.actualPoints).toBe(0);
    expect(ctx.strokeStyles.filter((s) => s === '#ffb347').length).toBe(0);
    expect(layer.last!.fourd!.actualPct).toBeNull();
    expect(ctx.has(/Actual/)).toBe(false);
  });

  it('lists the current activities with trade swatches', () => {
    const { ctx, layer } = draw(score(), 12);
    const a = layer.last!.fourd!.activities!;
    expect(a.rows.length).toBeGreaterThan(0);
    expect(a.rows.length).toBeLessThanOrEqual(5);
    expect(ctx.has(/^Now: \d+ activit/)).toBe(true);
    for (const r of a.rows) {
      expect(ctx.rects.some((q) => q.style === r.colour && q.w === 10)).toBe(true);
      expect(ctx.has(String(r.elements))).toBe(true);
    }
  });

  it('draws the legend with the trade colours, critical, and behind and ahead when there are actuals', () => {
    const { layer } = draw(score(), 12);
    const l = layer.last!.fourd!.legend!;
    expect(l.entries).toContain('Critical');
    expect(l.entries).toContain('Behind');
    expect(l.entries).toContain('Ahead');
    expect(l.entries.length).toBeGreaterThan(3);
    expect(l.rect.y + l.rect.h).toBeLessThanOrEqual(500);
  });

  it('draws the milestone caption while it is held, and the data-date mark on the progress bar', () => {
    let hit: number | null = null;
    for (let t = 2; t < 22; t += 0.05) if (viewAt(plan, (t - 2) / 20, 20).milestone) { hit = t + 0.2; break; }
    expect(hit).not.toBeNull();
    const { ctx, layer } = draw(score(), hit!);
    const m = layer.last!.fourd!.milestone!;
    expect(m.name).toBe(plan.milestones[0]!.name);
    expect(ctx.has(m.name)).toBe(true);
    const dd = layer.last!.fourd!.dataDate!;
    expect(dd.x).toBeGreaterThan(0);
    expect(dd.x).toBeLessThan(900);
    expect(ctx.rects.some((r) => r.style === '#ffc447' && r.x === dd.x - 1 && r.h === 11)).toBe(true);
  });

  it('is active while a schedule cue runs even with every other HUD item off', () => {
    const layer = new ScoreHudLayer(source, () => ({ ...DEFAULT_HUD, progress: false, compass: false, scaleBar: false }));
    layer.setScore(score());
    expect(layer.active(12)).toBe(true);
    expect(layer.active(1)).toBe(false);
  });

  it('the HUD options switch each item off', () => {
    const off = draw(score(), 12, { scheduleDate: false, sCurve: false, activities: false, milestones: false, legend: false });
    const d = off.layer.last!.fourd!;
    expect(d.panel).toBeNull();
    expect(d.curve).toBeNull();
    expect(d.activities).toBeNull();
    expect(d.legend).toBeNull();
    expect(off.ctx.has(/^\d:\d\d \/ \d:\d\d$/)).toBe(true); // the clock stays when the date is off
  });

  it('fits a phone: panels inside the frame', () => {
    const { layer } = draw(score(), 12, {}, 360, 640);
    const d = layer.last!.fourd!;
    for (const r of [d.panel, d.activities?.rect, d.curve?.rect, d.legend?.rect]) {
      if (!r) continue;
      expect(r.x).toBeGreaterThanOrEqual(0);
      expect(r.x + r.w).toBeLessThanOrEqual(360);
      expect(r.y + r.h).toBeLessThanOrEqual(640);
    }
  });
});

describe('legend and strip layout', () => {
  const overlap = (a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  for (const [w, h] of [[1280, 720], [390, 700]] as const) {
    it(`draws both at ${w} x ${h}, inside the frame, apart from each other and from the panels`, () => {
      const { layer, ctx } = draw(score(), 12, {}, w, h);
      const d = layer.last!.fourd!;
      expect(d.legend).not.toBeNull();
      expect(d.strip).not.toBeNull();
      for (const r of [d.legend!.rect, d.strip!.rect]) {
        expect(r.x).toBeGreaterThanOrEqual(0);
        expect(r.x + r.w).toBeLessThanOrEqual(w);
        expect(r.y + r.h).toBeLessThanOrEqual(h);
      }
      expect(overlap(d.legend!.rect, d.strip!.rect)).toBe(false);
      for (const p of [d.panel, d.activities?.rect]) if (p) expect(overlap(p, d.legend!.rect) || overlap(p, d.strip!.rect)).toBe(false);
      expect(ctx.has('Trades') || w < 500).toBe(true);
      expect(ctx.has('Active')).toBe(true);
      expect(d.strip!.rows).toBeGreaterThan(1);
    });
  }

  it('the plan style switches them off', () => {
    const off = (key: 'legend' | 'strip'): Score => ({ schema: SCORE_SCHEMA, duration: 30, cues: [{ at: 2, dur: 20, kind: 'schedule4d', plan: { ...plan, style: { ...plan.style, [key]: 'off' } } }] });
    expect(draw(off('legend'), 12).layer.last!.fourd!.legend).toBeNull();
    expect(draw(off('legend'), 12).layer.last!.fourd!.strip).not.toBeNull();
    expect(draw(off('strip'), 12).layer.last!.fourd!.strip).toBeNull();
    expect(draw(off('strip'), 12).layer.last!.fourd!.legend).not.toBeNull();
  });

  it('draws neither without a schedule cue (a plain fly-through)', () => {
    const plain: Score = { schema: SCORE_SCHEMA, duration: 30, cues: [{ at: 1, dur: 3, kind: 'caption', text: 'hello' }] };
    const { layer } = draw(plain, 2);
    expect(layer.last!.fourd ?? null).toBeNull();
  });
});

describe('HUD settings', () => {
  it('has the 4D options on by default, and sanitizes them', () => {
    const d = defaultHud();
    expect([d.scheduleDate, d.sCurve, d.activities, d.milestones, d.legend]).toEqual([true, true, true, true, true]);
    expect(isDefaultHud(d)).toBe(true);
    const s = sanitizeHud({ sCurve: false, legend: 'no', activities: false });
    expect(s.sCurve).toBe(false);
    expect(s.activities).toBe(false);
    expect(s.legend).toBe(true);
    expect(isDefaultHud(s)).toBe(false);
    // an old document without the new fields reads as the defaults
    expect(sanitizeHud({ progress: false, compass: true }).scheduleDate).toBe(true);
  });
});
