// Small DOM widgets for tool drawers, styled by the toolbar stylesheet (class prefix `xt-`).
// Every widget returns its root element plus an `update()` where the value can change from elsewhere.

import { el } from '../ui/dom';

export interface Widget<T extends HTMLElement = HTMLElement> {
  root: T;
  update(): void;
}

export function section(title: string): HTMLElement {
  return el('div', 'xt-sec', undefined, title);
}

export function note(text: string): HTMLElement {
  return el('div', 'xt-note', undefined, text);
}

export function button(label: string, onClick: () => void, opts: { primary?: boolean; title?: string } = {}): HTMLButtonElement & { setDisabled(why: string | false): void } {
  const b = el('button', `xt-btn${opts.primary ? ' primary' : ''}`, { type: 'button' }, label) as HTMLButtonElement & { setDisabled(why: string | false): void };
  if (opts.title) b.title = opts.title;
  const base = opts.title ?? '';
  b.addEventListener('click', () => {
    if (!b.disabled) onClick();
  });
  b.setDisabled = (why) => {
    b.disabled = why !== false;
    b.title = why === false ? base : why;
  };
  return b;
}

export function row(...children: Array<HTMLElement | null>): HTMLElement {
  const r = el('div', 'xt-row');
  for (const c of children) if (c) r.appendChild(c);
  return r;
}

export function check(label: string, get: () => boolean, set: (v: boolean) => void): Widget<HTMLLabelElement> {
  const root = el('label', 'xt-check');
  const input = el('input', undefined, { type: 'checkbox' });
  root.append(input, el('span', undefined, undefined, label));
  input.addEventListener('change', () => set(input.checked));
  return { root, update: () => { input.checked = get(); } };
}

export function slider(label: string, min: number, max: number, step: number, get: () => number, set: (v: number) => void, fmt: (v: number) => string = (v) => String(v)): Widget {
  const root = el('div', 'xt-slider');
  const name = el('span', 'xt-lbl', undefined, label);
  const input = el('input', undefined, { type: 'range', min: String(min), max: String(max), step: String(step) });
  const val = el('span', 'xt-val');
  root.append(name, input, val);
  input.addEventListener('input', () => {
    const v = Number(input.value);
    set(v);
    val.textContent = fmt(v);
  });
  const update = (): void => {
    const v = get();
    input.value = String(v);
    val.textContent = fmt(v);
  };
  return { root, update };
}

export function select<T extends string>(label: string, options: readonly T[], get: () => T, set: (v: T) => void): Widget {
  const root = el('label', 'xt-select');
  const sel = el('select');
  for (const o of options) sel.appendChild(el('option', undefined, { value: o }, o));
  root.append(el('span', 'xt-lbl', undefined, label), sel);
  sel.addEventListener('change', () => set(sel.value as T));
  return { root, update: () => { sel.value = get(); } };
}

export function number(label: string, min: number, step: number, get: () => number, set: (v: number) => void): Widget {
  const root = el('label', 'xt-select');
  const inp = el('input', 'xt-num', { type: 'number', min: String(min), step: String(step) });
  root.append(el('span', 'xt-lbl', undefined, label), inp);
  inp.addEventListener('change', () => {
    const v = Number(inp.value);
    if (Number.isFinite(v) && v >= min) set(v);
    else inp.value = String(get());
  });
  return { root, update: () => { inp.value = String(get()); } };
}

/** A row of toggle chips. `selected` is mutated in place; `onChange` runs after every toggle. */
export function chips<T extends string | number | null>(items: ReadonlyArray<{ value: T; label: string; title?: string }>, selected: Set<T>, onChange: () => void): HTMLElement {
  const root = el('div', 'xt-chips');
  for (const it of items) {
    const b = el('button', 'xt-chip', { type: 'button' }, it.label);
    if (it.title) b.title = it.title;
    const paint = (): void => { b.classList.toggle('on', selected.has(it.value)); };
    paint();
    b.addEventListener('click', () => {
      if (selected.has(it.value)) selected.delete(it.value);
      else selected.add(it.value);
      paint();
      onChange();
    });
    root.appendChild(b);
  }
  return root;
}

export function statusLine(initial = ''): HTMLElement & { set(text: string): void } {
  const e = el('div', 'xt-status', undefined, initial) as unknown as HTMLElement & { set(text: string): void };
  e.set = (t) => { e.textContent = t; };
  return e;
}
