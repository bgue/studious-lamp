// A snapshot of a model (design 4.1): everything the revision diff needs from the model that came before, kept small enough to store.
// Columnar arrays (index = element order), the geometry signatures, the classifier's results, a GUID sketch for detection.
// Pure: no DOM, no three.js. `snapshotOf` reads a SceneModel and the signatures that geomSig.ts computed.

import { buildInput } from '../classify/build';
import { signatureOf } from '../classify/state';
import type { ChoiceResult, ClassifyResult } from '../classify/types';
import { compareModels, modelIdentity } from '../markup/model';
import { identityKey } from '../markup/scope';
import type { SceneModel } from '../types';
import { DEFAULT_REVISION_OPTIONS, SIG_STRIDE } from './types';
import type { ModelIdentity, ModelSnapshot, PropValue, RevisionOptions, SnapshotRecord, Vec3 } from './types';

export const SKETCH_SIZE = 256;

// ---------------------------------------------------------------- GUIDs, sketches, names

/** A GlobalId without the "~n" that the federation adds to a clash. */
export const stripFederation = (gid: string): string => (gid.indexOf('~') < 0 ? gid : gid.replace(/~\d+$/, ''));

/** 32-bit FNV-1a with a final avalanche, so the sketch is not biased by the base-64 alphabet of a GUID. */
export function hash32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return h >>> 0;
}

/** Bottom-k minhash: the k smallest distinct hashes of the (federation-stripped) GlobalIds, ascending. */
export function guidSketch(ids: Iterable<string>, k = SKETCH_SIZE): Uint32Array {
  const set = new Set<number>();
  for (const id of ids) set.add(hash32(stripFederation(id)));
  const all = Uint32Array.from(set);
  all.sort();
  return all.length > k ? all.slice(0, k) : all;
}

/**
 * Estimated Jaccard index of two GUID sets from their bottom-k sketches: of the k smallest hashes of the union, the share that both
 * sets hold. Exact when both sets have at most k elements.
 */
export function sketchJaccard(a: Uint32Array, b: Uint32Array, k = SKETCH_SIZE): number {
  if (a.length === 0 || b.length === 0) return 0;
  let i = 0, j = 0, taken = 0, both = 0;
  while (taken < k && (i < a.length || j < b.length)) {
    const x = i < a.length ? a[i]! : Infinity;
    const y = j < b.length ? b[j]! : Infinity;
    if (x === y) { both++; i++; j++; } else if (x < y) i++; else j++;
    taken++;
  }
  return taken === 0 ? 0 : both / taken;
}

/** A file name without its extension, copy number, "rev X", "_vN" and dates: two revisions of one model share it. */
export function nameStemOfFile(name: string): string {
  let s = name.toLowerCase().replace(/^.*[\\/]/, '');
  s = s.replace(/\.(ifczip|ifc|zip|glb|json)$/i, '');
  s = s.replace(/\(\d+\)/g, ' ');
  s = s.replace(/\d{4}[-_.]\d{1,2}[-_.]\d{1,2}|\d{1,2}[-_.]\d{1,2}[-_.]\d{4}|\b\d{8}\b/g, ' ');
  s = s.replace(/(^|[\s_.-])rev(?:ision)?[\s_.-]*[a-z0-9]+/g, ' ');
  s = s.replace(/(^|[\s_.-])v\d+(?:\.\d+)*(?=$|[\s_.-])/g, ' ');
  return s.replace(/[^a-z0-9]+/g, ' ').trim();
}

export const sameStem = (a: string, b: string): boolean => {
  const x = nameStemOfFile(a);
  return x !== '' && x === nameStemOfFile(b);
};

export function classHistogramOf(classes: Iterable<string>): Record<string, number> {
  const h: Record<string, number> = {};
  for (const c of classes) h[c] = (h[c] ?? 0) + 1;
  return h;
}

/** Cosine similarity of two class histograms, 0 to 1. */
export function histogramSimilarity(a: Record<string, number>, b: Record<string, number>): number {
  let dot = 0, na = 0, nb = 0;
  for (const [k, v] of Object.entries(a)) { na += v * v; dot += v * (b[k] ?? 0); }
  for (const v of Object.values(b)) nb += v * v;
  return na === 0 || nb === 0 ? 0 : dot / Math.sqrt(na * nb);
}

