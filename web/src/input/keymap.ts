// Keymap engine: chord parsing, matching, dispatch, hold actions, conflicts and user overrides.
// Pure TypeScript apart from the optional `target` of a key event (blur on Escape): no DOM access at import time,
// so the whole engine runs in vitest with synthetic KeyboardEvent-like objects and an in-memory storage.
//
// Chord syntax (see actions.ts): optional modifiers `Ctrl+ Alt+ Shift+ Meta+`, then a KeyboardEvent.key
// ('x', '?', 'Escape', 'ArrowLeft') or `code:` + KeyboardEvent.code ('code:Numpad7', 'code:Digit1').
// Matching rules:
//   - Ctrl, Alt and Meta must be exactly as in the chord.
//   - Shift must be exactly as in the chord, except for a chord that is one printable symbol (not a letter or a digit),
//     such as '?', '+', '[': the shift state is implied by the character, so Shift is then ignored.
//   - Letters match case-insensitively. A chord Alt+<letter> or Alt+<digit> also matches by physical key
//     (KeyboardEvent.code), because Alt produces other characters on some layouts.

import type { ViewerApp } from '../app';
import type { HoldMods, XrayAction } from './actions';
import { getActions, onActionsChanged } from './actions';
import type { StorageLike } from '../selectionSets';

export const KEYMAP_STORAGE_KEY = 'xray.keymap';
export const KEYMAP_SCHEMA = 'xray-keymap/1';

export interface Chord {
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  meta: boolean;
  /** Lower-case key name, or `code:` + the code in its original case. */
  key: string;
}

/** The members of a KeyboardEvent the engine reads. */
export interface KeyLike {
  key: string;
  code?: string;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  metaKey?: boolean;
  repeat?: boolean;
  isComposing?: boolean;
  target?: unknown;
  preventDefault?(): void;
}

const NAMED_KEYS = [
  'Escape', 'Enter', 'Tab', 'Backspace', 'Delete', 'Insert', 'Home', 'End', 'PageUp', 'PageDown',
  'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space',
  'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12',
];
const NAME_BY_LOWER = new Map<string, string>(NAMED_KEYS.map((k) => [k.toLowerCase(), k]));
const ALIASES: Record<string, string> = {
  esc: 'Escape', return: 'Enter', del: 'Delete', ins: 'Insert', pgup: 'PageUp', pgdn: 'PageDown', pageup: 'PageUp', pagedown: 'PageDown',
  up: 'ArrowUp', down: 'ArrowDown', left: 'ArrowLeft', right: 'ArrowRight', ' ': 'Space', spacebar: 'Space',
};
const MOD_NAMES: Record<string, 'ctrl' | 'alt' | 'shift' | 'meta'> = {
  ctrl: 'ctrl', control: 'ctrl', alt: 'alt', option: 'alt', shift: 'shift', meta: 'meta', cmd: 'meta', command: 'meta',
};
const MOD_PREFIX = /^(ctrl|control|alt|option|shift|meta|cmd|command)\+/i;

/** Parse a chord string. Returns null when it is empty or has no key. */
export function parseChord(text: string): Chord | null {
  if (typeof text !== 'string') return null;
  let rest = text.trim();
  const c: Chord = { ctrl: false, alt: false, shift: false, meta: false, key: '' };
  for (;;) {
    const m = MOD_PREFIX.exec(rest);
    if (!m || rest.length <= m[0].length) break;
    c[MOD_NAMES[m[1]!.toLowerCase()]!] = true;
    rest = rest.slice(m[0].length);
  }
  if (!rest) return null;
  if (/^code:/i.test(rest)) {
    const code = rest.slice(5).trim();
    if (!code) return null;
    c.key = `code:${code}`;
    return c;
  }
  if (rest.length > 1 || rest === ' ') {
    const lower = rest.toLowerCase();
    const named = NAME_BY_LOWER.get(lower) ?? ALIASES[lower];
    if (!named) {
      // Unknown multi-character key names are accepted as given (KeyboardEvent.key values such as 'ContextMenu').
      if (/\s/.test(rest) || rest.endsWith('+') || MOD_NAMES[lower]) return null;
      c.key = lower;
      return c;
    }
    c.key = named.toLowerCase();
    return c;
  }
  c.key = rest.toLowerCase();
  return c;
}

