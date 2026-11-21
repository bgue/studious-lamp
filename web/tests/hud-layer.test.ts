import { describe, expect, it } from 'vitest';
import { PerspectiveCamera } from 'three';
import { getHudLayer, setHudLayer } from '../src/anim/hud';
import type { HudFrame } from '../src/anim/hud';
import { ScoreHudLayer } from '../src/anim/hud/layer';
import type { HudSource } from '../src/anim/hud/layer';
import { makeProjector } from '../src/anim/hud/project';
import { DEFAULT_HUD } from '../src/anim/hud/settings';
import type { HudSettings } from '../src/anim/hud/settings';
import type { Score } from '../src/anim/score';
import { SCORE_SCHEMA } from '../src/anim/score';

/** A 2D context that records what is drawn. */
class FakeCtx {
  font = '10px sans-serif';
  fillStyle = '';
  strokeStyle = '';
  lineWidth = 1;
  globalAlpha = 1;
  textBaseline = '';
  lineJoin = '';
  texts: Array<{ text: string; alpha: number; x: number; y: number }> = [];
  fills = 0;
  strokes = 0;
  scaleArgs: number[] = [];
  depth = 0;
  maxDepth = 0;
  save(): void {
    this.depth++;
  }
  restore(): void {
    this.depth--;
  }
  scale(x: number, y: number): void {
    this.scaleArgs = [x, y];
  }
  measureText(text: string): { width: number } {
    const m = /(\d+(?:\.\d+)?)px/.exec(this.font);
    return { width: text.length * (m ? Number(m[1]) : 10) * 0.55 };
  }
  fillText(text: string, x: number, y: number): void {
    this.texts.push({ text, alpha: this.globalAlpha, x, y });
  }
  fill(): void {
    this.fills++;
  }
  stroke(): void {
    this.strokes++;
  }
  fillRect(): void {
    this.fills++;
  }
  beginPath(): void {}
  closePath(): void {}
  moveTo(): void {}
  lineTo(): void {}
  arcTo(): void {}
  arc(): void {}
}

const bounds = (cx: number, cy: number, cz: number): [number, number, number, number, number, number] => [cx - 1, cy - 1, cz - 1, cx + 1, cy + 1, cz + 1];

function source(n = 3): HudSource {
  return {
    elementIds: (ref) => ('globalIds' in ref ? ref.globalIds.map((g) => Number(g)) : Array.from({ length: n }, (_, i) => i)),
    element: (id) => ({ name: `Element ${id}`, ifcClass: 'IfcWall', storey: 'Level 1', globalId: `g${id}` }),
    bounds: (id) => bounds(id * 4 - 4, 0, -20),
    card: (id) => ({ title: `Card ${id}`, subtitle: 'IfcWall · Level 1', rows: [['Pset_WallCommon.FireRating', '2HR']], footer: '' }),
    camera: () => ({ focus: [0, 0, -20], right: [1, 0, 0], distance: 20 }),
    northDeg: () => 0,
  };
}

function frame(t: number, w = 800, h = 450, duration = 10): HudFrame {
  const cam = new PerspectiveCamera(50, w / h, 0.1, 1000);
  cam.updateMatrixWorld();
  return { t, duration, width: w, height: h, pixelRatio: 2, project: makeProjector(cam, w, h), recording: false };
}

const score = (cues: Score['cues'], extra: Partial<Score> = {}): Score => ({ schema: SCORE_SCHEMA, duration: 10, cues, ...extra });

function layer(s: Score | null, hud: Partial<HudSettings> = {}, n = 3): ScoreHudLayer {
  const l = new ScoreHudLayer(source(n), () => ({ ...DEFAULT_HUD, ...hud }));
  l.setScore(s);
  return l;
}

const draw = (l: ScoreHudLayer, f: HudFrame): FakeCtx => {
  const c = new FakeCtx();
  l.draw(c as never, f);
  return c;
};

describe('HUD layer: registration and activity', () => {
  it('registers with setHudLayer', () => {
    const l = layer(null);
    setHudLayer(l);
    expect(getHudLayer()).toBe(l);
    setHudLayer(null);
  });
  it('is not active without a score and draws nothing', () => {
    const l = layer(null);
    expect(l.active(1)).toBe(false);
    const c = draw(l, frame(1));
    expect(c.texts).toEqual([]);
    expect(c.fills).toBe(0);
    expect(l.last).toBeNull();
  });
  it('is active while a score is set and the progress bar is on, and only during items when everything else is off', () => {
    const s = score([{ kind: 'caption', at: 2, dur: 2, title: 'Hello' }]);
    expect(layer(s).active(0)).toBe(true);
    const bare = layer(s, { progress: false });
    expect(bare.active(0)).toBe(false);
    expect(bare.active(3)).toBe(true);
    expect(bare.active(5)).toBe(false);
    bare.setScore(null);
    expect(bare.active(3)).toBe(false);
  });
});

