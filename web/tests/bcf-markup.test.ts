// Viewer markup in BCF: topic pins and viewpoint annotations in the side file xray-markup.json, the coordinate mapping,
// the snapshot burn-in layout (pure part) and schema validation with markup present.

import { describe, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { parseBcf, parseViewpoint } from '../src/bcf/parse';
import { writeBcf } from '../src/bcf/write';
import type { WriteOptions } from '../src/bcf/write';
import { readZip } from '../src/bcf/zip';
import { dirViewerToIfc, emptyProject, ifcToViewer, newGuid, viewerToIfc } from '../src/bcf/model';
import type { BcfAnnotation, BcfProject, BcfTopic, BcfVersion, Vec3 } from '../src/bcf/model';
import { SIDECAR_NAME, annotationGuids, parseSidecar, sidecarJson } from '../src/bcf/sidecar';
import { defaultOffset, drawOps, layoutAnnotation, layoutPin, layoutSnapshot, projectPoint, snapshotProjector, viewProjection, wrapText } from '../src/bcf/annotate';
import type { Ctx2D, DrawOp, LayoutContext } from '../src/bcf/annotate';
import { FIXTURES, G1, G2, nodeMod } from './bcf-helpers';

const SHIFT: Vec3 = [6.0, 5.0, 3.058846]; // fzk-haus originShift
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 9, 9, 9, 9]);
const BURNED = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 7, 7, 7, 7]);

function annotations(): BcfAnnotation[] {
  return [
    { guid: newGuid(), type: 'callout', text: 'Reveal too small\nsee detail 4', anchor: { kind: 'element', point: [7.25, 2.5, 4.125], elementGuid: G1 }, offset: [0.1, -0.09], author: 'me', date: '2026-11-04T10:00:00.000Z' },
    { guid: newGuid(), type: 'note', text: 'Check on site', anchor: { kind: 'point', point: [1.5, -2.25, 0.333333333] }, offset: [0.05, -0.04] },
    { guid: newGuid(), type: 'arrow', text: '', anchor: { kind: 'element', point: [3, 3, 3], elementGuid: `${G2}~2` }, offset: [-0.1, -0.08] },
    {
      guid: newGuid(), type: 'callout', text: '0.874 m', offset: [0.12, 0.05],
      anchor: { kind: 'measurement', point: [5, 5, 1.5], measurement: { kind: 'element', a: [4.5, 5, 1.5], b: [5.5, 5, 1.5], distance: 0.874, label: '0.874 m', elementGuids: [G1, G2], sourceId: 3 } },
    },
  ];
}

function project(): BcfProject {
  const p = emptyProject('2.1');
  const vpGuid = newGuid();
  const vp2 = newGuid();
  const t: BcfTopic = {
    guid: newGuid(), topicType: 'Issue', topicStatus: 'Open', title: 'Pinned', labels: [], referenceLinks: [], creationDate: '2026-11-04T09:00:00Z', creationAuthor: 'me',
    headerFiles: [], documentReferences: [], relatedTopics: [], comments: [],
    pin: { position: [7.123456789, 2.5, 4.0], elementGuid: G1 },
    viewpoints: [
      {
        guid: vpGuid,
        data: { guid: vpGuid, camera: { kind: 'perspective', position: [20, -10, 8], direction: [-0.8, 0.5, -0.3], up: [0, 0, 1], fov: 38, aspect: 1.6 }, selection: [], visibility: null, coloring: [], clipping: [], lines: [] },
        snapshot: PNG, snapshotMime: 'image/png',
        snapshotView: { position: [20, -10, 8], direction: [-0.8, 0.5, -0.3], up: [0, 0, 1], fov: 38, aspect: 1.6 },
        annotations: annotations(),
      },
      { guid: vp2, data: { guid: vp2, camera: { kind: 'perspective', position: [0, 0, 9], direction: [0, 0, -1], up: [0, 1, 0], fov: 50, aspect: 1 }, selection: [], visibility: null, coloring: [], clipping: [], lines: [] } },
    ],
  };
  const plain: BcfTopic = { ...t, guid: newGuid(), title: 'Plain', viewpoints: [], pin: undefined };
  delete plain.pin;
  p.topics.push(t, plain);
  return p;
}

const compose: WriteOptions['composeSnapshot'] = async () => BURNED;

