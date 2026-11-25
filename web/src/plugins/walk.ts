// Walk plugin: the on-screen parts of Walk mode and the navigation style setting. Docs: docs-features/keyboard.md, pointer-modes.md.
//
//   Walk mode (action `nav.walk`, Shift+W, the walk button on the gizmo): the keys move the eye on the horizontal plane (the maths
//   and the camera glue are in input/walk.ts and input/navigation.ts); here: the "Walk · Esc to exit" chip, the cursor, a left drag
//   (or one finger) that looks around from the eye, the wheel that walks, Esc that leaves first, and the exit when a film plays.
//   Walk mode is a per-viewer state: nothing here touches the params, the share link, saved views, presets or packed pages.
//   Navigation style: `navigation style` in the Keyboard folder, BIM (default) or Game; kept in localStorage `xray.keynav`.

import type { AppPlugin, ViewerApp } from '../app';
import { getKeymap } from '../input/keymap';
import {
  isWalking,
  navSettings,
  onNavStyleChange,
  onWalkChange,
  playerPlaying,
  saveNavSettings,
  setNavStyle,
  setWalking,
  walkDropIn,
  walkTurn,
  walkWheel,
} from '../input/navigation';
import { EYE_HEIGHT_MAX, EYE_HEIGHT_MIN, lookRadiansPerPixel } from '../input/walk';
import type { NavStyle } from '../input/walk';

const CHIP_ID = 'xray-walk-chip';

// The cursor is a small eye; `all-scroll` is the fallback. It beats the Hand and Arrow cursors of plugins/pointerMode.ts.
const EYE = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" fill="#141820"/><circle cx="12" cy="12" r="3" fill="#3b9cff"/></svg>',
);
const CSS = `
canvas[data-walk="1"],canvas[data-walk="1"][data-pointer-mode]{cursor:url("data:image/svg+xml,${EYE}") 12 12,all-scroll}
canvas[data-walk="1"].xp-grabbing{cursor:url("data:image/svg+xml,${EYE}") 12 12,all-scroll}
#${CHIP_ID}{position:absolute;left:50%;top:42px;transform:translateX(-50%);z-index:13;box-sizing:border-box;max-width:calc(100% - 32px);
  display:none;align-items:center;gap:6px;padding:5px 12px;border-radius:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  background:var(--sb-bg,#141820);color:var(--sb-fg,#dfe6ee);border:1px solid var(--sb-accent,#3b9cff);
  font:600 12px/1.2 system-ui,-apple-system,'Segoe UI',sans-serif;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.25)}
#${CHIP_ID}.on{display:inline-flex}
#${CHIP_ID}:focus-visible{outline:2px solid var(--sb-accent,#3b9cff);outline-offset:2px}
`;

function storage(): Storage | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
  }
}

/** Wheel delta in notches (100 pixels or 3 lines), limited so one fast event cannot throw the eye across the model. */
export function wheelNotches(e: { deltaY: number; deltaMode: number }): number {
  const n = e.deltaMode === 1 ? e.deltaY / 3 : e.deltaMode === 2 ? e.deltaY : e.deltaY / 100;
  return Math.max(-3, Math.min(3, n));
}

