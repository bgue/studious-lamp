// The minimal model view the 4D linker, plan builder and report need. Pure data: no viewer, no DOM, no IFC reader. Adapters
// build it from the viewer's SceneModel, from the sidecar the node IFC reader of xray-pack produces (same element and storey
// records), or by hand (tests, other tools).
//
// Coordinates: bbox is [minx, miny, minz, maxx, maxy, maxz] in the IFC frame (Z up, metres). The viewer is Y up
// ((x, y, z)_ifc -> (x, z, -y)_viewer), so the adapter converts. Sweeps and "storey below" checks use bbox z as the height.

import { coreColumn } from '../query/table';
import type { Accessor, QueryTable } from '../query/compile';
import type { Value } from '../query/parser';

export type BBox = [number, number, number, number, number, number];

export interface FourDElement {
  globalId: string;
  ifcClass: string;
  name: string;
  storey?: string;
  /** The IfcZone name the element belongs to. */
  zone?: string;
  /** Property values by 'PsetName.PropName' (also 'Attr.*' keys of the viewer). */
  props: Record<string, string>;
  bbox?: BBox;
  /** The classifier's discipline, when the model has one. */
  discipline?: string;
  material?: string;
}

export interface FourDModel {
  /** Stable identity of the model (the viewer's identityKey: name|count|guid hash). */
  identityKey: string;
  name: string;
  elements: FourDElement[];
  /** Storeys with elevations (m), any order. When absent the order is derived from the elements' bbox z. */
  storeys?: Array<{ name: string; elevation: number }>;
}

// ---------------------------------------------------------------- adapters

/** The part of the viewer's SceneModel (or the node reader's sidecar) the adapter reads. */
export interface SceneLike {
  storeys: Array<{ id: number; name: string; elevation: number }>;
  elements: Array<{
    id: number; globalId: string; ifcClass: string; name?: string; storey: number | null; material?: string;
    bounds: [number, number, number, number, number, number];
    props?: Record<string, string | number | boolean>;
  }>;
}

export interface AdapterOptions {
  identityKey?: string;
  name?: string;
  /** Property keys: the zone name and the discipline (defaults below). */
  zoneProperty?: string;
  disciplineProperty?: string;
}

const DISCIPLINE_KEYS = ['XR_Classification.Discipline', 'Xray_Review.Discipline'];
const ZONE_KEYS = ['Xray_4D.Zone', 'Attr.Zone'];