function displayKey(key: string): string {
  if (key.startsWith('code:')) return key;
  if (key.length === 1) return key;
  const named = NAME_BY_LOWER.get(key);
  if (named) return named;
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/** Canonical text of a parsed chord: 'Ctrl+Alt+Shift+Meta+' then the key. */
export function chordToString(c: Chord): string {
  return `${c.ctrl ? 'Ctrl+' : ''}${c.alt ? 'Alt+' : ''}${c.shift ? 'Shift+' : ''}${c.meta ? 'Meta+' : ''}${displayKey(c.key)}`;
}

/** Canonical form of a chord string ('shift+H' -> 'Shift+h'), or null when it is not valid. */
export function normalizeChord(text: string): string | null {
  const c = parseChord(text);
  return c ? chordToString(c) : null;
}

/** Index key of a chord string: the canonical form in lower case. */
export function chordKey(text: string): string | null {
  const n = normalizeChord(text);
  return n === null ? null : n.toLowerCase();
}

const isLetter = (k: string): boolean => k.length === 1 && k.toLowerCase() !== k.toUpperCase();
const isDigit = (k: string): boolean => k.length === 1 && k >= '0' && k <= '9';
/** A chord key that is one printable symbol whose shift state comes from the layout ('?', '+', '['). */
const isSymbol = (k: string): boolean => k.length === 1 && !isLetter(k) && !isDigit(k);

function modPrefix(ctrl: boolean, alt: boolean, shift: boolean, meta: boolean): string {
  return `${ctrl ? 'ctrl+' : ''}${alt ? 'alt+' : ''}${shift ? 'shift+' : ''}${meta ? 'meta+' : ''}`;
}

/** Lower-case chord keys an event can match, most specific first. */
export function eventCandidates(ev: KeyLike): string[] {
  const ctrl = !!ev.ctrlKey;
  const alt = !!ev.altKey;
  const shift = !!ev.shiftKey;
  const meta = !!ev.metaKey;
  const out: string[] = [];
  const add = (mods: string, token: string): void => {
    const k = mods + token;
    if (!out.includes(k)) out.push(k);
  };
  const full = modPrefix(ctrl, alt, shift, meta);
  const noShift = modPrefix(ctrl, alt, false, meta);
  const code = ev.code ?? '';
  if (code) add(full, `code:${code}`.toLowerCase());
  let key = ev.key ?? '';
  if (key === ' ') key = 'space';
  const lk = key.toLowerCase();
  if (lk && lk !== 'dead' && lk !== 'unidentified') {
    add(full, lk);
    if (shift && isSymbol(key)) add(noShift, lk);
  }
  if (alt && code) {
    // Alt changes the produced character on some layouts: fall back to the physical key.
    const m = /^Key([A-Z])$/.exec(code) ?? /^Digit([0-9])$/.exec(code);
    if (m) add(full, m[1]!.toLowerCase());
  }
  return out;
}

/** Does the event match the chord (a string or a parsed chord)? */
export function matchesChord(chord: string | Chord, ev: KeyLike): boolean {
  const c = typeof chord === 'string' ? parseChord(chord) : chord;
  if (!c) return false;
  const k = chordToString(c).toLowerCase();
  return eventCandidates(ev).includes(k);
}

/** Like matchesChord, but the modifiers in `allowed` may differ from the chord. */
function matchesLoose(c: Chord, ev: KeyLike, allowed: ReadonlyArray<'ctrl' | 'alt' | 'shift' | 'meta'>): boolean {
  const flags = { ctrl: !!ev.ctrlKey, alt: !!ev.altKey, shift: !!ev.shiftKey, meta: !!ev.metaKey };
  const forced = { ...flags };
  for (const m of allowed) forced[m] = c[m];
  const e2: KeyLike = { key: ev.key, code: ev.code, ctrlKey: forced.ctrl, altKey: forced.alt, shiftKey: forced.shift, metaKey: forced.meta };
  return matchesChord(c, e2);
}

const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'OS', 'CapsLock', 'NumLock', 'ScrollLock', 'Fn', 'Hyper', 'Super']);
export function isModifierKey(key: string): boolean {
  return MODIFIER_KEYS.has(key);
}

