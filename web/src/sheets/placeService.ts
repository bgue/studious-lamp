// Sheet placement in the running viewer: the levels of the model, the plan cut at a level (vectors, cached), automatic placement of
// geo-PDFs, applying and removing a placement, and the attachment of sketches through a placed sheet to model elements. The pure
// parts are in placement.ts, geoPdf.ts, mapConversion.ts, sectionCut.ts and attachSheet.ts. Docs: docs-features/sheets.md.

import type { BufferAttribute } from 'three';
import type { ViewerApp } from '../app';
import { attachGuids, isSpatial } from '../bcf/attach';
import type { Attachment } from '../bcf/attach';
import { dirViewerToIfc, ifcToViewer, newGuid, viewerToIfc } from '../bcf/model';
import type { BcfViewpoint, Vec3 } from '../bcf/model';
import { frameCamera } from '../bcf/plan';
import type { Box6 } from '../bcf/plan';
import type { DerivedViewSwitch } from '../issues/derivedSwitch';
import { PLAN_CUT_ABOVE_FLOOR } from '../issues/derivedViews';
import { shapePath } from '../markup/attachScene';
import { isAnchorKind, nowIso } from '../markup/model';
import type { Markup, MarkupSet } from '../markup/model';
import type { MapConversion } from '../types';
import { deriveSheetAttachment } from './attachSheet';
import { geoPlacement } from './mapConversion';
import type { GeoPlacementResult } from './mapConversion';
import { applySim, isPlan, planeOf, sheetToModel } from './placement';
import type { SheetPlacement, Vec2 } from './placement';
import { cutElement, sliceMesh } from './sectionCut';
import type { CutElement, PlanCut } from './sectionCut';
import type { Sheet } from './model';
import type { SheetsController } from './controller';

export interface Level {
  /** Index in the model's storeys, or -1 for the whole model without storeys. */
  index: number;
  name: string;
  /** Metres, IFC frame. */
  elevation: number;
  guid?: string;
  /** The next level's elevation: the top of the storey band. */
  top?: number;
}

export interface ApplyResult {
  ok: boolean;
  /** Shapes that would leave the elements they are on: the caller asks first, then applies again with `confirmed`. */
  moved?: number;
  error?: string;
}

const r2 = (v: number): number => Math.round(v * 100) / 100;

export class PlaceService {
  /** Set by the plugin: the 3D · Plan · Section switch, which derives the target box of a sketch. */
  views: DerivedViewSwitch | null = null;
  private readonly cuts = new WeakMap<object, Map<string, PlanCut>>();
  /** Geo-PDF findings that could not place a sheet by themselves (session only): what was found and why not. */
  readonly geoNotes = new Map<string, string>();

  constructor(private readonly ctl: SheetsController) {}

  private get app(): ViewerApp {
    return this.ctl.app;
  }
  get loaded(): boolean {
    return !!this.app.loaded;
  }
  private get shift(): Vec3 {
    const s = this.app.loaded?.model.originShift;
    return s ? [s[0], s[1], s[2]] : [0, 0, 0];
  }
  get mapConversion(): MapConversion | undefined {
    return this.app.loaded?.model.mapConversion;
  }

  // ---------------------------------------------------------------- levels

  /** The storeys of the model, lowest first; a model without storeys has one level at its lowest element. */
  levels(): Level[] {
    const m = this.app.loaded?.model;
    if (!m) return [];
    const st = [...m.storeys].filter((s) => Number.isFinite(s.elevation)).sort((a, b) => a.elevation - b.elevation || a.id - b.id);
    if (!st.length) {
      let low = Infinity;
      for (const e of m.elements) low = Math.min(low, e.bounds[1]);
      return [{ index: -1, name: 'Model', elevation: Number.isFinite(low) ? r2(low + this.shift[2]) : 0 }];
    }
    return st.map((s, i) => ({ index: s.id, name: s.name || `Level ${i + 1}`, elevation: s.elevation, ...(s.guid ? { guid: s.guid } : {}), ...(st[i + 1] ? { top: st[i + 1]!.elevation } : {}) }));
  }

  levelOf(p: Pick<SheetPlacement, 'level'>): Level {
    const ls = this.levels();
    return (p.level.storeyGuid ? ls.find((l) => l.guid === p.level.storeyGuid) : undefined) ?? ls.find((l) => Math.abs(l.elevation - p.level.elevation) < 0.01) ?? { index: -1, name: p.level.name ?? 'Level', elevation: p.level.elevation };
  }

