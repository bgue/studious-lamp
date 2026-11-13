// web-ifc side of the IFC reader: `extractIfc` turns one IFC file into a neutral RawModel (see ifcShared.ts).
// Runs inside the module worker (ifcWorker.ts) or, as a fallback, on the main thread. Nothing here touches the DOM.
//
// web-ifc facts this code relies on (0.0.78, checked against the node build and the browser build):
//  - StreamMeshes() gives, per product, PlacedGeometry { color, geometryExpressID, flatTransformation } where the vertex
//    buffer is interleaved [x y z nx ny nz] in the geometry's local frame, and flatTransformation (column-major 4x4)
//    already contains the file's length unit scale and a Y-up swap: world_y_up = (x, z, -y) of the IFC frame.
//    We undo the swap so RawModel is in the IFC frame (Z up, metres) as the converter's inputs are.
//  - Vertices are not shared between triangles and normals are flat per face, so we weld and crease-smooth ourselves.
//  - Type codes are the same in IFC2X3, IFC4 and IFC4X3 (CRC of the entity name).
import * as WebIFC from 'web-ifc';
import type { IfcAPI } from 'web-ifc';
import type { MapConversion } from '../types';
import { mapConversionFrom } from './ifcMap';
import { isMarker, isSkippedClass, SYSTEM_CLASSES, smoothMesh } from './ifcShared';
import type { IfcProgress, RawElement, RawModel, RawStorey } from './ifcShared';
import {
  SI_SCALES, attributeEntries, finalizeProps, normalizeNumber, propertyGroup, quantityGroup,
} from './ifcProps';
import type { PropEntry, PropValue, PropsMode, UnitScales } from './ifcProps';

export type WasmSource = { url: string } | { bytes: ArrayBuffer | Uint8Array };

export interface ExtractHooks {
  onProgress?(p: IfcProgress): void;
  /** Checked between chunks; return true to stop with an AbortError. */
  cancelled?(): boolean;
  /** Awaited between chunks (main-thread fallback hands the event loop back here). */
  yieldNow?(): Promise<void>;
  /** Which element properties to read (see ifcProps.ts). Default `common`. */
  props?: PropsMode;
}

export class IfcReadError extends Error {
  constructor(message: string, readonly code: 'invalid' | 'empty' | 'no-geometry' | 'cancelled' | 'wasm') {
    super(message);
    this.name = 'IfcReadError';
  }
}

/** Create and initialise a web-ifc API object. `wasm.bytes` is served through a Blob URL (single-file bundle). */
export async function createIfcApi(wasm: WasmSource): Promise<IfcAPI> {
  const api = new WebIFC.IfcAPI();
  let url: string;
  if ('bytes' in wasm) {
    const bytes = wasm.bytes instanceof Uint8Array ? wasm.bytes : new Uint8Array(wasm.bytes);
    url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: 'application/wasm' }));
  } else {
    url = wasm.url;
  }
  try {
    // forceSingleThread: the multithreaded build needs cross-origin isolation, which a plain page or file:// does not have.
    await api.Init((path: string, prefix: string) => (path.endsWith('.wasm') ? url : prefix + path), true);
  } catch (e) {
    throw new IfcReadError(`Could not start the IFC reader: ${e instanceof Error ? e.message : String(e)}`, 'wasm');
  }
  try {
    api.SetLogLevel(WebIFC.LogLevel.LOG_LEVEL_OFF);
  } catch { /* older API */ }
  return api;
}

/**
 * web-ifc 0.0.78 quirk: the JS wrapper's StreamMeshes passes a 4th argument (applyLinearScalingFactor), but the browser
 * build of web-ifc.wasm only declares 3 and embind throws "called with 4 arguments, expected 3" (the node wasm takes 4).
 * Try the wrapper, and on that error call the wasm function directly with the 3-argument form (scaling is applied by
 * default there too: positions come out in metres either way).
 */
let streamThreeArgs = false;
function streamMeshes(api: IfcAPI, model: number, ids: number[], cb: (mesh: WebIFC.FlatMesh) => void): void {
  if (!streamThreeArgs) {
    try {
      api.StreamMeshes(model, ids, cb);
      return;
    } catch (e) {
      if (!/called with 4 arguments/.test(e instanceof Error ? e.message : String(e))) throw e;
      streamThreeArgs = true;
    }
  }
  (api.wasmModule as { StreamMeshes(m: number, ids: number[], cb: unknown): void }).StreamMeshes(model, ids, cb);
}

// ---------------------------------------------------------------- small readers over web-ifc line objects

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Line = any;

