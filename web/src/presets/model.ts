// Preset data model: types, validation, the `xray-presets/1` document, the built-in/override merge, user-preset
// naming and the `#preset=<base64url>` share encoding. Pure (no DOM, no app); see docs-features/presets.md.

export const PRESETS_SCHEMA = 'xray-presets/1';

export const GROUPS = ['Review', 'Cutaway', 'Imaging', 'Presentation', 'Basic'] as const;
/** Group of presets the user saved. */
export const USER_GROUP = 'My presets';

export type PresetBase = 'defaults' | 'current';

export interface Preset {
  /** Stable id: lower-case letters, digits and dashes. */
  id: string;
  name: string;
  /** One sentence in plain words. */
  description: string;
  /** One of GROUPS for built-ins, USER_GROUP for presets the user saved. */
  group: string;
  /**
   * `defaults`: the sections this preset touches are first reset to the factory values, then the preset is applied.
   * `current`: the preset is applied over whatever is set now.
   */
  base: PresetBase;
  /** A partial xray-params/1 document. An empty object as a section value only marks the section as touched (reset by `defaults`). */
  params: Record<string, unknown>;
  /** Action ids run (runAction) after the params are applied, for example `section.fitSelection`. */
  actions?: string[];
  /**
   * `selection`: after the params and actions, move the camera so the selection fills the view (nothing happens without
   * a selection). Without it a preset never moves the camera (unless `params.camera` is set).
   */
  frame?: 'selection';
  builtIn: boolean;
}