// ---------------------------------------------------------------- results

/** A result with the probabilities of each part cut to the three most likely codes. */
export function trimResult(r: ClassifyResult): ClassifyResult {
  const top = (p: Record<string, number>): Record<string, number> => Object.fromEntries(Object.entries(p).sort((x, y) => y[1] - x[1] || (x[0] < y[0] ? -1 : 1)).slice(0, 3));
  const choice = (c: ChoiceResult): ChoiceResult => ({ ...c, probabilities: top(c.probabilities) });
  return {
    ...r,
    discipline: choice(r.discipline),
    subDiscipline: r.subDiscipline ? choice(r.subDiscipline) : null,
    masterformat: r.masterformat ? { ...r.masterformat, probabilities: top(r.masterformat.probabilities) } : null,
  };
}

// ---------------------------------------------------------------- snapshotOf

export interface SnapshotInput {
  name: string;
  /** The model's elements, storeys, systems, hosts and origin shift. */
  model: Pick<SceneModel, 'elements' | 'storeys' | 'relations' | 'byGlobalId' | 'originShift'> & Partial<SceneModel>;
  /** computeSignatures over the model's geometry (11 floats per element, element order). Omitted: all zero (no geometry). */
  sig?: Float32Array;
  results?: (globalId: string) => ClassifyResult | null | undefined;
  schemaHash: string;
  reviewFingerprint: string;
  savedAt?: string;
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

/** viewer-axis bounds [x0,y0,z0,x1,y1,z1] to IFC axes (x, -z, y), relative to the origin shift. Zeros when there is no geometry. */
function ifcBounds(b: readonly number[] | undefined, out: Float32Array, o: number): void {
  if (!b || b.length < 6 || !b.every(Number.isFinite)) { for (let k = 0; k < 6; k++) out[o + k] = 0; return; }
  out[o] = b[0]!; out[o + 1] = -b[5]!; out[o + 2] = b[1]!;
  out[o + 3] = b[3]!; out[o + 4] = -b[2]!; out[o + 5] = b[4]!;
}

export function snapshotOf(inp: SnapshotInput): ModelSnapshot {
  const m = inp.model;
  const els = m.elements;
  const n = els.length;
  const systems = new Map<number, string[]>();
  for (const s of m.relations.systems) for (const id of s.elements) (systems.get(id) ?? systems.set(id, []).get(id)!).push(s.name);
  const storeys = new Map(m.storeys.map((s) => [s.id, s]));
  const snap: ModelSnapshot = {
    schema: 'xray-model-snapshot/1',
    identity: modelIdentity(inp.name, n, els.map((e) => e.globalId).filter(Boolean)),
    savedAt: inp.savedAt ?? new Date().toISOString(),
    classificationSchemaHash: inp.schemaHash,
    reviewFingerprint: inp.reviewFingerprint,
    originShift: [m.originShift[0], m.originShift[1], m.originShift[2]],
    guidSketch: guidSketch(els.map((e) => e.globalId)),
    classHistogram: classHistogramOf(els.map((e) => e.ifcClass)),
    globalId: new Array<string>(n), ifcClass: new Array<string>(n), name: new Array<string>(n), tag: new Array<string>(n),
    typeName: new Array<string>(n), material: new Array<string>(n),
    storey: new Array<ModelSnapshot['storey'][number]>(n), systems: new Array<string[]>(n),
    classifySignature: new Array<string>(n), props: new Array<Record<string, PropValue> | null>(n),
    bounds: new Float32Array(n * 6), sig: new Float32Array(n * SIG_STRIDE),
    results: new Array<ClassifyResult | null>(n),
  };
  if (inp.sig) snap.sig.set(inp.sig.subarray(0, n * SIG_STRIDE));
  for (let i = 0; i < n; i++) {
    const e = els[i]!;
    snap.globalId[i] = e.globalId;
    snap.ifcClass[i] = e.ifcClass;
    snap.name[i] = e.name ?? '';
    snap.tag[i] = str(e.props?.['Attr.Tag']);
    snap.typeName[i] = str(e.props?.['Attr.ObjectType']);
    snap.material[i] = e.material ?? '';
    const st = e.storey === null ? undefined : storeys.get(e.storey);
    snap.storey[i] = st ? { name: st.name, elevation: st.elevation } : null;
    snap.systems[i] = [...(systems.get(e.id) ?? [])].sort();
    const input = buildInput(m as SceneModel, e.id);
    snap.classifySignature[i] = input ? signatureOf(input) : '';
    snap.props[i] = e.props && Object.keys(e.props).length ? { ...e.props } : null;
    ifcBounds(e.bounds, snap.bounds, i * 6);
    const r = inp.results?.(e.globalId);
    snap.results[i] = r ? trimResult(r) : null;
  }
  return snap;
}

/** The world (IFC frame) centroid of element i, in Float64: relative centroid plus the origin shift. */
export function worldCentroid(s: ModelSnapshot, i: number): Vec3 {
  const o = i * SIG_STRIDE;
  return [s.sig[o + 2]! + s.originShift[0], s.sig[o + 3]! + s.originShift[1], s.sig[o + 4]! + s.originShift[2]];
}

export const snapshotKey = (s: Pick<ModelSnapshot, 'identity'>): string => identityKey(s.identity);

const isCommitted = (r: ClassifyResult | null): boolean => !!r && (r.source === 'confirmed' || r.source === 'corrected');

// ---------------------------------------------------------------- encode and decode

const MAGIC = 0x31535258; // "XRS1"

async function gzip(bytes: Uint8Array): Promise<Uint8Array> {
  if (typeof CompressionStream === 'undefined') return bytes;
  const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new CompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function gunzip(bytes: Uint8Array): Promise<Uint8Array> {
  if (bytes.length < 2 || bytes[0] !== 0x1f || bytes[1] !== 0x8b) return bytes;
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot read a compressed snapshot (DecompressionStream is missing).');
  const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** gzip( magic, header length, header JSON (all columns), guid sketch, bounds, sig ). */
export async function encodeSnapshot(s: ModelSnapshot): Promise<Blob> {
  const { guidSketch: sk, bounds, sig, ...rest } = s;
  const header = new TextEncoder().encode(JSON.stringify({ ...rest, counts: { sketch: sk.length, bounds: bounds.length, sig: sig.length } }));
  const pad = (4 - (header.length % 4)) % 4;
  const total = 8 + header.length + pad + sk.byteLength + bounds.byteLength + sig.byteLength;
  const buf = new ArrayBuffer(total);
  const dv = new DataView(buf);
  dv.setUint32(0, MAGIC, true);
  dv.setUint32(4, header.length + pad, true);
  const u8 = new Uint8Array(buf);
  u8.set(header, 8);
  u8.fill(0x20, 8 + header.length, 8 + header.length + pad); // spaces: the padding stays valid JSON whitespace
  let o = 8 + header.length + pad;
  u8.set(new Uint8Array(sk.buffer, sk.byteOffset, sk.byteLength), o); o += sk.byteLength;
  u8.set(new Uint8Array(bounds.buffer, bounds.byteOffset, bounds.byteLength), o); o += bounds.byteLength;
  u8.set(new Uint8Array(sig.buffer, sig.byteOffset, sig.byteLength), o);
  return new Blob([(await gzip(u8)) as BlobPart], { type: 'application/octet-stream' });
}

export async function decodeSnapshot(body: Blob | ArrayBuffer | Uint8Array): Promise<ModelSnapshot> {
  const raw = body instanceof Blob ? new Uint8Array(await body.arrayBuffer()) : body instanceof Uint8Array ? body : new Uint8Array(body);
  const u8 = await gunzip(raw);
  const copy = u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength) as ArrayBuffer; // aligned for the typed views
  const dv = new DataView(copy);
  if (copy.byteLength < 8 || dv.getUint32(0, true) !== MAGIC) throw new Error('This is not a model snapshot.');
  const hlen = dv.getUint32(4, true);
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(copy, 8, hlen))) as Omit<ModelSnapshot, 'guidSketch' | 'bounds' | 'sig'> & { counts: { sketch: number; bounds: number; sig: number } };
  if (head.schema !== 'xray-model-snapshot/1') throw new Error('This snapshot has an unknown format.');
  let o = 8 + hlen;
  const { counts, ...cols } = head;
  const sk = new Uint32Array(copy, o, counts.sketch); o += counts.sketch * 4;
  const bounds = new Float32Array(copy, o, counts.bounds); o += counts.bounds * 4;
  const sig = new Float32Array(copy, o, counts.sig);
  return { ...cols, guidSketch: sk, bounds, sig };
}

