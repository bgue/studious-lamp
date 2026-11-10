// Help tooltips: key derivation for lil-gui controls and folders, help lookup, and the popover UI.
// The key functions are pure (no DOM at import time) so tests can drive them with a fake lil-gui structure.

import { HELP, type HelpEntry } from './helpText';

// ---------------------------------------------------------------- keys

/** The part of lil-gui that the key functions read. A fake object with these fields works in tests. */
export interface GuiLike {
  _title?: string;
  $title?: { textContent: string | null };
  parent?: GuiLike | null;
}

export interface ControllerLike {
  _name?: string;
  property?: string;
  parent: GuiLike;
}

/** Pattern key for the folder of one object class. The folder sits in "Classes" inside "Class styles". */
export const CLASS_FOLDER_KEY = 'Class styles/*';

export function folderTitle(g: GuiLike): string {
  const t = typeof g._title === 'string' ? g._title : (g.$title?.textContent ?? '');
  return t.trim();
}

/** True for the per-class folders that the class styles plugin builds. */
export function isClassFolder(g: GuiLike): boolean {
  const classes = g.parent;
  const styles = classes?.parent;
  return !!classes && !!styles && folderTitle(classes) === 'Classes' && folderTitle(styles) === 'Class styles';
}

/** "IfcSlab (12)" and "Concrete (4) [alias]" give "IfcSlab" and "Concrete". */
export function classNameOf(title: string): string {
  return title.replace(/\s*\[alias\]\s*$/, '').replace(/\s*\(\d+\)\s*$/, '').trim();
}

/** The "Classes" sub folder of Model cleanup shares its title with the one in Class styles: give it its own key. */
export const CLEANUP_CLASSES_KEY = 'Model cleanup/Classes';

/** Key of a folder: its title, the pattern key for a per-class folder, or a parent qualified key for a title that two folders share. */
export function folderKey(g: GuiLike): string {
  if (isClassFolder(g)) return CLASS_FOLDER_KEY;
  const t = folderTitle(g);
  if (t === 'Classes' && g.parent && folderTitle(g.parent) === 'Model cleanup') return CLEANUP_CLASSES_KEY;
  return t;
}

/** Key of a control: "<folder key>/<display name>". */
export function controllerKey(c: ControllerLike): string {
  const name = (typeof c._name === 'string' && c._name !== '' ? c._name : (c.property ?? '')).trim();
  return `${folderKey(c.parent)}/${name}`;
}

/** Second key to try when the display name has no text: the property name of the bound object. */
export function controllerAltKey(c: ControllerLike): string | null {
  const alt = (c.property ?? '').trim();
  const name = typeof c._name === 'string' ? c._name.trim() : '';
  return alt && alt !== name ? `${folderKey(c.parent)}/${alt}` : null;
}

/** The class name of a per-class folder or of a control inside one, else null. */
export function classOf(g: GuiLike): string | null {
  return isClassFolder(g) ? classNameOf(folderTitle(g)) : null;
}

// ---------------------------------------------------------------- lookup

/** Case, space and punctuation insensitive form of a key. */
export function normalizeKey(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9*/]+/g, '');
}

let exactIndex: Map<string, HelpEntry> | null = null;
let looseIndex: Map<string, HelpEntry> | null = null;

function buildIndex(): void {
  exactIndex = new Map();
  looseIndex = new Map();
  for (const [k, v] of Object.entries(HELP)) {
    exactIndex.set(k, v);
    const n = normalizeKey(k);
    if (!looseIndex.has(n)) looseIndex.set(n, v);
  }
}

function lookupOne(key: string): HelpEntry | undefined {
  if (!exactIndex || !looseIndex) buildIndex();
  return exactIndex!.get(key) ?? looseIndex!.get(normalizeKey(key));
}

/** A unit at the end of a label: "max size (mm)" gives "max size" and "mm". */
const UNIT_SUFFIX = /\s*\(([^()]*)\)$/;

/**
 * Find the help entry of a key: exact match first, then the loose match. A control whose label shows a unit the user
 * picked ("max size (mm)", "max size (cm)") uses the entry of its metre key ("max size (m)"). A label whose unit
 * follows another setting ("threshold (m³)") falls back to the key without the unit ("threshold").
 */