function val(x: Line): Line {
  if (x === null || x === undefined) return null;
  if (typeof x === 'object' && 'value' in x) return x.value;
  return x;
}
const str = (x: Line): string => {
  const v = val(x);
  return v === null || v === undefined ? '' : String(v);
};
const refId = (x: Line): number | null => {
  const v = val(x);
  return typeof v === 'number' ? v : null;
};
const refList = (x: Line): number[] => {
  const out: number[] = [];
  if (Array.isArray(x)) for (const r of x) { const n = refId(r); if (n !== null) out.push(n); }
  return out;
};
const num = (x: Line): number | null => {
  const v = val(x);
  if (typeof v === 'number') return v;
  if (x && typeof x === 'object' && typeof x._representationValue === 'number') return x._representationValue;
  return null;
};

function ids(api: IfcAPI, model: number, type: number, inherited = false): number[] {
  let vec;
  try {
    vec = api.GetLineIDsWithType(model, type, inherited);
  } catch {
    return [];
  }
  const out: number[] = new Array(vec.size());
  for (let i = 0; i < out.length; i++) out[i] = vec.get(i);
  return out;
}

const PREFIX: Record<string, number> = {
  EXA: 1e18, PETA: 1e15, TERA: 1e12, GIGA: 1e9, MEGA: 1e6, KILO: 1e3, HECTO: 1e2, DECA: 10,
  DECI: 0.1, CENTI: 0.01, MILLI: 0.001, MICRO: 1e-6, NANO: 1e-9,
};

/** Metres per file length unit (for storey elevations; geometry is already scaled by web-ifc). */
function lengthScale(api: IfcAPI, model: number): number {
  try {
    const proj = ids(api, model, WebIFC.IFCPROJECT)[0];
    if (proj === undefined) return 1;
    const ua = api.GetLine(model, refId(api.GetLine(model, proj).UnitsInContext) ?? -1);
    for (const u of refList(ua?.Units)) {
      const line = api.GetLine(model, u);
      if (str(line?.UnitType) !== 'LENGTHUNIT') continue;
      const typeName = api.GetNameFromTypeCode(line.type);
      if (typeName === 'IfcSIUnit') return PREFIX[str(line.Prefix)] ?? 1;
      if (typeName === 'IfcConversionBasedUnit') {
        const mwu = api.GetLine(model, refId(line.ConversionFactor) ?? -1);
        const f = num(mwu?.ValueComponent) ?? 1;
        const base = api.GetLine(model, refId(mwu?.UnitComponent) ?? -1);
        return f * (base ? (PREFIX[str(base.Prefix)] ?? 1) : 1);
      }
    }
  } catch { /* fall through */ }
  return 1;
}


/** Metres per unit of an IfcNamedUnit line (SI with prefix, or conversion based); 1 when it cannot be told. */
function unitFactor(api: IfcAPI, model: number, unitId: number | null): number {
  if (unitId === null) return 1;
  try {
    const line = api.GetLine(model, unitId);
    if (!line) return 1;
    const typeName = api.GetNameFromTypeCode(line.type);
    if (typeName === 'IfcSIUnit') return PREFIX[str(line.Prefix)] ?? 1;
    if (typeName === 'IfcConversionBasedUnit') {
      const mwu = api.GetLine(model, refId(line.ConversionFactor) ?? -1);
      const f = num(mwu?.ValueComponent) ?? 1;
      const base = api.GetLine(model, refId(mwu?.UnitComponent) ?? -1);
      return f * (base ? (PREFIX[str(base.Prefix)] ?? 1) : 1);
    }
  } catch { /* metres */ }
  return 1;
}

/** The first IfcMapConversion of the file with its IfcProjectedCRS (IFC4 and later), in metres; undefined when there is none. */
function readMapConversion(api: IfcAPI, model: number, lengthUnit: number): MapConversion | undefined {
  try {
    for (const id of ids(api, model, WebIFC.IFCMAPCONVERSION)) {
      const c = api.GetLine(model, id);
      if (!c) continue;
      const crsId = refId(c.TargetCRS);
      const crs = crsId !== null ? api.GetLine(model, crsId) : null;
      const mapUnit = unitFactor(api, model, crs ? refId(crs.MapUnit) : null);
      const m = mapConversionFrom({
        Eastings: num(c.Eastings), Northings: num(c.Northings), OrthogonalHeight: num(c.OrthogonalHeight),
        XAxisAbscissa: num(c.XAxisAbscissa), XAxisOrdinate: num(c.XAxisOrdinate), Scale: num(c.Scale),
      }, crs ? { Name: str(crs.Name) } : null, { mapUnit, lengthUnit });
      if (m) return m;
    }
  } catch { /* a file without the IFC4 map entities */ }
  return undefined;
}

