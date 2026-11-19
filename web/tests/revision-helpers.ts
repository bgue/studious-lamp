// Shared by the revision tests: IFC file -> SceneModel + geometry arrays -> ModelSnapshot, all in node (web-ifc WASM, no browser).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { IfcAPI } from 'web-ifc';
import { schemaHash, defaultSchema } from '../src/classify/schema';
import { modelFingerprint } from '../src/classify/reviewLog';
import type { ClassifyResult } from '../src/classify/types';
import { buildMergedData } from '../src/model/ifcBuild';
import { createIfcApi, extractIfc } from '../src/model/ifcRaw';
import { normaliseRelations } from '../src/model/loader';
import type { MergedArrays } from '../src/model/mergedArrays';
import { computeSignatures, rangesOfPairs } from '../src/revision/geomSig';
import { snapshotOf } from '../src/revision/snapshot';
import type { ModelSnapshot } from '../src/revision/types';
import type { SceneModel } from '../src/types';

const here = dirname(fileURLToPath(import.meta.url));
export const WEB = resolve(here, '..');
export const MODELS = resolve(WEB, '..', 'models');
export const FIXTURES = resolve(here, 'fixtures', 'ifc');
const wasm = resolve(WEB, 'node_modules/web-ifc/web-ifc-node.wasm');

let api: Promise<IfcAPI> | null = null;
export const ifcApi = (): Promise<IfcAPI> => (api ??= createIfcApi({ url: wasm }));

export const SCHEMA_HASH = schemaHash(defaultSchema());

export interface LoadedIfc {
  model: SceneModel;
  arrays: MergedArrays;
  snap: ModelSnapshot;
  /** Milliseconds spent in computeSignatures. */
  sigMs: number;
}

/** Read an IFC file the way the viewer does and take a snapshot of it (signatures included). */
export async function loadIfc(path: string, o: { name?: string; results?: (gid: string) => ClassifyResult | null | undefined; savedAt?: string } = {}): Promise<LoadedIfc> {
  const name = o.name ?? path.replace(/^.*[\\/]/, '');
  const raw = await extractIfc(await ifcApi(), new Uint8Array(readFileSync(path)), name);
  const built = buildMergedData([raw], { edges: 'none' });
  const model: SceneModel = {
    schema: 'xray-model/1', units: 'm', originShift: built.head.originShift, storeys: built.head.storeys, elements: built.records,
    relations: normaliseRelations(built.head.relations), byGlobalId: new Map(built.records.map((e) => [e.globalId, e.id])),
  };
  const t0 = performance.now();
  const sig = computeSignatures({ position: built.arrays.position, index: built.arrays.index, ranges: rangesOfPairs(built.arrays.ranges) });
  const sigMs = performance.now() - t0;
  const snap = snapshotOf({
    name, model, sig, schemaHash: SCHEMA_HASH,
    reviewFingerprint: modelFingerprint(model.elements.map((e) => e.globalId), SCHEMA_HASH),
    ...(o.results ? { results: o.results } : {}), ...(o.savedAt ? { savedAt: o.savedAt } : {}),
  });
  return { model, arrays: built.arrays, snap, sigMs };
}

export const fzk1 = (): string => resolve(MODELS, 'AC20-FZK-Haus.ifc');
export const fzk2 = (): string => resolve(FIXTURES, 'fzk-v2.ifc');
export const fzk2Reguid = (): string => resolve(FIXTURES, 'fzk-v2-reguid.ifc');

export interface TruthChange {
  name: string; ifcClass: string; baseGuid: string | null; headGuid: string | null;
  category: 'changed' | 'rematched' | 'new' | 'deleted'; flags: string[]; moveMm?: number; rotated?: boolean;
}
export interface Truth { changes: TruthChange[]; reguidMap: Record<string, string>; reguidShift: number[] }
export const readTruth = (): Truth => JSON.parse(readFileSync(resolve(FIXTURES, 'fzk-v2.truth.json'), 'utf8')) as Truth;

// ---------------------------------------------------------------- synthetic snapshots (no IFC): timing budgets, store and detection tests

import { modelIdentity } from '../src/markup/model';
import { classHistogramOf, guidSketch } from '../src/revision/snapshot';
import { SIG_STRIDE } from '../src/revision/types';
import type { PropValue, Vec3 } from '../src/revision/types';

/** A small deterministic generator (mulberry32). */
export function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const B64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$';
export const randomGuid = (r: () => number): string => {
  let s = '';
  for (let i = 0; i < 22; i++) s += B64[Math.floor(r() * 64)];
  return s;
};

const CLASSES = ['IfcWall', 'IfcSlab', 'IfcColumn', 'IfcBeam', 'IfcDoor', 'IfcWindow', 'IfcPipeSegment', 'IfcDuctSegment'];

/** Identity, sketch and histogram of a snapshot whose columns were edited (call after changing globalId or ifcClass). */
export function refresh(s: ModelSnapshot, name = s.identity.name): ModelSnapshot {
  s.identity = modelIdentity(name, s.globalId.length, s.globalId);
  s.guidSketch = guidSketch(s.globalId);
  s.classHistogram = classHistogramOf(s.ifcClass);
  return s;
}

