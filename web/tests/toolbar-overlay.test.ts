import { describe, expect, it } from 'vitest';
import { Matrix4, PerspectiveCamera } from 'three';
import { legendSpot, projectToScreen } from '../src/ui/overlay';

function viewProj(cam: PerspectiveCamera): Matrix4 {
  cam.updateMatrixWorld();
  return new Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
}

describe('overlay projection', () => {
  const cam = new PerspectiveCamera(60, 2, 0.1, 100);
  cam.position.set(0, 0, 10);
  cam.lookAt(0, 0, 0);
  const m = viewProj(cam).elements;

  it('the target projects to the centre of the canvas', () => {
    const p = projectToScreen(m, 800, 400, 0, 0, 0);
    expect(p.x).toBeCloseTo(400, 6);
    expect(p.y).toBeCloseTo(200, 6);
    expect(p.visible).toBe(true);
    expect(p.depth).toBeGreaterThan(-1);
    expect(p.depth).toBeLessThan(1);
  });
  it('+x is right and +y is up (screen y grows downward)', () => {
    const c = projectToScreen(m, 800, 400, 0, 0, 0);
    const r = projectToScreen(m, 800, 400, 1, 0, 0);
    const u = projectToScreen(m, 800, 400, 0, 1, 0);
    expect(r.x).toBeGreaterThan(c.x);
    expect(r.y).toBeCloseTo(c.y, 6);
    expect(u.y).toBeLessThan(c.y);
  });
  it('matches the analytic pinhole result', () => {
    // half height at distance 10: tan(30deg) * 10 = 5.7735 m maps to 200 px
    const p = projectToScreen(m, 800, 400, 0, 5.7735026919, 0);
    expect(p.y).toBeCloseTo(0, 3);
  });
  it('points behind the camera and outside the frustum are not visible', () => {
    expect(projectToScreen(m, 800, 400, 0, 0, 20).visible).toBe(false);
    const off = projectToScreen(m, 800, 400, 100, 0, 0);
    expect(off.visible).toBe(false);
    expect(off.front).toBe(true); // in front of the camera, just outside the frustum
    expect(projectToScreen(m, 800, 400, 0, 0, 20).front).toBe(false);
    expect(projectToScreen(m, 800, 400, 0, 0, -200).visible).toBe(false); // beyond far
  });
  it('re-uses the output object', () => {
    const out = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    expect(projectToScreen(m, 800, 400, 0, 0, 0, out)).toBe(out);
    expect(out.visible).toBe(true);
  });
  it('follows the camera', () => {
    cam.position.set(5, 0, 10);
    cam.lookAt(5, 0, 0);
    const p = projectToScreen(viewProj(cam).elements, 800, 400, 5, 0, 0);
    expect(p.x).toBeCloseTo(400, 6);
  });
});

describe('legend placement (legendSpot)', () => {
  const none = { top: 0, right: 0, bottom: 0, left: 0 };
  it('sits bottom right above the status bar', () => {
    expect(legendSpot(800, 600, { ...none, bottom: 22 }, null, 200, 100)).toEqual({ x: 800 - 12 - 200, y: 600 - 22 - 8 - 100 });
  });
  it('goes left of the gizmo when there is room, else above it, and stacks in the same column', () => {
    const gizmo = { x: 590, y: 440, w: 200, h: 130 };
    expect(legendSpot(800, 600, { ...none, bottom: 22 }, gizmo, 200, 100)).toEqual({ x: 590 - 8 - 200, y: 600 - 22 - 8 - 100 });
    const narrow = { ...none, bottom: 22, left: 400 };
    expect(legendSpot(800, 600, narrow, gizmo, 200, 100)).toEqual({ x: 800 - 12 - 200, y: 440 - 8 - 100 });
    // a narrower legend stacked on a wider one follows the column choice of the wider one
    expect(legendSpot(800, 600, { ...none, bottom: 22, left: 375 }, gizmo, 190, 94, 120, 210).y).toBe(440 - 8 - 120 - 94);
  });
  it('stays inside the stage when a drawer leaves no room', () => {
    expect(legendSpot(424, 700, { ...none, bottom: 22, left: 364 }, null, 210, 112).x).toBe(424 - 12 - 210);
  });
});
