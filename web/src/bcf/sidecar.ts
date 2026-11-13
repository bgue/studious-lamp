// Viewer markup side file: topic pins and viewpoint annotations, stored as `<topic folder>/xray-markup.json`.
//
// BCF 2.1 and 3.0 have no field for a topic pin or for annotations. The side file keeps the BCF XML untouched, so the
// archive still validates against the official XSDs, and other BCF tools ignore it: they read markup.bcf and only the
// files it names (viewpoints, snapshots, bitmaps), and the BCF 3.0 documentation allows other files in the topic folder.
// What other tools do see is the snapshot with the annotations (and the pin) burned in and the annotated elements in the viewpoint selection
// (see write.ts). The clean snapshot is kept next to it (`xray-<viewpoint guid>-base.png`) so that a re-export burns the
// markup once, not twice.
//
// All points are IFC project coordinates (metres, Z up), the same frame as the viewpoint cameras (model.ts).
//
//   {
//     "format": "xray-bcf-markup", "version": 1, "frame": "ifc", "units": "m",
//     "topic": "<topic guid>", "pinNumber": 3,
//     "model": { "name", "elementCount", "guidCount", "guidHash" },   (the model the topic was made on, see markup/scope.ts)
//     "pin": { "position": [x, y, z], "elementGuid": "<IfcGuid>", "local": [dx, dy, dz] },
//     "viewpoints": {
//       "<viewpoint guid>": {
//         "annotations": [ { "guid", "type": "callout" | "note" | "arrow" | "rect" | "freehand", "text", "offset": [dx, dy],
//                            "anchor": { "kind": "element" | "measurement" | "point", "point": [x, y, z], "elementGuid"?,
//                                        "local"?: [dx, dy, dz],
//                                        "measurement"?: { "kind", "a", "b", "distance", "label", "elementGuids"? } },
//                            "shape"?: { "points": [[u, v], ...], "depth": d },
//                            "attach"?: { "kind": "none" | "elements" | "surface" | "measurement" | "penetration" | "region" | "lines", ... } } ],
//                            (attach: see attach.ts; a `lines` annotation of a foreign viewpoint has no shape)
//         "markupSelection": ["<IfcGuid>", ...],
//         "snapshotView": { "position", "direction", "up", "fov", "aspect" },
//         "baseSnapshot": "xray-<viewpoint guid>-base.png",
//         "derived": { "kind": "plan" | "section", "sketch": "<sketch id>", "of": "<viewpoint guid>" }
//                    (a Plan or Section viewpoint written beside a sketch's viewpoint; it has no annotations of its own)
//       }
//     }
//   }

import { ANNOTATION_TYPES, IFC_GUID_RE, isShapeType, newGuid } from './model';
import { attachGuids, cleanAttachment, cloneAttachment } from './attach';
import { cleanIdentity } from '../markup/model';
import type { ModelIdentity } from '../markup/model';
import type { BcfAnchor, BcfAnnotation, BcfDerived, BcfMeasureLink, BcfPin, BcfShape, BcfSnapshotView, BcfTopic, BcfVersion, BcfViewpointRef, Vec3 } from './model';

export const SIDECAR_NAME = 'xray-markup.json';
export const SIDECAR_FORMAT = 'xray-bcf-markup';
export const SIDECAR_VERSION = 1;

export interface SidecarViewpoint {
  annotations?: BcfAnnotation[];
  snapshotView?: BcfSnapshotView;
  /** File name (in the topic folder) of the snapshot without the burned-in markup. */
  baseSnapshot?: string;
  /** IfcGuids in the viewpoint Selection only because annotations point at them (not selected on apply here). */
  markupSelection?: string[];
  /** This viewpoint is a Plan or Section view derived from another viewpoint's sketch (see src/issues/derivedViews.ts). */
  derived?: BcfDerived;
}

export interface Sidecar {
  format: typeof SIDECAR_FORMAT;
  version: number;
  frame: 'ifc';
  units: 'm';
  topic: string;
  pinNumber?: number;
  pin?: BcfPin;
  model?: ModelIdentity;
  viewpoints: Record<string, SidecarViewpoint>;
}

/** True when the topic carries viewer markup (a pin or annotations). */
export function hasMarkup(t: BcfTopic): boolean {
  return !!t.pin || t.viewpoints.some((r) => (r.annotations?.length ?? 0) > 0 || !!r.derived);
}

/**
 * True when the snapshot of this viewpoint gets the markup burned in: it has annotations (the topic pin is then drawn
 * too). A pin alone leaves the snapshot as it is, so pinned topics cost no second image.
 */
export function needsBurn(_t: BcfTopic, r: BcfViewpointRef): boolean {
  return !!r.snapshot && (r.annotations?.length ?? 0) > 0;
}