/**
 * Chord string for a key event, for the keymap editor. Null for a bare modifier key. Numpad keys and Alt or Ctrl
 * with a letter or digit are recorded by physical key so the binding survives a layout change.
 */
export function eventToChord(ev: KeyLike): string | null {
  if (!ev.key || isModifierKey(ev.key)) return null;
  const code = ev.code ?? '';
  const mods = { ctrl: !!ev.ctrlKey, alt: !!ev.altKey, shift: !!ev.shiftKey, meta: !!ev.metaKey };
  let key: string;
  const digit = /^Digit([0-9])$/.exec(code);
  const letter = /^Key([A-Z])$/.exec(code);
  if (code.startsWith('Numpad')) key = `code:${code}`;
  else if (digit && (mods.alt || mods.ctrl || mods.meta || !mods.shift)) key = `code:${code}`;
  else if (letter && (mods.alt || mods.meta)) key = letter[1]!.toLowerCase();
  else key = ev.key === ' ' ? 'Space' : ev.key;
  if (isSymbol(key)) mods.shift = false;
  return chordToString({ ...mods, key: parseChord(key)?.key ?? key.toLowerCase() });
}

export interface TypingTargetLike {
  tagName?: string;
  type?: string;
  isContentEditable?: boolean;
  readOnly?: boolean;
}

const NON_TEXT_INPUTS = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'image', 'file', 'color']);

/** True when keys typed at `t` belong to a text field (input, textarea, select, contenteditable). */
export function isTypingTarget(t: unknown): boolean {
  if (!t || typeof t !== 'object') return false;
  const e = t as TypingTargetLike;
  if (e.isContentEditable) return true;
  const tag = (e.tagName ?? '').toUpperCase();
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') return !NON_TEXT_INPUTS.has((e.type ?? 'text').toLowerCase());
  return false;
}