/** SI factors of the project units (LENGTH, AREA, VOLUME, MASS) as tools/glb_common.py `unit_scales` computes them. */
function unitScales(api: IfcAPI, model: number): UnitScales {
  const out: UnitScales = { ...SI_SCALES };
  try {
    const proj = ids(api, model, WebIFC.IFCPROJECT)[0];
    if (proj === undefined) return out;
    const ua = api.GetLine(model, refId(api.GetLine(model, proj).UnitsInContext) ?? -1);
    for (const u of refList(ua?.Units)) {
      const line = api.GetLine(model, u);
      const kind = { LENGTHUNIT: 'length', AREAUNIT: 'area', VOLUMEUNIT: 'volume', MASSUNIT: 'mass' }[str(line?.UnitType)] as keyof UnitScales | undefined;
      if (!kind) continue;
      const typeName = api.GetNameFromTypeCode(line.type);
      if (typeName === 'IfcSIUnit') {
        out[kind] = (PREFIX[str(line.Prefix)] ?? 1) * (str(line.Name) === 'GRAM' ? 0.001 : 1);
      } else if (typeName === 'IfcConversionBasedUnit') {
        const mwu = api.GetLine(model, refId(line.ConversionFactor) ?? -1);
        const f = num(mwu?.ValueComponent) ?? 1;
        const base = api.GetLine(model, refId(mwu?.UnitComponent) ?? -1);
        out[kind] = f * (base ? (PREFIX[str(base.Prefix)] ?? 1) * (str(base.Name) === 'GRAM' ? 0.001 : 1) : 1);
      }
    }
  } catch { /* SI defaults */ }
  return out;
}

/** An IfcValue (`{ name: 'IFCLABEL', value }` or `{ name, _representationValue }`) as a property value, or null. */
function propValue(x: Line, scales: UnitScales): PropValue | null {
  if (x === null || x === undefined || typeof x !== 'object') return null;
  const name = String(x.name ?? '');
  const v = x.value;
  if (typeof v === 'boolean') return v;
  if (name === 'IFCLOGICAL' || name === 'IFCBOOLEAN') {
    if (v === 'T' || v === '.T.') return true;
    if (v === 'F' || v === '.F.') return false;
    return null;
  }
  if (typeof v === 'string') return v === '' ? null : v;
  const n = typeof x._representationValue === 'number' ? x._representationValue : typeof v === 'number' ? v : null;
  return n === null ? null : normalizeNumber(name, n, scales);
}

const QTY_VALUE: Record<string, [string, string]> = {
  IfcQuantityLength: ['LengthValue', 'IFCLENGTHMEASURE'],
  IfcQuantityArea: ['AreaValue', 'IFCAREAMEASURE'],
  IfcQuantityVolume: ['VolumeValue', 'IFCVOLUMEMEASURE'],
  IfcQuantityCount: ['CountValue', 'IFCCOUNTMEASURE'],
  IfcQuantityWeight: ['WeightValue', 'IFCMASSMEASURE'],
  IfcQuantityTime: ['TimeValue', 'IFCTIMEMEASURE'],
};

/**
 * One pass over IfcRelDefinesByProperties builds element -> definitions; each property set / quantity set is parsed once
 * and shared by every element it describes. Mirrors tools/ifc2glb.py `element_props`.
 */