describe.each(['2.1', '3.0'] as BcfVersion[])('markup side file, BCF %s', (version) => {
  it('writes xray-markup.json only for topics with markup, and reads pins and annotations back exactly', async () => {
    const src = project();
    const bytes = await writeBcf(src, version, { composeSnapshot: compose });
    const names = readZip(bytes).map((e) => e.name);
    const t = src.topics[0]!;
    const folder = version === '3.0' ? t.guid.toLowerCase() : t.guid;
    expect(names).toContain(`${folder}/${SIDECAR_NAME}`);
    expect(names.filter((n) => n.endsWith(SIDECAR_NAME))).toHaveLength(1);
    const back = await parseBcf(bytes);
    expect(back.warnings).toEqual([]);
    const bt = back.topics.find((x) => x.guid.toLowerCase() === t.guid.toLowerCase())!;
    expect(bt.pin).toEqual(t.pin);
    expect(bt.viewpoints[0]!.annotations).toEqual(t.viewpoints[0]!.annotations);
    expect(bt.viewpoints[0]!.snapshotView).toEqual(t.viewpoints[0]!.snapshotView);
    expect(bt.viewpoints[1]!.annotations).toBeUndefined();
    expect(back.topics.find((x) => x.title === 'Plain')!.pin).toBeUndefined();
  });

  it('burns the snapshot under the markup name and keeps the clean one for the viewer', async () => {
    const src = project();
    const bytes = await writeBcf(src, version, { composeSnapshot: compose });
    const entries = readZip(bytes);
    const t = src.topics[0]!;
    const g = version === '3.0' ? t.viewpoints[0]!.guid.toLowerCase() : t.viewpoints[0]!.guid;
    const snapName = version === '2.1' ? 'snapshot.png' : `${g}.png`;
    const snap = entries.find((e) => e.name.endsWith(`/${snapName}`))!;
    expect([...(await snap.read())]).toEqual([...BURNED]);
    const base = entries.find((e) => e.name.endsWith(`/xray-${g}-base.png`))!;
    expect([...(await base.read())]).toEqual([...PNG]);
    // the viewer reads the clean snapshot back, so a second export burns once, not twice
    const back = await parseBcf(bytes);
    expect([...back.topics.find((x) => x.title === 'Pinned')!.viewpoints[0]!.snapshot!]).toEqual([...PNG]);
    // without a compositor (node, or nothing to burn) the snapshot is unchanged and no base file is written
    const plain = readZip(await writeBcf(project(), version));
    expect(plain.some((e) => /-base\.png$/.test(e.name))).toBe(false);
    // a pin alone does not burn the snapshot
    const pinOnly = project();
    pinOnly.topics[0]!.viewpoints[0]!.annotations = undefined;
    let calls = 0;
    const z = readZip(await writeBcf(pinOnly, version, { composeSnapshot: async () => { calls++; return BURNED; } }));
    expect(calls).toBe(0);
    expect(z.some((e) => /-base\.png$/.test(e.name))).toBe(false);
    expect(z.some((e) => e.name.endsWith(SIDECAR_NAME))).toBe(true);
  });

  it('puts the annotated elements into the viewpoint selection (valid IfcGuids, federation suffix removed)', async () => {
    const src = project();
    const bytes = await writeBcf(src, version);
    const t = src.topics[0]!;
    const entries = readZip(bytes);
    const vpName = version === '2.1' ? 'viewpoint.bcfv' : `${t.viewpoints[0]!.guid.toLowerCase()}.bcfv`;
    const vp = parseViewpoint(new TextDecoder().decode(await entries.find((e) => e.name.endsWith(`/${vpName}`))!.read()));
    expect(vp.selection.map((c) => c.ifcGuid).sort()).toEqual([G1, G2].sort());
    expect(annotationGuids(t.viewpoints[0]!.annotations)).toEqual([G1, G2]);
  });
});

