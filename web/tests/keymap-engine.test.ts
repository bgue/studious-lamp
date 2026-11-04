import { describe, expect, it, vi } from 'vitest';
import type { ViewerApp } from '../src/app';
import type { XrayAction } from '../src/input/actions';
import {
  Keymap,
  KEYMAP_STORAGE_KEY,
  chordKey,
  eventCandidates,
  eventToChord,
  formatChord,
  isTypingTarget,
  matchesChord,
  normalizeChord,
  parseChord,
} from '../src/input/keymap';
import type { KeyLike } from '../src/input/keymap';
import { MemoryStorage } from '../src/selectionSets';

const app = {} as ViewerApp;
const ev = (key: string, o: Partial<KeyLike> = {}): KeyLike => ({ key, code: o.code ?? '', ...o });

function action(id: string, keys: string[], extra: Partial<XrayAction> = {}): XrayAction {
  return { id, label: id, group: 'Other', keys, run: () => undefined, ...extra };
}

describe('chord parsing and normalisation', () => {
  it('parses modifiers and keys', () => {
    expect(parseChord('Ctrl+Shift+k')).toEqual({ ctrl: true, alt: false, shift: true, meta: false, key: 'k' });
    expect(parseChord('code:Numpad7')).toMatchObject({ key: 'code:Numpad7', ctrl: false });
    expect(parseChord('Ctrl+code:Numpad1')).toMatchObject({ ctrl: true, key: 'code:Numpad1' });
  });
  it('normalises case, order, aliases', () => {
    expect(normalizeChord('shift+ctrl+K')).toBe('Ctrl+Shift+k');
    expect(normalizeChord('alt+left')).toBe('Alt+ArrowLeft');
    expect(normalizeChord('esc')).toBe('Escape');
    expect(normalizeChord('cmd+K')).toBe('Meta+k');
    expect(normalizeChord('pgup')).toBe('PageUp');
    expect(normalizeChord('F1')).toBe('F1');
    expect(chordKey('Ctrl+K')).toBe('ctrl+k');
  });
  it('keeps symbols, including + and the combination Ctrl++', () => {
    expect(normalizeChord('+')).toBe('+');
    expect(normalizeChord('Ctrl++')).toBe('Ctrl++');
    expect(normalizeChord('?')).toBe('?');
    expect(normalizeChord('Alt+=')).toBe('Alt+=');
    expect(normalizeChord('[')).toBe('[');
  });
  it('rejects empty and modifier-only chords', () => {
    expect(parseChord('')).toBeNull();
    expect(parseChord('Ctrl+')).toBeNull();
    expect(parseChord('Shift')).toBeNull();
    expect(parseChord('code:')).toBeNull();
  });
  it('formats for display', () => {
    expect(formatChord('code:Numpad7')).toBe('Num 7');
    expect(formatChord('Ctrl+code:Numpad1')).toBe('Ctrl+Num 1');
    expect(formatChord('Alt+ArrowLeft')).toBe('Alt+Left');
    expect(formatChord('Ctrl+k')).toBe('Ctrl+K');
    expect(formatChord('code:Digit1')).toBe('1');
  });
});