export function lookupHelp(key: string): HelpEntry | undefined {
  const hit = lookupOne(key);
  if (hit) return hit;
  const m = UNIT_SUFFIX.exec(key);
  if (!m) return undefined;
  const base = key.slice(0, m.index);
  if (m[1] === 'mm' || m[1] === 'cm') {
    const metre = lookupOne(`${base} (m)`);
    if (metre) return metre;
  }
  return base.endsWith('/') || base === '' ? undefined : lookupOne(base);
}

/** Replace the {class} placeholder. */
export function fillEntry(e: HelpEntry, cls?: string | null): HelpEntry {
  if (!cls) return e;
  const f = (s: string): string => s.split('{class}').join(cls);
  return { intent: f(e.intent), impact: f(e.impact), use: f(e.use), ref: f(e.ref) };
}

/** One labelled line of the popover. */
export interface PopoverLine {
  label: 'Intent' | 'Impact' | 'Use' | 'Ref';
  text: string;
  cls: string;
}

/** The labelled lines under the title, in display order: Intent, Impact, Use, Ref. Pure, so tests can check it. */
export function popoverLines(e: HelpEntry): PopoverLine[] {
  return [
    { label: 'Intent', text: e.intent, cls: 'hp-intent' },
    { label: 'Impact', text: e.impact, cls: 'hp-impact' },
    { label: 'Use', text: e.use, cls: 'hp-use' },
    { label: 'Ref', text: e.ref, cls: 'hp-ref' },
  ];
}

/** Fill a popover element: the title, then the labelled lines. Works with any Document, also a fake one. */
export function renderPopover(doc: Document, el: HTMLElement, title: string, e: HelpEntry): void {
  el.textContent = '';
  const t = doc.createElement('div');
  t.className = 'hp-title';
  t.textContent = title;
  el.appendChild(t);
  for (const { label, text, cls } of popoverLines(e)) {
    const line = doc.createElement('div');
    line.className = `hp-line ${cls}`;
    const l = doc.createElement('span');
    l.className = 'hp-label';
    l.textContent = label;
    const x = doc.createElement('span');
    x.className = 'hp-text';
    x.textContent = text;
    line.append(l, x);
    el.appendChild(line);
  }
}

// ---------------------------------------------------------------- targets

/** What a hovered element stands for. */
export interface HelpTarget {
  key: string;
  title: string;
  cls?: string | null;
}

/** Selectors for elements that the viewer builds outside lil-gui: the sidebar and the panel dock. */
export const ELEMENT_RULES: ReadonlyArray<{ selector: string; key: string | ((el: Element) => string | null); title: string | ((el: Element) => string) }> = [
  { selector: '.sb-toggle, .sb-rail-label', key: 'Sidebar/Collapse toggle', title: 'Collapse toggle' },
  { selector: '.sb-tab', key: (e) => ((e.textContent ?? '').trim() === 'Sets' ? 'Sidebar/Sets tab' : 'Sidebar/Model tab'), title: (e) => `${(e.textContent ?? '').trim()} tab` },
  { selector: '.dk-toggle, .dk-rail-label', key: 'Panel dock/Collapse toggle', title: 'Collapse toggle' },
  { selector: '.sb-filter', key: 'Sidebar/Filter box', title: 'Filter box' },
  { selector: '.eye', key: 'Sidebar/Eye icon', title: 'Eye icon' },
  { selector: '.tr .dot', key: 'Sidebar/Bucket dot', title: 'Bucket dot' },
  { selector: '.tr .caret:not(.none)', key: 'Sidebar/Expand arrow', title: 'Expand arrow' },
  { selector: '.sets-top input', key: 'Sidebar/Set name box', title: 'Set name box' },
  {
    selector: '.sets-top .btn',
    key: (e) => {
      const t = (e.textContent ?? '').trim();
      if (t.startsWith('Save')) return 'Sidebar/Save selection';
      if (t === 'Export') return 'Sidebar/Export sets';
      if (t === 'Import') return 'Sidebar/Import sets';
      return null;
    },
    title: (e) => (e.textContent ?? '').trim(),
  },
  {
    selector: '.set .btn[data-act]',
    key: (e) => {
      const a = (e as HTMLElement).dataset['act'];
      return a === 'apply' || a === 'add' || a === 'update' || a === 'rename' || a === 'delete' ? `Sidebar/${a[0]!.toUpperCase()}${a.slice(1)} set` : null;
    },
    title: (e) => `${(e.textContent ?? '').trim()} set`,
  },
  { selector: '.props-head .btn', key: 'Sidebar/Copy GlobalId', title: 'Copy GlobalId' },
];

