import { describe, expect, it } from 'vitest';
import { Object3D } from 'three';
import {
  AR_SCALES, IDENTITY_RIG, SNAP_TURN, apparentSize, arPlacement, arScaleFactor, clipDistances, defaultArSurface, controllerRayToWorld, defaultArHit, len,
  moveStep, norm, poseToCamera, quatRotate, rigDirection, rigFromOrbitCamera, rigLocalPoint, rigMatrix, rigPoint, snapTurn, snapTurnStep,
  turnAboutHead, wrapAngle, yawOfDirection, yawQuat,
} from '../src/xr/maths';
import type { Q4, Rig, V3 } from '../src/xr/maths';

const close = (a: ArrayLike<number>, b: ArrayLike<number>, d = 1e-9): void => {
  expect(a.length).toBe(b.length);
  for (let i = 0; i < a.length; i++) expect(a[i]!, `component ${i}`).toBeCloseTo(b[i]!, -Math.log10(d));
};

const rig: Rig = { position: [10, 2, -5], yaw: 0.7, scale: 3 };

describe('rig transform', () => {
  it('maps points like the matrix translate * rotateY * scale', () => {
    const m = rigMatrix(rig);
    const p: V3 = [1.5, -0.4, 2];
    const viaMatrix: V3 = [m[0]! * p[0] + m[4]! * p[1] + m[8]! * p[2] + m[12]!, m[1]! * p[0] + m[5]! * p[1] + m[9]! * p[2] + m[13]!, m[2]! * p[0] + m[6]! * p[1] + m[10]! * p[2] + m[14]!];
    close(rigPoint(rig, p), viaMatrix);
  });

  it('agrees with a three.js Object3D carrying the same position, yaw and scale (what the viewer really uses)', () => {
    const o = new Object3D();
    o.position.set(...rig.position);
    o.rotation.set(0, rig.yaw, 0);
    o.scale.setScalar(rig.scale);
    o.updateMatrixWorld(true);
    close(o.matrixWorld.elements, rigMatrix(rig), 1e-12);
  });

  it('is inverted by rigLocalPoint', () => {
    const p: V3 = [0.3, 1.6, -2.2];
    close(rigLocalPoint(rig, rigPoint(rig, p)), p);
  });

  it('turns directions without scaling them', () => {
    const d = rigDirection(rig, [0, 0, -1]);
    expect(len(d)).toBeCloseTo(1, 12);
    close(d, [-Math.sin(0.7), 0, -Math.cos(0.7)]);
  });

  it('has a yaw of 0 that leaves a point alone at scale 1', () => {
    close(rigPoint(IDENTITY_RIG, [1, 2, 3]), [1, 2, 3]);
  });
});

describe('orbit camera to head (pose to camera)', () => {
  it('puts the head at the orbit camera position and looks along its horizontal direction', () => {
    const camPos: V3 = [6, 5.5, 13];
    const camDir = norm([-9.95, -7.3, -17.8]);
    const r = rigFromOrbitCamera(camPos, camDir);
    // head at the origin of the local reference space, looking straight ahead
    const cam = poseToCamera(r, [0, 0, 0], [0, 0, 0, 1]);
    close(cam.position, camPos);
    close(cam.forward, norm([camDir[0], 0, camDir[2]]));
    // a head 1.6 m above the local origin (a local-floor space) sits 1.6 m above the camera
    close(poseToCamera(r, [0, 1.6, 0], [0, 0, 0, 1]).position, [6, 5.5 + 1.6, 13]);
  });

  it('keeps the head where the headset says when the head moves, in the rig frame', () => {
    const r = rigFromOrbitCamera([0, 0, 0], [1, 0, 0]); // looking along +x
    close(poseToCamera(r, [0, 0, -1], [0, 0, 0, 1]).position, [1, 0, 0], 1e-9); // one metre ahead of the start
    close(poseToCamera(r, [1, 0, 0], [0, 0, 0, 1]).position, [0, 0, 1], 1e-9); // one metre to the right (+x local = +z world here)
  });

  it('composes the head orientation with the rig yaw', () => {
    const headYaw = 0.5;
    const r: Rig = { position: [0, 0, 0], yaw: 0.25, scale: 1 };
    const cam = poseToCamera(r, [0, 0, 0], yawQuat(headYaw));
    close(cam.quaternion, yawQuat(0.75));
    close(cam.forward, quatRotate(yawQuat(0.75), [0, 0, -1]));
  });

  it('computes the yaw of a direction (forward is -Z)', () => {
    expect(yawOfDirection([0, 0, -1])).toBeCloseTo(0, 12);
    expect(yawOfDirection([-1, 0, 0])).toBeCloseTo(Math.PI / 2, 12);
    expect(yawOfDirection([0, 1, 0])).toBe(0);
  });
});

describe('controller ray to world ray', () => {
  it('starts at the controller and points along its -Z, turned by the rig', () => {
    const q: Q4 = yawQuat(Math.PI / 2); // controller turned left by 90 degrees: points to -X in the local space
    const ray = controllerRayToWorld({ position: [0, 0, 0], yaw: 0, scale: 1 }, [0.2, 1.1, -0.3], q);
    close(ray.origin, [0.2, 1.1, -0.3]);
    close(ray.direction, [-1, 0, 0]);
    const turned = controllerRayToWorld({ position: [5, 0, 0], yaw: Math.PI / 2, scale: 1 }, [0, 0, 0], [0, 0, 0, 1]);
    close(turned.origin, [5, 0, 0]);
    close(turned.direction, [-1, 0, 0]);
  });

  it('scales the origin but not the direction in a tabletop rig', () => {
    const r: Rig = { position: [0, 0, 0], yaw: 0, scale: 50 };
    const ray = controllerRayToWorld(r, [0.1, 0.2, 0.3], [0, 0, 0, 1]);
    close(ray.origin, [5, 10, 15]);
    close(ray.direction, [0, 0, -1]);
  });

  it('pitches with the controller', () => {
    const pitchDown: Q4 = [-Math.sin(Math.PI / 8), 0, 0, Math.cos(Math.PI / 8)]; // 45 degrees down about x
    const ray = controllerRayToWorld(IDENTITY_RIG, [0, 1, 0], pitchDown);
    close(ray.direction, [0, -Math.SQRT1_2, -Math.SQRT1_2]);
  });
});