function readProps(
  api: IfcAPI, model: number, mode: PropsMode, exported: Set<number>, attrs: Map<number, PropEntry[]>,
  line: (eid: number) => Line,
): Map<number, Record<string, PropValue>> {
  const out = new Map<number, Record<string, PropValue>>();
  if (mode === 'none') return out;
  const scales = unitScales(api, model);
  const defsOf = new Map<number, number[]>();
  for (const rid of ids(api, model, WebIFC.IFCRELDEFINESBYPROPERTIES).sort((a, b) => a - b)) {
    const r = line(rid);
    if (!r) continue;
    const d = refId(r.RelatingPropertyDefinition);
    if (d === null) continue;
    for (const o of refList(r.RelatedObjects)) {
      if (!exported.has(o)) continue;
      let list = defsOf.get(o);
      if (!list) defsOf.set(o, (list = []));
      list.push(d);
    }
  }
  const cache = new Map<number, PropEntry[]>();
  const parse = (did: number): PropEntry[] => {
    const hit = cache.get(did);
    if (hit) return hit;
    const entries: PropEntry[] = [];
    cache.set(did, entries);
    const d = line(did);
    if (!d) return entries;
    const t = api.GetNameFromTypeCode(d.type);
    const setName = str(d.Name) || (t === 'IfcPropertySet' ? 'Pset' : 'Qto');
    if (t === 'IfcPropertySet') {
      for (const pid of refList(d.HasProperties)) {
        const p = line(pid);
        if (!p) continue;
        const pt = api.GetNameFromTypeCode(p.type);
        const pname = str(p.Name);
        const group = propertyGroup(setName, mode);
        if (group === null || !pname) continue;
        let value: PropValue | null = null;
        if (pt === 'IfcPropertySingleValue') value = propValue(p.NominalValue, scales);
        else if (pt === 'IfcPropertyEnumeratedValue' && Array.isArray(p.EnumerationValues)) {
          const parts = p.EnumerationValues.map((x: Line) => propValue(x, scales)).filter((x: PropValue | null) => x !== null);
          if (parts.length > 0) value = parts.join(', ');
        }
        if (value !== null) entries.push({ key: `${setName}.${pname}`, value, group });
      }
    } else if (t === 'IfcElementQuantity') {
      for (const qid of refList(d.Quantities)) {
        const q = line(qid);
        if (!q) continue;
        const spec = QTY_VALUE[api.GetNameFromTypeCode(q.type)];
        const qname = str(q.Name);
        if (!spec || !qname) continue;
        const group = quantityGroup(setName, qname, mode);
        if (group === null) continue;
        const raw = num(q[spec[0]]);
        if (raw === null) continue;
        const value = normalizeNumber(spec[1], raw, scales);
        if (value !== null) entries.push({ key: `${setName}.${qname}`, value, group });
      }
    }
    return entries;
  };
  for (const eid of exported) {
    const entries: PropEntry[] = [...(attrs.get(eid) ?? [])];
    for (const did of defsOf.get(eid) ?? []) entries.push(...parse(did));
    const props = finalizeProps(entries);
    if (props) out.set(eid, props);
  }
  return out;
}

// ---------------------------------------------------------------- geometry of one product

/** embind vectors need delete() in the browser build; the node build hands out plain objects. */
function freeVector(v: unknown): void {
  (v as { delete?: () => void }).delete?.();
}

interface Built {
  positions: Float32Array;
  indices: Uint32Array;
  color: [number, number, number, number] | null;
  white: boolean;
}

/** Origin chosen from the first vertex of the first element; fixed afterwards so all positions share it. */
interface Frame { origin: [number, number, number] | null }

function buildElementMesh(api: IfcAPI, model: number, mesh: WebIFC.FlatMesh, frame: Frame): Built | null {
  const geoms = mesh.geometries;
  const n = geoms.size();
  interface Piece { vd: Float32Array; ix: Uint32Array; m: number[]; flip: boolean; col: string; rgba: [number, number, number, number] }
  const pieces: Piece[] = [];
  let nv = 0;
  let nt = 0;
  for (let k = 0; k < n; k++) {
    const pg = geoms.get(k);
    const geo = api.GetGeometry(model, pg.geometryExpressID);
    try {
      const vdSize = geo.GetVertexDataSize();
      const ixSize = geo.GetIndexDataSize();
      if (vdSize < 18 || ixSize < 3) continue;
      // copy out of the WASM heap before anything else can grow it
      const vd = api.GetVertexArray(geo.GetVertexData(), vdSize).slice();
      const ix = api.GetIndexArray(geo.GetIndexData(), ixSize).slice();
      const m = Array.from(pg.flatTransformation);
      const det = m[0]! * (m[5]! * m[10]! - m[6]! * m[9]!) - m[4]! * (m[1]! * m[10]! - m[2]! * m[9]!) + m[8]! * (m[1]! * m[6]! - m[2]! * m[5]!);
      const c = pg.color;
      const rgba: [number, number, number, number] = [c.x, c.y, c.z, c.w];
      pieces.push({ vd, ix, m, flip: det < 0, col: rgba.map((x) => x.toFixed(4)).join(','), rgba });
      nv += vd.length / 6;
      nt += ix.length / 3;
    } finally {
      geo.delete?.();
    }
  }
  freeVector(geoms);
  if (nt === 0) return null;

  const positions = new Float32Array(nv * 3);
  const indices = new Uint32Array(nt * 3);
  let vo = 0;
  let io = 0;
  const trisByColour = new Map<string, { n: number; rgba: [number, number, number, number] }>();
  for (const p of pieces) {
    const m = p.m;
    const cnt = p.vd.length / 6;
    for (let i = 0; i < cnt; i++) {
      const x = p.vd[i * 6]!, y = p.vd[i * 6 + 1]!, z = p.vd[i * 6 + 2]!;
      const X = m[0]! * x + m[4]! * y + m[8]! * z + m[12]!;
      const Y = m[1]! * x + m[5]! * y + m[9]! * z + m[13]!;
      const Z = m[2]! * x + m[6]! * y + m[10]! * z + m[14]!;
      // web-ifc Y-up -> IFC Z-up: (X, Y, Z) -> (X, -Z, Y)
      const wx = X, wy = -Z, wz = Y;
      if (frame.origin === null) frame.origin = [Math.round(wx), Math.round(wy), Math.round(wz)];
      const o = (vo + i) * 3;
      positions[o] = wx - frame.origin[0];
      positions[o + 1] = wy - frame.origin[1];
      positions[o + 2] = wz - frame.origin[2];
    }
    const tris = p.ix.length / 3;
    for (let t = 0; t < tris; t++) {
      const o = io + t * 3;
      indices[o] = p.ix[t * 3]! + vo;
      indices[o + 1] = p.ix[t * 3 + (p.flip ? 2 : 1)]! + vo;
      indices[o + 2] = p.ix[t * 3 + (p.flip ? 1 : 2)]! + vo;
    }
    vo += cnt;
    io += tris * 3;
    const e = trisByColour.get(p.col);
    if (e) e.n += tris;
    else trisByColour.set(p.col, { n: tris, rgba: p.rgba });
  }
  // dominant colour = the one covering most triangles (the converter takes the dominant material by face count)
  let best: { n: number; rgba: [number, number, number, number] } | null = null;
  for (const e of trisByColour.values()) if (!best || e.n > best.n) best = e;
  const rgba = best ? best.rgba : null;
  const white = !!rgba && rgba[0] === 1 && rgba[1] === 1 && rgba[2] === 1 && rgba[3] === 1;
  return { positions, indices, color: rgba, white };
}