// ---------------------------------------------------------------- tool strip, drawers and dialogs

/** One rule for an element that no lil-gui control owns. It returns the candidate keys, best first, or null. */
export interface DomRule {
  selector: string;
  keys: (el: Element, drawer: string) => string[] | null;
  title: (el: Element, drawer: string) => string;
}

const txt = (e: Element | null | undefined): string => (e?.textContent ?? '').replace(/\s+/g, ' ').trim();
/** A button or heading label without the count in it: "Export CSV (12)" and "Comments (3)" lose the count. */
const bare = (s: string): string => s.replace(/\s*\(\d+\)\s*$/, '').replace(/\s+\d+$/, '').trim();
const lblOf = (e: Element): string => txt(e.querySelector('.xt-lbl'));
const prevSection = (e: Element): string => {
  for (let n: Element | null = e; n; n = n.parentElement) {
    for (let p = n.previousElementSibling; p; p = p.previousElementSibling) {
      if (p.classList.contains('xt-sec')) return txt(p);
    }
    if (n.classList.contains('xt-body')) break;
  }
  return '';
};

/** The title of the open tool drawer, or "" when the element lies outside a drawer. */
export function drawerTitleOf(e: Element): string {
  const d = e.closest('#xray-toolbar-drawer');
  return d ? txt(d.querySelector('.xt-title')) : '';
}

/** Key prefix of a drawer: "<tool label> drawer". */
export const drawerKeyOf = (title: string): string => `${title} drawer`;

const D = (d: string, name: string): string => `${drawerKeyOf(d)}/${name}`;

/** Folders of the parameter panel that hold the same controls as a drawer. A drawer widget falls back to these texts. */
export const DRAWER_FOLDERS: Readonly<Record<string, readonly string[]>> = {
  'View modes': ['Behind only', 'Peelback'],
  Cleanup: ['Floating', 'Tiny', 'Distant strays', 'Duplicates', 'Degenerate', 'Model cleanup', 'Model cleanup/Classes'],
  Imaging: ['Imaging', 'MRI slice'],
  Scan: ['Point cloud'],
  'Large model': ['Open model'],
};

/** A shortcut hint such as "(C)" or "(Alt+C)" at the end of a label. A unit such as "(m)" stays. */
const noHint = (s: string): string => s.replace(/\s*\((?:\w+\+)*[A-Z]\)$/, '');

/** Candidate keys of a drawer widget: its own text first, then the same control in the parameter panel. */
const same = (d: string, name: string): string[] => {
  const names = noHint(name) === name ? [name] : [name, noHint(name)];
  const folders = DRAWER_FOLDERS[d] ?? [d];
  return [...names.map((n) => D(d, n)), ...names.flatMap((n) => folders.map((f) => `${f}/${n}`))];
};

