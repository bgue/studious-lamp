// The 3D · Plan · Section switch of a sketch that is tied to a 3D construct: the viewer side of src/issues/derivedViews.ts.
// Plan and Section put the camera in the pseudo-orthographic projection (src/input/navigation.ts) and set the clip planes on the
// renderer, the way a BCF viewpoint does (src/bcf/controller.ts execute). 3D puts the sketch's own camera back and takes the
// clip planes away that the switch added. A section the user had (the section box or plane, or a BCF viewpoint's planes) is
// remembered and put back; planes someone set after the switch are left alone. The attached drawings follow in any camera
// (src/markup/attachScene.ts), so nothing else changes. Docs: docs-features/issues.md.

import type { ViewerApp } from '../app';
import { dirIfcToViewer } from '../bcf/model';
import type { BcfTopic, BcfViewpointRef, Vec3 } from '../bcf/model';
import type { Box6 } from '../bcf/plan';
import { isPseudoOrtho, orthoDistance, placeCamera, setPseudoOrtho } from '../input/navigation';
import { attachmentOf } from '../markup/model';
import type { MarkupSet } from '../markup/model';
import type { MarkupController } from '../markup/controller';
import { storeyFloors } from '../xr/field';
import { deriveView, hintOf, sketchIsTied, sketchTarget } from './derivedViews';
import type { DerivedInput, DerivedSource, DerivedView, TargetCtx, TiedMarkup, ViewMode } from './derivedViews';

interface SavedClips {
  planes: Array<{ normal: Vec3; point: Vec3 }> | null;
  /** The section tool owned the planes: it pushes them again once it has reclaimed them. */
  sectionOwned: boolean;
}

interface SectionLike {
  config: { caps: boolean; capColor: [number, number, number] };
  planes(): unknown[];
  foreignPlanes(): number;
  reclaim(): void;
}

const sectionApi = (): SectionLike | null => (window as unknown as { __xraySection?: SectionLike }).__xraySection ?? null;