/** The small record that detection reads, with the encoded body. */
export async function recordOf(s: ModelSnapshot): Promise<SnapshotRecord> {
  const body = await encodeSnapshot(s);
  return {
    key: snapshotKey(s),
    identity: s.identity,
    name: s.identity.name,
    savedAt: s.savedAt,
    counts: { elements: s.globalId.length, results: s.results.filter(Boolean).length, committed: s.results.filter(isCommitted).length },
    guidSketch: s.guidSketch,
    classHistogram: s.classHistogram,
    body,
    size: body.size,
    classificationSchemaHash: s.classificationSchemaHash,
  };
}

// ---------------------------------------------------------------- detection (3.1)

export interface CandidateTarget {
  identity: ModelIdentity;
  guidSketch: Uint32Array;
  classHistogram: Record<string, number>;
}

export interface RevisionCandidate {
  key: string;
  name: string;
  savedAt: string;
  reason: 'same-name' | 'shared-guids' | 'regenerated-guids';
  /** The first two reasons are strong, the third (only the name stem and the class mix agree) is weak. */
  strength: 'strong' | 'weak';
  /** Estimated share of the union of GUIDs that both hold (0 to 1). */
  overlap: number;
  similarity: number;
  /** For the banner: "This looks like a revision of <name> (saved <date>, <n> reviewed)". */
  reviewed: number;
  message: string;
}