describe('matching events', () => {
  it('matches letters case-insensitively with exact modifiers', () => {
    expect(matchesChord('x', ev('x'))).toBe(true);
    expect(matchesChord('x', ev('X', { shiftKey: true }))).toBe(false); // Shift+x is a different chord
    expect(matchesChord('Shift+h', ev('H', { shiftKey: true }))).toBe(true);
    expect(matchesChord('h', ev('H', { shiftKey: true }))).toBe(false);
    expect(matchesChord('h', ev('h', { ctrlKey: true }))).toBe(false);
    expect(matchesChord('Ctrl+a', ev('a', { ctrlKey: true }))).toBe(true);
    expect(matchesChord('Ctrl+a', ev('a', { ctrlKey: true, altKey: true }))).toBe(false);
    expect(matchesChord('Meta+k', ev('k', { metaKey: true }))).toBe(true);
  });
  it('ignores Shift for chords that are one symbol', () => {
    expect(matchesChord('?', ev('?', { shiftKey: true, code: 'Slash' }))).toBe(true);
    expect(matchesChord('+', ev('+', { shiftKey: true }))).toBe(true);
    expect(matchesChord('=', ev('=', { code: 'Equal' }))).toBe(true);
    expect(matchesChord('[', ev('['))).toBe(true);
    expect(matchesChord('?', ev('?', { ctrlKey: true }))).toBe(false);
  });
  it('matches code: chords by physical key and exact modifiers', () => {
    expect(matchesChord('code:Numpad7', ev('7', { code: 'Numpad7' }))).toBe(true);
    expect(matchesChord('code:Numpad7', ev('Home', { code: 'Numpad7' }))).toBe(true); // NumLock off
    expect(matchesChord('code:Numpad7', ev('7', { code: 'Digit7' }))).toBe(false);
    expect(matchesChord('code:Numpad1', ev('1', { code: 'Numpad1', ctrlKey: true }))).toBe(false);
    expect(matchesChord('Ctrl+code:Numpad1', ev('1', { code: 'Numpad1', ctrlKey: true }))).toBe(true);
    expect(matchesChord('Alt+code:Digit1', ev('¡', { code: 'Digit1', altKey: true }))).toBe(true);
    expect(matchesChord('Alt+Shift+code:Digit1', ev('!', { code: 'Digit1', altKey: true, shiftKey: true }))).toBe(true);
    expect(matchesChord('code:Digit1', ev('1', { code: 'Digit1', altKey: true }))).toBe(false);
  });
  it('Alt+letter matches by physical key when the layout produces another character', () => {
    expect(matchesChord('Alt+s', ev('ß', { code: 'KeyS', altKey: true }))).toBe(true);
    expect(matchesChord('s', ev('ß', { code: 'KeyS' }))).toBe(false);
  });
  it('matches named keys', () => {
    expect(matchesChord('Alt+ArrowLeft', ev('ArrowLeft', { altKey: true }))).toBe(true);
    expect(matchesChord('Escape', ev('Escape'))).toBe(true);
    expect(matchesChord('Space', ev(' '))).toBe(true);
    expect(eventCandidates(ev('a', { code: 'KeyA' }))).toContain('a');
  });
  it('records chords from events', () => {
    expect(eventToChord(ev('Control', { ctrlKey: true }))).toBeNull();
    expect(eventToChord(ev('K', { code: 'KeyK', ctrlKey: true, shiftKey: true }))).toBe('Ctrl+Shift+k');
    expect(eventToChord(ev('7', { code: 'Numpad7' }))).toBe('code:Numpad7');
    expect(eventToChord(ev('1', { code: 'Digit1' }))).toBe('code:Digit1');
    expect(eventToChord(ev('?', { code: 'Slash', shiftKey: true }))).toBe('?');
    expect(eventToChord(ev('ß', { code: 'KeyS', altKey: true }))).toBe('Alt+s');
    expect(eventToChord(ev('ArrowLeft', { code: 'ArrowLeft', altKey: true }))).toBe('Alt+ArrowLeft');
  });
});

