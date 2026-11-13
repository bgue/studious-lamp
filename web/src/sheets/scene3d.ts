// A placed sheet in the 3D view: the PDF page as a textured quad at its level, and the sketches drawn on a placed sheet, drawn on the
// SVG overlay with the attached-markup layout of the 3D sketches (src/markup/layout.ts). The quad is a plain mesh of the scene
// with no raycast, so picks (which walk the per-element BVHs), measurements and the classification never see it; it does not write
// depth, so section caps, the x-ray modes and the OIT composite draw as they did. Docs: docs-features/sheets.md ("In 3D").

import { BufferGeometry, CanvasTexture, DoubleSide, Float32BufferAttribute, LinearMipmapLinearFilter, Mesh, MeshBasicMaterial, SRGBColorSpace } from 'three';
import type { Camera } from 'three';
import type { ViewerApp } from '../app';
import { renderOps } from '../bcf/pins';
import type { SurfaceData } from '../bcf/attach';
import { ifcToViewer } from '../bcf/model';
import type { Vec3 } from '../bcf/model';
import { shapePath } from '../markup/attachScene';
import { layoutMarkupFull } from '../markup/layout';
import { isAnchorKind } from '../markup/model';
import type { Markup, MarkupSet } from '../markup/model';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import type { SheetsController } from './controller';
import { displayToUser } from './model';
import type { Sheet } from './model';
import { isPlan, sheetToModel } from './placement';
import type { SheetPlacement } from './placement';

interface Quad {
  mesh: Mesh;
  tex: CanvasTexture;
  /** What the quad was built from: the placement and the page, so a change rebuilds it. */
  key: string;
  /** The texture is the sharp one (drawn when the camera got close). */
  sharp: boolean;
  building: boolean;
}

const BASE_PX = 2048;
const SHARP_PX = 4096;
const LIFT = 0.03;

export class SheetScene3D {
  private readonly quads = new Map<string, Quad>();
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  /** Counts for tests: textures drawn. */
  renders = { base: 0, sharp: 0 };

  constructor(private readonly ctl: SheetsController, private readonly app: ViewerApp) {
    ctl.onChange(() => { this.sync(); this.overlay?.invalidate(); });
    ctl.markup.onChange(() => this.overlay?.invalidate());
    ctl.quadOpacityChanged = () => {
      for (const q of this.quads.values()) this.material(q).opacity = ctl.quadOpacity;
      this.app.renderer.markDirty();
    };
  }

  /** Per frame (the plugin): make the overlay layer once the model is there. */
  tick(): void {
    if (this.overlay || !this.app.loaded) return;
    const ov = getOverlay(this.app);
    this.overlay = ov;
    this.layer = ov.layer('sheet-sketches');
    ov.onUpdate((o) => this.drawSketches(o));
  }

  // ---------------------------------------------------------------- the quads

  private keyOf(sheet: Sheet): string {
    return `${JSON.stringify(sheet.placement)}|${sheet.widthPt}x${sheet.heightPt}|${sheet.rotation}`;
  }

  /** Make, update and remove the quads so they match the sheets that are shown. */
  sync(): void {
    const want = new Set<string>();
    for (const id of this.ctl.shown3d) {
      const sh = this.ctl.store.sheet(id);
      if (sh?.placement && this.app.loaded) want.add(id);
    }
    for (const [id, q] of this.quads) {
      if (!want.has(id)) this.remove(id, q);
    }
    for (const id of want) {
      const sh = this.ctl.store.sheet(id)!;
      const have = this.quads.get(id);
      if (have && have.key === this.keyOf(sh)) { have.mesh.visible = true; have.mesh.material = this.material(have); continue; }
      if (have) this.remove(id, have);
      void this.build(sh);
    }
    for (const q of this.quads.values()) (q.mesh.material as MeshBasicMaterial).opacity = this.ctl.quadOpacity;
    this.app.renderer.markDirty();
  }

  private material(q: Quad): MeshBasicMaterial {
    return q.mesh.material as MeshBasicMaterial;
  }