/** FNV-1a of the sorted GlobalIds: an identity when the caller has none. */
export function guidHash(ids: string[]): string {
  let h = 0x811c9dc5;
  for (const id of [...ids].sort()) {
    for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    h ^= 0x7c; h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

/** Viewer (Y up) bounds -> IFC frame (Z up). */
export function viewerBoundsToIfc(b: readonly number[]): BBox {
  return [b[0]!, 0 - b[5]!, b[1]!, b[3]!, 0 - b[2]!, b[4]!];
}

/** Adapter for the viewer's SceneModel and for the node reader's sidecar. */
export function fromSceneModel(m: SceneLike, opts: AdapterOptions = {}): FourDModel {
  const storeyName = new Map(m.storeys.map((s) => [s.id, s.name]));
  const elements: FourDElement[] = m.elements.map((e) => {
    const props: Record<string, string> = {};
    if (e.props) for (const k in e.props) props[k] = String(e.props[k]);
    const pick = (keys: string[]): string | undefined => { for (const k of keys) if (props[k]) return props[k]; return undefined; };
    const el: FourDElement = { globalId: e.globalId, ifcClass: e.ifcClass, name: e.name ?? '', props, bbox: viewerBoundsToIfc(e.bounds) };
    const st = e.storey === null ? undefined : storeyName.get(e.storey);
    if (st !== undefined) el.storey = st;
    const z = opts.zoneProperty ? props[opts.zoneProperty] : pick(ZONE_KEYS);
    if (z) el.zone = z;
    const d = opts.disciplineProperty ? props[opts.disciplineProperty] : pick(DISCIPLINE_KEYS);
    if (d) el.discipline = d;
    if (e.material) el.material = e.material;
    return el;
  });
  return {
    identityKey: opts.identityKey ?? `${(opts.name ?? 'model').trim().toLowerCase()}|${elements.length}|${guidHash(elements.map((e) => e.globalId))}`,
    name: opts.name ?? 'model',
    elements,
    storeys: m.storeys.map((s) => ({ name: s.name, elevation: s.elevation })),
  };
}

/** Adapter for the node IFC reader's result (`convertIfc(...).sidecar`, same records as the viewer model). */
export function fromSidecar(sc: SceneLike & { source?: { files: string[] } }, opts: AdapterOptions = {}): FourDModel {
  return fromSceneModel(sc, { name: sc.source?.files?.[0], ...opts });
}

// ---------------------------------------------------------------- helpers

/** Centre of a bbox. */
export function bboxCentre(b: BBox): [number, number, number] {
  return [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
}

export function bboxVolume(b: BBox | undefined): number {
  return b ? Math.max(0, b[3] - b[0]) * Math.max(0, b[4] - b[1]) * Math.max(0, b[5] - b[2]) : 0;
}

/** Storey names bottom-up: from `model.storeys` elevations, else by the median bbox min z of each storey's elements. */
export function storeyOrder(model: FourDModel): string[] {
  const elev = new Map<string, number>();
  for (const s of model.storeys ?? []) elev.set(s.name, s.elevation);
  const zs = new Map<string, number[]>();
  for (const e of model.elements) {
    if (!e.storey) continue;
    if (!zs.has(e.storey)) zs.set(e.storey, []);
    if (e.bbox) zs.get(e.storey)!.push(e.bbox[2]);
  }
  for (const [name, list] of zs) {
    if (elev.has(name)) continue;
    list.sort((a, b) => a - b);
    elev.set(name, list.length ? list[Math.floor(list.length / 2)]! : Number.MAX_SAFE_INTEGER);
  }
  return [...zs.keys(), ...[...elev.keys()].filter((n) => !zs.has(n))]
    .filter((n, i, a) => a.indexOf(n) === i)
    .sort((a, b) => (elev.get(a)! - elev.get(b)!) || a.localeCompare(b, undefined, { numeric: true }));
}

// ---------------------------------------------------------------- query table

/**
 * The criteria-language table of a FourDModel (src/query), so `tradeQueries`, `existing` and activity overrides run on it.
 * Columns follow the viewer's table: the core columns (class, name, storey, material, globalId, bounds...), then every
 * property key (exact, any case, or the short name when unique), `zone` and `discipline`. Bounds are the viewer's (Y up).
 */
export class FourDTable implements QueryTable {
  readonly size: number;
  private readonly els: FourDElement[];
  private readonly lower = new Map<string, string>();
  private readonly short = new Map<string, string | null>();
  private readonly elev = new Map<string, number>();

  constructor(model: FourDModel) {
    this.els = model.elements;
    this.size = model.elements.length;
    for (const s of model.storeys ?? []) this.elev.set(s.name, s.elevation);
    const seen = new Set<string>();
    for (const e of this.els) for (const k in e.props) {
      if (seen.has(k)) continue;
      seen.add(k);
      const l = k.toLowerCase();
      if (!this.lower.has(l)) this.lower.set(l, k);
      const dot = k.indexOf('.');
      if (dot > 0) { const s = l.slice(dot + 1); this.short.set(s, this.short.has(s) ? null : k); }
    }
  }

  accessor(name: string): Accessor | null {
    const els = this.els;
    const core = coreColumn(name);
    const b = (f: (e: FourDElement) => number | null): Accessor => (r) => f(els[r]!);
    const bb = (e: FourDElement) => e.bbox;
    switch (core) {
      case 'globalId': return (r) => els[r]!.globalId;
      case 'class': return (r) => els[r]!.ifcClass;
      case 'name': return (r) => els[r]!.name || null;
      case 'material': return (r) => els[r]!.material || null;
      case 'storey': return (r) => els[r]!.storey ?? null;
      case 'storeyElevation': return (r) => { const s = els[r]!.storey; return s !== undefined && this.elev.has(s) ? this.elev.get(s)! : null; };
      case 'id': return (r) => r;
      case 'xMin': return b((e) => bb(e)?.[0] ?? null);
      case 'xMax': return b((e) => bb(e)?.[3] ?? null);
      case 'yMin': return b((e) => bb(e)?.[2] ?? null);
      case 'yMax': return b((e) => bb(e)?.[5] ?? null);
      case 'zMin': return b((e) => { const x = bb(e); return x ? 0 - x[4] : null; });
      case 'zMax': return b((e) => { const x = bb(e); return x ? 0 - x[1] : null; });
      case 'sizeX': return b((e) => { const x = bb(e); return x ? x[3] - x[0] : null; });
      case 'sizeY': return b((e) => { const x = bb(e); return x ? x[5] - x[2] : null; });
      case 'sizeZ': return b((e) => { const x = bb(e); return x ? x[4] - x[1] : null; });
      case 'volume': return b((e) => (bb(e) ? bboxVolume(bb(e)) : null));
      default: break;
    }
    const l = name.toLowerCase();
    if (l === 'zone') return (r) => els[r]!.zone ?? null;
    if (l === 'discipline') return (r) => els[r]!.discipline ?? null;
    const key = this.lower.get(l) ?? this.short.get(l) ?? null;
    if (key === null) return null;
    return (r): Value => els[r]!.props[key] ?? null;
  }
}
