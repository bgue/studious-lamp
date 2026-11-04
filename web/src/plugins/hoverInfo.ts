// Hover info: after the pointer rests on an element for a moment, a small card near the pointer shows its name, class,
// storey, material and a few properties (the optional `props` of the sidecar, see SPEC.md "Element properties").
//
// The pick itself is app.hoverId (updated every 80 ms by app.ts); this plugin only reads it in afterFrame. It adds the
// lil-gui folder "Hover info", the action `hover.toggle` (key i), the params section `hoverInfo` and feeds the
// collapsible "Properties" list in the sidebar footer (ui/propsView.ts).
// Alt freezes the card in place so its text can be selected or copied.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { copyText } from '../ui/dom';
import { DEFAULT_PROPERTY_FILTER, HoverCard, cardRows, parsePatterns, subtitleOf } from '../ui/hoverCard';
import type { CardContent } from '../ui/hoverCard';
import { registerParamSection } from '../ui/params';
import { refreshPropsViews, setPropRowsProvider } from '../ui/propsView';

export interface HoverInfoSettings {
  showOnHover: boolean;
  delayMs: number;
  maxRows: number;
  showXrayState: boolean;
  highlight: boolean;
  propertyFilter: string;
  allPropsInSidebar: boolean;
}

export const hoverInfoSettings: HoverInfoSettings = {
  showOnHover: true,
  delayMs: 350,
  maxRows: 6,
  showXrayState: true,
  highlight: true,
  propertyFilter: DEFAULT_PROPERTY_FILTER,
  allPropsInSidebar: false,
};

type HighlightRenderer = { setHoverHighlight?: (id: number | null, color?: number | string) => void };

/** Sidebar rows for an element: every property, or the ones the filter keeps. */
function sidebarRows(app: ViewerApp, globalId: string): { rows: Array<[string, string | number | boolean]>; total: number } | null {
  const m = app.controller.model;
  const id = m.byGlobalId.get(globalId);
  const props = id === undefined ? undefined : m.elements[id]?.props;
  if (!props) return null;
  const total = Object.keys(props).length;
  if (total === 0) return null;
  const rows = hoverInfoSettings.allPropsInSidebar ? Object.entries(props) : cardRows(props, parsePatterns(hoverInfoSettings.propertyFilter), Infinity);
  return { rows, total };
}

function contentFor(app: ViewerApp, id: number): CardContent | null {
  const m = app.controller.model;
  const e = m.elements[id];
  const info = app.controller.describe(id);
  if (!e || !info) return null;
  const storey = e.storey === null ? undefined : m.storeys.find((s) => s.id === e.storey)?.name;
  return {
    title: e.name && e.name.trim() !== '' ? e.name : e.ifcClass,
    subtitle: subtitleOf(e.ifcClass, storey, e.material),
    rows: cardRows(e.props, parsePatterns(hoverInfoSettings.propertyFilter), Math.max(0, Math.floor(hoverInfoSettings.maxRows))),
    footer: footerFor(app, id),
  };
}

function footerFor(app: ViewerApp, id: number): string {
  if (!hoverInfoSettings.showXrayState || !app.settings.xray) return '';
  const info = app.controller.describe(id);
  if (!info) return '';
  return `x-ray: ${info.bucket === 'none' ? 'not classified' : info.bucket} · alpha ${info.alpha.toFixed(2)}`;
}