  private remove(id: string, q: Quad): void {
    this.app.renderer.scene.remove(q.mesh);
    q.mesh.geometry.dispose();
    this.material(q).dispose();
    q.tex.dispose();
    this.quads.delete(id);
  }

  private geometry(sheet: Sheet): BufferGeometry | null {
    const corners = this.ctl.place.quadCorners(sheet, (dx, dy) => displayToUser(sheet, dx, dy));
    if (!corners) return null;
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(corners.flat(), 3));
    g.setAttribute('uv', new Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2));
    g.setIndex([0, 1, 2, 0, 2, 3]);
    g.computeBoundingSphere();
    return g;
  }

  private async paint(sheet: Sheet, px: number): Promise<HTMLCanvasElement> {
    const cv = document.createElement('canvas');
    const scale = Math.min(8, px / Math.max(sheet.widthPt, sheet.heightPt));
    const r = await this.ctl.render(sheet, cv, scale);
    await r.done;
    return cv;
  }

  private async build(sheet: Sheet): Promise<void> {
    const key = this.keyOf(sheet);
    const geo = this.geometry(sheet);
    if (!geo) return;
    let cv: HTMLCanvasElement;
    try {
      cv = await this.paint(sheet, BASE_PX);
    } catch {
      geo.dispose();
      return;
    }
    // The sheet may have been hidden or placed anew while the page was drawn.
    const now = this.ctl.store.sheet(sheet.id);
    if (!now || !this.ctl.shown3d.has(sheet.id) || this.keyOf(now) !== key || this.quads.has(sheet.id)) { geo.dispose(); return; }
    this.renders.base++;
    const tex = new CanvasTexture(cv);
    tex.colorSpace = SRGBColorSpace;
    tex.minFilter = LinearMipmapLinearFilter;
    tex.anisotropy = 4;
    const mat = new MeshBasicMaterial({ map: tex, transparent: true, opacity: this.ctl.quadOpacity, depthWrite: false, side: DoubleSide, toneMapped: false, fog: false });
    const mesh = new Mesh(geo, mat);
    mesh.name = `sheet-quad:${sheet.id}`;
    mesh.userData['sheetQuad'] = sheet.id;
    mesh.renderOrder = 2;
    mesh.frustumCulled = false;
    mesh.raycast = () => {}; // never a pick, a measurement or a classification target
    const q: Quad = { mesh, tex, key, sharp: false, building: false };
    mesh.onBeforeRender = (_r, _s, cam) => this.near(q, sheet.id, cam);
    this.quads.set(sheet.id, q);
    this.app.renderer.scene.add(mesh);
    this.app.renderer.markDirty();
    this.ctl.emit();
  }

  /** The camera came close: draw the page again at a higher resolution (once; cheap to ask, it only starts when close). */
  private near(q: Quad, id: string, cam: Camera): void {
    if (q.sharp || q.building) return;
    const sh = this.ctl.store.sheet(id);
    const bs = q.mesh.geometry.boundingSphere;
    if (!sh || !bs) return;
    const d = cam.position.distanceTo(bs.center);
    if (d > bs.radius * 1.6) return;
    q.building = true;
    void this.paint(sh, SHARP_PX).then((cv) => {
      if (this.quads.get(id) !== q) return;
      q.tex.image = cv;
      q.tex.needsUpdate = true;
      q.sharp = true;
      this.renders.sharp++;
      this.app.renderer.markDirty();
    }).catch(() => undefined).finally(() => { q.building = false; });
  }

  /** For scripts and tests: the quad of a sheet, where it is (IFC elevation of its corners) and how it is drawn. */
  state(sheetId: string): { exists: boolean; elevation?: number; opacity?: number; sharp?: boolean; corners?: Vec3[]; pickable?: boolean; inScene?: boolean } {
    const q = this.quads.get(sheetId);
    if (!q) return { exists: false };
    const pos = q.mesh.geometry.getAttribute('position');
    const shift = this.app.loaded?.model.originShift ?? [0, 0, 0];
    const corners: Vec3[] = [];
    for (let i = 0; i < pos.count; i++) corners.push([pos.getX(i) + shift[0], -pos.getZ(i) + shift[1], pos.getY(i) + shift[2]]);
    return {
      exists: true, elevation: corners[0]![2], opacity: this.material(q).opacity, sharp: q.sharp, corners,
      pickable: q.mesh.raycast.toString().replace(/\s/g, '') !== '()=>{}', inScene: q.mesh.parent === this.app.renderer.scene,
    };
  }

  // ---------------------------------------------------------------- the sketches of placed sheets

  /** The markup as the 3D layout draws it: a shape lies on the sheet's plane (a surface path), an anchor is a point in the model. */
  private asModel(m: Markup, p: SheetPlacement): Markup | null {
    if (isAnchorKind(m.kind)) {
      if (!m.anchor) return null;
      const w = sheetToModel(p, [m.anchor.point[0], m.anchor.point[1]]);
      return { ...m, anchor: { kind: 'point', point: [w[0], w[1], w[2] + LIFT] } };
    }
    if (!m.shape) return null;
    const sp = shapePath(m.kind, m.shape.points);
    const pts: SurfaceData['pts'] = [];
    for (let i = 0; i + 1 < sp.path.length; i += 2) {
      const w = sheetToModel(p, [sp.path[i]!, sp.path[i + 1]!]);
      pts.push({ e: 0, p: [w[0], w[1], w[2] + LIFT] });
    }
    if (pts.length < 2) return null;
    return { ...m, attach: { kind: 'surface', surface: { guids: [], pts, closed: sp.closed } } };
  }

  private shownSets(): Array<{ set: MarkupSet; sheet: Sheet }> {
    const out: Array<{ set: MarkupSet; sheet: Sheet }> = [];
    const mk = this.ctl.markup;
    const here = new Set(this.ctl.docs().here.map((d) => d.id));
    for (const sheet of this.ctl.store.sheets) {
      if (!sheet.placement || !isPlan(sheet.placement) || !here.has(sheet.docId)) continue;
      const sets = this.ctl.sketchesOn(sheet.id).filter((s) => mk.inScope(s));
      for (const set of sets) if (this.ctl.shown3d.has(sheet.id) || mk.activeId === set.id) out.push({ set, sheet });
    }
    return out;
  }

  private drawSketches(o: Overlay): void {
    const layer = this.layer;
    if (!layer) return;
    layer.textContent = '';
    if (!this.app.loaded || this.ctl.openId || this.ctl.placeId || !this.ctl.markup.visible) return;
    for (const { set, sheet } of this.shownSets()) {
      const p = sheet.placement!;
      const ctx = this.ctl.markup.layoutContext(set, o.width, o.height, {
        insets: o.insets, reserved: o.reserved, occluded: undefined as never, resolveSurface: (s: SurfaceData) => s,
      });
      for (const m of set.markups) {
        const t = this.asModel(m, p);
        if (!t) continue;
        const L = layoutMarkupFull(t, ctx, { selected: false });
        if (!L.ops.length) continue;
        const g = svgEl('g', { 'data-mk-sheet3d': m.id, 'data-number': String(m.number), 'data-sheet': sheet.id });
        renderOps(g, L.ops);
        layer.appendChild(g);
      }
    }
  }

  /** Markups drawn in 3D now (scripts, tests). */
  drawnCount(): number {
    return this.layer?.querySelectorAll('[data-mk-sheet3d]').length ?? 0;
  }

  /** Where a sheet point is in the viewer frame (scripts and tests). */
  toViewer(sheet: Sheet, user: [number, number]): Vec3 | null {
    const p = sheet.placement;
    if (!p) return null;
    const w = sheetToModel(p, user);
    return ifcToViewer([w[0], w[1], w[2]], this.app.loaded?.model.originShift ? [...this.app.loaded.model.originShift] as Vec3 : [0, 0, 0]);
  }
}