/** Rules for the action panel strip and the drawers. The tests of the help text check that each key has an entry. */
export const TOOL_RULES: ReadonlyArray<DomRule> = [
  { selector: '.xt-btn-tool[data-tool]', keys: (e) => [`Tool strip/${e.getAttribute('aria-label') ?? ''}`], title: (e) => e.getAttribute('aria-label') ?? 'Tool' },
  { selector: '.xt-strip', keys: () => ['Tool strip'], title: () => 'Tool strip' },
  { selector: '.xt-close', keys: () => ['Tool drawer/Close button'], title: () => 'Close button' },
  { selector: '.xt-grip', keys: () => ['Tool drawer/Resize edge'], title: () => 'Resize edge' },
  { selector: '.xt-title, .xt-head', keys: (_e, d) => [drawerKeyOf(d)], title: (_e, d) => drawerKeyOf(d) },
  { selector: '.xt-sec', keys: (e, d) => [D(d, `${txt(e)} (heading)`), ...(d === 'Presets' ? [D(d, 'Preset group (heading)')] : [])], title: (e) => txt(e) },
  { selector: '.xt-table th', keys: (e, d) => [D(d, `Column: ${txt(e)}`)], title: (e) => `${txt(e)} column` },
  { selector: '.xt-table tbody tr[data-pen]', keys: (_e, d) => [D(d, 'Table row')], title: () => 'Table row' },
  { selector: '.xt-table', keys: (e, d) => [e.querySelector('th') ? D(d, 'Schedule table') : D(d, `Table: ${prevSection(e)}`)], title: (e) => (e.querySelector('th') ? 'Schedule table' : `${prevSection(e)} table`) },
  { selector: '.xt-slider, .xt-select', keys: (e, d) => same(d, lblOf(e)), title: (e) => lblOf(e) },
  { selector: '.xp-ticks .xt-check', keys: (_e, d) => [D(d, 'Section tick')], title: () => 'Section tick' },
  { selector: '.xt-check', keys: (e, d) => same(d, txt(e)), title: (e) => txt(e) },
  { selector: '.xt-chip', keys: (e, d) => {
    const sec = prevSection(e);
    return [sec === 'Status' ? D(d, `Chip: ${bare(txt(e))}`) : D(d, `Chip: ${sec || 'filter'}`)];
  }, title: (e) => bare(txt(e)) },
  { selector: '.xt-item .x', keys: (_e, d) => [D(d, 'Delete measurement')], title: () => 'Delete measurement' },
  { selector: '.xt-item', keys: (_e, d) => [D(d, 'Measurement row')], title: () => 'Measurement row' },
  { selector: '.xp-key', keys: (_e, d) => [D(d, 'Key badge')], title: () => 'Key badge' },
  { selector: '.xp-badge', keys: (_e, d) => [D(d, 'Active badge')], title: () => 'Active badge' },
  { selector: '.xp-skip', keys: (_e, d) => [D(d, 'Skipped list')], title: () => 'Skipped list' },
  { selector: '.xp-form input[type=text]', keys: (e, d) => [D(d, /desc/i.test(e.getAttribute('aria-label') ?? '') ? 'Description box' : 'Name box')], title: (e) => e.getAttribute('aria-label') ?? 'Text box' },
  { selector: '.xp-card', keys: (_e, d) => [D(d, 'Preset card')], title: () => 'Preset card' },
  { selector: '.bcf-modal .bcf-btn', keys: (e) => [`BCF topic dialog/${bare(txt(e))}`], title: (e) => bare(txt(e)) },
  { selector: '.bcf-modal .bcf-in', keys: () => ['BCF topic dialog/Field'], title: () => 'Dialog field' },
  { selector: '.bcf-btn', keys: (e, d) => same(d, bare(txt(e))), title: (e) => bare(txt(e)) },
  { selector: 'textarea[data-bcf-comment]', keys: (_e, d) => [D(d, 'Comment box')], title: () => 'Comment box' },
  { selector: '.bcf-detail select', keys: (_e, d) => [D(d, 'Topic status list')], title: () => 'Topic status list' },
  { selector: 'input.bcf-in', keys: (_e, d) => [D(d, 'Search box')], title: () => 'Search box' },
  { selector: 'select.bcf-in', keys: (_e, d) => [D(d, 'Status filter')], title: () => 'Status filter' },
  { selector: '.bcf-detail label', keys: (_e, d) => [D(d, 'Attach view tick')], title: () => 'Attach view tick' },
  { selector: '.bcf-h', keys: (e, d) => [D(d, `${bare(txt(e))} (heading)`)], title: (e) => bare(txt(e)) },
  { selector: '.bcf-snap', keys: (_e, d) => [D(d, 'Snapshot')], title: () => 'Snapshot' },
  { selector: '.bcf-comment', keys: (_e, d) => [D(d, 'Comment')], title: () => 'Comment' },
  { selector: '.bcf-item', keys: (_e, d) => [D(d, 'Topic row')], title: () => 'Topic row' },
  { selector: '.mk-tool', keys: (_e, d) => [D(d, 'Tool button')], title: (e) => e.getAttribute('aria-label') ?? 'Tool' },
  { selector: '.mk-sw', keys: (_e, d) => [D(d, 'Colour swatch')], title: (e) => e.getAttribute('aria-label') ?? 'Colour' },
  { selector: '.mk-w', keys: (_e, d) => [D(d, 'Line weight')], title: () => 'Line weight' },
  { selector: '.mk-set', keys: (_e, d) => [D(d, 'Set card')], title: () => 'Set card' },
  { selector: '.mk-item', keys: (_e, d) => [D(d, 'Markup row')], title: () => 'Markup row' },
  { selector: '.mk-status', keys: (_e, d) => [D(d, 'Status line')], title: () => 'Status line' },
  { selector: '.xt-btn', keys: (e, d) => same(d, bare(txt(e))), title: (e) => bare(txt(e)) },
  { selector: '.pc-result', keys: (_e, d) => [D(d, 'Deviation result')], title: () => 'Deviation result' },
  { selector: '.xt-status, .bcf-status', keys: (_e, d) => [D(d, 'Status line')], title: () => 'Status line' },
];

