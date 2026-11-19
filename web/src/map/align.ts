// The manual alignment of the map: a small card with the latitude and longitude, the rotation, and a drag on the ground of the 3D view
// that moves the imagery under the model (Shift+drag turns it about the middle of the model). The location is stored per model in
// IndexedDB when the card is closed with Done. Docs: docs-features/map.md.

import { Vector3 } from 'three';
import type { PerspectiveCamera } from 'three';
import type { MapController } from './controller';
import { moveGeoref, normaliseDeg, parseLatLon } from './geo';
import type { Georef, ManualLocation } from './geo';

export const ALIGN_ID = 'xray-map-align';

export interface AlignHost {
  canvas: HTMLCanvasElement;
  camera: PerspectiveCamera;
  setControlsEnabled(on: boolean): void;
  /** Look straight down on the model (the aligner's "Top view"). */
  topView(): void;
  markDirty(): void;
}

/** Where a pointer ray meets the horizontal plane y = planeY, in the viewer frame; null when it never does. */
export function groundHit(camera: PerspectiveCamera, ndcX: number, ndcY: number, planeY: number): [number, number] | null {
  camera.updateMatrixWorld();
  const p = new Vector3(ndcX, ndcY, 0.5).unproject(camera);
  const o = camera.position;
  const d = p.sub(o);
  if (Math.abs(d.y) < 1e-9) return null;
  const t = (planeY - o.y) / d.y;
  if (t <= 0) return null;
  return [o.x + d.x * t, o.z + d.z * t];
}

const CSS = `
#${ALIGN_ID}{position:absolute;left:50%;transform:translateX(-50%);bottom:30px;z-index:30;width:min(420px,calc(100% - 16px));box-sizing:border-box;padding:8px 10px 9px;
  background:rgba(20,24,32,.96);color:var(--sb-fg,#dfe6ee);border:1px solid var(--sb-line,#262d3a);border-radius:6px;box-shadow:0 6px 22px rgba(0,0,0,.4);
  font:12px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif}
#${ALIGN_ID}[hidden]{display:none}
#${ALIGN_ID} *{box-sizing:border-box}
#${ALIGN_ID} h3{margin:0 0 4px;font-size:12px;font-weight:600}
#${ALIGN_ID} p{margin:0 0 6px;color:var(--sb-dim,#8d99a8)}
#${ALIGN_ID} .ma-row{display:flex;align-items:center;gap:6px;margin:4px 0}
#${ALIGN_ID} .ma-row label{flex:0 0 74px;color:var(--sb-dim,#8d99a8)}
#${ALIGN_ID} input[type=text],#${ALIGN_ID} input[type=number]{flex:1 1 0;min-width:0;background:#0f131a;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;padding:5px 6px;font:inherit}
#${ALIGN_ID} input[type=range]{flex:1 1 0;min-width:0}
#${ALIGN_ID} .ma-btns{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
#${ALIGN_ID} button{background:var(--sb-hover,#1c2230);color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;padding:6px 10px;font:inherit;cursor:pointer;min-height:30px}
#${ALIGN_ID} button.ma-primary{background:var(--sb-sel,#1f4a7a)}
#${ALIGN_ID} .ma-err{color:#ff9d8a;min-height:1em}
@media (max-width:700px){#${ALIGN_ID}{bottom:26px}#${ALIGN_ID} .ma-row label{flex-basis:62px}}
`;

function ensureStyle(): void {
  if (document.getElementById(`${ALIGN_ID}-css`)) return;
  const st = document.createElement('style');
  st.id = `${ALIGN_ID}-css`;
  st.textContent = CSS;
  document.head.appendChild(st);
}

function mk<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}

export class AlignPanel {
  readonly root: HTMLDivElement;
  private readonly latlon: HTMLInputElement;
  private readonly rot: HTMLInputElement;
  private readonly rotRange: HTMLInputElement;
  private readonly err: HTMLElement;
  private before: ManualLocation | null = null;
  private beforeHad = false;
  private opened = false;
  private drag: { id: number; start: [number, number]; georef: Georef; rotate: boolean; angle0: number; rot0: number } | null = null;
  private pending: ManualLocation | null = null;
  private raf = 0;