/**
 * n elements on a jittered 1.5 m lattice (about 8 neighbours per 27 m3 search window, like a dense building), eight shape families
 * with a per-element size, unique names. Deterministic.
 */
export function synthSnapshot(o: { n: number; name?: string; seed?: number; shift?: Vec3; savedAt?: string }): ModelSnapshot {
  const n = o.n;
  const r = prng(o.seed ?? 7);
  const nz = Math.max(1, Math.min(20, Math.round(Math.cbrt(n / 4))));
  const nx = Math.ceil(Math.sqrt(n / nz));
  const s: ModelSnapshot = {
    schema: 'xray-model-snapshot/1', identity: { name: '', elementCount: 0, guidCount: 0, guidHash: '' }, savedAt: o.savedAt ?? '2026-01-01T00:00:00.000Z',
    classificationSchemaHash: SCHEMA_HASH, reviewFingerprint: `fp${o.seed ?? 7}`, originShift: o.shift ?? [0, 0, 0], guidSketch: new Uint32Array(0), classHistogram: {},
    globalId: new Array<string>(n), ifcClass: new Array<string>(n), name: new Array<string>(n), tag: new Array<string>(n), typeName: new Array<string>(n),
    material: new Array<string>(n), storey: new Array<ModelSnapshot['storey'][number]>(n), systems: new Array<string[]>(n), classifySignature: new Array<string>(n),
    props: new Array<Record<string, PropValue> | null>(n), bounds: new Float32Array(n * 6), sig: new Float32Array(n * SIG_STRIDE), results: new Array<ClassifyResult | null>(n).fill(null),
  };
  const noSys: string[] = [];
  for (let i = 0; i < n; i++) {
    const k = i % 8;
    const ix = i % nx, iy = Math.floor(i / nx) % nx, iz = Math.floor(i / (nx * nx)) % nz;
    const x = ix * 1.5 + (r() - 0.5) * 0.6, y = iy * 1.5 + (r() - 0.5) * 0.6, z = iz * 3 + (r() - 0.5) * 0.6;
    const size = 0.8 + r() * 0.4;
    const area = (1 + k * 0.7) * size * size;
    const e: Vec3 = [(0.3 + k * 0.1) * size, (1 + k * 0.2) * size, (0.5 + k * 0.15) * size];
    const m1 = e[1] * e[1] / 12, m2 = e[0] * e[0] / 12 + 0.01 * k, m3 = e[2] * e[2] / 12 * 0.5 + 0.002;
    s.globalId[i] = randomGuid(r);
    s.ifcClass[i] = CLASSES[k]!;
    s.name[i] = `Item-${i}`;
    s.tag[i] = ''; s.typeName[i] = ''; s.material[i] = ''; s.systems[i] = noSys;
    s.storey[i] = { name: `L${iz}`, elevation: iz * 3 };
    s.classifySignature[i] = `${CLASSES[k]}|k${k}`;
    s.props[i] = null;
    const o2 = i * SIG_STRIDE;
    s.sig.set([area, area * 0.3, x, y, z, Math.max(m1, m2, m3), Math.max(Math.min(m1, m2), Math.min(Math.max(m1, m2), m3)), Math.min(m1, m2, m3), e[0], e[1], e[2]], o2);
    s.bounds.set([x - e[0] / 2, y - e[1] / 2, z - e[2] / 2, x + e[0] / 2, y + e[1] / 2, z + e[2] / 2], i * 6);
  }
  return refresh(s, o.name ?? 'synthetic.ifc');
}

/** A copy of a snapshot's columns (typed arrays copied, strings shared): the base of an edited head. */
export function cloneSnapshot(s: ModelSnapshot): ModelSnapshot {
  return {
    ...s, globalId: s.globalId.slice(), ifcClass: s.ifcClass.slice(), name: s.name.slice(), tag: s.tag.slice(), typeName: s.typeName.slice(),
    material: s.material.slice(), storey: s.storey.slice(), systems: s.systems.slice(), classifySignature: s.classifySignature.slice(), props: s.props.slice(),
    bounds: s.bounds.slice(), sig: s.sig.slice(), results: s.results.slice(), guidSketch: s.guidSketch.slice(), classHistogram: { ...s.classHistogram },
  };
}

export interface DerivedHead {
  head: ModelSnapshot;
  /** base GlobalId -> head GlobalId for every element that exists in both (same id unless `reguid`). */
  pair: Map<string, string>;
  deleted: Set<string>;
  added: Set<string>;
  moved: Set<string>;
  propChanged: Set<string>;
}

/**
 * A revised copy of a synthetic snapshot: some elements deleted, some added at random places, some moved by `moveBy` metres in x, some
 * with a changed property. `reguid` gives every element a new GlobalId and shifts the whole model by `shift` (world metres).
 */
