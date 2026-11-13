// Where the floating drawing toolbar goes: bottom centre inside the edge chrome, aside or up where another reserved rect is.

import { describe, expect, it } from 'vitest';
import { toolbarSpot } from '../src/markup/toolbar';
import type { Rect } from '../src/ui/overlay';

const ins = { top: 36, right: 4, bottom: 24, left: 4 };
const view = (reserved: Rect[], width = 900, height = 700) => ({ width, height, insets: ins, reserved });
const hit = (a: { x: number; y: number }, w: number, h: number, r: Rect): boolean => a.x < r.x + r.w && r.x < a.x + w && a.y < r.y + r.h && r.y < a.y + h;

describe('toolbarSpot', () => {
  it('sits at the bottom centre inside the insets', () => {
    const p = toolbarSpot(view([]), 500, 100, null);
    expect(p.x).toBeCloseTo((4 + 900 - 4 - 500) / 2, 5);
    expect(p.y).toBe(700 - 24 - 100 - 8);
  });

  it('keeps out of the gizmo: left of it when there is room', () => {
    const gizmo: Rect = { x: 650, y: 520, w: 240, h: 170 };
    const p = toolbarSpot(view([gizmo]), 500, 100, null);
    expect(hit(p, 500, 100, gizmo)).toBe(false);
    expect(p.x + 500).toBeLessThanOrEqual(gizmo.x - 8 + 0.01);
  });

  it('goes above the gizmo when it fits nowhere beside it, and stays below the top bar', () => {
    const gizmo: Rect = { x: 120, y: 520, w: 700, h: 170 };
    const p = toolbarSpot(view([gizmo]), 500, 100, null);
    expect(hit(p, 500, 100, gizmo)).toBe(false);
    expect(p.y).toBeGreaterThanOrEqual(ins.top + 8);
  });

  it('does not treat its own previous rect as an obstacle', () => {
    const first = toolbarSpot(view([]), 500, 100, null);
    const own: Rect = { ...first, w: 500, h: 100 };
    const again = toolbarSpot(view([own]), 500, 100, own);
    expect(again).toEqual(first);
  });

  it('fits a 390 px phone: the bar is as wide as the view minus the gutters and starts inside it', () => {
    const p = toolbarSpot(view([], 390, 780), 374, 150, null);
    expect(p.x).toBeGreaterThanOrEqual(0);
    expect(p.x + 374).toBeLessThanOrEqual(390);
  });
});
