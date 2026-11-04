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
//     "topic": "<topic guid>",
//     "pin": { "position": [x, y, z], "elementGuid": "<IfcGuid>" },
//     "viewpoints": {
//       "<viewpoint guid>": {
//         "annotations": [ { "guid", "type": "callout" | "note" | "arrow", "text", "offset": [dx, dy],
//                            "anchor": { "kind": "element" | "measurement" | "point", "point": [x, y, z], "elementGuid"?,
//                                        "measurement"?: { "kind", "a", "b", "distance", "label", "elementGuids"? } } } ],
//         "snapshotView": { "position", "direction", "up", "fov", "aspect" },
//         "baseSnapshot": "xray-<viewpoint guid>-base.png"
//       }
//     }
//   }

import { ANNOTATION_TYPES, IFC_GUID_RE, newGuid } from './model';
import type { BcfAnchor, BcfAnnotation, BcfMeasureLink, BcfPin, BcfSnapshotView, BcfTopic, BcfVersion, BcfViewpointRef, Vec3 } from './model';

export const SIDECAR_NAME = 'xray-markup.json';
export const SIDECAR_FORMAT = 'xray-bcf-markup';
export const SIDECAR_VERSION = 1;

export interface SidecarViewpoint {
  annotations?: BcfAnnotation[];
  snapshotView?: BcfSnapshotView;
  /** File name (in the topic folder) of the snapshot without the burned-in markup. */
  baseSnapshot?: string;
}

export interface Sidecar {
  format: typeof SIDECAR_FORMAT;
  version: number;
  frame: 'ifc';
  units: 'm';
  topic: string;
  pin?: BcfPin;
  viewpoints: Record<string, SidecarViewpoint>;
}

/** True when the topic carries viewer markup (a pin or annotations). */
export function hasMarkup(t: BcfTopic): boolean {
  return !!t.pin || t.viewpoints.some((r) => (r.annotations?.length ?? 0) > 0);
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
    const g = [a.anchor.elementGuid, ...(a.anchor.measurement?.elementGuids ?? [])];
    for (const x of g) {
      const s = x?.replace(/~\d+$/, '');
      if (s && IFC_GUID_RE.test(s)) out.add(s);
    }
  }
  return [...out];
}

export function baseSnapshotName(viewpointGuid: string, version: BcfVersion): string {
  return `xray-${version === '3.0' ? viewpointGuid.toLowerCase() : viewpointGuid}-base.png`;
}

/**
 * The side file text of a topic, or null when the topic has no markup. `baseSnapshots` maps a viewpoint guid to the
 * file name of its clean snapshot (only for the snapshots that were burned).
 */
export function sidecarJson(t: BcfTopic, version: BcfVersion, baseSnapshots: ReadonlyMap<string, string> = new Map()): string | null {
  if (!hasMarkup(t)) return null;
  const g = (s: string): string => (version === '3.0' ? s.toLowerCase() : s);
  const out: Sidecar = { format: SIDECAR_FORMAT, version: SIDECAR_VERSION, frame: 'ifc', units: 'm', topic: g(t.guid), viewpoints: {} };
  if (t.pin) out.pin = { position: [...t.pin.position], ...(t.pin.elementGuid ? { elementGuid: t.pin.elementGuid } : {}) };
  for (const r of t.viewpoints) {
    const v: SidecarViewpoint = {};
    if (r.annotations?.length) v.annotations = r.annotations.map(cloneAnnotation);
    if (r.snapshotView) v.snapshotView = { ...r.snapshotView, position: [...r.snapshotView.position], direction: [...r.snapshotView.direction], up: [...r.snapshotView.up] };
    const base = baseSnapshots.get(r.guid);
    if (base) v.baseSnapshot = base;
    if (v.annotations || v.baseSnapshot || v.snapshotView) out.viewpoints[g(r.guid)] = v;
  }
  return `${JSON.stringify(out, null, 1)}\n`;
}

export function cloneAnnotation(a: BcfAnnotation): BcfAnnotation {
  const anchor: BcfAnchor = { kind: a.anchor.kind, point: [...a.anchor.point] };
  if (a.anchor.elementGuid) anchor.elementGuid = a.anchor.elementGuid;
  const m = a.anchor.measurement;
  if (m) {
    anchor.measurement = { kind: m.kind, a: [...m.a], b: [...m.b], distance: m.distance, label: m.label };
    if (m.elementGuids?.length) anchor.measurement.elementGuids = [...m.elementGuids];
    if (m.sourceId !== undefined) anchor.measurement.sourceId = m.sourceId;
  }
  const out: BcfAnnotation = { guid: a.guid, type: a.type, text: a.text, anchor, offset: [a.offset[0], a.offset[1]] };
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
  if (an['measurement'] !== undefined) {
    const m = readMeasure(an['measurement']);
    if (m) anchor.measurement = m;
  }
  if (kind === 'measurement' && !anchor.measurement) return null;
  const off = v['offset'];
  const offset: [number, number] = Array.isArray(off) && off.length === 2 && off.every(fin) ? [off[0] as number, off[1] as number] : [0, 0];
  const out: BcfAnnotation = { guid: str(v['guid']) ?? newGuid(), type, text: typeof v['text'] === 'string' ? v['text'] : '', anchor, offset };
  const au = str(v['author']);
  if (au) out.author = au;
  const d = str(v['date']);
  if (d) out.date = d;
  return out;
}

export interface SidecarRead {
  pin?: BcfPin;
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
    } else problems.push('pin has no valid position');
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
  const baseSnapshots = new Map<string, string>();
  const seen = new Set<string>();
  for (const r of t.viewpoints) {
    const v = s.viewpoints.get(r.guid.toLowerCase());
    if (!v) continue;
    seen.add(r.guid.toLowerCase());
    if (v.annotations) r.annotations = v.annotations;
    if (v.snapshotView) r.snapshotView = v.snapshotView;
    if (v.baseSnapshot) baseSnapshots.set(r.guid, v.baseSnapshot);
  }
  const missing = [...s.viewpoints.keys()].filter((g) => !seen.has(g));
  return { baseSnapshots, missing };
}
