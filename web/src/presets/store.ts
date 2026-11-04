// The preset list: built-ins (TS data, optionally replaced by the build-time override) plus the user's own presets,
// persisted in localStorage 'xray.presets'. No DOM; the storage is injected.

import type { StorageLike } from '../selectionSets';
import { BUILTIN_PRESETS } from './builtin';
import { PRESETS_SCHEMA, USER_GROUP, mergeOverrides, normalizePreset, parsePresetsDocument, serializePresets, slugify, uniqueId, uniqueName } from './model';
import type { Preset } from './model';

export const PRESETS_STORAGE_KEY = 'xray.presets';

export class PresetStore {
  private builtins: Preset[];
  private user: Preset[] = [];
  private readonly listeners = new Set<() => void>();

  constructor(private readonly storage: StorageLike | null, overrides: readonly Preset[] = []) {
    this.builtins = mergeOverrides(BUILTIN_PRESETS, overrides);
    this.load();
  }

  /** Built-ins in order, then user presets in the order they were saved. */
  list(): Preset[] {
    return [...this.builtins, ...this.user];
  }

  userPresets(): Preset[] {
    return [...this.user];
  }

  get(id: string): Preset | undefined {
    return this.list().find((p) => p.id === id);
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  /** Replace the built-ins by the merge of the TS data with `overrides` (after the JSON file was fetched). */
  setOverrides(overrides: readonly Preset[]): void {
    this.builtins = mergeOverrides(BUILTIN_PRESETS, overrides);
    // A user preset whose id now clashes with a built-in id gets a new one.
    const taken = new Set(this.builtins.map((p) => p.id));
    this.user = this.user.map((p) => {
      if (!taken.has(p.id)) {
        taken.add(p.id);
        return p;
      }
      const id = uniqueId(p.id, taken);
      taken.add(id);
      return { ...p, id };
    });
    this.changed(true);
  }

  private takenIds(): Set<string> {
    return new Set(this.list().map((p) => p.id));
  }

  private takenNames(except?: string): Set<string> {
    return new Set(this.list().filter((p) => p.id !== except).map((p) => p.name));
  }

  /** Add a user preset (id and name are made unique). Returns the stored preset. */
  add(p: Preset): Preset {
    const stored: Preset = {
      ...JSON.parse(JSON.stringify(p)) as Preset,
      id: uniqueId(slugify(p.id || p.name), this.takenIds()),
      name: uniqueName(p.name, this.takenNames()),
      group: USER_GROUP,
      builtIn: false,
    };
    this.user.push(stored);
    this.changed(true);
    return stored;
  }

  /** Rename and/or re-describe a user preset. Returns false for an unknown or built-in id. */
  update(id: string, patch: { name?: string; description?: string }): boolean {
    const p = this.user.find((x) => x.id === id);
    if (!p) return false;
    if (patch.name !== undefined && patch.name.trim()) p.name = uniqueName(patch.name.trim(), this.takenNames(id));
    if (patch.description !== undefined) p.description = patch.description.trim();
    this.changed(true);
    return true;
  }

  /** A copy of any preset as a new user preset. */
  duplicate(id: string): Preset | null {
    const p = this.get(id);
    if (!p) return null;
    return this.add({ ...JSON.parse(JSON.stringify(p)) as Preset, id: `${p.id}-copy`, name: `${p.name} copy` });
  }

  remove(id: string): boolean {
    const i = this.user.findIndex((x) => x.id === id);
    if (i < 0) return false;
    this.user.splice(i, 1);
    this.changed(true);
    return true;
  }

  /** Export document: the user presets, or every preset with `all`. */
  exportJson(all = false, now?: Date): string {
    return serializePresets(all ? this.list() : this.user, now);
  }

  /** Import a presets document. Imported presets are always user presets; ids and names are made unique. */
  importJson(text: string): { added: Preset[]; errors: string[] } {
    const { presets, errors } = parsePresetsDocument(text, false);
    const added: Preset[] = [];
    for (const p of presets) {
      const norm = normalizePreset(p, false);
      if (norm) added.push(this.add(norm));
    }
    return { added, errors };
  }

  private changed(persist: boolean): void {
    if (persist) this.persist();
    for (const l of this.listeners) l();
  }

  private persist(): boolean {
    if (!this.storage) return false;
    try {
      this.storage.setItem(PRESETS_STORAGE_KEY, serializePresets(this.user));
      return true;
    } catch {
      return false;
    }
  }

  private load(): void {
    if (!this.storage) return;
    let text: string | null = null;
    try {
      text = this.storage.getItem(PRESETS_STORAGE_KEY);
    } catch {
      return;
    }
    if (!text) return;
    const taken = new Set(this.builtins.map((p) => p.id));
    const names = new Set(this.builtins.map((p) => p.name));
    for (const p of parsePresetsDocument(text, false).presets) {
      const id = uniqueId(p.id, taken);
      taken.add(id);
      const name = uniqueName(p.name, names);
      names.add(name);
      this.user.push({ ...p, id, name, group: USER_GROUP, builtIn: false });
    }
  }
}

export { PRESETS_SCHEMA };
