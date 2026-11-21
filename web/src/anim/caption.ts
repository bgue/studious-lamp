// A lower-third caption over the canvas while a score plays (title and text of a caption cue). A plain overlay: no input.

let box: HTMLDivElement | null = null;
let titleEl: HTMLDivElement | null = null;
let textEl: HTMLDivElement | null = null;

const CSS = `
.fl-caption { position: fixed; left: 50%; bottom: 9%; transform: translateX(-50%); z-index: 850; max-width: min(640px, 86vw); box-sizing: border-box;
  padding: 8px 14px 9px; border-radius: 6px; background: rgba(12, 16, 22, 0.78); color: #f1f5f9; pointer-events: none; text-align: left;
  font: 14px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6); border-left: 3px solid #3b9cff; }
.fl-caption[hidden] { display: none; }
.fl-caption .fl-cap-title { font-weight: 700; font-size: 16px; }
.fl-caption .fl-cap-text { margin-top: 2px; opacity: 0.92; }
`;

function ensure(): void {
  if (box) return;
  const st = document.createElement('style');
  st.textContent = CSS;
  document.head.appendChild(st);
  box = document.createElement('div');
  box.className = 'fl-caption';
  box.hidden = true;
  box.setAttribute('role', 'status');
  box.setAttribute('aria-live', 'polite');
  titleEl = document.createElement('div');
  titleEl.className = 'fl-cap-title';
  textEl = document.createElement('div');
  textEl.className = 'fl-cap-text';
  box.append(titleEl, textEl);
  document.body.appendChild(box);
}

export function showCaption(title?: string, text?: string): void {
  ensure();
  titleEl!.textContent = title ?? '';
  titleEl!.style.display = title ? '' : 'none';
  textEl!.textContent = text ?? '';
  textEl!.style.display = text ? '' : 'none';
  box!.hidden = !title && !text;
}

export function hideCaption(): void {
  if (box) box.hidden = true;
}

/** What the caption shows now (for smoke tests). */
export function captionState(): { visible: boolean; title: string; text: string } {
  if (!box) return { visible: false, title: '', text: '' };
  return { visible: !box.hidden, title: titleEl?.textContent ?? '', text: textEl?.textContent ?? '' };
}