/** Rules for the keyboard dialogs: command palette, shortcut sheet and shortcut editor. */
export const DIALOG_RULES: ReadonlyArray<DomRule> = [
  { selector: '.kx-palette .kx-input', keys: () => ['Command palette/Search box'], title: () => 'Search box' },
  { selector: '.kx-palette .kx-item', keys: () => ['Command palette/Result row'], title: () => 'Result row' },
  { selector: '.kx-sheet .kx-input', keys: () => ['Shortcut sheet/Search box'], title: () => 'Search box' },
  { selector: '.kx-sheet .kx-btn', keys: (e) => [`Shortcut sheet/${txt(e)}`], title: (e) => txt(e) },
  { selector: '.kx-sheet .kx-row', keys: () => ['Shortcut sheet/Shortcut row'], title: () => 'Shortcut row' },
  { selector: '.kx-edit .kx-input', keys: () => ['Shortcut editor/Filter box'], title: () => 'Filter box' },
  { selector: '.kx-edit tr .kx-btn', keys: () => ['Shortcut editor/Reset row'], title: () => 'Reset row' },
  { selector: '.kx-edit .kx-btn', keys: (e) => [`Shortcut editor/${txt(e)}`], title: (e) => txt(e) },
  { selector: '.kx-edit .kx-add', keys: () => ['Shortcut editor/Add key cell'], title: () => 'Add key cell' },
  { selector: '.kx-edit .kx-cell', keys: () => ['Shortcut editor/Key cell'], title: () => 'Key cell' },
];

/** Match the DOM rules against one element. The first rule that matches and gives a key with a text wins; else the first key. */
export function domTarget(e: Element): HelpTarget | null {
  const d = drawerTitleOf(e);
  const rules = d ? TOOL_RULES : [TOOL_RULES[0]!, TOOL_RULES[1]!, ...DIALOG_RULES];
  for (const r of rules) {
    if (!e.matches(r.selector)) continue;
    const keys = r.keys(e, d);
    if (!keys || keys.length === 0 || keys[0]!.endsWith('/')) continue;
    const found = keys.find((k) => lookupHelp(k)) ?? keys[0]!;
    return { key: found, title: r.title(e, d) };
  }
  return null;
}

/** Elements of a drawer or dialog that carry help: the check on the drawer content uses this list. */
export const DOM_CANDIDATES =
  '.xt-btn-tool, .xt-title, .xt-close, .xt-grip, .xt-sec, .xt-table, .xt-table th, .xt-slider, .xt-select, .xt-check, .xt-chip, .xt-btn, .xt-status, .xt-item, .xp-card, .xp-key, .xp-badge, .xp-skip, .xp-form input[type=text], .pc-result, ' +
  '.bcf-btn, .bcf-in, .bcf-h, .bcf-item, .bcf-snap, .bcf-comment, .bcf-status, .bcf-detail label, .kx-input, .kx-btn, .kx-cell, .kx-row, .kx-item';