export interface PresetsDocument {
  schema: typeof PRESETS_SCHEMA;
  exportedAt?: string;
  presets: Array<Omit<Preset, 'builtIn'> & { builtIn?: boolean }>;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

export function slugify(name: string): string {
  const s = name
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return s.slice(0, 48) || 'preset';
}

/** `base`, else `base-2`, `base-3`, ... the first that is not in `taken`. */
export function uniqueId(base: string, taken: ReadonlySet<string>): string {
  if (!taken.has(base)) return base;
  for (let n = 2; ; n++) if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
}

/** `name`, else `name (2)`, `name (3)`, ... compared case-insensitively. */
export function uniqueName(name: string, taken: ReadonlySet<string>): string {
  const t = new Set([...taken].map((x) => x.toLowerCase()));
  if (!t.has(name.toLowerCase())) return name;
  for (let n = 2; ; n++) if (!t.has(`${name} (${n})`.toLowerCase())) return `${name} (${n})`;
}

const ACTION_ID = /^[A-Za-z][\w.-]{0,63}$/;

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

/** Validate one preset. Returns null (with the reason in `why`) for anything unusable. `builtIn` is forced by the caller. */
export function normalizePreset(raw: unknown, builtIn: boolean, why: string[] = []): Preset | null {
  if (!isObj(raw)) {
    why.push('preset is not an object');
    return null;
  }
  const name = typeof raw['name'] === 'string' ? raw['name'].trim() : '';
  if (!name) {
    why.push('preset has no name');
    return null;
  }
  let id = typeof raw['id'] === 'string' ? raw['id'].trim() : '';
  if (!/^[a-z0-9][a-z0-9-]*$/.test(id)) id = slugify(id || name);
  const params = raw['params'];
  if (!isObj(params)) {
    why.push(`preset "${name}" has no params object`);
    return null;
  }
  const base: PresetBase = raw['base'] === 'defaults' ? 'defaults' : 'current';
  const actionsRaw = raw['actions'];
  const actions = Array.isArray(actionsRaw) ? actionsRaw.filter((a): a is string => typeof a === 'string' && ACTION_ID.test(a)) : [];
  const p: Preset = {
    id,
    name,
    description: typeof raw['description'] === 'string' ? raw['description'].trim() : '',
    group: typeof raw['group'] === 'string' && raw['group'].trim() ? raw['group'].trim() : builtIn ? 'Basic' : USER_GROUP,
    base,
    params: clone(params),
    builtIn,
  };
  if (actions.length > 0) p.actions = actions;
  if (raw['frame'] === 'selection') p.frame = 'selection';
  return p;
}

/** Read a presets document (JSON text, parsed JSON, or a bare array of presets). Bad entries are listed in `errors`. */
export function parsePresetsDocument(input: unknown, builtIn = false): { presets: Preset[]; errors: string[] } {
  const errors: string[] = [];
  let data = input;
  if (typeof input === 'string') {
    try {
      data = JSON.parse(input);
    } catch (e) {
      return { presets: [], errors: [`not valid JSON: ${e instanceof Error ? e.message : String(e)}`] };
    }
  }
  let list: unknown;
  if (Array.isArray(data)) list = data;
  else if (isObj(data)) {
    if (data['schema'] !== PRESETS_SCHEMA) errors.push(`schema is not ${PRESETS_SCHEMA}`);
    list = data['presets'];
  }
  if (!Array.isArray(list)) {
    errors.push('no presets array');
    return { presets: [], errors };
  }
  const presets: Preset[] = [];
  for (const raw of list) {
    const p = normalizePreset(raw, builtIn, errors);
    if (p) presets.push(p);
  }
  return { presets, errors };
}

export function serializePresets(presets: readonly Preset[], now: Date = new Date()): string {
  const doc: PresetsDocument = {
    schema: PRESETS_SCHEMA,
    exportedAt: now.toISOString(),
    presets: presets.map((p) => {
      const o: PresetsDocument['presets'][number] = { id: p.id, name: p.name, description: p.description, group: p.group, base: p.base, params: clone(p.params) };
      if (p.actions && p.actions.length > 0) o.actions = [...p.actions];
      if (p.frame) o.frame = p.frame;
      return o;
    }),
  };
  return JSON.stringify(doc, null, 2) + '\n';
}

/**
 * The build-time override: entries whose id matches a built-in replace it (keeping its place in the order), new ids are
 * appended after the built-ins. Override entries count as built-in.
 */
export function mergeOverrides(builtins: readonly Preset[], overrides: readonly Preset[]): Preset[] {
  const out = builtins.map((p) => clone(p));
  for (const o of overrides) {
    const i = out.findIndex((p) => p.id === o.id);
    const entry = { ...clone(o), builtIn: true };
    if (i >= 0) out[i] = entry;
    else out.push(entry);
  }
  return out;
}

/** Find by id, else by name (case-insensitive), else by 1-based key number ("3"). */
export function findPreset<T extends { id: string; name: string }>(list: readonly T[], idOrName: string): T | undefined {
  const q = idOrName.trim();
  const lower = q.toLowerCase();
  return list.find((p) => p.id === q) ?? list.find((p) => p.name.toLowerCase() === lower) ?? (/^[1-9]$/.test(q) ? list[Number(q) - 1] : undefined);
}

/** Key hint for the preset at `index` of the list (keys 1 to 9), else null. */
export function keyOf(index: number): string | null {
  return index >= 0 && index < 9 ? String(index + 1) : null;
}

// ---------------------------------------------------------------- share link `#preset=<base64url>`

function toBase64Url(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(s: string): Uint8Array {
  const b = s.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b + '='.repeat((4 - (b.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** base64url(JSON of { schema, preset }) for one preset (id and builtIn are not carried). */
export function encodePresetShare(p: Preset): string {
  const preset: Record<string, unknown> = { name: p.name, description: p.description, group: p.group, base: p.base, params: p.params };
  if (p.actions && p.actions.length > 0) preset['actions'] = p.actions;
  if (p.frame) preset['frame'] = p.frame;
  return toBase64Url(new TextEncoder().encode(JSON.stringify({ schema: PRESETS_SCHEMA, preset })));
}

/** Inverse of encodePresetShare. The result is a user preset (builtIn false). Null for anything that is not a valid preset. */
export function decodePresetShare(s: string): Preset | null {
  try {
    const v: unknown = JSON.parse(new TextDecoder().decode(fromBase64Url(s.trim())));
    if (!isObj(v) || v['schema'] !== PRESETS_SCHEMA) return null;
    const p = normalizePreset(v['preset'], false);
    if (!p) return null;
    return { ...p, group: USER_GROUP };
  } catch {
    return null;
  }
}

/** The `preset=` value of a location hash like `#preset=...` (also inside `#p=...&preset=...`), decoded. */
export function presetFromHash(hash: string): Preset | null {
  const h = hash.startsWith('#') ? hash.slice(1) : hash;
  for (const part of h.split('&')) if (part.startsWith('preset=')) return decodePresetShare(part.slice('preset='.length));
  return null;
}

/** The hash with the `preset=` part removed (other parts such as `p=` are kept). */
export function hashWithoutPreset(hash: string): string {
  const h = hash.startsWith('#') ? hash.slice(1) : hash;
  const rest = h.split('&').filter((x) => x && !x.startsWith('preset='));
  return rest.length > 0 ? `#${rest.join('&')}` : '';
}

export function presetShareUrl(p: Preset, base: { origin: string; pathname: string; search?: string }): string {
  return `${base.origin}${base.pathname}${base.search ?? ''}#preset=${encodePresetShare(p)}`;
}