/** IfcGuids of the elements the annotations point at (element anchors and element measurements), unique, valid only. */
export function annotationGuids(list: readonly BcfAnnotation[] | undefined): string[] {
  const out = new Set<string>();
  for (const a of list ?? []) {
    const g = [a.anchor.elementGuid, ...(a.anchor.measurement?.elementGuids ?? []), ...attachGuids(a.attach)];
    for (const x of g) {
      const s = x?.replace(/~\d+$/, '');
      if (s && IFC_GUID_RE.test(s)) out.add(s);
    }
  }
  return [...out];
}

/**
 * The IfcGuids of a viewpoint that are selected only for the annotations: the annotated elements that the author did not
 * select. `markupSelection` records which selection entries addAnnotation added; without it (a viewpoint from an older
 * side file) every annotated element counts, unless that would leave nothing of a non-empty selection.
 */
export function markupSelectionOf(r: BcfViewpointRef): string[] {
  const ann = annotationGuids(r.annotations);
  if (!ann.length) return [];
  const sel = (r.data?.selection ?? []).map((c) => c.ifcGuid).filter((g): g is string => !!g);
  if (r.markupSelection) {
    const added = new Set(r.markupSelection);
    const author = new Set(sel.filter((g) => !added.has(g)));
    return ann.filter((g) => !author.has(g));
  }
  const annSet = new Set(ann);
  const rest = sel.filter((g) => !annSet.has(g));
  return sel.length && !rest.length ? [] : ann;
}

export function baseSnapshotName(viewpointGuid: string, version: BcfVersion): string {
  return `xray-${version === '3.0' ? viewpointGuid.toLowerCase() : viewpointGuid}-base.png`;
}

/**
 * The side file text of a topic, or null when the topic has neither markup nor a model identity. `baseSnapshots` maps a viewpoint guid to the
 * file name of its clean snapshot (only for the snapshots that were burned).
 */
export function sidecarJson(t: BcfTopic, version: BcfVersion, baseSnapshots: ReadonlyMap<string, string> = new Map()): string | null {
  // The model identity alone is worth a side file: it says which model the topic belongs to.
  if (!hasMarkup(t) && !t.model) return null;
  const g = (s: string): string => (version === '3.0' ? s.toLowerCase() : s);
  const out: Sidecar = { format: SIDECAR_FORMAT, version: SIDECAR_VERSION, frame: 'ifc', units: 'm', topic: g(t.guid), viewpoints: {} };
  if (t.pinNumber !== undefined) out.pinNumber = t.pinNumber;
  if (t.pin) out.pin = clonePin(t.pin);
  if (t.model) out.model = { ...t.model };
  for (const r of t.viewpoints) {
    const v: SidecarViewpoint = {};
    if (r.annotations?.length) v.annotations = r.annotations.map(cloneAnnotation);
    // Written whenever there are annotations (an empty list too): its absence marks an older side file.
    if (r.annotations?.length) v.markupSelection = markupSelectionOf(r);
    if (r.snapshotView) v.snapshotView = { ...r.snapshotView, position: [...r.snapshotView.position], direction: [...r.snapshotView.direction], up: [...r.snapshotView.up] };
    const base = baseSnapshots.get(r.guid);
    if (base) v.baseSnapshot = base;
    if (r.derived) v.derived = { kind: r.derived.kind, ...(r.derived.sketch ? { sketch: r.derived.sketch } : {}), of: g(r.derived.of) };
    if (v.annotations || v.baseSnapshot || v.snapshotView || v.derived) out.viewpoints[g(r.guid)] = v;
  }
  return `${JSON.stringify(out, null, 1)}\n`;
}

export function clonePin(p: BcfPin): BcfPin {
  const out: BcfPin = { position: [...p.position] };
  if (p.elementGuid) out.elementGuid = p.elementGuid;
  if (p.local) out.local = [...p.local];
  return out;
}

export function cloneAnnotation(a: BcfAnnotation): BcfAnnotation {
  const anchor: BcfAnchor = { kind: a.anchor.kind, point: [...a.anchor.point] };
  if (a.anchor.elementGuid) anchor.elementGuid = a.anchor.elementGuid;
  if (a.anchor.local) anchor.local = [...a.anchor.local];
  const m = a.anchor.measurement;
  if (m) {
    anchor.measurement = { kind: m.kind, a: [...m.a], b: [...m.b], distance: m.distance, label: m.label };
    if (m.elementGuids?.length) anchor.measurement.elementGuids = [...m.elementGuids];
    if (m.sourceId !== undefined) anchor.measurement.sourceId = m.sourceId;
  }
  const out: BcfAnnotation = { guid: a.guid, type: a.type, text: a.text, anchor, offset: [a.offset[0], a.offset[1]] };
  if (a.shape) out.shape = { points: a.shape.points.map((p) => [p[0], p[1]] as [number, number]), depth: a.shape.depth };
  if (a.attach) out.attach = cloneAttachment(a.attach);
  if (a.author) out.author = a.author;
  if (a.date) out.date = a.date;
  return out;
}

