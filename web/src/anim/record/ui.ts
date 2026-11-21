// The two pieces of DOM of the video export: the options dialog and the busy overlay with the progress bar and Cancel. Plain DOM,
// no framework; the styles are injected once. Every control has a help key (src/ui/helpText.ts, "Record dialog/...").

import type { Quality, VideoFormat } from './encoder';
import { QUALITY_CHOICES } from './encoder';
import type { ExportOptions } from './options';
import { summarize } from './options';
import { FPS_CHOICES, formatDuration } from './schedule';
import type { Progress } from './frames';
import type { OutputSize, SizeChoice } from './size';
import { SIZE_CHOICES, resolveOutputSize } from './size';

const CSS = `
.rc-back { position: fixed; inset: 0; z-index: 90000; display: flex; align-items: center; justify-content: center; background: rgba(6, 9, 14, 0.62);
  font: 13px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif; color: #dfe6ee; }
.rc-back.rc-clear { background: transparent; align-items: flex-end; justify-content: flex-end; pointer-events: auto; }
.rc-card { box-sizing: border-box; width: min(440px, calc(100vw - 24px)); max-height: calc(100vh - 24px); overflow: auto; padding: 14px 16px 14px; background: #141820;
  border: 1px solid #3a4558; border-radius: 8px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.55); }
.rc-clear .rc-card { width: min(320px, calc(100vw - 24px)); margin: 0 12px 12px 0; }
.rc-card h2 { margin: 0 0 8px; font-size: 15px; font-weight: 700; color: #fff; }
.rc-grid { display: grid; grid-template-columns: 112px 1fr; gap: 8px 10px; align-items: center; margin: 6px 0 8px; }
.rc-grid label { color: #8d99a8; }
.rc-grid select, .rc-grid input[type=text] { box-sizing: border-box; width: 100%; min-width: 0; padding: 5px 6px; background: #1c2230; color: #dfe6ee; border: 1px solid #2a3447; border-radius: 4px; font: inherit; }
.rc-grid input[type=checkbox] { justify-self: start; }
.rc-note { margin: 6px 0; padding: 6px 8px; border-radius: 4px; background: #1c2230; color: #c8d1dc; }
.rc-note.rc-warn { border-left: 3px solid #e0b252; }
.rc-note.rc-bad { border-left: 3px solid #e5534b; }
.rc-row { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; flex-wrap: wrap; }
.rc-btn { padding: 6px 14px; background: #2a3447; color: #dfe6ee; border: 1px solid #3a4558; border-radius: 4px; font: inherit; cursor: pointer; }
.rc-btn:hover { background: #35425a; }
.rc-btn.rc-go { background: #1f4a7a; border-color: #3b9cff; color: #fff; }
.rc-btn:disabled { opacity: 0.5; cursor: default; }
.rc-bar { height: 8px; margin: 10px 0 6px; background: #262d3a; border-radius: 4px; overflow: hidden; }
.rc-bar > i { display: block; height: 100%; width: 0; background: #3b9cff; }
.rc-stat { color: #c8d1dc; font-variant-numeric: tabular-nums; min-height: 1.4em; }
`;

function ensureStyle(): void {
  if (document.getElementById('rc-style')) return;
  const st = document.createElement('style');
  st.id = 'rc-style';
  st.textContent = CSS;
  document.head.appendChild(st);
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', attrs: Record<string, string> = {}, text = ''): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text) e.textContent = text;
  return e;
}

const help = (name: string): Record<string, string> => ({ 'data-help-key': `Record dialog/${name}`, 'data-help-title': name });

export interface DialogArgs {
  /** The title: what is recorded ("Fly-through: Tour"). */
  subject: string;
  /** Score duration in seconds. */
  duration: number;
  initial: ExportOptions;
  windowSize: OutputSize;
  maxSide: number;
  /** What this browser can do, in words, shown under the format. */
  capability: string;
  /** Time a few frames at the chosen options; resolves milliseconds per frame, or null when it could not. */
  timeFrames?: (o: ExportOptions) => Promise<number | null>;
}