// ---------------------------------------------------------------- popover

export const HELP_DELAY_MS = 350;
const GAP = 10;
const MARGIN = 8;
const STORAGE_KEY = 'xray.help';

/** False when the user turned help off (localStorage['xray.help'] === 'off'). */
export function helpEnabled(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
}

const CSS = `
#xray-help { position: fixed; left: 0; top: 0; z-index: 100000; max-width: 360px; box-sizing: border-box; padding: 8px 10px 9px;
  background: #141820; color: #dfe6ee; border: 1px solid #3a4558; border-radius: 5px; box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  font: 12px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif; pointer-events: none; display: none; }
#xray-help.show { display: block; }
#xray-help .hp-title { font-weight: 700; font-size: 13px; color: #fff; margin-bottom: 4px; }
#xray-help .hp-line { display: grid; grid-template-columns: 44px 1fr; column-gap: 6px; margin-top: 3px; }
#xray-help .hp-label { color: #3b9cff; font-weight: 600; }
#xray-help .hp-line.hp-impact .hp-label { color: #e0b252; }
#xray-help .hp-line.hp-ref .hp-text { color: #8d99a8; }
body.xh-on .xt-btn-tool[data-tool]::after { display: none !important; }
`;

export interface PopoverOptions {
  /** Map a hovered or focused node to its help target. */
  resolve: (node: Node | null) => (HelpTarget & { anchor: HTMLElement }) | null;
  delayMs?: number;
  /** Extra gate besides localStorage. */
  enabled?: () => boolean;
}

/** One positioned popover that follows hover and keyboard focus. */
export class HelpPopover {
  readonly el: HTMLDivElement;
  private readonly delay: number;
  private anchor: HTMLElement | null = null;
  private shown = false;
  private suppressed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private watch: ReturnType<typeof setInterval> | null = null;
  private keyboard = false;
  private stripped: Array<[HTMLElement, string]> = [];
  private forced = true;
  private readonly cleanup: Array<() => void> = [];