// ---------------------------------------------------------------- reading (tolerant: bad parts are dropped and reported)

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
function vec3(v: unknown): Vec3 | null {
  return Array.isArray(v) && v.length === 3 && v.every(fin) ? [v[0] as number, v[1] as number, v[2] as number] : null;
}
const str = (v: unknown): string | undefined => (typeof v === 'string' && v.trim() !== '' ? v : undefined);

/** A stored `derived` marker, or undefined when it is not usable. */
export function cleanDerived(v: unknown): BcfDerived | undefined {
  if (!isObj(v) || (v['kind'] !== 'plan' && v['kind'] !== 'section')) return undefined;
  const of = str(v['of']);
  const sketch = str(v['sketch']);
  if (!of || of.length > 80 || (sketch && sketch.length > 80)) return undefined;
  return { kind: v['kind'], ...(sketch ? { sketch } : {}), of };
}

function readView(v: unknown): BcfSnapshotView | undefined {
  if (!isObj(v)) return undefined;
  const position = vec3(v['position']);
  const direction = vec3(v['direction']);
  const up = vec3(v['up']);
  const fov = v['fov'];
  const aspect = v['aspect'];
  if (!position || !direction || !up || !fin(fov) || !fin(aspect) || fov <= 0 || fov >= 180 || aspect <= 0) return undefined;
  return { position, direction, up, fov, aspect };
}

function readMeasure(v: unknown): BcfMeasureLink | null {
  if (!isObj(v)) return null;
  const a = vec3(v['a']);
  const b = vec3(v['b']);
  const kind = v['kind'] === 'element' ? 'element' : v['kind'] === 'point' ? 'point' : null;
  if (!a || !b || !kind || !fin(v['distance'])) return null;
  const m: BcfMeasureLink = { kind, a, b, distance: v['distance'], label: typeof v['label'] === 'string' ? v['label'] : '' };
  const eg = v['elementGuids'];
  if (Array.isArray(eg)) {
    const list = eg.filter((x): x is string => typeof x === 'string' && x !== '');
    if (list.length) m.elementGuids = list;
  }
  if (fin(v['sourceId'])) m.sourceId = v['sourceId'];
  return m;
}

function readShape(v: unknown, type: string): BcfShape | null {
  if (!isObj(v) || !Array.isArray(v['points']) || !fin(v['depth']) || v['depth'] <= 0) return null;
  const points: Array<[number, number]> = [];
  for (const p of v['points']) {
    if (!Array.isArray(p) || p.length !== 2 || !p.every(fin)) return null;
    points.push([p[0] as number, p[1] as number]);
  }
  if (type === 'rect' ? points.length !== 2 : points.length < 2 || points.length > 4096) return null;
  return { points, depth: v['depth'] };
}

const guidList = (v: unknown): string[] | undefined => {
  if (!Array.isArray(v)) return undefined;
  const list = v.filter((x): x is string => typeof x === 'string' && x !== '');
  return list.length ? list : undefined;
};

export function readAnnotation(v: unknown): BcfAnnotation | null {
  if (!isObj(v)) return null;
  const type = ANNOTATION_TYPES.find((t) => t === v['type']);
  const an = v['anchor'];
  if (!type || !isObj(an)) return null;
  const kind = an['kind'] === 'element' || an['kind'] === 'measurement' || an['kind'] === 'point' ? an['kind'] : null;
  const point = vec3(an['point']);
  if (!kind || !point) return null;
  const anchor: BcfAnchor = { kind, point };
  const eg = str(an['elementGuid']);
  if (eg) anchor.elementGuid = eg;
  const local = vec3(an['local']);
  if (local && eg) anchor.local = local;
  if (an['measurement'] !== undefined) {
    const m = readMeasure(an['measurement']);
    if (m) anchor.measurement = m;
  }
  if (kind === 'measurement' && !anchor.measurement) return null;
  const off = v['offset'];
  const offset: [number, number] = Array.isArray(off) && off.length === 2 && off.every(fin) ? [off[0] as number, off[1] as number] : [0, 0];
  const out: BcfAnnotation = { guid: str(v['guid']) ?? newGuid(), type, text: typeof v['text'] === 'string' ? v['text'] : '', anchor, offset };
  if (isShapeType(type)) {
    const shape = readShape(v['shape'], type);
    // A foreign viewpoint's lines have no fractions: they are world lines, drawn in 3D only.
    const attach = v['attach'] !== undefined ? cleanAttachment(v['attach']) : undefined;
    if (!shape && attach?.kind !== 'lines') return null;
    if (shape) out.shape = shape;
    if (v['attach'] !== undefined) out.attach = attach ?? { kind: 'none' };
  }
  const au = str(v['author']);
  if (au) out.author = au;
  const d = str(v['date']);
  if (d) out.date = d;
  return out;
}