  constructor(private readonly ctl: MapController, private readonly host: AlignHost, parent: HTMLElement, private readonly onClose: () => void = () => {}) {
    ensureStyle();
    this.root = mk('div', { id: ALIGN_ID, role: 'dialog', 'aria-label': 'Align the map manually' });
    this.root.hidden = true;
    this.root.append(mk('h3', {}, 'Align the map manually'));
    this.root.append(mk('p', {}, 'Enter the place of the model, or drag on the ground to move the map under it. Shift and drag turns it.'));
    const r1 = mk('div', { class: 'ma-row' });
    this.latlon = mk('input', { type: 'text', id: 'xray-map-latlon', inputmode: 'text', placeholder: 'latitude, longitude', 'aria-label': 'Latitude and longitude', autocomplete: 'off', spellcheck: 'false' });
    r1.append(mk('label', { for: 'xray-map-latlon' }, 'Lat, lon'), this.latlon);
    const r2 = mk('div', { class: 'ma-row' });
    this.rot = mk('input', { type: 'number', id: 'xray-map-rot', step: '0.5', 'aria-label': 'Rotation in degrees' });
    r2.append(mk('label', { for: 'xray-map-rot' }, 'Rotation °'), this.rot);
    const r3 = mk('div', { class: 'ma-row' });
    this.rotRange = mk('input', { type: 'range', min: '-180', max: '180', step: '0.5', 'aria-label': 'Rotation slider' });
    r3.append(mk('label', {}, ''), this.rotRange);
    this.err = mk('div', { class: 'ma-err', role: 'alert' });
    const btns = mk('div', { class: 'ma-btns' });
    const top = mk('button', { type: 'button', id: 'xray-map-top' }, 'Top view');
    const reset = mk('button', { type: 'button', id: 'xray-map-reset' }, 'Use the model’s own place');
    const cancel = mk('button', { type: 'button', id: 'xray-map-cancel' }, 'Cancel');
    const done = mk('button', { type: 'button', id: 'xray-map-done', class: 'ma-primary' }, 'Done');
    btns.append(top, reset, cancel, done);
    this.root.append(r1, r2, r3, this.err, btns);
    parent.appendChild(this.root);

    this.latlon.addEventListener('change', () => this.applyText());
    this.latlon.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.applyText(); e.stopPropagation(); });
    this.rot.addEventListener('keydown', (e) => e.stopPropagation());
    this.rot.addEventListener('change', () => this.applyRotation(Number(this.rot.value)));
    this.rotRange.addEventListener('input', () => this.applyRotation(Number(this.rotRange.value)));
    top.addEventListener('click', () => this.host.topView());
    reset.addEventListener('click', () => { void this.useModelPlace(); });
    cancel.addEventListener('click', () => { void this.close(false); });
    done.addEventListener('click', () => { void this.close(true); });
    this.root.addEventListener('pointerdown', (e) => e.stopPropagation());

    host.canvas.addEventListener('pointerdown', this.onDown, true);
    window.addEventListener('pointermove', this.onMove, true);
    window.addEventListener('pointerup', this.onUp, true);
    window.addEventListener('pointercancel', this.onUp, true);
    ctl.onChange(() => { if (this.opened) this.fill(); });
  }

  get isOpen(): boolean { return this.opened; }

  open(): void {
    this.before = this.ctl.manual ? { ...this.ctl.manual } : null;
    this.beforeHad = !!this.ctl.manual;
    this.opened = true;
    this.root.hidden = false;
    this.err.textContent = this.ctl.georef ? '' : 'The place of the model is not known. Enter a latitude and longitude.';
    this.fill();
  }

  async close(keep: boolean): Promise<void> {
    if (!this.opened) return;
    this.opened = false;
    this.root.hidden = true;
    this.drag = null;
    this.host.setControlsEnabled(true);
    if (keep) {
      // from the model's own place or from an edit: the result is a manual place if anything was changed
      if (this.ctl.manual) await this.ctl.setManual(this.ctl.manual, true);
    } else {
      await this.ctl.setManual(this.beforeHad ? this.before : null, this.beforeHad || !!this.ctl.manual);
    }
    this.onClose();
  }

  private fill(): void {
    const g = this.ctl.georef;
    if (document.activeElement !== this.latlon) this.latlon.value = g ? `${g.lat.toFixed(6)}, ${g.lon.toFixed(6)}` : '';
    if (document.activeElement !== this.rot) this.rot.value = g ? String(Math.round(g.rotation * 100) / 100) : '0';
    this.rotRange.value = g ? String(Math.max(-180, Math.min(180, g.rotation))) : '0';
  }

  private current(): ManualLocation {
    return this.ctl.currentAsManual() ?? { lat: 0, lon: 0, rotation: 0 };
  }

  private async set(loc: ManualLocation): Promise<void> {
    await this.ctl.setManual(loc, false); // stored when Done is pressed
  }

  private applyText(): void {
    const ll = parseLatLon(this.latlon.value);
    if (!ll) {
      this.err.textContent = 'Enter latitude and longitude in degrees, like 52.5200, 13.4050.';
      return;
    }
    this.err.textContent = '';
    void this.set({ lat: ll[0], lon: ll[1], rotation: this.current().rotation });
  }

  private applyRotation(v: number): void {
    if (!Number.isFinite(v)) return;
    const base = this.ctl.georef ? this.current() : null;
    if (!base) {
      this.err.textContent = 'Enter a latitude and longitude first.';
      return;
    }
    void this.set({ ...base, rotation: normaliseDeg(v) });
  }

  private async useModelPlace(): Promise<void> {
    await this.ctl.setManual(null, true);
    this.beforeHad = false;
    this.before = null;
    this.err.textContent = this.ctl.georef ? '' : 'The model does not say where it is. Enter a latitude and longitude.';
    this.fill();
  }

  // ---------------------------------------------------------------- the drag

  private ndc(e: PointerEvent): [number, number] {
    const r = this.host.canvas.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1)];
  }

  private onDown = (e: PointerEvent): void => {
    if (!this.opened || e.button !== 0 || !this.ctl.georef) return;
    const [nx, ny] = this.ndc(e);
    const hit = groundHit(this.host.camera, nx, ny, this.ctl.groundY);
    if (!hit) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    this.host.setControlsEnabled(false);
    const g = this.ctl.georef;
    this.drag = { id: e.pointerId, start: hit, georef: g, rotate: e.shiftKey, angle0: Math.atan2(-hit[1], hit[0]), rot0: g.rotation };
  };

  private onMove = (e: PointerEvent): void => {
    const d = this.drag;
    if (!d || e.pointerId !== d.id) return;
    const [nx, ny] = this.ndc(e);
    const hit = groundHit(this.host.camera, nx, ny, this.ctl.groundY);
    if (!hit) return;
    e.stopImmediatePropagation();
    if (d.rotate) {
      const a = Math.atan2(-hit[1], hit[0]);
      const rotation = normaliseDeg(d.rot0 + ((a - d.angle0) * 180) / Math.PI);
      this.queue({ lat: d.georef.lat, lon: d.georef.lon, rotation });
    } else {
      const g = moveGeoref(d.georef, hit[0] - d.start[0], hit[1] - d.start[1]);
      this.queue({ lat: g.lat, lon: g.lon, rotation: d.georef.rotation });
    }
  };

  private onUp = (e: PointerEvent): void => {
    if (!this.drag || e.pointerId !== this.drag.id) return;
    this.drag = null;
    this.host.setControlsEnabled(true);
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (this.pending) { const p = this.pending; this.pending = null; void this.set(p); }
  };

  private queue(p: ManualLocation): void {
    this.pending = p;
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      if (this.pending) { const q = this.pending; this.pending = null; void this.set(q); }
    });
  }

  /** For tests: a drag from one ground point to another, in the viewer frame (as the pointer would make it). */
  dragGround(from: [number, number], to: [number, number], rotate = false): void {
    const g = this.ctl.georef;
    if (!g || !this.opened) return;
    if (rotate) {
      const a0 = Math.atan2(-from[1], from[0]), a1 = Math.atan2(-to[1], to[0]);
      void this.set({ lat: g.lat, lon: g.lon, rotation: normaliseDeg(g.rotation + ((a1 - a0) * 180) / Math.PI) });
    } else {
      const m = moveGeoref(g, to[0] - from[0], to[1] - from[1]);
      void this.set({ lat: m.lat, lon: m.lon, rotation: g.rotation });
    }
  }
}