/** The options dialog. Resolves the options on Record, null on Cancel or Escape. */
export function openOptionsDialog(a: DialogArgs): Promise<ExportOptions | null> {
  ensureStyle();
  return new Promise((resolve) => {
    const back = el('div', 'rc-back', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Record a video', 'data-record-dialog': '1' });
    const card = el('div', 'rc-card');
    card.append(el('h2', '', {}, 'Record a video'), el('div', 'rc-stat', {}, a.subject));
    const grid = el('div', 'rc-grid');
    const sel = (label: string, key: string, opts: ReadonlyArray<{ id: string | number; label: string }>, value: string | number): HTMLSelectElement => {
      const id = `rc-${key}`;
      const l = el('label', '', { for: id }, label);
      const s = el('select', '', { id, ...help(label) });
      for (const o of opts) {
        const op = el('option', '', { value: String(o.id) }, o.label);
        if (String(o.id) === String(value)) op.selected = true;
        s.append(op);
      }
      grid.append(l, s);
      return s;
    };
    const size = sel('Size', 'size', SIZE_CHOICES, a.initial.size);
    const fps = sel('Frame rate', 'fps', FPS_CHOICES.map((f) => ({ id: f, label: `${f} frames per second` })), a.initial.fps);
    const quality = sel('Quality', 'quality', QUALITY_CHOICES, a.initial.quality);
    const format = sel('Format', 'format', [
      { id: 'auto', label: 'Automatic' },
      { id: 'mp4', label: 'MP4 (H.264)' },
      { id: 'webm', label: 'WebM (VP9)' },
      { id: 'png', label: 'PNG image sequence (zip)' },
    ], a.initial.format);
    const hudLabel = el('label', '', { for: 'rc-hud' }, 'Captions and labels');
    const hud = el('input', '', { id: 'rc-hud', type: 'checkbox', ...help('Include HUD') });
    hud.checked = a.initial.hud;
    grid.append(hudLabel, hud);
    const nameLabel = el('label', '', { for: 'rc-name' }, 'File name');
    const name = el('input', '', { id: 'rc-name', type: 'text', maxlength: '80', spellcheck: 'false', autocomplete: 'off', ...help('File name') });
    name.value = a.initial.name;
    grid.append(nameLabel, name);
    card.append(grid);

    const info = el('div', 'rc-note', { role: 'status' });
    const warn = el('div', 'rc-note rc-warn');
    const cap = el('div', 'rc-note', {}, a.capability);
    card.append(info, warn, cap);

    const row = el('div', 'rc-row');
    const timeBtn = el('button', 'rc-btn', { type: 'button', ...help('Time frames') }, 'Time a few frames');
    const cancel = el('button', 'rc-btn', { type: 'button', ...help('Cancel') }, 'Cancel');
    const go = el('button', 'rc-btn rc-go', { type: 'button', ...help('Record') }, 'Record');
    if (a.timeFrames) row.append(timeBtn);
    row.append(cancel, go);
    card.append(row);
    back.append(card);

    const read = (): ExportOptions => ({
      size: size.value as SizeChoice,
      fps: Number(fps.value),
      quality: quality.value as Quality,
      format: format.value as VideoFormat,
      hud: hud.checked,
      name: name.value,
    });
    let measured: number | null = null;
    const refresh = (): void => {
      const o = read();
      const sz = resolveOutputSize(o.size, a.windowSize, a.maxSide);
      const s = summarize(a.duration, o, sz.width, sz.height);
      info.textContent = `${sz.width} x ${sz.height}, ${s.frames} frames, about ${s.megabytes < 10 ? s.megabytes.toFixed(1) : Math.round(s.megabytes)} MB.`;
      const big = Math.max(sz.width, sz.height) >= 2560;
      const parts: string[] = [];
      if (big) parts.push('This size takes a long time on a slow machine. Use the button to time a few frames first.');
      if (o.format === 'png') parts.push('PNG frames need a lot of memory. Use a short fly-through or a small size.');
      if (measured !== null) parts.push(`A frame takes about ${Math.round(measured)} ms here. The whole video takes about ${formatDuration(measured * s.frames)}.`);
      warn.textContent = parts.join(' ');
      warn.style.display = parts.length ? '' : 'none';
    };
    for (const c of [size, fps, quality, format, hud]) c.addEventListener('change', () => {
      measured = null;
      refresh();
    });
    refresh();

    const close = (v: ExportOptions | null): void => {
      window.removeEventListener('keydown', onKey, true);
      back.remove();
      resolve(v);
    };
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        close(null);
      } else if (e.key === 'Enter' && (e.target as HTMLElement | null)?.tagName !== 'BUTTON' && (e.target as HTMLElement | null)?.tagName !== 'SELECT') {
        e.preventDefault();
        e.stopPropagation();
        close(read());
      }
    };
    window.addEventListener('keydown', onKey, true);
    back.addEventListener('pointerdown', (e) => {
      if (e.target === back) close(null);
    });
    cancel.addEventListener('click', () => close(null));
    go.addEventListener('click', () => close(read()));
    timeBtn.addEventListener('click', () => {
      if (!a.timeFrames) return;
      timeBtn.disabled = true;
      timeBtn.textContent = 'Timing...';
      void a.timeFrames(read()).then((ms) => {
        measured = ms;
        timeBtn.disabled = false;
        timeBtn.textContent = 'Time a few frames';
        refresh();
      });
    });
    document.body.append(back);
    go.focus();
  });
}