describe('typing targets', () => {
  it('detects text fields', () => {
    expect(isTypingTarget({ tagName: 'INPUT', type: 'text' })).toBe(true);
    expect(isTypingTarget({ tagName: 'INPUT', type: 'search' })).toBe(true);
    expect(isTypingTarget({ tagName: 'input' })).toBe(true);
    expect(isTypingTarget({ tagName: 'TEXTAREA' })).toBe(true);
    expect(isTypingTarget({ tagName: 'SELECT' })).toBe(true);
    expect(isTypingTarget({ tagName: 'DIV', isContentEditable: true })).toBe(true);
    expect(isTypingTarget({ tagName: 'INPUT', type: 'checkbox' })).toBe(false);
    expect(isTypingTarget({ tagName: 'BUTTON' })).toBe(false);
    expect(isTypingTarget({ tagName: 'CANVAS' })).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
  it('does not dispatch while typing, and Escape blurs the field', () => {
    const run = vi.fn();
    const km = new Keymap({ actions: () => [action('a.b', ['b'], { run }), action('a.x', ['Escape'], { run })] });
    const blur = vi.fn();
    const target = { tagName: 'INPUT', type: 'text', blur };
    expect(km.handleKeyDown(ev('b', { target }), app)).toBe(false);
    expect(km.handleKeyDown(ev('Escape', { target }), app)).toBe(false);
    expect(run).not.toHaveBeenCalled();
    expect(blur).toHaveBeenCalledTimes(1);
    expect(km.handleKeyDown(ev('b', { target: { tagName: 'CANVAS' } }), app)).toBe(true);
    expect(run).toHaveBeenCalledTimes(1);
  });
});

describe('dispatch', () => {
  it('prevents default only for handled keys and falls through disabled actions', () => {
    const ran: string[] = [];
    const km = new Keymap({
      actions: () => [
        action('one', ['q'], { enabled: () => false, run: () => ran.push('one') }),
        action('two', ['q'], { run: () => ran.push('two') }),
        action('off', ['z'], { enabled: () => false }),
      ],
      warn: () => undefined,
    });
    const pd = vi.fn();
    expect(km.handleKeyDown(ev('q', { preventDefault: pd }), app)).toBe(true);
    expect(ran).toEqual(['two']);
    expect(pd).toHaveBeenCalledTimes(1);
    const pd2 = vi.fn();
    expect(km.handleKeyDown(ev('z', { preventDefault: pd2 }), app)).toBe(false);
    expect(km.handleKeyDown(ev('y', { preventDefault: pd2 }), app)).toBe(false);
    expect(pd2).not.toHaveBeenCalled();
  });
  it('swallows auto-repeat unless the action asks for it', () => {
    const a = vi.fn();
    const b = vi.fn();
    const km = new Keymap({ actions: () => [action('a', ['h'], { run: a }), action('b', ['='], { run: b, repeat: true })] });
    km.handleKeyDown(ev('h'), app);
    km.handleKeyDown(ev('h', { repeat: true }), app);
    km.handleKeyDown(ev('=', { repeat: true }), app);
    km.handleKeyDown(ev('=', { repeat: true }), app);
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(2);
  });
  it('is suppressed while an overlay is open', () => {
    const run = vi.fn();
    const km = new Keymap({ actions: () => [action('a', ['h'], { run })] });
    let open = true;
    km.registerOverlay({ isOpen: () => open, close: () => (open = false) });
    expect(km.handleKeyDown(ev('h'), app)).toBe(false);
    expect(km.closeOverlays()).toBe(true);
    expect(km.handleKeyDown(ev('h'), app)).toBe(true);
    expect(run).toHaveBeenCalledTimes(1);
  });
});

describe('conflicts', () => {
  it('reports two actions on one chord, once on the console', () => {
    const warn = vi.fn();
    const km = new Keymap({ actions: () => [action('a', ['h', 'Ctrl+q']), action('b', ['H']), action('c', ['Ctrl+q'])], warn });
    const c = km.conflicts();
    expect(c.map((x) => x.chord)).toEqual(['Ctrl+q', 'h']);
    expect(c[1]!.ids).toEqual(['a', 'b']);
    km.lookup(ev('h'));
    km.lookup(ev('h'));
    expect(warn).toHaveBeenCalledTimes(2);
    expect(km.conflictKeys().has('h')).toBe(true);
  });
  it('a rebinding that resolves the conflict clears it', () => {
    const km = new Keymap({ actions: () => [action('a', ['h']), action('b', ['h'])], warn: () => undefined });
    expect(km.conflicts()).toHaveLength(1);
    km.setBinding('b', ['j']);
    expect(km.conflicts()).toHaveLength(0);
  });
  it('an exact chord wins over a loose modifier match', () => {
    const km = new Keymap({
      actions: () => [action('fly', ['a'], { hold: () => undefined, modifiers: ['ctrl'] }), action('all', ['Ctrl+a'])],
    });
    expect(km.lookup(ev('a', { ctrlKey: true })).map((a) => a.id)).toEqual(['all']);
    expect(km.lookup(ev('a')).map((a) => a.id)).toEqual(['fly']);
    expect(km.lookup(ev('a', { ctrlKey: true, shiftKey: true })).map((a) => a.id)).toEqual([]);
  });
});

describe('override persistence', () => {
  const defs = (): XrayAction[] => [action('a', ['h']), action('b', ['Ctrl+k', 'Meta+k']), action('c', [])];
  it('round-trips through storage and applies at dispatch', () => {
    const storage = new MemoryStorage();
    const km = new Keymap({ actions: defs, storage });
    km.setBinding('a', ['j', 'Shift+J']);
    km.setBinding('b', []);
    expect(JSON.parse(storage.getItem(KEYMAP_STORAGE_KEY)!)).toEqual({ a: ['j', 'Shift+j'], b: [] });
    const km2 = new Keymap({ actions: defs, storage });
    km2.load();
    expect(km2.bindingsOf('a')).toEqual(['j', 'Shift+j']);
    expect(km2.bindingsOf('b')).toEqual([]);
    expect(km2.bindingsOf('c')).toEqual([]);
    expect(km2.lookup(ev('h'))).toEqual([]);
    expect(km2.lookup(ev('j')).map((x) => x.id)).toEqual(['a']);
    expect(km2.lookup(ev('k', { ctrlKey: true }))).toEqual([]);
  });
  it('drops an override equal to the defaults and resets', () => {
    const storage = new MemoryStorage();
    const km = new Keymap({ actions: defs, storage });
    km.setBinding('a', ['j']);
    km.setBinding('a', ['H']);
    expect(km.overrides).toEqual({});
    km.setBinding('a', ['j']);
    km.resetAll();
    expect(km.bindingsOf('a')).toEqual(['h']);
    expect(storage.getItem(KEYMAP_STORAGE_KEY)).toBe('{}');
  });
  it('survives corrupt storage', () => {
    const storage = new MemoryStorage();
    storage.setItem(KEYMAP_STORAGE_KEY, '{nope');
    const km = new Keymap({ actions: defs, storage });
    km.load();
    expect(km.overrides).toEqual({});
  });
  it('exports and imports JSON, reporting bad chords', () => {
    const km = new Keymap({ actions: defs, storage: new MemoryStorage() });
    km.setBinding('a', ['j']);
    const text = km.exportJson();
    const km2 = new Keymap({ actions: defs, storage: new MemoryStorage() });
    expect(km2.importJson(text)).toEqual({ ok: true, applied: 1, bad: [] });
    expect(km2.bindingsOf('a')).toEqual(['j']);
    const r = km2.importJson(JSON.stringify({ a: ['k', 'Ctrl+'], b: 'x' }));
    expect(r.ok).toBe(true);
    expect(r.bad).toHaveLength(2);
    expect(km2.bindingsOf('a')).toEqual(['k']);
    expect(km2.importJson('[1]').ok).toBe(false);
    expect(km2.importJson('not json').ok).toBe(false);
  });
});

describe('hold actions (fake dt)', () => {
  function setup() {
    const log: Array<{ id: string; dt: number; ctrl: boolean }> = [];
    const hold = (id: string) => (_a: ViewerApp, dt: number, m?: { ctrl: boolean }) => log.push({ id, dt, ctrl: !!m?.ctrl });
    const km = new Keymap({
      actions: () => [
        action('left', ['ArrowLeft'], { hold: hold('left'), modifiers: ['ctrl'] }),
        action('panLeft', ['Shift+ArrowLeft'], { hold: hold('pan') }),
        action('fwd', ['w'], { hold: hold('fwd'), modifiers: ['ctrl'] }),
      ],
    });
    return { km, log };
  }
  const sum = (log: Array<{ id: string; dt: number }>, id: string): number => log.filter((l) => l.id === id).reduce((s, l) => s + l.dt, 0);

  it('runs every tick while held, with dt, and stops on keyup', () => {
    const { km, log } = setup();
    expect(km.handleKeyDown(ev('ArrowLeft', { code: 'ArrowLeft' }), app)).toBe(true);
    for (let i = 0; i < 30; i++) km.tick(app, 16.6); // 500 ms
    expect(sum(log, 'left')).toBeCloseTo(498, 0);
    km.handleKeyUp(ev('ArrowLeft', { code: 'ArrowLeft' }));
    km.tick(app, 16);
    expect(sum(log, 'left')).toBeCloseTo(498, 0);
  });
  it('ignores auto-repeat keydowns for hold actions (no double counting)', () => {
    const { km, log } = setup();
    km.handleKeyDown(ev('w', { code: 'KeyW' }), app);
    km.handleKeyDown(ev('w', { code: 'KeyW', repeat: true }), app);
    km.handleKeyDown(ev('w', { code: 'KeyW', repeat: true }), app);
    km.tick(app, 16);
    expect(log.filter((l) => l.id === 'fwd')).toHaveLength(1);
    expect(km.heldCount).toBe(1);
  });
  it('clamps a stalled frame and combines keys', () => {
    const { km, log } = setup();
    km.handleKeyDown(ev('ArrowLeft', { code: 'ArrowLeft' }), app);
    km.handleKeyDown(ev('w', { code: 'KeyW' }), app);
    km.tick(app, 5000);
    expect(log.map((l) => [l.id, l.dt])).toEqual([['left', 100], ['fwd', 100]]);
  });
  it('switches between orbit and pan as Shift changes, and passes Ctrl for slow moves', () => {
    const { km, log } = setup();
    km.handleKeyDown(ev('ArrowLeft', { code: 'ArrowLeft' }), app);
    km.tick(app, 10);
    km.handleKeyDown(ev('Shift', { code: 'ShiftLeft', shiftKey: true }), app);
    km.tick(app, 10);
    km.handleKeyUp(ev('Shift', { code: 'ShiftLeft' }));
    km.handleKeyDown(ev('Control', { code: 'ControlLeft', ctrlKey: true }), app);
    km.tick(app, 10);
    expect(log.map((l) => `${l.id}${l.ctrl ? '+ctrl' : ''}`)).toEqual(['left', 'pan', 'left+ctrl']);
  });
  it('stops everything on clearPressed (window blur) and while an overlay is open', () => {
    const { km, log } = setup();
    km.handleKeyDown(ev('w', { code: 'KeyW' }), app);
    km.clearPressed();
    km.tick(app, 16);
    expect(log).toHaveLength(0);
    km.handleKeyDown(ev('w', { code: 'KeyW' }), app);
    let open = true;
    km.registerOverlay({ isOpen: () => open, close: () => (open = false) });
    km.tick(app, 16);
    open = false;
    km.tick(app, 16);
    expect(log).toHaveLength(0);
  });
  it('a disabled hold action does not start', () => {
    const km = new Keymap({ actions: () => [action('w', ['w'], { hold: () => undefined, enabled: () => false })] });
    expect(km.handleKeyDown(ev('w', { code: 'KeyW' }), app)).toBe(false);
    expect(km.heldCount).toBe(0);
  });
});