  /** The level a geo-referenced sheet goes to: the one its name mentions, else the lowest. */
  guessLevel(sheet: Pick<Sheet, 'name'>): Level | undefined {
    const ls = this.levels();
    const n = sheet.name.toLowerCase();
    return ls.find((l) => l.name && n.includes(l.name.toLowerCase())) ?? ls[0];
  }

  // ---------------------------------------------------------------- the plan cut

  /** The height of the plan cut above a level: the same as the Plan view of a sketch (src/issues/derivedViews.ts). */
  cutHeight(elevation: number): number {
    return elevation + PLAN_CUT_ABOVE_FLOOR;
  }

  /** What the plane at the cut height slices: the outline of every element it passes through (cached per model and level). */
  cut(elevation: number): PlanCut {
    const loaded = this.app.loaded;
    if (!loaded) return { z: this.cutHeight(elevation), elements: [] };
    let per = this.cuts.get(loaded);
    if (!per) { per = new Map(); this.cuts.set(loaded, per); }
    const key = elevation.toFixed(3);
    const have = per.get(key);
    if (have) return have;
    const z = this.cutHeight(elevation);
    const shift = this.shift;
    const y = z - shift[2];
    const geo = loaded.geometry;
    const pos = geo.geometry.getAttribute('position') as BufferAttribute;
    const index = geo.geometry.getIndex()!.array as ArrayLike<number>;
    const out: CutElement[] = [];
    // sliceMesh on a range of the merged index (viewer frame, y up) gives (x, z) of the plan: back to the IFC frame below.
    for (const e of loaded.model.elements) {
      const b = e.bounds;
      if (!(b[1] < y && b[4] > y)) continue;
      const r = geo.ranges[e.id];
      if (!r || r.count < 3) continue;
      const segs = sliceMesh(pos.array as ArrayLike<number>, (index as Uint32Array).subarray(r.start, r.start + r.count), y, 1);
      const ifc: number[] = new Array(segs.length);
      for (let i = 0; i < segs.length; i += 2) { ifc[i] = segs[i]! + shift[0]; ifc[i + 1] = -segs[i + 1]! + shift[1]; }
      const c = cutElement(e.globalId, ifc, e.ifcClass);
      if (c) out.push(c);
    }
    const cut: PlanCut = { z, elements: out };
    per.set(key, cut);
    return cut;
  }