export interface SidecarRead {
  pinNumber?: number;
  pin?: BcfPin;
  model?: ModelIdentity;
  viewpoints: Map<string, SidecarViewpoint>;
  problems: string[];
}

/** Parse the side file. Throws only on text that is not JSON of this format. */
export function parseSidecar(text: string): SidecarRead {
  const raw: unknown = JSON.parse(text);
  if (!isObj(raw) || raw['format'] !== SIDECAR_FORMAT) throw new Error(`not an ${SIDECAR_FORMAT} file`);
  const problems: string[] = [];
  if (fin(raw['version']) && raw['version'] > SIDECAR_VERSION) problems.push(`side file version ${raw['version']} is newer than ${SIDECAR_VERSION}`);
  const out: SidecarRead = { viewpoints: new Map(), problems };
  const pin = raw['pin'];
  if (pin !== undefined) {
    const p = isObj(pin) ? vec3(pin['position']) : null;
    if (p) {
      out.pin = { position: p };
      const eg = isObj(pin) ? str(pin['elementGuid']) : undefined;
      if (eg) out.pin.elementGuid = eg;
      const local = isObj(pin) ? vec3(pin['local']) : null;
      if (local && eg) out.pin.local = local;
    } else problems.push('pin has no valid position');
  }
  const model = cleanIdentity(raw['model']);
  if (model) out.model = model;
  const pn = raw['pinNumber'];
  if (pn !== undefined) {
    if (fin(pn) && Number.isInteger(pn) && pn >= 1 && pn < 1e6) out.pinNumber = pn;
    else problems.push('pinNumber is not a positive whole number');
  }
  const vps = raw['viewpoints'];
  if (isObj(vps)) {
    for (const [guid, v] of Object.entries(vps)) {
      if (!isObj(v)) continue;
      const sv: SidecarViewpoint = {};
      if (Array.isArray(v['annotations'])) {
        const list: BcfAnnotation[] = [];
        v['annotations'].forEach((a, i) => {
          const r = readAnnotation(a);
          if (r) list.push(r);
          else problems.push(`viewpoint ${guid}: annotation ${i + 1} is not valid`);
        });
        if (list.length) sv.annotations = list;
      }
      const view = readView(v['snapshotView']);
      if (view) sv.snapshotView = view;
      const base = str(v['baseSnapshot']);
      if (base && !/[\\/]/.test(base)) sv.baseSnapshot = base;
      if (Array.isArray(v['markupSelection'])) sv.markupSelection = guidList(v['markupSelection']) ?? [];
      const dv = cleanDerived(v['derived']);
      if (dv) sv.derived = dv;
      out.viewpoints.set(guid.toLowerCase(), sv);
    }
  }
  return out;
}

/**
 * Put the side file content on a parsed topic: the pin, and per viewpoint (guid match ignores case) the annotations and the
 * snapshot camera. Returns the clean snapshot file names to load, by viewpoint guid, and the viewpoint guids not found.
 */
export function applySidecar(t: BcfTopic, s: SidecarRead): { baseSnapshots: Map<string, string>; missing: string[] } {
  if (s.pin) t.pin = s.pin;
  if (s.model) t.model = s.model;
  if (s.pinNumber !== undefined) t.pinNumber = s.pinNumber;
  const baseSnapshots = new Map<string, string>();
  const seen = new Set<string>();
  for (const r of t.viewpoints) {
    const v = s.viewpoints.get(r.guid.toLowerCase());
    if (!v) continue;
    seen.add(r.guid.toLowerCase());
    if (v.annotations) r.annotations = v.annotations;
    if (v.snapshotView) r.snapshotView = v.snapshotView;
    // Absent (an older side file): derived from the annotations by markupSelectionOf.
    if (v.markupSelection) r.markupSelection = v.markupSelection;
    if (v.derived) r.derived = v.derived;
    if (v.baseSnapshot) baseSnapshots.set(r.guid, v.baseSnapshot);
  }
  const missing = [...s.viewpoints.keys()].filter((g) => !seen.has(g));
  return { baseSnapshots, missing };
}