export class DerivedViewSwitch {
  private active: { setId: string; mode: 'plan' | 'section' } | null = null;
  private saved: SavedClips | null = null;
  private ourVersion = -1;
  /** Set by the plugin: lets the BCF controller keep ownership of the planes it had set. */
  reclaimBcf: (() => void) | null = null;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly app: ViewerApp, private readonly markup: MarkupController) {}

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  // ---------------------------------------------------------------- what a sketch is tied to

  private tiedOf(set: MarkupSet): TiedMarkup[] {
    return set.markups.map((m) => ({ id: m.id, attach: attachmentOf(m), ...(m.anchor ? { anchorPoint: m.anchor.point } : {}) }));
  }

  /** True when a drawing of the sketch is tied to a 3D construct: the sketch gets the switch. */
  tied(set: MarkupSet | null | undefined): boolean {
    return !!set && sketchIsTied(this.tiedOf(set));
  }

  /** The mode the live view is in for this sketch: Plan or Section after a switch, else 3D. */
  mode(set: MarkupSet | null | undefined): ViewMode {
    // Leaving the orthographic projection by hand (the P key, a saved view) ends the derived view as far as the switch shows.
    return set && this.active?.setId === set.id && isPseudoOrtho() ? this.active.mode : '3d';
  }

  /** A string that changes when the switch of a sketch should be drawn again. */
  key(set: MarkupSet | null | undefined): string {
    return set ? `${this.tied(set) ? 1 : 0}${this.mode(set)}` : '0';
  }

  private ctx(set: MarkupSet): TargetCtx | null {
    const app = this.app;
    if (!app.loaded) return null;
    const model = app.loaded.model;
    const floors = new Map(storeyFloors(model).map((l) => [l.id, l.floorY]));
    const idOf = (g: string): number | undefined => model.byGlobalId.get(g) ?? model.byGlobalId.get(g.replace(/~\d+$/, ''));
    return {
      shift: [model.originShift[0], model.originShift[1], model.originShift[2]],
      elementBox: (g) => {
        const id = idOf(g);
        const b = id !== undefined ? model.elements[id]?.bounds : undefined;
        return b ? [b[0], b[1], b[2], b[3], b[4], b[5]] : null;
      },
      storeyY: (g) => {
        const id = idOf(g);
        const st = id !== undefined ? model.elements[id]?.storey : null;
        return st !== null && st !== undefined ? floors.get(st) ?? null : null;
      },
      resolveSurface: (s) => this.markup.resolveSurface(s, set),
    };
  }

  private modelBox(): Box6 | null {
    const b = this.app.loaded?.geometry.totalBounds();
    return b && !b.isEmpty() ? [b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z] : null;
  }

  /** The input of the derivation for a sketch, or null when nothing it is tied to is in the model. */
  input(set: MarkupSet, aspect: number, selected?: string | null): DerivedInput | null {
    const ctx = this.ctx(set);
    if (!ctx) return null;
    const t = sketchTarget(this.tiedOf(set), ctx, selected);
    if (!t) return null;
    const model = this.app.loaded!.model;
    return {
      target: t.box,
      normal: t.normal,
      storeyY: t.storeyY,
      floors: storeyFloors(model).map((l) => l.floorY),
      model: this.modelBox(),
      aspect,
      hint: hintOf(dirIfcToViewer(set.camera.direction)),
    };
  }

  /** The views of a sketch as the live view would show them now (for the switch and for scripts). */
  derive(set: MarkupSet, mode: 'plan' | 'section', aspect?: number): DerivedView | null {
    const i = this.input(set, aspect ?? this.app.renderer.camera.aspect, this.markup.selected);
    return i ? deriveView(mode, i) : null;
  }

  /** The Plan and Section of the sketch of an issue viewpoint, for the BCF export. Null when the viewpoint has no tied sketch. */
  source(_topic: BcfTopic, ref: BcfViewpointRef): DerivedSource | null {
    const set = ref.sketchId ? this.markup.get(ref.sketchId) : undefined;
    if (!set || !this.app.loaded) return null;
    const i = this.input(set, set.camera.aspect > 0 ? set.camera.aspect : 1.6, null);
    if (!i) return null;
    const model = this.app.loaded.model;
    return {
      sketch: set.id,
      views: { plan: deriveView('plan', i), section: deriveView('section', i) },
      shift: [model.originShift[0], model.originShift[1], model.originShift[2]],
      aspect: set.camera.aspect > 0 ? set.camera.aspect : 1.6,
    };
  }

  // ---------------------------------------------------------------- switching

  /** Switch the live view of a sketch. False when it cannot (not tied, nothing of the target in the model, no model). */
  apply(setId: string, mode: ViewMode): boolean {
    const set = this.markup.get(setId);
    const app = this.app;
    if (!set || !app.loaded) return false;
    if (mode === '3d') return this.back(set);
    const view = this.derive(set, mode);
    if (!view) return false;
    if (!this.saved) this.save();
    const r = app.renderer;
    setPseudoOrtho(app, true);
    const d = orthoDistance(view.orthoHeight);
    placeCamera(app, {
      position: [view.target[0] - view.direction[0] * d, view.target[1] - view.direction[1] * d, view.target[2] - view.direction[2] * d],
      target: view.target,
      up: view.up,
    });
    r.setClipPlanes(view.clip, { cap: true });
    this.ourVersion = r.clipVersion;
    this.active = { setId: set.id, mode };
    this.markup.activeId = set.id;
    this.markup.selected = this.markup.selected && set.markups.some((m) => m.id === this.markup.selected) ? this.markup.selected : null;
    this.done();
    return true;
  }

  /** 3D: the authored camera of the sketch and no clip planes of ours. */
  private back(set: MarkupSet): boolean {
    const app = this.app;
    const cam = set.view.camera;
    setPseudoOrtho(app, cam.ortho === true);
    placeCamera(app, { position: cam.position, target: cam.target, up: cam.up, fov: cam.fov });
    this.restore();
    this.active = null;
    this.markup.activeId = set.id;
    this.done();
    return true;
  }

  private done(): void {
    this.app.renderer.markDirty();
    this.markup.emit(true);
    for (const l of this.listeners) l();
  }

  private save(): void {
    const r = this.app.renderer;
    const sec = sectionApi();
    const planes = r.getClipPlanes();
    this.saved = {
      planes: planes && planes.length ? planes.map((p) => ({ normal: [...p.normal] as Vec3, point: [...p.point] as Vec3 })) : null,
      sectionOwned: !!sec && !!planes && planes.length > 0 && sec.foreignPlanes() === 0 && sec.planes().length > 0,
    };
  }

  /** Put the planes back that were in force before the first switch, unless someone set planes since. */
  private restore(): void {
    const s = this.saved;
    this.saved = null;
    if (!s) return;
    const r = this.app.renderer;
    if (r.clipVersion !== this.ourVersion) return; // the section tool or a viewpoint took the planes since: theirs stand
    const sec = sectionApi();
    r.setClipPlanes(s.planes, { cap: sec?.config.caps ?? true, ...(sec ? { capColor: sec.config.capColor } : {}) });
    if (s.sectionOwned) sec?.reclaim();
    else this.reclaimBcf?.();
  }

  /** A model was installed: the planes and the camera belong to the old one. */
  onModel(): void {
    this.active = null;
    this.saved = null;
  }
}
