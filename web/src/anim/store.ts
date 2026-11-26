// The fly-throughs of the loaded model: a list of named fly-throughs, one active, persisted in localStorage under the model's
// identity key (`xray.flythroughs.<identityKey>`). No DOM. The first load of a model that has the old keyframes
// (`xray.flythrough.<modelName>`) imports them as a fly-through named "Imported". Tested in tests/anim-store.test.ts.

import type { SavedView, StorageLike } from '../views/model';
import {
  FLYTHROUGHS_SCHEMA,
  LEGACY_KEY_PREFIX,
  MAX_KEYFRAMES,
  flyStorageKey,
  migrateLegacy,
  newFlyThrough,
  newKeyframe,
  parseFlyDoc,
  serializeFlyDoc,
  uniqueFlyName,
} from './flythrough';
import { cleanFields } from './flythrough';
import type { FlyDoc, FlyKeyframe, FlyThrough } from './flythrough';
import { defaultHud, sanitizeHud } from './hud/settings';
import type { HudSettings } from './hud/settings';

export type KeyframePatch = Partial<Pick<FlyKeyframe, 'name' | 'hold' | 'ease' | 'fade' | 'fadeFraction' | 'switchAt' | 'caption' | 'hover'>> & { travel?: number | null; labels?: { fields: string[] } | null };

export class FlyStore {
  doc: FlyDoc = { schema: FLYTHROUGHS_SCHEMA, flythroughs: [], active: null };
  key = '';
  /** Default speed (m/s) of a new fly-through. */
  defaultSpeed = 3;
  private listeners = new Set<() => void>();

  constructor(private readonly storage: StorageLike | null) {}

  onChange(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    for (const f of this.listeners) f();
  }

  /** Load the fly-throughs of a model. `legacyKey` is the old key (`xray.flythrough.<modelName>`). */
  load(identityKey: string, legacyModelName: string, fov = 50): { migrated: boolean } {
    this.key = flyStorageKey(identityKey);
    let text: string | null = null;
    try {
      text = this.storage?.getItem(this.key) ?? null;
    } catch {
      text = null;
    }
    const parsed = parseFlyDoc(text);
    if (parsed) {
      this.doc = parsed;
      this.emit();
      return { migrated: false };
    }
    this.doc = { schema: FLYTHROUGHS_SCHEMA, flythroughs: [], active: null };
    let migrated = false;
    if (text === null) {
      let legacy: string | null = null;
      try {
        legacy = this.storage?.getItem(LEGACY_KEY_PREFIX + legacyModelName) ?? null;
      } catch {
        legacy = null;
      }
      const ft = migrateLegacy(legacy, fov);
      if (ft) {
        ft.speed = this.defaultSpeed;
        this.doc.flythroughs.push(ft);
        this.doc.active = ft.id;
        migrated = true;
        this.save();
      }
    }
    this.emit();
    return { migrated };
  }

  save(): boolean {
    if (!this.storage || !this.key) return false;
    try {
      this.storage.setItem(this.key, serializeFlyDoc(this.doc));
      return true;
    } catch {
      return false;
    }
  }

  private commit(): void {
    this.save();
    this.emit();
  }

  get list(): readonly FlyThrough[] {
    return this.doc.flythroughs;
  }

  get active(): FlyThrough | null {
    return this.doc.flythroughs.find((f) => f.id === this.doc.active) ?? this.doc.flythroughs[0] ?? null;
  }

  find(key: string): FlyThrough | null {
    const l = this.doc.flythroughs;
    const n = Number(key);
    return l.find((f) => f.id === key) ?? l.find((f) => f.name.toLowerCase() === key.toLowerCase()) ?? (Number.isInteger(n) && n >= 1 ? l[n - 1] ?? null : null);
  }

  setActive(id: string): void {
    if (this.doc.flythroughs.some((f) => f.id === id) && this.doc.active !== id) {
      this.doc.active = id;
      this.commit();
    }
  }

  create(name?: string): FlyThrough {
    const ft = newFlyThrough(uniqueFlyName(name ?? `Fly-through ${this.doc.flythroughs.length + 1}`, this.doc.flythroughs), this.defaultSpeed);
    this.doc.flythroughs.push(ft);
    this.doc.active = ft.id;
    this.commit();
    return ft;
  }

  /** The active fly-through, created when there is none. */
  ensureActive(): FlyThrough {
    return this.active ?? this.create('Fly-through 1');
  }

  rename(id: string, name: string): void {
    const f = this.find(id);
    if (!f || !name.trim()) return;
    f.name = uniqueFlyName(name, this.doc.flythroughs, f.id);
    this.commit();
  }

  duplicate(id: string): FlyThrough | null {
    const f = this.find(id);
    if (!f) return null;
    const copy = JSON.parse(JSON.stringify(f)) as FlyThrough;
    const fresh = newFlyThrough(uniqueFlyName(`${f.name} copy`, this.doc.flythroughs), f.speed);
    copy.id = fresh.id;
    copy.name = fresh.name;
    copy.keyframes = copy.keyframes.map((k) => ({ ...k, id: newKeyframe(k.view).id }));
    this.doc.flythroughs.push(copy);
    this.doc.active = copy.id;
    this.commit();
    return copy;
  }

  remove(id: string): void {
    const i = this.doc.flythroughs.findIndex((f) => f.id === id);
    if (i < 0) return;
    this.doc.flythroughs.splice(i, 1);
    if (this.doc.active === id) this.doc.active = this.doc.flythroughs[0]?.id ?? null;
    this.commit();
  }

