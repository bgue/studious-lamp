// The attachment chip of a markup: "Attached to: 2 pipes · change" or "View-locked · change", with the Change menu
// (Elements, Surface, Region, Measurement, Penetration, View-locked). Built twice from the same code: in the markup panel
// (ui.ts) and on the canvas next to the selected markup (view.ts). DOM only; the changes go through MarkupController.setAttachment
// and so through the markup history.

import { el } from '../ui/dom';
import type { Markup } from './model';
import type { MarkupController } from './controller';

const STYLE_ID = 'markup-attach-styles';
const CSS = `
.mk-attach { display: inline-flex; align-items: center; gap: 4px; position: relative; font: 600 11px/1.3 system-ui, sans-serif; padding: 2px 8px; border-radius: 11px; border: 1px solid #3b6c9c; background: #14202e; color: #eaf2ff; max-width: 100%; }
.mk-attach[data-attached="0"] { border-color: #8d99a8; color: #cfd6df; }
.mk-attach[data-detached="1"] { border-color: #e0a030; color: #ffd37a; }
.mk-attach-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mk-attach-change { border: 0; background: transparent; color: #7fc0ff; font: inherit; cursor: pointer; padding: 0 2px; text-decoration: underline; }
.mk-attach-menu { position: absolute; left: 0; bottom: calc(100% + 4px); z-index: 20; display: flex; flex-direction: column; min-width: 190px; padding: 4px; border-radius: 8px; border: 1px solid #3b6c9c; background: #14202e; box-shadow: 0 4px 14px rgba(0,0,0,0.5); }
.mk-attach.below .mk-attach-menu { bottom: auto; top: calc(100% + 4px); }
.mk-attach-menu button { text-align: left; border: 0; background: transparent; color: #eaf2ff; font: 500 12px system-ui, sans-serif; padding: 6px 8px; border-radius: 5px; cursor: pointer; min-height: 30px; }
.mk-attach-menu button:hover { background: #1f4a7a; }
.mk-attach-menu button[aria-current=true] { color: #7fc0ff; font-weight: 700; }
`;

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

export const ATTACH_CHOICES: ReadonlyArray<{ id: 'elements' | 'surface' | 'region' | 'measurement' | 'penetration' | 'none'; label: string; title: string }> = [
  { id: 'elements', label: 'Elements (current selection)', title: 'Attach to the elements selected in the model' },
  { id: 'surface', label: 'Surface', title: 'Project the outline onto the model surfaces under it' },
  { id: 'region', label: 'Region', title: 'Fit a 3D box to the geometry inside the outline' },
  { id: 'measurement', label: 'Measurement (pick)', title: 'Click a dimension line of the measure tool' },
  { id: 'penetration', label: 'Penetration (pick)', title: 'Click a marker of the penetrations tool' },
  { id: 'none', label: 'View-locked', title: 'Keep the outline on the screen of the view it was drawn in' },
];

/** The chip of a markup. `where` marks the canvas chip (its menu opens below when there is no room above). */
export function buildAttachChip(c: MarkupController, m: Markup, where: 'panel' | 'canvas' = 'panel'): HTMLElement {
  ensureStyles();
  const d = c.describe(m);
  const root = el('span', 'mk-attach', { 'data-attach-chip': m.id, 'data-attached': d.attached ? '1' : '0', 'data-detached': d.detached ? '1' : '0', 'data-where': where });
  root.appendChild(el('span', 'mk-attach-text', { 'data-attach-text': '' }, d.text));
  if (!m.shape) return root;
  const btn = el('button', 'mk-attach-change', { type: 'button', 'data-act': 'attach-change', 'aria-haspopup': 'menu', 'aria-expanded': String(c.attachMenuOpen === m.id) }, 'change');
  btn.addEventListener('pointerdown', (e) => e.stopPropagation());
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    c.toggleAttachMenu(m.id);
  });
  root.append(el('span', undefined, undefined, '·'), btn);
  if (c.attachMenuOpen === m.id) {
    const menu = el('div', 'mk-attach-menu', { role: 'menu', 'data-attach-menu': m.id });
    const cur = m.attach?.kind ?? 'none';
    for (const ch of ATTACH_CHOICES) {
      const b = el('button', undefined, { type: 'button', role: 'menuitem', title: ch.title, 'data-attach-choice': ch.id, 'aria-current': String(cur === ch.id || (ch.id === 'elements' && cur === 'elements')) }, ch.label);
      b.addEventListener('pointerdown', (e) => e.stopPropagation());
      b.addEventListener('click', (e) => {
        e.stopPropagation();
        c.chooseAttachment(m.id, ch.id);
      });
      menu.appendChild(b);
    }
    root.appendChild(menu);
    if (where === 'canvas') root.classList.add('below');
  }
  return root;
}