describe('HUD layer: captions', () => {
  const s = score([{ kind: 'caption', at: 1, dur: 3, title: 'Main hall', text: 'The hall spans two floors and carries the roof truss.' }]);

  it('draws title and text, scaled by the pixel ratio, balanced save and restore', () => {
    const l = layer(s);
    const c = draw(l, frame(2));
    expect(c.scaleArgs).toEqual([2, 2]);
    expect(c.depth).toBe(0);
    const all = c.texts.map((t) => t.text).join(' ');
    expect(all).toContain('Main hall');
    expect(all).toContain('The hall');
    expect(l.last!.caption!.alpha).toBe(1);
  });
  it('fades in and out over 0.3 s and is gone outside', () => {
    const l = layer(s);
    draw(l, frame(1.15));
    expect(l.last!.caption!.alpha).toBeCloseTo(0.5, 5);
    draw(l, frame(3.85));
    expect(l.last!.caption!.alpha).toBeCloseTo(0.5, 5);
    draw(l, frame(0.5));
    expect(l.last!.caption).toBeNull();
    draw(l, frame(4.5));
    expect(l.last!.caption).toBeNull();
    const c = draw(l, frame(1.15));
    expect(c.texts.find((t) => t.text === 'Main hall')!.alpha).toBeCloseTo(0.5, 5);
  });
  it('wraps to the width and keeps safe margins on a phone', () => {
    const l = layer(s);
    draw(l, frame(2, 360, 640));
    const r = l.last!.caption!.rect;
    expect(r.x).toBeGreaterThanOrEqual(12);
    expect(r.x + r.w).toBeLessThanOrEqual(360 - 12);
    expect(r.y + r.h).toBeLessThanOrEqual(640 - 12);
    const wide = layer(s);
    draw(wide, frame(2, 1280, 720));
    expect(wide.last!.caption!.rect.w).toBeLessThanOrEqual(640);
    expect(wide.last!.caption!.rect.h).toBeLessThan(r.h + 1); // the wide caption wraps no more than the phone one
  });
  it('sits above the progress bar, and at the top when asked', () => {
    const l = layer(s);
    draw(l, frame(2));
    expect(l.last!.caption!.rect.y + l.last!.caption!.rect.h).toBeLessThanOrEqual(450 - 3);
    const top = layer(s, { captionPosition: 'top' });
    draw(top, frame(2));
    expect(top.last!.caption!.rect.y).toBeLessThan(60);
  });
  it('shows the latest caption when two overlap', () => {
    const two = layer(score([{ kind: 'caption', at: 0, dur: 5, title: 'First' }, { kind: 'caption', at: 2, dur: 5, title: 'Second' }]));
    draw(two, frame(3));
    expect(two.last!.caption!.title).toBe('Second');
  });
});

describe('HUD layer: labels', () => {
  const s = score([{ kind: 'label', at: 1, dur: 3, elements: { all: true }, fields: ['name', 'class'] }]);

  it('draws one tag per element with the fields, pinned near the element, with a fade', () => {
    const l = layer(s);
    const c = draw(l, frame(2));
    expect(l.last!.labels).toHaveLength(3);
    expect(l.last!.labels[0]!.lines).toEqual(expect.arrayContaining(['IfcWall']));
    expect(c.texts.map((t) => t.text)).toEqual(expect.arrayContaining(['Element 1', 'IfcWall']));
    draw(l, frame(1.15));
    expect(l.last!.labels[0]!.alpha).toBeCloseTo(0.5, 5);
    draw(l, frame(0.5));
    expect(l.last!.labels).toHaveLength(0);
  });
  it('hides elements behind the camera', () => {
    const src = source(2);
    src.bounds = (id) => (id === 0 ? bounds(0, 0, 20) : bounds(0, 0, -20)); // 0 is behind the camera
    const l = new ScoreHudLayer(src, () => DEFAULT_HUD);
    l.setScore(s);
    draw(l, frame(2));
    expect(l.last!.labels.map((x) => x.id)).toEqual([1]);
  });
  it('shows at most 12 and says how many more', () => {
    const src = source(30);
    src.bounds = (id) => bounds((id % 6) * 3 - 7, Math.floor(id / 6) * 2.5 - 5, -20);
    const l = new ScoreHudLayer(src, () => DEFAULT_HUD);
    l.setScore(score([{ kind: 'label', at: 0, dur: 5, elements: { all: true }, fields: ['name'] }]));
    const c = draw(l, frame(2, 1280, 720));
    expect(l.last!.labels.length).toBeLessThanOrEqual(12);
    expect(l.last!.labels.length + l.last!.more).toBe(30);
    expect(l.last!.more).toBeGreaterThan(0);
    expect(c.texts.some((t) => t.text === `+${l.last!.more} more`)).toBe(true);
  });
  it('keeps tags off each other and off the caption', () => {
    const l = layer(score([{ kind: 'label', at: 0, dur: 5, elements: { all: true }, fields: ['name', 'class'] }, { kind: 'caption', at: 0, dur: 5, title: 'Caption' }]), {}, 8);
    draw(l, frame(2));
    const rects = [...l.last!.labels.map((x) => x.rect), l.last!.caption!.rect];
    for (let i = 0; i < rects.length; i++)
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i]!;
        const b = rects[j]!;
        expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h).toBe(false);
      }
  });
});