// ---------------------------------------------------------------- extraction

const CHUNK = 48;

export async function extractIfc(api: IfcAPI, data: Uint8Array, fileName: string, hooks: ExtractHooks = {}): Promise<RawModel> {
  const progress = (p: IfcProgress): void => hooks.onProgress?.(p);
  const check = async (): Promise<void> => {
    if (hooks.cancelled?.()) throw new IfcReadError('Load cancelled', 'cancelled');
    if (hooks.yieldNow) await hooks.yieldNow();
  };

  if (data.length === 0) throw new IfcReadError(`${fileName} is empty`, 'empty');
  const head = new TextDecoder('latin1').decode(data.subarray(0, Math.min(data.length, 4096)));
  if (!/ISO-10303-21/i.test(head)) {
    throw new IfcReadError(`${fileName} is not a valid IFC file (no ISO-10303-21 header)`, 'invalid');
  }
  progress({ phase: 'open', file: fileName, bytes: data.length });
  await check();

  const model = api.OpenModel(data, { COORDINATE_TO_ORIGIN: false });
  if (model < 0) throw new IfcReadError(`${fileName} could not be parsed as IFC`, 'invalid');
  try {
    return await extractModel(api, model, fileName, progress, check, hooks.props ?? 'common');
  } finally {
    try { api.CloseModel(model); } catch { /* already closed */ }
  }
}