describe('side file parsing', () => {
  it('drops invalid annotations with a warning and keeps the rest', () => {
    const vp = newGuid();
    const text = JSON.stringify({
      format: 'xray-bcf-markup', version: 1, frame: 'ifc', units: 'm', topic: 't',
      pin: { position: [1, 2, 3] },
      viewpoints: { [vp.toUpperCase()]: { annotations: [
        { guid: 'a', type: 'callout', text: 'ok', anchor: { kind: 'point', point: [0, 0, 0] }, offset: [0, 0] },
        { guid: 'b', type: 'balloon', text: 'bad type', anchor: { kind: 'point', point: [0, 0, 0] } },
        { guid: 'c', type: 'note', text: 'bad point', anchor: { kind: 'point', point: [0, 'x', 0] } },
        { guid: 'd', type: 'callout', text: 'measurement without data', anchor: { kind: 'measurement', point: [0, 0, 0] } },
      ] } },
    });
    const s = parseSidecar(text);
    expect(s.pin).toEqual({ position: [1, 2, 3] });
    expect(s.viewpoints.get(vp.toLowerCase())!.annotations!.map((a) => a.guid)).toEqual(['a']);
    expect(s.problems).toHaveLength(3);
    expect(() => parseSidecar('{"format":"other"}')).toThrow();
  });

  it('a broken side file only warns; the topic still loads', async () => {
    const src = project();
    src.topics[0]!.viewpoints[0]!.annotations = undefined;
    const bytes = await writeBcf(src, '3.0');
    const { writeZip } = await import('../src/bcf/zip');
    const files = await Promise.all(readZip(bytes).filter((e) => !e.isDirectory).map(async (e) => ({ name: e.name, data: e.name.endsWith(SIDECAR_NAME) ? new TextEncoder().encode('{not json') : await e.read() })));
    const back = await parseBcf(await writeZip(files));
    expect(back.topics).toHaveLength(2);
    expect(back.warnings.some((w) => w.includes(SIDECAR_NAME))).toBe(true);
  });

  it('writes no side file for a topic without markup', () => {
    const t = project().topics[1]!;
    expect(sidecarJson(t, '2.1')).toBeNull();
  });
});

// ---------------------------------------------------------------- coordinates and projection

describe('markup coordinates', () => {
  it('stores points in IFC coordinates with the viewpoint mapping and projects them like the three.js camera', () => {
    // A camera in the viewer frame, as the viewer has it when the snapshot is taken.
    const cam = new PerspectiveCamera(42, 1280 / 720, 0.05, 1e5);
    cam.position.set(9.5, 5.5, 11.5);
    cam.up.set(0, 1, 0);
    cam.lookAt(0.5, 1.2, -0.5);
    cam.updateMatrixWorld();
    const dir = new Vector3();
    cam.getWorldDirection(dir);
    const up = new Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const view = {
      position: viewerToIfc([cam.position.x, cam.position.y, cam.position.z], SHIFT),
      direction: dirViewerToIfc([dir.x, dir.y, dir.z]),
      up: dirViewerToIfc([up.x, up.y, up.z]),
      fov: 42,
      aspect: 1280 / 720,
    };
    const project = snapshotProjector(view, SHIFT, 1280, 720);
    for (const v of [[0.5, 1.2, -0.5], [2, 0.3, 1.7], [-3.1, 2.9, -4.4]] as Vec3[]) {
      const anchorIfc = viewerToIfc(v, SHIFT); // what the side file stores
      const p = project(ifcToViewer(anchorIfc, SHIFT));
      const ref = new Vector3(...v).project(cam);
      expect(p.front).toBe(true);
      expect(p.x).toBeCloseTo((ref.x * 0.5 + 0.5) * 1280, 6);
      expect(p.y).toBeCloseTo((1 - (ref.y * 0.5 + 0.5)) * 720, 6);
    }
    // the orbit target sits in the middle of the image
    const c = project([0.5, 1.2, -0.5]);
    expect(c.x).toBeCloseTo(640, 6);
    expect(c.y).toBeCloseTo(360, 6);
  });

  it('does not depend on the shift used for the snapshot (it cancels)', () => {
    const view = { position: [20, -10, 8] as Vec3, direction: [-0.8, 0.5, -0.3] as Vec3, up: [0, 0, 1] as Vec3, fov: 50, aspect: 1.5 };
    const p: Vec3 = [7, 2.5, 4];
    const a = snapshotProjector(view, SHIFT, 900, 600)(ifcToViewer(p, SHIFT));
    const b = snapshotProjector(view, [0, 0, 0], 900, 600)(ifcToViewer(p, [0, 0, 0]));
    expect(a.x).toBeCloseTo(b.x, 6);
    expect(a.y).toBeCloseTo(b.y, 6);
  });

  it('gives a screen direction for points behind the camera', () => {
    const m = viewProjection([0, 0, 0], [0, 0, -1], [0, 1, 0], 60, 1);
    const behindRight = projectPoint(m, 100, 100, [5, 0, 10]);
    expect(behindRight.front).toBe(false);
    expect(behindRight.dx).toBeGreaterThan(0); // behind and to the right: the edge marker sits on the right (turn right to see it)
    const left = projectPoint(m, 100, 100, [-50, 0, -1]);
    expect(left.front).toBe(true);
    expect(left.visible).toBe(false);
    expect(left.dx).toBeLessThan(0);
  });
});