  /** Bounds of what the cut at a level shows (plan metres), else of the model's footprint. */
  cutBounds(elevation: number): [number, number, number, number] | null {
    const c = this.cut(elevation);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const e of c.elements) { x0 = Math.min(x0, e.box[0]); y0 = Math.min(y0, e.box[1]); x1 = Math.max(x1, e.box[2]); y1 = Math.max(y1, e.box[3]); }
    if (Number.isFinite(x0)) return [x0, y0, x1, y1];
    const b = this.app.loaded?.geometry.totalBounds();
    if (!b || b.isEmpty()) return null;
    const s = this.shift;
    return [b.min.x + s[0], -b.max.z + s[1], b.max.x + s[0], -b.min.z + s[1]];
  }

  // ---------------------------------------------------------------- geo-PDF

  /** Place a geo-referenced sheet by itself when the model's IfcMapConversion and the PDF's CRS agree. Never overwrites a placement. */
  autoPlace(sheet: Sheet): GeoPlacementResult | null {
    if (!sheet.geo || !this.loaded) return null;
    const r = geoPlacement(sheet.geo, this.mapConversion);
    if (!r.ok || !r.transform) {
      this.geoNotes.set(sheet.id, `${r.detected ? `Found: ${r.detected}. ` : ''}${r.reason ?? ''} Place it by hand.`);
      return r;
    }
    this.geoNotes.delete(sheet.id);
    if (sheet.placement) return r;
    const lv = this.guessLevel(sheet);
    if (!lv) return r;
    const p: SheetPlacement = {
      kind: 'geo', level: { ...(lv.guid ? { storeyGuid: lv.guid } : {}), name: lv.name, elevation: lv.elevation }, plane: 'plan', transform: r.transform,
      source: r.source ?? 'geo-PDF',
    };
    this.apply(sheet.id, p, { confirmed: true });
    return r;
  }

  /** Try the geo placement of every unplaced sheet that has geo data (a model was loaded, or a PDF was opened). */
  autoPlaceAll(): number {
    let n = 0;
    for (const s of this.ctl.store.sheets) {
      if (!s.geo || s.placement) continue;
      const d = this.ctl.store.doc(s.docId);
      if (d && !this.ctl.docs().here.includes(d)) continue;
      if (this.autoPlace(s)?.ok) n++;
    }
    return n;
  }

  // ---------------------------------------------------------------- applying a placement

  /** How many shapes of the sheet would lose the elements they are on if the sheet were placed like this. */
  wouldMove(sheetId: string, p: SheetPlacement | undefined): number {
    let n = 0;
    for (const set of this.ctl.sketchesOn(sheetId)) {
      if (set.readonly) continue;
      for (const m of set.markups) {
        const before = this.guidsOf(m);
        if (!before.length) continue;
        const next = p ? this.derive(m, { ...this.ctl.store.sheet(sheetId)!, placement: p }) : null;
        const after = next ? attachGuids(next.attach) : [];
        if (before.length !== after.length || before.some((g) => !after.includes(g))) n++;
      }
    }
    return n;
  }

  private guidsOf(m: Markup): string[] {
    return m.shape ? attachGuids(m.attach) : m.anchor?.elementGuid ? [m.anchor.elementGuid] : [];
  }

  /** Put a placement on a sheet and attach its sketches again. Asks first (returns `moved`) when shapes would leave their elements. */
  apply(sheetId: string, p: SheetPlacement, o: { confirmed?: boolean } = {}): ApplyResult {
    const sheet = this.ctl.store.sheet(sheetId);
    if (!sheet) return { ok: false, error: 'No such sheet' };
    if (!o.confirmed) {
      const moved = this.wouldMove(sheetId, p);
      if (moved > 0) return { ok: false, moved };
    }
    sheet.placement = p;
    this.rederive(sheet);
    this.ctl.placementChanged(sheet);
    return { ok: true };
  }

  /** Remove the placement: the sketches become plain sheet sketches again (no model attachment). */
  remove(sheetId: string): void {
    const sheet = this.ctl.store.sheet(sheetId);
    if (!sheet?.placement) return;
    delete sheet.placement;
    for (const set of this.ctl.sketchesOn(sheetId)) {
      if (set.readonly) continue;
      for (const m of set.markups) {
        if (m.shape) m.attach = { kind: 'none' };
        else if (m.anchor && m.anchor.kind !== 'point') m.anchor = { kind: 'point', point: m.anchor.point };
      }
      set.updated = nowIso();
    }
    this.geoNotes.delete(sheetId);
    this.ctl.placementChanged(sheet);
  }

  // ---------------------------------------------------------------- attachment through a placed sheet

  /** The sheet's placement when sketches on it attach to the model: a plan placement, with a model loaded. */
  private planOf(sheet: Sheet | undefined): SheetPlacement | null {
    const p = sheet?.placement;
    return p && isPlan(p) && this.loaded ? p : null;
  }

  /** The attachment a markup on a placed sheet gets now (not stored). Null when the sheet is not placed or the markup has no geometry. */
  derive(m: Markup, sheet: Sheet): { attach: Attachment; reason: string } | null {
    const p = this.planOf(sheet);
    if (!p) return null;
    const lv = this.levelOf(p);
    const cut = this.cut(p.level.elevation);
    const level = { elevation: p.level.elevation, ...(lv.top !== undefined ? { top: lv.top } : {}) };
    const toModel = (pts: ReadonlyArray<readonly [number, number]>): number[] => pts.flatMap((q) => applySim(p.transform, [q[0], q[1]]));
    if (isAnchorKind(m.kind)) {
      if (!m.anchor) return null;
      const xy = applySim(p.transform, [m.anchor.point[0], m.anchor.point[1]]);
      const r = deriveSheetAttachment({ path: [xy[0], xy[1]], closed: false, anchored: true, cut: cut.elements, level });
      return { attach: r.attach, reason: r.reason };
    }
    if (!m.shape || m.shape.points.length < 1) return null;
    const sp = shapePath(m.kind, m.shape.points);
    const path = toModel(chunk2(sp.path));
    const r = deriveSheetAttachment({ path, closed: sp.closed, cut: cut.elements, level });
    return { attach: r.attach, reason: r.reason };
  }

  /** Attach one markup of a sketch on a placed sheet (a shape was drawn or moved). No-op for an unplaced sheet. */
  attachMarkup(set: MarkupSet, m: Markup): boolean {
    const sheet = this.ctl.sheetOfSet(set);
    if (!sheet || set.readonly) return false;
    const r = this.derive(m, sheet);
    if (!r) return false;
    this.store(m, r.attach, sheet);
    m.modified = nowIso();
    set.updated = m.modified;
    return true;
  }

  private store(m: Markup, a: Attachment, sheet: Sheet): void {
    if (m.shape) {
      m.attach = a;
      return;
    }
    if (!m.anchor) return;
    const g = a.kind === 'point' ? a.guids?.[0] : undefined;
    const point = m.anchor.point;
    void sheet;
    m.anchor = g ? { kind: 'element', point, elementGuid: g } : { kind: 'point', point };
  }

  /** Attach every markup of the sketches on a sheet again (the sheet was placed, or placed anew). */
  rederive(sheet: Sheet): void {
    for (const set of this.ctl.sketchesOn(sheet.id)) {
      if (set.readonly) continue;
      for (const m of set.markups) {
        const r = this.derive(m, sheet);
        if (r) this.store(m, r.attach, sheet);
      }
      set.updated = nowIso();
    }
  }

  // ---------------------------------------------------------------- 3D: targets, framing, viewpoint

  /** Where a markup of a placed sheet is in the model (IFC frame): its anchor, or the middle of its shape. Undefined when unplaced. */
  anchorPoint(set: MarkupSet, m: Markup): Vec3 | undefined {
    const sheet = this.ctl.sheetOfSet(set);
    const p = sheet?.placement;
    if (!p) return undefined;
    let c: Vec2 | null = null;
    if (m.anchor) c = [m.anchor.point[0], m.anchor.point[1]];
    else if (m.shape && m.shape.points.length) {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const q of m.shape.points) { x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]); }
      c = [(x0 + x1) / 2, (y0 + y1) / 2];
    }
    return c ? sheetToModel(p, c) : undefined;
  }

  /** The GlobalIds a sketch is attached to. */
  targets(set: MarkupSet): string[] {
    const out = new Set<string>();
    for (const m of set.markups) for (const g of this.guidsOf(m)) out.add(g);
    return [...out];
  }

  /** The camera that frames what a sketch on a placed sheet is attached to (viewer frame), or null when it is attached to nothing. */
  framing(set: MarkupSet): { position: Vec3; target: Vec3; up: Vec3; fov: number } | null {
    const v = this.views;
    const cam = this.app.renderer.camera;
    if (!v || !this.loaded) return null;
    const i = v.input(set, cam.aspect, null);
    if (!i) return null;
    const f = frameCamera(i.target as Box6, cam.fov, cam.aspect, [0.28, 0.85, 0.45]);
    return { position: f.position, target: f.target, up: [0, 1, 0], fov: cam.fov };
  }

  /** A BCF viewpoint for a sketch on a placed sheet: the target elements as components, a camera that frames them. Null when it has none. */
  viewpointFor(set: MarkupSet): BcfViewpoint | null {
    const f = this.framing(set);
    const guids = this.targets(set).slice(0, 200);
    if (!f) return null;
    const shift = this.shift;
    const d: Vec3 = [f.target[0] - f.position[0], f.target[1] - f.position[1], f.target[2] - f.position[2]];
    const l = Math.hypot(d[0], d[1], d[2]) || 1;
    return {
      guid: newGuid(),
      camera: {
        kind: 'perspective', position: viewerToIfc(f.position, shift), direction: dirViewerToIfc([d[0] / l, d[1] / l, d[2] / l]), up: dirViewerToIfc(f.up),
        fov: f.fov, aspect: this.app.renderer.camera.aspect,
      },
      selection: guids.map((g) => ({ ifcGuid: g })),
      visibility: null, coloring: [], clipping: [], lines: [],
    };
  }

  /** The corners of a sheet's page in the model (viewer frame), display order: top left, top right, bottom right, bottom left. Null when unplaced. */
  quadCorners(sheet: Sheet, userOf: (dx: number, dy: number) => Vec2): Vec3[] | null {
    const p = sheet.placement;
    if (!p) return null;
    const shift = this.shift;
    const lift = isPlan(p) ? 0.03 : 0;
    return ([[0, 0], [sheet.widthPt, 0], [sheet.widthPt, sheet.heightPt], [0, sheet.heightPt]] as Vec2[]).map((c) => {
      const w = sheetToModel(p, userOf(c[0], c[1]));
      return ifcToViewer([w[0], w[1], w[2] + lift], shift);
    });
  }

  /** The plane of the placement, for scripts: 'plan' or the vertical plane. */
  planeName(sheet: Sheet): string {
    return sheet.placement ? (planeOf(sheet.placement) === 'plan' ? 'plan' : 'vertical') : 'none';
  }

  /** True when a markup has a spatial attachment to draw (scripts). */
  spatial(m: Markup): boolean {
    return m.shape ? isSpatial(m.attach) : !!m.anchor?.elementGuid;
  }
}

function chunk2(flat: readonly number[]): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (let i = 0; i + 1 < flat.length; i += 2) out.push([flat[i]!, flat[i + 1]!]);
  return out;
}