  setOptions(id: string, o: Partial<Pick<FlyThrough, 'timing' | 'speed' | 'segmentS' | 'lookAtSelection' | 'loop' | 'overlays'>>): void {
    const f = this.find(id);
    if (!f) return;
    if (o.timing) f.timing = o.timing;
    if (o.speed !== undefined && o.speed > 0) f.speed = o.speed;
    if (o.segmentS !== undefined && o.segmentS >= 0) f.segmentS = o.segmentS;
    if (o.lookAtSelection !== undefined) f.lookAtSelection = o.lookAtSelection;
    if (o.loop !== undefined) {
      if (o.loop) f.loop = true;
      else delete f.loop;
    }
    if (o.overlays !== undefined) {
      if (o.overlays) f.overlays = true;
      else delete f.overlays;
    }
    this.commit();
  }

  // ---------------------------------------------------------------- keyframes

  add(ft: FlyThrough, view: SavedView, at?: number, opts: Partial<FlyKeyframe> = {}): FlyKeyframe | null {
    if (ft.keyframes.length >= MAX_KEYFRAMES) return null;
    const k = newKeyframe(view, opts);
    const i = at === undefined ? ft.keyframes.length : Math.min(Math.max(at, 0), ft.keyframes.length);
    ft.keyframes.splice(i, 0, k);
    this.commit();
    return k;
  }

  replaceAll(ft: FlyThrough, keys: FlyKeyframe[]): void {
    ft.keyframes = keys.slice(0, MAX_KEYFRAMES);
    this.commit();
  }

  update(ft: FlyThrough, index: number, patch: KeyframePatch): boolean {
    const k = ft.keyframes[index];
    if (!k) return false;
    if (patch.name !== undefined && patch.name.trim()) k.name = patch.name.trim();
    if (patch.travel !== undefined) {
      if (patch.travel === null || !Number.isFinite(patch.travel)) delete k.travel;
      else k.travel = Math.max(0, patch.travel);
    }
    if (patch.hold !== undefined) k.hold = Math.min(3600, Math.max(0, Number(patch.hold) || 0));
    if (patch.ease !== undefined) k.ease = !!patch.ease;
    if (patch.fade !== undefined) k.fade = !!patch.fade;
    if (patch.fadeFraction !== undefined) k.fadeFraction = Math.min(1, Math.max(0.05, Number(patch.fadeFraction) || 0.4));
    if (patch.switchAt !== undefined) k.switchAt = patch.switchAt;
    if ('caption' in patch) {
      const c = patch.caption;
      if (c && ((c.title ?? '').trim() || (c.text ?? '').trim())) k.caption = { ...(c.title ? { title: c.title } : {}), ...(c.text ? { text: c.text } : {}) };
      else delete k.caption;
    }
    if ('labels' in patch) {
      if (patch.labels) k.labels = { fields: cleanFields(patch.labels.fields) };
      else delete k.labels;
    }
    if (patch.hover !== undefined) {
      if (patch.hover) k.hover = true;
      else delete k.hover;
    }
    this.commit();
    return true;
  }

  /** The HUD settings (progress bar, compass, scale bar, label size, caption position) of this model's fly-throughs. */
  get hud(): HudSettings {
    return this.doc.hud ?? defaultHud();
  }

  setHud(patch: Partial<HudSettings>): void {
    this.doc.hud = sanitizeHud({ ...this.hud, ...patch });
    this.commit();
  }

  /** Replace the state of a keyframe with a view; timing, name and caption stay. */
  setView(ft: FlyThrough, index: number, view: SavedView): boolean {
    const k = ft.keyframes[index];
    if (!k) return false;
    k.view = JSON.parse(JSON.stringify(view)) as SavedView;
    this.commit();
    return true;
  }

  removeKeyframe(ft: FlyThrough, index: number): boolean {
    if (!ft.keyframes[index]) return false;
    ft.keyframes.splice(index, 1);
    this.commit();
    return true;
  }

  move(ft: FlyThrough, from: number, to: number): boolean {
    const n = ft.keyframes.length;
    if (from < 0 || from >= n || to < 0 || to >= n || from === to) return false;
    const [k] = ft.keyframes.splice(from, 1);
    ft.keyframes.splice(to, 0, k!);
    this.commit();
    return true;
  }

  clear(ft: FlyThrough): void {
    ft.keyframes = [];
    this.commit();
  }

  /** An explicit export of the active fly-through (or all), with captions. */
  exportDoc(all = false, withThumbs = true): string {
    const a = this.active;
    const doc: FlyDoc = all || !a ? this.doc : { schema: FLYTHROUGHS_SCHEMA, flythroughs: [a], active: a.id, ...(this.doc.hud ? { hud: this.doc.hud } : {}) };
    return serializeFlyDoc(doc, withThumbs);
  }

  /** Add the fly-throughs of an exported document (new ids on a clash). Returns how many. */
  importDoc(text: string): number {
    const d = parseFlyDoc(text);
    if (!d) return 0;
    const ids = new Set(this.doc.flythroughs.map((f) => f.id));
    let n = 0;
    for (const f of d.flythroughs) {
      if (ids.has(f.id)) f.id = newFlyThrough('x').id;
      f.name = uniqueFlyName(f.name, this.doc.flythroughs);
      this.doc.flythroughs.push(f);
      this.doc.active = f.id;
      n++;
    }
    if (n) this.commit();
    return n;
  }
}
