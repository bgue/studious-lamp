import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import {
  DEFAULT_NAV_STYLE,
  WALK_PITCH_LIMIT,
  clampPitch,
  eyeTarget,
  flyKeysEnabled,
  horizontalForward,
  isDoubleClick,
  lookFromYawPitch,
  lookRadiansPerPixel,
  parseNavStyle,
  pivotDepth,
  retargetAtDepth,
  turnLook,
  walkMove,
  walkRight,
  walkSpeedFactor,
  walkTargetDistance,
  yawPitchOf,
} from '../src/input/walk';
import { MemoryStorage } from '../src/selectionSets';
import { NAV_STORAGE_KEY, loadNavSettings, navSettings, saveNavSettings } from '../src/input/navigation';
import { getActions } from '../src/input/actions';
import { registerNavigationActions } from '../src/input/navigation';
import { paramSectionNames } from '../src/ui/params';

const v = (x: number, y: number, z: number): Vector3 => new Vector3(x, y, z);
const close = (a: Vector3, b: Vector3, eps = 1e-9): void => {
  expect(a.distanceTo(b)).toBeLessThan(eps);
};

describe('walk motion maths', () => {
  it('forward is the view direction on the horizontal plane, unit length', () => {
    const f = horizontalForward(v(0, -0.6, -0.8));
    close(f, v(0, 0, -1));
    close(horizontalForward(v(3, 5, 4)), v(0.6, 0, 0.8));
    expect(f.length()).toBeCloseTo(1, 12);
  });

  it('a vertical view takes its forward from the fallback, else -Z', () => {
    close(horizontalForward(v(0, -1, 0), v(1, 0.2, 0)), v(1, 0, 0));
    close(horizontalForward(v(0, -1, 0)), v(0, 0, -1));
  });

  it('right is to the right of forward (looking -Z: +X)', () => {
    close(walkRight(v(0, 0, -1)), v(1, 0, 0));
    close(walkRight(v(1, 0, 0)), v(0, 0, 1));
  });

  it('walking keeps the eye height whatever the pitch', () => {
    const eye = v(1, 1.7, 2);
    const look = lookFromYawPitch(0.4, -0.9);
    const p = walkMove(eye, look, 3, 1, 0);
    expect(p.y).toBeCloseTo(1.7, 12);
    // 3 m forward and 1 m right of the horizontal forward
    const f = horizontalForward(look);
    close(p, eye.clone().addScaledVector(f, 3).addScaledVector(walkRight(f), 1));
    expect(walkMove(eye, look, 0, 0, 0.5).y).toBeCloseTo(2.2, 12);
  });

  it('yaw turns about the eye and leaves the pitch alone; positive turns left', () => {
    const look = lookFromYawPitch(0, 0.3);
    const t = turnLook(look, Math.PI / 2, 0);
    close(t, lookFromYawPitch(Math.PI / 2, 0.3), 1e-9);
    expect(t.x).toBeLessThan(0); // looking -Z, turning left: towards -X
    expect(yawPitchOf(t).pitch).toBeCloseTo(0.3, 9);
    close(turnLook(look, 2 * Math.PI, 0), look, 1e-9);
  });

  it('the pitch is clamped to 85 degrees up and down', () => {
    expect(WALK_PITCH_LIMIT).toBeCloseTo((85 * Math.PI) / 180, 12);
    expect(clampPitch(2)).toBeCloseTo(WALK_PITCH_LIMIT, 12);
    expect(clampPitch(-2)).toBeCloseTo(-WALK_PITCH_LIMIT, 12);
    expect(clampPitch(0.2)).toBe(0.2);
    expect(yawPitchOf(turnLook(v(0, 0, -1), 0, 10)).pitch).toBeCloseTo(WALK_PITCH_LIMIT, 9);
    expect(yawPitchOf(turnLook(v(0, 0, -1), 0, -10)).pitch).toBeCloseTo(-WALK_PITCH_LIMIT, 9);
    // from a top view the yaw comes from the fallback and the pitch is brought inside the limit
    const fromTop = turnLook(v(0, -1, 0), 0, 0, undefined, v(0, 0, -1));
    expect(yawPitchOf(fromTop).pitch).toBeCloseTo(-WALK_PITCH_LIMIT, 9);
    expect(fromTop.z).toBeLessThan(0);
  });

  it('the orbit target is a point in front of the eye', () => {
    const eye = v(2, 1.7, 3);
    const look = lookFromYawPitch(1, 0.2);
    const t = eyeTarget(eye, look, 5);
    expect(t.distanceTo(eye)).toBeCloseTo(5, 12);
    close(t.clone().sub(eye).normalize(), look, 1e-12);
  });

  it('speed factors: Shift is 3x, Ctrl 0.25x', () => {
    expect(walkSpeedFactor({})).toBe(1);
    expect(walkSpeedFactor({ shift: true })).toBe(3);
    expect(walkSpeedFactor({ ctrl: true })).toBe(0.25);
    expect(walkSpeedFactor({ shift: true, ctrl: true })).toBe(0.75);
  });

  it('a look drag turns by the field of view over the height', () => {
    expect(lookRadiansPerPixel(45, 900) * 900).toBeCloseTo((45 * Math.PI) / 180, 12);
    expect(lookRadiansPerPixel(45, 0)).toBeGreaterThan(0);
  });

  it('keeps the target distance inside the zoom limits and a quarter of the model', () => {
    expect(walkTargetDistance(100, 0.5, 400, 40)).toBeCloseTo(10, 12);
    expect(walkTargetDistance(2, 0.5, 400, 40)).toBe(2);
    expect(walkTargetDistance(0.1, 1, 400, 40)).toBeCloseTo(1.01, 12);
    expect(walkTargetDistance(5, 0, Infinity, 40)).toBe(5);
  });
});