describe('HUD layer: hover card', () => {
  it('draws the card of the first element with a leader, for the cue and no longer', () => {
    const l = layer(score([{ kind: 'hover', at: 1, dur: 2, elements: { globalIds: ['2', '1'] } }]));
    const c = draw(l, frame(2));
    expect(l.last!.hover!.id).toBe(2);
    expect(c.texts.map((t) => t.text)).toEqual(expect.arrayContaining(['Card 2', 'IfcWall · Level 1', 'FireRating: 2HR']));
    expect(c.strokes).toBeGreaterThan(0);
    draw(l, frame(3.5));
    expect(l.last!.hover).toBeNull();
  });
});

describe('HUD layer: progress bar, compass and scale bar', () => {
  const s = score([{ kind: 'caption', at: 2, dur: 1, title: 'a' }, { kind: 'caption', at: 6, dur: 1, title: 'b' }]);

  it('draws the elapsed and total time with the chapters, and can be hidden', () => {
    const l = layer(s);
    const c = draw(l, frame(4.2));
    expect(c.texts.some((t) => t.text === '0:04 / 0:10')).toBe(true);
    expect(l.last!.progress!.fraction).toBeCloseTo(0.42, 5);
    expect(l.last!.progress!.chapters).toEqual([2, 6]);
    const off = layer(s, { progress: false });
    draw(off, frame(4.2));
    expect(off.last!.progress).toBeNull();
  });
  it('draws the compass and the scale bar only when asked, and the north follows the camera', () => {
    const plain = layer(s);
    draw(plain, frame(4));
    expect(plain.last!.compass).toBeNull();
    expect(plain.last!.scale).toBeNull();
    const on = layer(s, { compass: true, scaleBar: true });
    const c = draw(on, frame(4));
    expect(on.last!.compass).not.toBeNull();
    expect(on.last!.scale).not.toBeNull();
    expect(c.texts.some((t) => t.text === 'N')).toBe(true);
    expect(c.texts.some((t) => /^\d+(\.\d+)? (m|cm|km)$/.test(t.text))).toBe(true);
    // Project +Y is -Z in the viewer: with the camera looking down -Z it points up the screen (angle -90 deg).
    expect(on.last!.compass!.angle).toBeCloseTo(-Math.PI / 2, 1);
  });
  it('turns the north arrow with the true north angle', () => {
    const src = source();
    src.northDeg = () => 90; // true north is 90 degrees counter-clockwise from project +Y: viewer -X
    const l = new ScoreHudLayer(src, () => ({ ...DEFAULT_HUD, compass: true }));
    l.setScore(s);
    draw(l, frame(4));
    expect(Math.abs(Math.abs(l.last!.compass!.angle) - Math.PI)).toBeLessThan(0.05);
  });
});

describe('projector', () => {
  it('gives pixels for a point in front, null behind and far off the frame', () => {
    const cam = new PerspectiveCamera(50, 2, 0.1, 100);
    cam.updateMatrixWorld();
    const p = makeProjector(cam, 800, 400);
    expect(p([0, 0, -10])).toEqual({ x: 400, y: 200 });
    expect(p([0, 0, 10])).toBeNull();
    expect(p([500, 0, -10])).toBeNull();
    const up = p([0, 1, -10])!;
    expect(up.y).toBeLessThan(200);
  });
});