export const walkPlugin: AppPlugin = {
  name: 'walk',

  install(app: ViewerApp) {
    const canvas = app.canvas;
    const stage = canvas.parentElement ?? document.body;
    const st = document.createElement('style');
    st.id = 'xray-walk-css';
    st.textContent = CSS;
    document.head.appendChild(st);

    const chip = document.createElement('button');
    chip.id = CHIP_ID;
    chip.type = 'button';
    chip.textContent = 'Walk · Esc to exit';
    chip.title = 'Leave Walk mode';
    chip.setAttribute('role', 'status');
    chip.setAttribute('aria-label', 'Walk mode is on. Press Escape or click to leave');
    chip.addEventListener('click', () => setWalking(app, false));
    stage.appendChild(chip);

    const refresh = (): void => {
      const on = isWalking();
      chip.classList.toggle('on', on);
      if (on) canvas.dataset['walk'] = '1';
      else delete canvas.dataset['walk'];
      canvas.classList.remove('xp-grabbing');
    };
    onWalkChange(refresh);
    refresh();

    // ---- look around from the eye: a left drag or one finger (no pointer lock: it works in an iframe and on a phone)
    let drag: { id: number; x: number; y: number } | null = null;
    canvas.addEventListener('pointerdown', (e) => {
      if (!isWalking() || !e.isPrimary || (e.pointerType !== 'touch' && e.button !== 0)) return;
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY };
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        /* synthetic event */
      }
    });
    canvas.addEventListener('pointermove', (e) => {
      const d = drag;
      if (!d || e.pointerId !== d.id || !isWalking()) return;
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      d.x = e.clientX;
      d.y = e.clientY;
      if (dx === 0 && dy === 0) return;
      // The world follows the pointer (as in Hand mode): drag right and the view turns left, drag down and it looks up.
      const k = lookRadiansPerPixel(app.renderer.camera.fov, canvas.clientHeight);
      walkTurn(app, dx * k, dy * k);
    });
    const end = (e: PointerEvent): void => {
      if (drag && e.pointerId === drag.id) drag = null;
    };
    canvas.addEventListener('pointerup', end);
    canvas.addEventListener('pointercancel', end);

    // ---- the wheel walks forward and back
    canvas.addEventListener(
      'wheel',
      (e) => {
        if (!isWalking()) return;
        e.preventDefault();
        walkWheel(app, wheelNotches(e));
      },
      { passive: false },
    );

    // ---- Drop in here: a double click in Walk mode stands on that spot; Alt + double click outside Walk mode enters Walk mode and
    // drops in there. Capture phase, so the fly-to double click of plugins/pointerMode.ts does not also run.
    let lastDown = { x: 0, y: 0 };
    canvas.addEventListener('pointerdown', (e) => {
      lastDown = { x: e.clientX, y: e.clientY };
    }, true);
    canvas.addEventListener(
      'dblclick',
      (e) => {
        if (e.button !== 0 || e.shiftKey || e.ctrlKey || e.metaKey || canvas.style.cursor) return;
        if (!isWalking() && !e.altKey) return;
        if (Math.hypot(e.clientX - lastDown.x, e.clientY - lastDown.y) > 5) return;
        if (walkDropIn(app, e.clientX, e.clientY)) {
          e.stopImmediatePropagation();
          e.preventDefault();
        }
      },
      true,
    );

    // ---- Esc leaves Walk mode first (before the Escape that clears the selection). Capture phase, like the other Esc owners.
    window.addEventListener(
      'keydown',
      (e) => {
        if (e.key !== 'Escape' || !isWalking() || e.ctrlKey || e.metaKey || e.altKey) return;
        const t = e.target as HTMLElement | null;
        if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return; // Esc leaves the field first
        if (getKeymap()?.anyOverlayOpen()) return; // the cheat sheet or the palette closes first
        setWalking(app, false);
        e.preventDefault();
        e.stopPropagation();
      },
      true,
    );

    // ---- the navigation style setting, in the Keyboard folder (built by plugins/keymap.ts, which installs before this plugin)
    const folder = app.panel?.folders.find((f) => (f as unknown as { _title?: string })._title === 'Keyboard');
    if (folder) {
      const model = { style: navSettings.style as NavStyle };
      const ctrl = folder.add(model, 'style', { BIM: 'bim', Game: 'game' }).name('navigation style');
      ctrl.onChange((v: NavStyle) => {
        setNavStyle(v);
        saveNavSettings(storage());
      });
      onNavStyleChange(() => {
        model.style = navSettings.style;
        ctrl.updateDisplay();
      });
      const save = (): void => saveNavSettings(storage());
      const eye = folder.add(navSettings, 'eyeHeight', EYE_HEIGHT_MIN, EYE_HEIGHT_MAX, 0.05).name('eye height (m)').onChange(save);
      const col = folder.add(navSettings, 'walkCollision').name('Walk collision').onChange(save);
      const after = folder.controllers.find((c) => c.property === 'smoothMoves');
      try {
        if (after) {
          after.domElement.after(ctrl.domElement);
          ctrl.domElement.after(eye.domElement);
          eye.domElement.after(col.domElement);
        }
      } catch {
        /* the control stays at the end of the folder */
      }
    }
  },

  onModel(app) {
    if (isWalking()) setWalking(app, false);
  },

  onFrame(app, now) {
    // A fly-through, a script or a 4D film owns the camera: Walk mode ends. Looked at a few times a second.
    if (!isWalking() || now - lastCheck < 200) return;
    lastCheck = now;
    if (playerPlaying()) setWalking(app, false);
  },
};

let lastCheck = 0;