/** Display text of a chord for humans: 'Ctrl+k', 'Num 7', 'Left'. */
export function formatChord(text: string): string {
  const c = parseChord(text);
  if (!c) return text;
  const parts: string[] = [];
  if (c.ctrl) parts.push('Ctrl');
  if (c.alt) parts.push('Alt');
  if (c.shift) parts.push('Shift');
  if (c.meta) parts.push('Meta');
  let k = c.key;
  if (k.startsWith('code:')) {
    const code = k.slice(5);
    const num = /^Numpad(.+)$/.exec(code);
    const dig = /^Digit([0-9])$/.exec(code);
    const key = /^Key([A-Z])$/.exec(code);
    const names: Record<string, string> = { Decimal: '.', Add: '+', Subtract: '-', Multiply: '*', Divide: '/', Enter: 'Enter' };
    k = num ? `Num ${names[num[1]!] ?? num[1]}` : dig ? dig[1]! : key ? key[1]! : code === 'Period' ? '.' : code;
  } else if (k.length === 1) {
    k = k.toUpperCase();
  } else {
    const named = NAME_BY_LOWER.get(k) ?? displayKey(k);
    const arrows: Record<string, string> = { ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', Escape: 'Esc' };
    k = arrows[named] ?? named;
  }
  parts.push(k);
  return parts.join('+');
}

export type Bindings = Record<string, string[]>;

export interface ImportResult {
  ok: boolean;
  applied: number;
  bad: string[];
}

export interface Conflict {
  /** Canonical chord. */
  chord: string;
  ids: string[];
}

export interface KeymapDeps {
  actions?: () => XrayAction[];
  storage?: StorageLike | null;
  warn?: (msg: string) => void;
}

export interface Overlay {
  isOpen(): boolean;
  close(): void;
}

/** Cap on the dt a hold action sees, so a stalled frame does not make the camera jump. */
export const MAX_HOLD_DT = 100;

const ZERO_MODS: HoldMods = { ctrl: false, shift: false, alt: false, meta: false };

export class Keymap {
  /** User overrides: action id -> chords. An empty array unbinds the action. */
  overrides: Bindings = {};

  private readonly deps: KeymapDeps;
  private index = new Map<string, string[]>();
  private byId = new Map<string, XrayAction>();
  private dirty = true;
  private lastConflictSig = '';
  private readonly pressed = new Map<string, KeyLike>();
  private mods: HoldMods = { ...ZERO_MODS };
  private readonly overlays = new Set<Overlay>();
  private readonly changeListeners = new Set<() => void>();
  private unsub: (() => void) | null = null;

  constructor(deps: KeymapDeps = {}) {
    this.deps = deps;
  }

  /** Follow the global action registry (rebuild the index when actions change). Call dispose() to stop. */
  watchRegistry(): void {
    this.unsub?.();
    this.unsub = onActionsChanged(() => this.invalidate());
  }

  dispose(): void {
    this.unsub?.();
    this.unsub = null;
  }

  private actions(): XrayAction[] {
    return (this.deps.actions ?? getActions)();
  }

  private warn(msg: string): void {
    (this.deps.warn ?? ((m: string) => console.warn(m)))(msg);
  }

  onChange(cb: () => void): () => void {
    this.changeListeners.add(cb);
    return () => this.changeListeners.delete(cb);
  }

  private emit(): void {
    for (const l of this.changeListeners) l();
  }

  invalidate(): void {
    this.dirty = true;
    this.emit();
  }

  // ------------------------------------------------------------------ bindings

  /** Default chords of an action, normalised. */
  defaultsOf(id: string): string[] {
    const a = this.actions().find((x) => x.id === id);
    return normalizeList(a?.keys ?? []);
  }

  /** Effective chords of an action: its override when there is one, else its defaults. */
  bindingsOf(id: string): string[] {
    const o = this.overrides[id];
    return o ? [...o] : this.defaultsOf(id);
  }

  isOverridden(id: string): boolean {
    return id in this.overrides;
  }

  /** Set the chords of an action. Chords equal to the defaults drop the override. */
  setBinding(id: string, chords: string[]): void {
    const list = normalizeList(chords);
    const def = this.defaultsOf(id);
    if (sameList(list, def)) delete this.overrides[id];
    else this.overrides[id] = list;
    this.save();
    this.invalidate();
  }

  resetBinding(id: string): void {
    delete this.overrides[id];
    this.save();
    this.invalidate();
  }

  resetAll(): void {
    this.overrides = {};
    this.save();
    this.invalidate();
  }

  // ------------------------------------------------------------------ persistence

  load(): void {
    try {
      const raw = this.deps.storage?.getItem(KEYMAP_STORAGE_KEY) ?? null;
      this.overrides = raw ? parseBindings(raw).bindings : {};
    } catch {
      this.overrides = {};
    }
    this.invalidate();
  }

  save(): void {
    try {
      this.deps.storage?.setItem(KEYMAP_STORAGE_KEY, JSON.stringify(this.overrides));
    } catch {
      /* storage refused: the overrides still work for this session */
    }
  }

  /** The overrides as a document for export. */
  exportJson(): string {
    return JSON.stringify({ schema: KEYMAP_SCHEMA, bindings: this.overrides }, null, 2);
  }

  /** Replace the overrides with those of a JSON document (an export, or a plain id -> chords map). */
  importJson(text: string): ImportResult {
    let parsed: ReturnType<typeof parseBindings>;
    try {
      parsed = parseBindings(text);
    } catch (e) {
      return { ok: false, applied: 0, bad: [e instanceof Error ? e.message : String(e)] };
    }
    this.overrides = parsed.bindings;
    this.save();
    this.invalidate();
    return { ok: true, applied: Object.keys(parsed.bindings).length, bad: parsed.bad };
  }

  // ------------------------------------------------------------------ index and conflicts

  private rebuild(): void {
    if (!this.dirty) return;
    this.dirty = false;
    this.index = new Map();
    this.byId = new Map();
    const actions = this.actions();
    for (const a of actions) this.byId.set(a.id, a);
    for (const a of actions) {
      for (const ch of this.bindingsOf(a.id)) {
        const k = ch.toLowerCase();
        const list = this.index.get(k) ?? [];
        if (!list.includes(a.id)) list.push(a.id);
        this.index.set(k, list);
      }
    }
    const conflicts = this.conflicts();
    const sig = conflicts.map((c) => `${c.chord}=${c.ids.join(',')}`).join(';');
    if (sig && sig !== this.lastConflictSig) {
      for (const c of conflicts) this.warn(`[keymap] conflict: ${c.chord} is bound to ${c.ids.join(', ')}`);
    }
    this.lastConflictSig = sig;
  }

  /** Chords bound to more than one action. */
  conflicts(): Conflict[] {
    this.rebuildIndexOnly();
    const out: Conflict[] = [];
    for (const [k, ids] of this.index) {
      if (ids.length > 1) out.push({ chord: normalizeChord(k) ?? k, ids: [...ids] });
    }
    return out.sort((a, b) => a.chord.localeCompare(b.chord));
  }

  private rebuildIndexOnly(): void {
    if (this.dirty) this.rebuild();
  }

  /** Lower-case chord keys that are in conflict. */
  conflictKeys(): Set<string> {
    return new Set(this.conflicts().map((c) => c.chord.toLowerCase()));
  }

  /** Ids bound to a chord (any text form). */
  idsFor(chord: string): string[] {
    this.rebuildIndexOnly();
    const k = chordKey(chord);
    return k ? [...(this.index.get(k) ?? [])] : [];
  }

  /** First chord of an action for display ('' when unbound). */
  primaryChord(id: string): string {
    return this.bindingsOf(id)[0] ?? '';
  }

  // ------------------------------------------------------------------ overlays

  registerOverlay(o: Overlay): () => void {
    this.overlays.add(o);
    return () => this.overlays.delete(o);
  }

  anyOverlayOpen(): boolean {
    for (const o of this.overlays) if (o.isOpen()) return true;
    return false;
  }

  /** Close every open overlay. Returns true when one was open. */
  closeOverlays(): boolean {
    let any = false;
    for (const o of this.overlays) {
      if (o.isOpen()) {
        o.close();
        any = true;
      }
    }
    return any;
  }

  // ------------------------------------------------------------------ dispatch

  /** Enabled-agnostic candidate actions for an event: exact chord matches first, then loose-modifier matches. */
  lookup(ev: KeyLike): XrayAction[] {
    this.rebuildIndexOnly();
    const out: XrayAction[] = [];
    for (const k of eventCandidates(ev)) {
      for (const id of this.index.get(k) ?? []) {
        const a = this.byId.get(id);
        if (a && !out.includes(a)) out.push(a);
      }
    }
    if (out.length === 0) {
      for (const a of this.byId.values()) {
        if (!a.modifiers || a.modifiers.length === 0) continue;
        for (const ch of this.bindingsOf(a.id)) {
          const c = parseChord(ch);
          if (c && matchesLoose(c, ev, a.modifiers)) {
            if (!out.includes(a)) out.push(a);
            break;
          }
        }
      }
    }
    return out;
  }

  private noteMods(ev: KeyLike): void {
    this.mods = { ctrl: !!ev.ctrlKey, shift: !!ev.shiftKey, alt: !!ev.altKey, meta: !!ev.metaKey };
  }

  /**
   * Handle a keydown. Returns true when an action took the key (the event is then prevented).
   * Suppressed while a text field has focus (Escape blurs the field) and while an overlay is open.
   */
  handleKeyDown(ev: KeyLike, app: ViewerApp): boolean {
    if (ev.isComposing) return false;
    this.noteMods(ev);
    if (isTypingTarget(ev.target)) {
      if (ev.key === 'Escape') {
        (ev.target as { blur?: () => void }).blur?.();
      }
      return false;
    }
    if (isModifierKey(ev.key)) return false;
    if (this.anyOverlayOpen()) return false;
    const candidates = this.lookup(ev);
    for (const a of candidates) {
      if (a.enabled && !a.enabled(app)) continue;
      if (a.hold) {
        this.pressed.set(ev.code || ev.key, { key: ev.key, code: ev.code });
        ev.preventDefault?.();
        return true;
      }
      if (ev.repeat && !a.repeat) {
        ev.preventDefault?.();
        return true;
      }
      a.run(app, ev as KeyboardEvent);
      ev.preventDefault?.();
      return true;
    }
    return false;
  }

  handleKeyUp(ev: KeyLike): void {
    this.noteMods(ev);
    if (ev.key === 'Meta') {
      // Browsers do not send keyup for other keys while Meta is down: release everything.
      this.pressed.clear();
      return;
    }
    this.pressed.delete(ev.code || ev.key);
  }

  clearPressed(): void {
    this.pressed.clear();
    this.mods = { ...ZERO_MODS };
  }

  get heldCount(): number {
    return this.pressed.size;
  }

  /** Run the hold actions of the keys that are down. Call once per frame with dt in ms. */
  tick(app: ViewerApp, dt: number): void {
    if (this.pressed.size === 0) return;
    if (this.anyOverlayOpen()) {
      this.pressed.clear();
      return;
    }
    const step = Math.max(0, Math.min(MAX_HOLD_DT, dt));
    const m = this.mods;
    for (const p of this.pressed.values()) {
      const ev: KeyLike = { key: p.key, code: p.code, ctrlKey: m.ctrl, shiftKey: m.shift, altKey: m.alt, metaKey: m.meta };
      for (const a of this.lookup(ev)) {
        if (!a.hold) continue;
        if (a.enabled && !a.enabled(app)) continue;
        a.hold(app, step, { ...m });
        break;
      }
    }
  }
}

// ---------------------------------------------------------------------------- helpers

function normalizeList(chords: readonly string[]): string[] {
  const out: string[] = [];
  for (const c of chords) {
    const n = normalizeChord(c);
    if (n && !out.some((x) => x.toLowerCase() === n.toLowerCase())) out.push(n);
  }
  return out;
}

function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((x, i) => x.toLowerCase() === b[i]!.toLowerCase());
}