async function extractModel(
  api: IfcAPI, model: number, fileName: string,
  progress: (p: IfcProgress) => void, check: () => Promise<void>, propsMode: PropsMode,
): Promise<RawModel> {
  let schema = 'IFC';
  try { schema = api.GetModelSchema(model); } catch { /* keep */ }

  const className = (eid: number): string => {
    try { return api.GetNameFromTypeCode(api.GetLineType(model, eid)); } catch { return ''; }
  };
  const line = (eid: number): Line => {
    try { return api.GetLine(model, eid); } catch { return null; }
  };

  // ---- candidates: every IfcProduct (subtypes included) whose class is not skipped
  const products = ids(api, model, WebIFC.IFCPRODUCT, true).sort((a, b) => a - b);
  if (products.length === 0 && ids(api, model, WebIFC.IFCPROJECT).length === 0) {
    throw new IfcReadError(`${fileName} could not be parsed as IFC (no IfcProject or products found)`, 'invalid');
  }
  const stats = { products: products.length, skippedClass: 0, noGeometry: 0, markers: 0 };
  const classOf = new Map<number, string>();
  const candidates: number[] = [];
  for (const p of products) {
    const c = className(p);
    classOf.set(p, c);
    if (isSkippedClass(c)) stats.skippedClass++;
    else candidates.push(p);
  }

  // ---- styled items (for the "no style -> class colour" fallback)
  const styled = new Set<number>();
  for (const s of ids(api, model, WebIFC.IFCSTYLEDITEM)) {
    const r = refId(line(s)?.Item);
    if (r !== null) styled.add(r);
  }
  const hasStyle = (eid: number): boolean => {
    // bounded walk: product -> representations -> items (-> mapped representation items)
    let budget = 60;
    const stack: number[] = [];
    const rep = refId(line(eid)?.Representation);
    if (rep !== null) stack.push(rep);
    while (stack.length && budget-- > 0) {
      const id = stack.pop()!;
      if (styled.has(id)) return true;
      const l = line(id);
      if (!l) continue;
      const t = api.GetNameFromTypeCode(l.type);
      if (t === 'IfcProductDefinitionShape') stack.push(...refList(l.Representations));
      else if (t === 'IfcShapeRepresentation' || t === 'IfcRepresentation') stack.push(...refList(l.Items));
      else if (t === 'IfcMappedItem') {
        const src = line(refId(l.MappingSource) ?? -1);
        const mr = refId(src?.MappedRepresentation);
        if (mr !== null) stack.push(mr);
      }
    }
    return false;
  };

  // ---- geometry, chunked so progress and cancellation work
  const frame: Frame = { origin: null };
  const attrs = new Map<number, PropEntry[]>();
  const elements: RawElement[] = [];
  let done = 0;
  const total = candidates.length;
  progress({ phase: 'meshing', file: fileName, done: 0, total });
  for (let c0 = 0; c0 < candidates.length; c0 += CHUNK) {
    await check();
    const chunk = candidates.slice(c0, c0 + CHUNK);
    streamMeshes(api, model, chunk, (mesh) => {
      const eid = mesh.expressID;
      const cls = classOf.get(eid) ?? className(eid);
      const l = line(eid);
      const name = str(l?.Name);
      if (isMarker(cls, name)) {
        stats.markers++;
        freeVector(mesh.geometries);
        return;
      }
      if (propsMode !== 'none') {
        const pd = l?.PredefinedType;
        attrs.set(eid, attributeEntries({
          objectType: str(l?.ObjectType), tag: str(l?.Tag), description: str(l?.Description),
          predefinedType: pd && typeof pd === 'object' ? str(pd) : '',
        }));
      }
      const built = buildElementMesh(api, model, mesh, frame);
      if (!built) {
        stats.noGeometry++;
        return;
      }
      const sm = smoothMesh(built.positions, built.indices);
      if (sm.indices.length === 0) {
        stats.noGeometry++;
        return;
      }
      // web-ifc reports opaque white for an element without any surface style; the converter then uses the class
      // colour. A file with no IfcStyledItem at all has no styles; otherwise only white elements are checked.
      let colour = built.color;
      if (styled.size === 0 || (built.white && !hasStyle(eid))) colour = null;
      elements.push({
        expressId: eid,
        globalId: str(l?.GlobalId) || `ifc${eid}`,
        ifcClass: cls,
        name,
        storeyExpressId: null,
        materialName: '',
        color: colour,
        positions: sm.positions,
        indices: sm.indices,
        normals: sm.normals,
      });
    });
    done = Math.min(total, c0 + chunk.length);
    progress({ phase: 'meshing', file: fileName, done, total });
  }
  elements.sort((a, b) => a.expressId - b.expressId);
  if (elements.length === 0) {
    throw new IfcReadError(`${fileName} has no geometry this reader can display`, 'no-geometry');
  }
  const exported = new Set(elements.map((e) => e.expressId));

  // ---- relations
  progress({ phase: 'relations', file: fileName });
  await check();
  const rels = (type: number): Line[] => ids(api, model, type).map((i) => line(i)).filter(Boolean);

  // storeys
  const scale = lengthScale(api, model);
  const storeys: RawStorey[] = [];
  const storeySet = new Set<number>();
  for (const sid of ids(api, model, WebIFC.IFCBUILDINGSTOREY)) {
    const l = line(sid);
    if (!l) continue;
    let elev = num(l.Elevation);
    if (elev !== null) elev *= scale;
    else {
      elev = 0;
      const pl = refId(l.ObjectPlacement);
      if (pl !== null) {
        try {
          const mtx = api.GetWorldTransformMatrix(model, pl); // web-ifc frame: Y up, already in metres
          if (mtx.length >= 14) elev = mtx[13]!;
        } catch { /* 0 */ }
      }
    }
    const guid = str(l.GlobalId);
    storeys.push({ expressId: sid, ...(guid ? { globalId: guid } : {}), name: str(l.Name), elevation: elev });
    storeySet.add(sid);
  }

  const mapConversion = readMapConversion(api, model, scale);

  // containment and decomposition
  const containerOf = new Map<number, number>();
  for (const r of rels(WebIFC.IFCRELCONTAINEDINSPATIALSTRUCTURE)) {
    const s = refId(r.RelatingStructure);
    if (s === null) continue;
    for (const e of refList(r.RelatedElements)) if (!containerOf.has(e)) containerOf.set(e, s);
  }
  const parentOf = new Map<number, number>();
  const childrenOf = new Map<number, number[]>();
  const addDecomp = (parent: number | null, kids: number[], nest: boolean): void => {
    if (parent === null) return;
    for (const k of kids) {
      if (!nest || !parentOf.has(k)) parentOf.set(k, parent);
      let list = childrenOf.get(parent);
      if (!list) childrenOf.set(parent, (list = []));
      list.push(k);
    }
  };
  for (const r of rels(WebIFC.IFCRELAGGREGATES)) addDecomp(refId(r.RelatingObject), refList(r.RelatedObjects), false);
  const nestRels = rels(WebIFC.IFCRELNESTS);
  for (const r of nestRels) addDecomp(refId(r.RelatingObject), refList(r.RelatedObjects), true);

  const isSpace = (e: number): boolean => (classOf.get(e) ?? className(e)).toLowerCase() === 'ifcspace';
  const storeyOf = (eid: number): number | null => {
    let e: number | null = eid;
    const seen = new Set<number>();
    while (e !== null && !seen.has(e)) {
      seen.add(e);
      const c = containerOf.get(e);
      if (c !== undefined) {
        if (storeySet.has(c)) return c;
        if (isSpace(c)) { e = c; continue; } // element inside a space: climb via the space
      }
      const p = parentOf.get(e);
      if (p !== undefined && storeySet.has(p)) return p;
      e = p ?? null;
    }
    return null;
  };

  // materials: own association, else the element type's
  const materialOf = new Map<number, number>();
  for (const r of rels(WebIFC.IFCRELASSOCIATESMATERIAL)) {
    const m = refId(r.RelatingMaterial);
    if (m === null) continue;
    for (const o of refList(r.RelatedObjects)) if (!materialOf.has(o)) materialOf.set(o, m);
  }
  const typeOf = new Map<number, number>();
  for (const r of rels(WebIFC.IFCRELDEFINESBYTYPE)) {
    const t = refId(r.RelatingType);
    if (t === null) continue;
    for (const o of refList(r.RelatedObjects)) typeOf.set(o, t);
  }
  const matCache = new Map<number, string>();
  const materialName = (mid: number, depth = 0): string => {
    const hit = matCache.get(mid);
    if (hit !== undefined) return hit;
    let out = '';
    const l = line(mid);
    if (l && depth < 4) {
      const t = api.GetNameFromTypeCode(l.type);
      const nameOfRef = (r: Line): string => {
        const id = refId(r);
        return id === null ? '' : materialName(id, depth + 1);
      };
      if (t === 'IfcMaterial') out = str(l.Name);
      else if (t === 'IfcMaterialLayerSetUsage') out = nameOfRef(l.ForLayerSet);
      else if (t === 'IfcMaterialLayerSet') {
        out = str(l.LayerSetName) || refList(l.MaterialLayers).map((x) => nameOfRef({ value: x })).find(Boolean) || '';
      } else if (t === 'IfcMaterialLayer') out = nameOfRef(l.Material);
      else if (t === 'IfcMaterialProfileSetUsage') out = nameOfRef(l.ForProfileSet);
      else if (t === 'IfcMaterialProfileSet') {
        out = str(l.Name) || refList(l.MaterialProfiles).map((x) => nameOfRef({ value: x })).find(Boolean) || '';
      } else if (t === 'IfcMaterialProfile') out = str(l.Name) || nameOfRef(l.Material);
      else if (t === 'IfcMaterialConstituentSet') {
        out = str(l.Name) || refList(l.MaterialConstituents).map((x) => nameOfRef({ value: x })).find(Boolean) || '';
      } else if (t === 'IfcMaterialConstituent') out = nameOfRef(l.Material) || str(l.Name);
      else if (t === 'IfcMaterialList') out = refList(l.Materials).map((x) => nameOfRef({ value: x })).find(Boolean) || '';
      else out = str(l.Name);
    }
    matCache.set(mid, out);
    return out;
  };

  const propsOf = readProps(api, model, propsMode, exported, attrs, line);
  for (const el of elements) {
    const pr = propsOf.get(el.expressId);
    if (pr) el.props = pr;
    el.storeyExpressId = storeyOf(el.expressId);
    const m = materialOf.get(el.expressId) ?? (typeOf.has(el.expressId) ? materialOf.get(typeOf.get(el.expressId)!) : undefined);
    el.materialName = m !== undefined ? materialName(m) : '';
  }

  // voids and fills
  const voids: Array<[number, number]> = [];
  for (const r of rels(WebIFC.IFCRELVOIDSELEMENT)) {
    const h = refId(r.RelatingBuildingElement);
    const o = refId(r.RelatedOpeningElement);
    if (h !== null && o !== null && exported.has(h)) voids.push([h, o]);
  }
  // opening bounds (the geometry of IfcOpeningElement is never exported, only its bounds go to the sidecar)
  const openings: NonNullable<RawModel['openings']> = [];
  {
    const hostOf = new Map<number, number>();
    for (const [h, o] of voids) if (!hostOf.has(o)) hostOf.set(o, h);
    const oids = [...hostOf.keys()];
    const org = frame.origin ?? [0, 0, 0];
    for (let c0 = 0; c0 < oids.length; c0 += CHUNK) {
      await check();
      streamMeshes(api, model, oids.slice(c0, c0 + CHUNK), (mesh) => {
        const built = buildElementMesh(api, model, mesh, frame);
        if (!built) return;
        const b: [number, number, number, number, number, number] = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
        const pos = built.positions;
        for (let i = 0; i < pos.length; i += 3) {
          for (let k = 0; k < 3; k++) {
            const v = pos[i + k]! + org[k]!;
            if (v < b[k]!) b[k] = v;
            if (v > b[k + 3]!) b[k + 3] = v;
          }
        }
        openings.push({ expressId: mesh.expressID, host: hostOf.get(mesh.expressID)!, bounds: b });
      });
    }
    openings.sort((a, b) => a.expressId - b.expressId);
  }
  const fills: Array<[number, number]> = [];
  for (const r of rels(WebIFC.IFCRELFILLSELEMENT)) {
    const o = refId(r.RelatingOpeningElement);
    const f = refId(r.RelatedBuildingElement);
    if (o !== null && f !== null && exported.has(f)) fills.push([o, f]);
  }

  // ports: owner of a port = the element that nests it (IFC4) or IfcRelConnectsPortToElement (IFC2x3, deprecated in IFC4)
  const portOwner = new Map<number, number>();
  for (const r of nestRels) {
    const owner = refId(r.RelatingObject);
    if (owner === null) continue;
    for (const p of refList(r.RelatedObjects)) {
      if (className(p).toLowerCase() === 'ifcdistributionport' && !portOwner.has(p)) portOwner.set(p, owner);
    }
  }
  for (const r of rels(WebIFC.IFCRELCONNECTSPORTTOELEMENT)) {
    const p = refId(r.RelatingPort);
    const e = refId(r.RelatedElement);
    if (p !== null && e !== null && !portOwner.has(p)) portOwner.set(p, e);
  }
  const ports: Array<[number, number]> = [];
  for (const r of rels(WebIFC.IFCRELCONNECTSPORTS)) {
    const pa = refId(r.RelatingPort);
    const pb = refId(r.RelatedPort);
    if (pa === null || pb === null) continue;
    const a = portOwner.get(pa);
    const b = portOwner.get(pb);
    if (a === undefined || b === undefined || a === b || !exported.has(a) || !exported.has(b)) continue;
    ports.push([a, b]);
  }

  // systems
  const systemSet = new Set(SYSTEM_CLASSES.map((c) => c.toLowerCase()));
  const expand = (obj: number, depth = 0): number[] => {
    if (exported.has(obj)) return [obj];
    if (depth > 6) return [];
    const out: number[] = [];
    for (const k of childrenOf.get(obj) ?? []) out.push(...expand(k, depth + 1));
    return out;
  };
  const systems = new Map<string, number[]>();
  for (const r of rels(WebIFC.IFCRELASSIGNSTOGROUP)) {
    const gid = refId(r.RelatingGroup);
    if (gid === null) continue;
    if (!systemSet.has(className(gid).toLowerCase())) continue;
    const members: number[] = [];
    for (const o of refList(r.RelatedObjects)) members.push(...expand(o));
    if (members.length === 0) continue;
    const name = str(line(gid)?.Name) || `System #${gid}`;
    let list = systems.get(name);
    if (!list) systems.set(name, (list = []));
    for (const m of members) if (!list.includes(m)) list.push(m);
  }

  return {
    fileName,
    schema,
    origin: frame.origin ?? [0, 0, 0],
    elements,
    storeys,
    ...(mapConversion ? { mapConversion } : {}),
    voids,
    fills,
    openings,
    ports,
    systems: [...systems].map(([name, els]) => ({ name, elements: els })),
    stats,
  };
}

/** Every ArrayBuffer inside a RawModel, for postMessage transfer lists. */
export function rawTransferables(raw: RawModel): ArrayBuffer[] {
  const out: ArrayBuffer[] = [];
  for (const e of raw.elements) {
    out.push(e.positions.buffer as ArrayBuffer, e.indices.buffer as ArrayBuffer);
    if (e.normals) out.push(e.normals.buffer as ArrayBuffer);
  }
  return out;
}