describe('orbit about what you grab', () => {
  it('pivot depth is the distance along the view axis, not along the pick ray', () => {
    const cam = v(0, 0, 10);
    const view = v(0, 0, -1);
    expect(pivotDepth(cam, view, v(0, 0, 4))).toBeCloseTo(6, 12);
    expect(pivotDepth(cam, view, v(3, 2, 4))).toBeCloseTo(6, 12); // off axis: same depth
  });

  it('the new target lies on the view axis at that depth, so the view does not jump', () => {
    const cam = v(5, 3, 8);
    const view = v(1, 0, -1).normalize();
    const t = retargetAtDepth(cam, view, 6)!;
    expect(t.distanceTo(cam)).toBeCloseTo(6, 12);
    close(t.clone().sub(cam).normalize(), view, 1e-12);
  });

  it('clamps into the orbit limits, and gives nothing for a hit behind the camera', () => {
    const cam = v(0, 0, 0);
    const view = v(0, 0, -1);
    expect(retargetAtDepth(cam, view, 0.1, 1, 50)!.distanceTo(cam)).toBeGreaterThan(1);
    expect(retargetAtDepth(cam, view, 500, 1, 50)!.distanceTo(cam)).toBeLessThan(50);
    expect(retargetAtDepth(cam, view, -3)).toBeNull();
    expect(retargetAtDepth(cam, view, 0)).toBeNull();
  });
});

describe('double click', () => {
  it('needs two clicks close in time and place', () => {
    const a = { t: 1000, x: 100, y: 100 };
    expect(isDoubleClick(null, a)).toBe(false);
    expect(isDoubleClick(a, { t: 1300, x: 102, y: 99 })).toBe(true);
    expect(isDoubleClick(a, { t: 1500, x: 100, y: 100 })).toBe(false);
    expect(isDoubleClick(a, { t: 1100, x: 140, y: 100 })).toBe(false);
  });
});

describe('navigation style', () => {
  it('defaults to BIM and parses only the two styles', () => {
    expect(DEFAULT_NAV_STYLE).toBe('bim');
    expect(parseNavStyle('game')).toBe('game');
    expect(parseNavStyle('bim')).toBe('bim');
    expect(parseNavStyle('fps')).toBeNull();
    expect(parseNavStyle(undefined)).toBeNull();
  });

  it('gates the fly keys: BIM only in Walk mode, Game at all times', () => {
    expect(flyKeysEnabled('bim', false)).toBe(false);
    expect(flyKeysEnabled('bim', true)).toBe(true);
    expect(flyKeysEnabled('game', false)).toBe(true);
    expect(flyKeysEnabled('game', true)).toBe(true);
  });

  it('keeps the fly actions, their ids and default chords, and gates them with enabled()', () => {
    registerNavigationActions();
    const by = Object.fromEntries(getActions().map((a) => [a.id, a]));
    const expected: Record<string, string> = { 'nav.forward': 'w', 'nav.back': 's', 'nav.left': 'a', 'nav.right': 'd', 'nav.down': 'q', 'nav.up': 'e' };
    const app = {} as never;
    const was = navSettings.style;
    for (const [id, key] of Object.entries(expected)) {
      expect(by[id]?.keys, id).toEqual([key]);
      navSettings.style = 'bim';
      expect(by[id]!.enabled!(app), `${id} bim`).toBe(false);
      navSettings.style = 'game';
      expect(by[id]!.enabled!(app), `${id} game`).toBe(true);
    }
    expect(by['nav.walk']?.keys).toEqual(['Shift+w']);
    navSettings.style = was;
  });

  it('is stored in localStorage xray.keynav only, never in a params section', () => {
    const store = new MemoryStorage();
    const was = navSettings.style;
    navSettings.style = 'game';
    saveNavSettings(store);
    expect(JSON.parse(store.getItem(NAV_STORAGE_KEY)!).style).toBe('game');
    navSettings.style = 'bim';
    loadNavSettings(store);
    expect(navSettings.style).toBe('game');
    store.setItem(NAV_STORAGE_KEY, JSON.stringify({ style: 'junk' }));
    loadNavSettings(store);
    expect(navSettings.style).toBe('game'); // junk is ignored
    const broken = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
    expect(() => loadNavSettings(broken)).not.toThrow();
    expect(() => saveNavSettings(broken)).not.toThrow();
    navSettings.style = was;
    expect(paramSectionNames()).not.toContain('walk');
    expect(paramSectionNames()).not.toContain('navStyle');
    for (const file of ['../src/plugins/walk.ts', '../src/input/walk.ts']) {
      const text = readFileSync(fileURLToPath(new URL(file, import.meta.url)), 'utf8');
      expect(text, file).not.toMatch(/registerParamSection\(/);
    }
  });
});