  constructor(private readonly opts: PopoverOptions) {
    this.delay = opts.delayMs ?? HELP_DELAY_MS;
    if (!document.getElementById('xray-help-style')) {
      const st = document.createElement('style');
      st.id = 'xray-help-style';
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    this.el = document.createElement('div');
    this.el.id = 'xray-help';
    this.el.setAttribute('role', 'tooltip');
    document.body.appendChild(this.el);
    this.bind();
  }

  /** The anchor element of the visible popover, or null. */
  get visibleAnchor(): HTMLElement | null {
    return this.shown ? this.anchor : null;
  }

  setEnabled(on: boolean): void {
    this.forced = on;
    if (!on) this.hide();
  }

  private on(): boolean {
    return this.forced && helpEnabled() && (this.opts.enabled?.() ?? true);
  }

  private listen<K extends keyof DocumentEventMap>(type: K, fn: (e: DocumentEventMap[K]) => void, capture = true): void {
    document.addEventListener(type, fn as EventListener, { capture, passive: true });
    this.cleanup.push(() => document.removeEventListener(type, fn as EventListener, { capture }));
  }

  private bind(): void {
    this.listen('pointerover', (e) => {
      if (e.pointerType === 'touch') return;
      const t = this.opts.resolve(e.target as Node | null);
      if (!t) {
        this.cancel();
        return;
      }
      if (t.anchor === this.anchor) return; // moved within the same anchor
      this.cancel();
      if (!this.on()) return;
      this.anchor = t.anchor;
      this.timer = setTimeout(() => {
        this.timer = null;
        if (this.anchor === t.anchor) this.show(t);
      }, this.delay);
    });
    this.listen('pointerout', (e) => {
      if (!this.anchor) return;
      const to = e.relatedTarget as Node | null;
      if (to && this.anchor.contains(to)) return;
      const next = this.opts.resolve(to);
      if (next && next.anchor === this.anchor) return;
      this.cancel();
    });
    // Pointer down and wheel hide the popover; it stays hidden until the pointer leaves the anchor.
    this.listen('pointerdown', () => {
      this.keyboard = false;
      this.suppress();
    });
    this.listen('wheel', () => this.suppress());
    this.listen('keydown', (e) => {
      this.keyboard = true;
      if (e.key === 'Escape') this.hide();
    });
    this.listen('focusin', (e) => {
      if (!this.keyboard || !this.on()) return;
      const t = this.opts.resolve(e.target as Node | null);
      if (!t || !(e.target as HTMLElement).matches('input, select, button, textarea')) return;
      this.cancel();
      this.anchor = t.anchor;
      this.show(t);
    });
    this.listen('focusout', (e) => {
      if (this.shown && this.anchor && this.anchor.contains(e.target as Node) && this.keyboard) this.cancel();
    });
    window.addEventListener('blur', this.onBlur);
    this.cleanup.push(() => window.removeEventListener('blur', this.onBlur));
  }

  private onBlur = (): void => this.cancel();

  private suppress(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.hide();
    this.suppressed = true; // keep this.anchor so that pointerover on the same anchor does not re-arm
  }

  /** Stop everything and forget the anchor. */
  cancel(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.hide();
    this.anchor = null;
    this.suppressed = false;
  }

  hide(): void {
    if (this.watch) {
      clearInterval(this.watch);
      this.watch = null;
    }
    if (this.shown) {
      this.el.classList.remove('show');
      this.anchor?.removeAttribute('aria-describedby');
    }
    this.shown = false;
    for (const [e, t] of this.stripped) e.setAttribute('title', t);
    this.stripped = [];
  }

  show(t: HelpTarget & { anchor: HTMLElement }): void {
    if (this.suppressed || !t.anchor.isConnected) return;
    const entry = lookupHelp(t.key);
    if (!entry) return;
    const e = fillEntry(entry, t.cls);
    this.render(t.title, e);
    this.el.classList.add('show');
    this.shown = true;
    t.anchor.setAttribute('aria-describedby', this.el.id);
    this.place(t.anchor);
    // Remove native tooltips of the anchor and its ancestors while ours is up.
    for (let n: HTMLElement | null = t.anchor; n && n !== document.body; n = n.parentElement) {
      const title = n.getAttribute('title');
      if (title) {
        this.stripped.push([n, title]);
        n.removeAttribute('title');
      }
    }
    // Tree rows are redrawn by the sidebar; hide when the anchor leaves the document.
    this.watch = setInterval(() => {
      if (!this.anchor || !this.anchor.isConnected) this.cancel();
    }, 200);
  }

  private render(title: string, e: HelpEntry): void {
    renderPopover(document, this.el, title, e);
  }

  /** Put the popover on the side of the anchor that has room. */
  private place(anchor: HTMLElement): void {
    const r = anchor.getBoundingClientRect();
    const vw = document.documentElement.clientWidth || window.innerWidth;
    const vh = document.documentElement.clientHeight || window.innerHeight;
    const w = this.el.offsetWidth;
    const h = this.el.offsetHeight;
    const roomRight = vw - r.right - GAP - MARGIN;
    const roomLeft = r.left - GAP - MARGIN;
    let left: number;
    let top = r.top;
    if (roomRight >= w || roomLeft >= w) {
      // Prefer the side with more room; the panel sits on the right edge, the sidebar on the left.
      left = roomRight >= roomLeft && roomRight >= w ? r.right + GAP : roomLeft >= w ? r.left - GAP - w : r.right + GAP;
    } else {
      // Narrow screen: put the popover below or above the anchor, inside the viewport.
      left = Math.min(Math.max(MARGIN, r.left), Math.max(MARGIN, vw - w - MARGIN));
      top = vh - r.bottom - GAP >= h ? r.bottom + GAP : r.top - GAP - h;
    }
    top = Math.min(Math.max(MARGIN, top), Math.max(MARGIN, vh - h - MARGIN));
    this.el.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
  }

  destroy(): void {
    this.cancel();
    for (const c of this.cleanup) c();
    this.el.remove();
  }
}