// ---------------------------------------------------------------- burn-in layout (pure part)

function ctxFor(w = 1000, h = 600, occluded?: (p: Vec3) => boolean): LayoutContext {
  // Simple camera on the viewer +Z axis looking at the origin.
  const m = viewProjection([0, 0, 10], [0, 0, -1], [0, 1, 0], 60, w / h);
  return { width: w, height: h, shift: [0, 0, 0], project: (p) => projectPoint(m, w, h, p), occluded, scale: 1 };
}

describe('snapshot compositing', () => {
  const at = (v: Vec3): Vec3 => viewerToIfc(v, [0, 0, 0]);

  it('lays out a callout: leader from the anchor to the box, box offset by a fraction of the height, wrapped text', () => {
    const a: BcfAnnotation = { guid: 'g1', type: 'callout', text: 'Too narrow', anchor: { kind: 'element', point: at([0, 0, 0]), elementGuid: G1 }, offset: [0.1, -0.1] };
    const ops = layoutAnnotation(a, ctxFor());
    const rect = ops.find((o) => o.op === 'rect') as Extract<DrawOp, { op: 'rect' }>;
    expect(rect.x + rect.w / 2).toBeCloseTo(500 + 60, 6);
    expect(rect.y + rect.h / 2).toBeCloseTo(300 - 60, 6);
    const lines = ops.filter((o) => o.op === 'line') as Array<Extract<DrawOp, { op: 'line' }>>;
    expect(lines.length).toBe(2); // halo + stroke
    expect(lines[1]!.x2).toBeCloseTo(500, 6);
    expect(lines[1]!.y2).toBeCloseTo(300, 6);
    const texts = ops.filter((o) => o.op === 'text').map((o) => (o as { text: string }).text);
    expect(texts).toEqual(['Too narrow']);
    expect(ops.every((o) => o.key === 'g1')).toBe(true);
  });

  it('draws a linked measurement with its label even when the text changed', () => {
    const a: BcfAnnotation = {
      guid: 'm', type: 'callout', text: 'Clearance', offset: [0, -0.1],
      anchor: { kind: 'measurement', point: at([0, 0, 0]), measurement: { kind: 'point', a: at([-1, 0, 0]), b: at([1, 0, 0]), distance: 2, label: '2.000 m' } },
    };
    const ops = layoutAnnotation(a, ctxFor());
    expect(ops.filter((o) => o.op === 'text').map((o) => (o as { text: string }).text)).toEqual(['Clearance', '2.000 m']);
    expect(ops.filter((o) => o.op === 'line' && o.stroke === '#ffd23f')).toHaveLength(1);
  });

  it('fades a pin behind geometry and leaves out the edge marker in a snapshot', () => {
    const pin = { position: at([0, 0, 0]) };
    const front = layoutPin(pin, '3', ctxFor());
    const hidden = layoutPin(pin, '3', ctxFor(1000, 600, () => true));
    expect(front.every((o) => (o.alpha ?? 1) === 1)).toBe(true);
    expect(hidden.every((o) => o.alpha === 0.45)).toBe(true);
    const off = { position: at([500, 0, 0]) };
    expect(layoutPin(off, '3', ctxFor()).some((o) => o.role === 'edge')).toBe(true);
    expect(layoutSnapshot({ pin: off, label: '3' }, [], ctxFor())).toEqual([]);
  });

  it('moves a pin under the viewer chrome (status bar, drawer) to an edge marker inside the free area', () => {
    const pin = { position: at([0, 0, 0]) }; // projects to the centre (500, 300)
    const ctx = { ...ctxFor(), insets: { top: 0, right: 0, bottom: 22, left: 600 } };
    const ops = layoutPin(pin, '3', ctx);
    expect(ops.every((o) => o.role === 'edge')).toBe(true);
    const c = ops.find((o) => o.op === 'circle') as Extract<DrawOp, { op: 'circle' }>;
    expect(c.x).toBeGreaterThanOrEqual(600 + 16 - 1e-9);
    expect(c.y).toBeLessThanOrEqual(600 - 22 - 16 + 1e-9);
    // no insets: the plain pin
    expect(layoutPin(pin, '3', ctxFor()).every((o) => o.role === 'pin')).toBe(true);
  });

  it('paints the operations on a canvas context in order', () => {
    const calls: string[] = [];
    const g: Ctx2D = {
      globalAlpha: 1, fillStyle: '', strokeStyle: '', lineWidth: 1, lineCap: '', lineJoin: '', font: '', textAlign: '', textBaseline: '',
      save: () => calls.push('save'), restore: () => calls.push('restore'), beginPath: () => calls.push('begin'), closePath: () => calls.push('close'),
      moveTo: () => calls.push('move'), lineTo: () => calls.push('line'), arc: () => calls.push('arc'), arcTo: () => calls.push('arcTo'),
      fill: () => calls.push(`fill:${String(g.fillStyle)}`), stroke: () => calls.push(`stroke:${String(g.strokeStyle)}`),
      fillText: (t: string) => calls.push(`text:${t}:${g.font}`), setLineDash: () => undefined,
    };
    const a: BcfAnnotation = { guid: 'n', type: 'note', text: 'Note text', anchor: { kind: 'point', point: at([0, 0, 0]) }, offset: [0, -0.1] };
    drawOps(g, layoutSnapshot({ pin: { position: at([1, 1, 0]) }, label: '7' }, [a], ctxFor()));
    const texts = calls.filter((c) => c.startsWith('text:'));
    expect(texts.map((t) => t.split(':')[1])).toEqual(['Note text', '7']);
    expect(texts[1]).toMatch(/700 12px/);
    expect(calls.filter((c) => c === 'arcTo')).toHaveLength(4); // the rounded note box
    expect(calls.filter((c) => c === 'save').length).toBe(calls.filter((c) => c === 'restore').length);
    expect(calls).toContain('fill:#ffe97a');
  });

  it('turns the default box offset through the 4 quadrants so new boxes do not stack', () => {
    const offs = [0, 1, 2, 3].map((n) => defaultOffset('callout', n));
    expect(new Set(offs.map((o) => `${Math.sign(o[0])},${Math.sign(o[1])}`)).size).toBe(4);
    expect(Math.abs(defaultOffset('callout', 4)[0])).toBeGreaterThan(Math.abs(offs[0]![0]));
  });

  it('wraps long text and keeps explicit line breaks', () => {
    expect(wrapText('a b', 10)).toEqual(['a b']);
    expect(wrapText('one two three four five six seven', 10)).toEqual(['one two', 'three four', 'five six', 'seven']);
    expect(wrapText('x\ny')).toEqual(['x', 'y']);
    expect(wrapText('abcdefghijkl', 5)).toEqual(['abcde', 'fghij', 'kl']);
  });
});