export interface BusyOverlay {
  setTitle(text: string): void;
  progress(p: Progress): void;
  /** A line under the bar (a warning about the time). */
  note(text: string): void;
  close(): void;
}

/** The busy overlay: blocks the pointer and the keys (Escape cancels). `dim: false` keeps the view visible (real-time recording). */
export function openBusyOverlay(title: string, onCancel: () => void, opts: { dim?: boolean } = {}): BusyOverlay {
  ensureStyle();
  const back = el('div', `rc-back${opts.dim === false ? ' rc-clear' : ''}`, { role: 'alertdialog', 'aria-modal': 'true', 'aria-label': 'Recording', 'data-record-busy': '1' });
  const card = el('div', 'rc-card');
  const h = el('h2', '', {}, title);
  const bar = el('div', 'rc-bar');
  const fill = el('i');
  bar.append(fill);
  const stat = el('div', 'rc-stat', { role: 'status', 'aria-live': 'off', 'data-record-status': '1' }, 'Starting...');
  const warn = el('div', 'rc-note rc-warn');
  warn.style.display = 'none';
  const row = el('div', 'rc-row');
  const cancel = el('button', 'rc-btn', { type: 'button', 'data-record-cancel': '1', ...help('Cancel recording') }, 'Cancel');
  row.append(cancel);
  card.append(h, el('div', 'rc-stat', {}, 'The viewer is busy until the video is ready. Input is blocked.'), bar, stat, warn, row);
  back.append(card);
  // Block every pointer and key event of the viewer; Escape cancels.
  const stopEv = (e: Event): void => {
    if ((e.target as HTMLElement | null)?.closest?.('.rc-card')) return;
    e.preventDefault();
    e.stopPropagation();
  };
  for (const t of ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'contextmenu', 'wheel', 'touchstart']) back.addEventListener(t, stopEv, { passive: false });
  const onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') onCancel();
    if ((e.target as HTMLElement | null)?.closest?.('.rc-card') && (e.key === 'Enter' || e.key === ' ' || e.key === 'Tab')) return;
    e.preventDefault();
    e.stopPropagation();
  };
  window.addEventListener('keydown', onKey, true);
  window.addEventListener('keyup', onKey, true);
  cancel.addEventListener('click', () => {
    cancel.disabled = true;
    cancel.textContent = 'Cancelling...';
    onCancel();
  });
  document.body.append(back);
  cancel.focus();
  return {
    setTitle: (t) => void (h.textContent = t),
    progress: (p) => {
      fill.style.width = `${Math.min(100, (100 * p.done) / Math.max(1, p.total)).toFixed(1)}%`;
      const eta = p.etaMs === null ? '' : `, about ${formatDuration(p.etaMs)} left`;
      stat.textContent = `Frame ${p.done} of ${p.total}${eta}`;
    },
    note: (t) => {
      warn.textContent = t;
      warn.style.display = t ? '' : 'none';
    },
    close: () => {
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('keyup', onKey, true);
      back.remove();
    },
  };
}