export const hoverInfoPlugin: AppPlugin = (() => {
  let card: HoverCard | null = null;
  let appRef: ViewerApp | null = null;
  let folder: { controllersRecursive(): Array<{ updateDisplay(): unknown }> } | null = null;

  // pointer state
  let px = 0;
  let py = 0;
  let inside = false;
  let buttonDown = false;
  let suppressed = false; // key press, wheel or click hid the card: stay hidden until the pointer moves again
  let restSince = 0; // performance.now() of the last significant pointer movement
  let candidate: number | null = null;
  let shownId: number | null = null;
  let highlighted: number | null = null;
  let lastFooterAt = 0;

  const view = (): { w: number; h: number } => ({ w: window.innerWidth, h: window.innerHeight });

  function setHighlight(app: ViewerApp, id: number | null): void {
    if (highlighted === id) return;
    highlighted = id;
    const r = app.renderer as unknown as HighlightRenderer;
    if (typeof r.setHoverHighlight === 'function') r.setHoverHighlight(id);
  }

  function hide(): void {
    if (!card) return;
    if (card.visible) card.hide();
    shownId = null;
    if (appRef) setHighlight(appRef, null);
  }

  function reset(): void {
    suppressed = true;
    hide();
    candidate = null;
    restSince = performance.now();
  }

  function unfreeze(): void {
    if (card?.frozen) {
      card.setFrozen(false);
      // After Alt is released the card behaves normally again: it stays while the pointer rests on the same element.
    }
  }

  function install(app: ViewerApp): void {
    appRef = app;
    card = new HoverCard();
    card.onCopy = copyText;
    const c = card;
    const canvas = app.canvas;

    canvas.addEventListener('pointermove', (e) => {
      const moved = Math.hypot(e.clientX - px, e.clientY - py);
      px = e.clientX;
      py = e.clientY;
      inside = true;
      buttonDown = e.buttons !== 0;
      if (buttonDown) {
        reset();
        return;
      }
      if (c.frozen) return;
      if (moved >= 2) {
        restSince = performance.now();
        suppressed = false;
      }
      if (c.visible) c.moveTo({ x: px, y: py }, view());
    });
    canvas.addEventListener('pointerleave', () => {
      inside = false;
      if (!c.frozen) reset(); // a frozen card sits over the canvas: entering it fires pointerleave on the canvas
    });
    canvas.addEventListener('pointerdown', () => {
      buttonDown = true;
      reset();
    });
    window.addEventListener('pointerup', () => {
      buttonDown = false;
    });
    canvas.addEventListener('wheel', () => reset(), { passive: true });
    window.addEventListener('pointermove', (e) => {
      // Frozen: unfreeze when the pointer leaves the neighbourhood of the card.
      if (!c.frozen) return;
      const r = c.rect;
      const pad = 40;
      if (e.clientX < r.left - pad || e.clientX > r.right + pad || e.clientY < r.top - pad || e.clientY > r.bottom + pad) {
        unfreeze();
        reset();
      }
    });
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Alt') {
        if (c.visible && !c.frozen) {
          c.setFrozen(true);
          e.preventDefault(); // keep a menu bar from taking focus on Alt
        }
        return;
      }
      if (e.key === 'Shift' || e.key === 'Control' || e.key === 'Meta' || e.key === 'CapsLock') return;
      if (c.frozen) {
        if (e.key === 'Escape') {
          unfreeze();
          reset();
        }
        return; // Ctrl+C and friends work on the frozen text
      }
      reset();
    });
    window.addEventListener('keyup', (e) => {
      if (e.key === 'Alt' && c.frozen) {
        unfreeze();
        e.preventDefault();
      }
    });
    window.addEventListener('blur', () => {
      unfreeze();
      reset();
    });

    buildGui(app);
    setPropRowsProvider((gid) => sidebarRows(app, gid));

    registerAction({
      id: 'hover.toggle',
      label: 'Toggle hover info',
      group: 'Modes',
      keys: ['i'],
      description: 'Show or hide the element card that appears when the pointer rests on an element.',
      run: () => {
        hoverInfoSettings.showOnHover = !hoverInfoSettings.showOnHover;
        if (!hoverInfoSettings.showOnHover) reset();
        refreshGui();
        c.toast(`Hover info ${hoverInfoSettings.showOnHover ? 'on' : 'off'}`);
      },
    });

    registerParamSection('hoverInfo', {
      share: false,
      collect: () => ({ ...hoverInfoSettings }),
      apply: (value, bad, path) => {
        if (!value || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        const v = value as Record<string, unknown>;
        const s = hoverInfoSettings;
        const bool = (k: 'showOnHover' | 'showXrayState' | 'highlight' | 'allPropsInSidebar'): void => {
          if (v[k] === undefined) return;
          if (typeof v[k] === 'boolean') s[k] = v[k] as boolean;
          else bad.push(`${path}.${k}`);
        };
        const num = (k: 'delayMs' | 'maxRows', lo: number, hi: number): void => {
          if (v[k] === undefined) return;
          if (typeof v[k] === 'number' && Number.isFinite(v[k])) s[k] = Math.min(hi, Math.max(lo, Math.round(v[k] as number)));
          else bad.push(`${path}.${k}`);
        };
        bool('showOnHover'); bool('showXrayState'); bool('highlight'); bool('allPropsInSidebar');
        num('delayMs', 0, 5000); num('maxRows', 0, 24);
        if (v.propertyFilter !== undefined) {
          if (typeof v.propertyFilter === 'string') s.propertyFilter = v.propertyFilter;
          else bad.push(`${path}.propertyFilter`);
        }
        refreshGui();
        refreshPropsViews();
      },
    });
  }

  function buildGui(app: ViewerApp): void {
    const gui = app.panel;
    if (!gui) return;
    const f = gui.addFolder('Hover info');
    f.close();
    const s = hoverInfoSettings;
    f.add(s, 'showOnHover').name('show on hover').onChange(() => { if (!s.showOnHover) reset(); });
    f.add(s, 'delayMs', 0, 2000, 10).name('delay (ms)');
    f.add(s, 'maxRows', 0, 24, 1).name('max rows');
    f.add(s, 'showXrayState').name('show x-ray state');
    f.add(s, 'highlight').name('highlight').onChange(() => { if (!s.highlight && appRef) setHighlight(appRef, null); });
    f.add(s, 'propertyFilter').name('property filter').onChange(() => refreshPropsViews());
    f.add(s, 'allPropsInSidebar').name('all properties in sidebar').onChange(() => refreshPropsViews());
    folder = f as unknown as typeof folder;
  }

  function refreshGui(): void {
    for (const c of folder?.controllersRecursive() ?? []) c.updateDisplay();
  }

  return {
    name: 'hoverInfo',
    install,
    onModel(app) {
      reset();
      refreshPropsViews();
      void app;
    },
    afterFrame(app, now) {
      const c = card;
      if (!c) return;
      if (c.frozen) return;
      const s = hoverInfoSettings;
      const id = app.hoverId;
      if (!s.showOnHover || suppressed || !app.loaded || !inside || buttonDown || id === null) {
        if (c.visible) hide();
        candidate = id === null ? null : candidate;
        return;
      }
      if (id !== candidate) {
        // A different element: hide and wait for the delay again.
        candidate = id;
        restSince = Math.max(restSince, now);
        if (c.visible) hide();
        return;
      }
      if (!c.visible) {
        if (now - restSince < s.delayMs) return;
        const content = contentFor(app, id);
        if (!content) return;
        c.setContent(content);
        c.show();
        c.moveTo({ x: px, y: py }, view());
        shownId = id;
        lastFooterAt = now;
        if (s.highlight) setHighlight(app, id);
      } else if (shownId === id && now - lastFooterAt > 250) {
        // the alpha in the footer follows the smoothing
        lastFooterAt = now;
        c.setFooter(footerFor(app, id));
      }
    },
  };
})();