// ---------------------------------------------------------------- schema validation with markup present

const { spawnSync } = nodeMod('node:child_process');
const { mkdirSync, mkdtempSync, rmSync, writeFileSync } = nodeMod('node:fs');
const { tmpdir } = nodeMod('node:os');
const { dirname, join } = nodeMod('node:path');
const hasLxml = ((): boolean => {
  try {
    return spawnSync('python3', ['-I', '-c', 'import lxml.etree'], { encoding: 'utf8' }).status === 0;
  } catch {
    return false;
  }
})();

describe.skipIf(!hasLxml)('BCF with markup validates against the official XSDs', () => {
  it.each(['2.1', '3.0'] as BcfVersion[])('BCF %s', async (v) => {
    const dir = mkdtempSync(join(tmpdir(), `bcf-markup-xsd-${v}-`));
    try {
      for (const e of readZip(await writeBcf(project(), v, { composeSnapshot: compose }))) {
        if (e.isDirectory) continue;
        const p = join(dir, e.name);
        mkdirSync(dirname(p), { recursive: true });
        writeFileSync(p, await e.read());
      }
      const r = spawnSync('python3', ['-I', join(FIXTURES, 'validate_xsd.py'), dir], { encoding: 'utf8' });
      const out = `${r.stdout}${r.stderr}`;
      expect(out).toMatch(/0 failed/);
      expect(out).toMatch(/markup\.bcf/);
      expect(r.status).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