export function deriveHead(base: ModelSnapshot, o: { seed?: number; deleteShare?: number; newShare?: number; moveShare?: number; moveBy?: number; propShare?: number; reguid?: boolean; shift?: Vec3; name?: string } = {}): DerivedHead {
  const r = prng(o.seed ?? 99);
  const n = base.globalId.length;
  const keep: number[] = [];
  const deleted = new Set<string>();
  const moved = new Set<string>();
  const propChanged = new Set<string>();
  for (let i = 0; i < n; i++) {
    if (r() < (o.deleteShare ?? 0)) deleted.add(base.globalId[i]!); else keep.push(i);
  }
  const nAdd = Math.round(n * (o.newShare ?? 0));
  const m = keep.length + nAdd;
  const head = cloneSnapshot(base);
  head.globalId = new Array<string>(m); head.ifcClass = new Array<string>(m); head.name = new Array<string>(m); head.tag = new Array<string>(m); head.typeName = new Array<string>(m);
  head.material = new Array<string>(m); head.storey = new Array<ModelSnapshot['storey'][number]>(m); head.systems = new Array<string[]>(m); head.classifySignature = new Array<string>(m);
  head.props = new Array<Record<string, PropValue> | null>(m); head.results = new Array<ClassifyResult | null>(m).fill(null);
  head.bounds = new Float32Array(m * 6); head.sig = new Float32Array(m * SIG_STRIDE);
  const pair = new Map<string, string>();
  keep.forEach((i, j) => {
    head.globalId[j] = o.reguid ? randomGuid(r) : base.globalId[i]!;
    pair.set(base.globalId[i]!, head.globalId[j]!);
    head.ifcClass[j] = base.ifcClass[i]!; head.name[j] = base.name[i]!; head.tag[j] = base.tag[i]!; head.typeName[j] = base.typeName[i]!;
    head.material[j] = base.material[i]!; head.storey[j] = base.storey[i]!; head.systems[j] = base.systems[i]!; head.classifySignature[j] = base.classifySignature[i]!;
    head.props[j] = base.props[i] ? { ...base.props[i]! } : null;
    head.sig.set(base.sig.subarray(i * SIG_STRIDE, (i + 1) * SIG_STRIDE), j * SIG_STRIDE);
    head.bounds.set(base.bounds.subarray(i * 6, i * 6 + 6), j * 6);
    if (r() < (o.moveShare ?? 0)) {
      head.sig[j * SIG_STRIDE + 2]! += o.moveBy ?? 0.01; moved.add(base.globalId[i]!);
      head.bounds[j * 6]! += o.moveBy ?? 0.01; head.bounds[j * 6 + 3]! += o.moveBy ?? 0.01;
    }
    if (r() < (o.propShare ?? 0)) { head.props[j] = { ...(head.props[j] ?? {}), 'Pset_Common.FireRating': 'F90' }; propChanged.add(base.globalId[i]!); }
    else if (base.props[i] === null && o.propShare) head.props[j] = null;
  });
  const added = new Set<string>();
  for (let a = 0; a < nAdd; a++) {
    const j = keep.length + a;
    const src = Math.floor(r() * n);
    head.globalId[j] = randomGuid(r); added.add(head.globalId[j]!);
    head.ifcClass[j] = base.ifcClass[src]!; head.name[j] = `New-${a}`; head.tag[j] = ''; head.typeName[j] = ''; head.material[j] = ''; head.storey[j] = base.storey[src]!;
    head.systems[j] = []; head.classifySignature[j] = base.classifySignature[src]!; head.props[j] = null;
    head.sig.set(base.sig.subarray(src * SIG_STRIDE, (src + 1) * SIG_STRIDE), j * SIG_STRIDE);
    head.sig[j * SIG_STRIDE + 2]! += 300 + r() * 50; // far from everything in the base
    head.bounds.set(base.bounds.subarray(src * 6, src * 6 + 6), j * 6);
  }
  if (o.shift) head.originShift = [base.originShift[0] + o.shift[0], base.originShift[1] + o.shift[1], base.originShift[2] + o.shift[2]];
  head.reviewFingerprint = `${base.reviewFingerprint}-head`;
  refresh(head, o.name ?? 'synthetic-v2.ifc');
  return { head, pair, deleted, added, moved, propChanged };
}

/**
 * Run `f` and say how long it took. The wall clock is wrong on a busy machine (parallel test files, other jobs), so the process's
 * own CPU time is read too and the smaller of the two counts: unloaded they agree, loaded the CPU time is what the code costs.
 */
export function measure<T>(f: () => T): { value: T; ms: number; wallMs: number; cpuMs: number } {
  const proc = (globalThis as unknown as { process?: { cpuUsage?: (p?: { user: number; system: number }) => { user: number; system: number } } }).process;
  const c0 = proc?.cpuUsage?.();
  const t0 = performance.now();
  const value = f();
  const wallMs = performance.now() - t0;
  const c = c0 && proc?.cpuUsage ? proc.cpuUsage(c0) : null;
  const cpuMs = c ? (c.user + c.system) / 1000 : wallMs;
  return { value, ms: Math.min(wallMs, cpuMs), wallMs, cpuMs };
}