/**
 * The stored snapshots that the model just opened may be a revision of, newest first (3.1). A snapshot of the same model (same
 * identity key) is not a candidate. Reads only the small record fields.
 */
export function revisionCandidates(records: readonly Pick<SnapshotRecord, 'key' | 'identity' | 'name' | 'savedAt' | 'guidSketch' | 'classHistogram' | 'counts'>[], now: CandidateTarget, o: Partial<Pick<RevisionOptions, 'candidateOverlap' | 'candidateStemSimilarity'>> = {}): RevisionCandidate[] {
  const overlapMin = o.candidateOverlap ?? DEFAULT_REVISION_OPTIONS.candidateOverlap;
  const stemMin = o.candidateStemSimilarity ?? DEFAULT_REVISION_OPTIONS.candidateStemSimilarity;
  const nowKey = identityKey(now.identity);
  const out: RevisionCandidate[] = [];
  for (const r of [...records].sort((a, b) => (a.savedAt < b.savedAt ? 1 : a.savedAt > b.savedAt ? -1 : 0))) {
    if (r.key === nowKey) continue;
    const jac = sketchJaccard(r.guidSketch, now.guidSketch);
    const sim = histogramSimilarity(r.classHistogram, now.classHistogram);
    const base = { key: r.key, name: r.name, savedAt: r.savedAt, overlap: jac, similarity: sim, reviewed: r.counts.committed };
    const saved = r.savedAt.slice(0, 10);
    const lead = `This looks like a revision of ${r.name} (saved ${saved}, ${r.counts.committed} reviewed)`;
    if (compareModels(r.identity, now.identity).match === 'revised') out.push({ ...base, reason: 'same-name', strength: 'strong', message: `${lead}: same file name, different content.` });
    else if (jac >= overlapMin) out.push({ ...base, reason: 'shared-guids', strength: 'strong', message: `${lead}: it shares ${Math.round(jac * 100)} % of its elements.` });
    else if (sameStem(r.name, now.identity.name) && sim >= stemMin) out.push({ ...base, reason: 'regenerated-guids', strength: 'weak', message: `${lead}: similar name and the same kinds of elements, but the element ids were regenerated.` });
  }
  return out;
}