/** Parse a stored or imported document. Throws on JSON that is not an object. Chords that do not parse go to `bad`. */
export function parseBindings(text: string): { bindings: Bindings; bad: string[] } {
  const v = JSON.parse(text) as unknown;
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('keymap: expected a JSON object');
  const obj = v as Record<string, unknown>;
  const src = obj.bindings && typeof obj.bindings === 'object' && !Array.isArray(obj.bindings) ? (obj.bindings as Record<string, unknown>) : obj;
  const bindings: Bindings = {};
  const bad: string[] = [];
  for (const [id, val] of Object.entries(src)) {
    if (id === 'schema') continue;
    if (!Array.isArray(val)) {
      bad.push(id);
      continue;
    }
    const list: string[] = [];
    for (const c of val) {
      const n = typeof c === 'string' ? normalizeChord(c) : null;
      if (n) list.push(n);
      else bad.push(`${id}: ${String(c)}`);
    }
    bindings[id] = normalizeList(list);
  }
  return { bindings, bad };
}

// ---------------------------------------------------------------------------- shared instance

let shared: Keymap | null = null;

/** The viewer's keymap (created by the keymap plugin). Null before install. */
export function getKeymap(): Keymap | null {
  return shared;
}

export function setKeymap(k: Keymap | null): void {
  shared = k;
}