describe('snap turn and walking', () => {
  it('turns by 30 degrees once per stick push and re-arms when the stick returns', () => {
    const st = { armed: true };
    const seq = [0, 0.5, 0.9, 0.95, 1, 0.5, 0.2, 0.9, -0.9, -1, 0.1, -0.8].map((x) => snapTurnStep(st, x));
    expect(seq).toEqual([0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, -1]);
  });

  it('keeps the head fixed in the world while turning', () => {
    const head: V3 = [0.2, 1.6, -0.1];
    const before = rigPoint(rig, head);
    const turned = snapTurn(rig, head, 1);
    close(rigPoint(turned, head), before);
    expect(turned.scale).toBe(rig.scale);
    expect(wrapAngle(turned.yaw - rig.yaw)).toBeCloseTo(-SNAP_TURN, 12); // right turns clockwise from above
    close(rigPoint(turnAboutHead(rig, head, 0.3), head), before);
    expect(snapTurn(rig, head, 0)).toBe(rig);
  });

  it('twelve right turns come back to the start', () => {
    let r: Rig = { position: [1, 0, 2], yaw: 0, scale: 1 };
    const head: V3 = [0.1, 1.6, 0.2];
    const p0 = rigPoint(r, head);
    for (let i = 0; i < 12; i++) r = snapTurn(r, head, 1);
    expect(wrapAngle(r.yaw)).toBeCloseTo(0, 9);
    close(r.position, [1, 0, 2], 1e-9);
    close(rigPoint(r, head), p0);
  });

  it('walks along the head forward, ignores a dead stick and scales with the rig', () => {
    const fwd: V3 = [0, -0.5, -1]; // looking a bit down: the walk stays horizontal
    const r1 = moveStep(IDENTITY_RIG, fwd, 0, -1, 0.5, 2);
    close(r1.position, [0, 0, -1]);
    expect(moveStep(IDENTITY_RIG, fwd, 0.05, -0.1, 1)).toBe(IDENTITY_RIG);
    const big = moveStep({ ...IDENTITY_RIG, scale: 50 }, fwd, 0, -1, 1, 1);
    close(big.position, [0, 0, -50]);
    const side = moveStep(IDENTITY_RIG, [0, 0, -1], 1, 0, 1, 1); // stick right strafes to the right: +x when looking along -z
    close(side.position, [1, 0, 0]);
  });
});

describe('AR placement and scale presets', () => {
  it('offers the presets 1:1 and tabletop 1:50', () => {
    expect([...AR_SCALES]).toEqual(['1:1', 'tabletop 1:50']);
    expect(arScaleFactor('1:1')).toBe(1);
    expect(arScaleFactor('tabletop 1:50')).toBe(50);
    expect(apparentSize(25, 'tabletop 1:50')).toBeCloseTo(0.5, 12);
    expect(apparentSize(25, '1:1')).toBe(25);
  });

  it('puts the anchor of the model at the hit point, whatever the scale and the turn', () => {
    const hit: V3 = [0.4, -1.3, -1.1];
    const anchor: V3 = [-3.9, 0, -4.8];
    for (const scale of [1, 50]) for (const yaw of [0, 1.1, -2]) {
      const r = arPlacement(hit, anchor, scale, yaw);
      close(rigPoint(r, hit), anchor);
      expect(r.scale).toBe(scale);
    }
  });

  it('shrinks the model 50 times in the room: a point 10 m from the anchor appears 0.2 m from the hit', () => {
    const hit: V3 = [0, -1.4, -1.2];
    const anchor: V3 = [100, 0, 100];
    const r = arPlacement(hit, anchor, 50);
    const local = rigLocalPoint(r, [100 + 10, 0, 100]);
    expect(Math.hypot(local[0] - hit[0], local[1] - hit[1], local[2] - hit[2])).toBeCloseTo(0.2, 9);
  });

  it('turns the model about the hit point, so it does not slide', () => {
    const hit: V3 = [0.2, -1, -2];
    const anchor: V3 = [5, 0, 5];
    for (const yaw of [0.5, 2]) close(rigPoint(arPlacement(hit, anchor, 50, yaw), hit), anchor);
  });

  it('puts the first model view ahead of the head, on the floor', () => {
    const h = defaultArHit([0, 0, 0], [0, -0.3, -1], 1.2, 1.4);
    close(h, [0, -1.4, -1.2]);
    expect(defaultArHit([0, 0, 0], [0, 1, 0])[2]).toBeCloseTo(-1.2, 12); // looking straight up: falls back to -Z
  });

  it('stands a small model on a table height and a full-size model on the floor', () => {
    expect(defaultArSurface(1)).toEqual({ distance: 1.2, eyeHeight: 1.4 });
    expect(defaultArSurface(50).eyeHeight).toBeLessThan(1);
  });

  it('keeps the far plane in physical metres', () => {
    expect(clipDistances(100, 1).far).toBeCloseTo(600, 9);
    expect(clipDistances(100, 50).far).toBe(50);
    expect(clipDistances(1, 1).near).toBe(0.05);
  });
});
