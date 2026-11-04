// Drag and drop of files onto the whole page, with a visible overlay while files are dragged over it.
// Plain DOM, no dependencies. Only drags that carry files react; text or link drags are left alone.

export interface DropZoneOptions {
  /** Text in the overlay, e.g. "Drop IFC or glb files to open". */
  text: string;
  onFiles(files: File[]): void;
  /** Called when a drag carrying files enters the page (once per drag), e.g. to warm something up. */
  onDragStart?(): void;
  /** Where to listen; default document. */
  target?: Document | HTMLElement;
}

export interface DropZone {
  readonly overlay: HTMLElement;
  dispose(): void;
}

function carriesFiles(e: DragEvent): boolean {
  const types = e.dataTransfer?.types;
  if (!types) return false;
  for (let i = 0; i < types.length; i++) if (types[i] === 'Files') return true;
  return false;
}

export function installDropZone(opts: DropZoneOptions): DropZone {
  const target = opts.target ?? document;
  const overlay = document.createElement('div');
  overlay.id = 'xray-drop-overlay';
  overlay.setAttribute('aria-hidden', 'true');
  overlay.style.cssText =
    'position:fixed;inset:0;z-index:60;display:none;align-items:center;justify-content:center;pointer-events:none;' +
    'background:rgba(24,40,64,0.55);';
  const box = document.createElement('div');
  box.textContent = opts.text;
  box.style.cssText =
    'padding:28px 44px;border:3px dashed #9fc6ff;border-radius:14px;background:rgba(14,22,36,0.88);color:#eaf2ff;' +
    'font:600 22px system-ui,sans-serif;letter-spacing:0.2px';
  overlay.appendChild(box);
  document.body.appendChild(overlay);

  let depth = 0;
  const show = (on: boolean): void => {
    overlay.style.display = on ? 'flex' : 'none';
  };
  const onEnter = (ev: Event): void => {
    const e = ev as DragEvent;
    if (!carriesFiles(e)) return;
    e.preventDefault();
    if (depth === 0) opts.onDragStart?.();
    depth++;
    show(true);
  };
  const onOver = (ev: Event): void => {
    const e = ev as DragEvent;
    if (!carriesFiles(e)) return;
    e.preventDefault(); // required, or the browser refuses the drop and navigates to the file
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    show(true);
  };
  const onLeave = (ev: Event): void => {
    const e = ev as DragEvent;
    if (!carriesFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) show(false);
  };
  const onDrop = (ev: Event): void => {
    const e = ev as DragEvent;
    if (!carriesFiles(e)) return;
    e.preventDefault();
    depth = 0;
    show(false);
    const files = e.dataTransfer ? Array.from(e.dataTransfer.files) : [];
    if (files.length > 0) opts.onFiles(files);
  };
  const hide = (): void => {
    depth = 0;
    show(false);
  };
  target.addEventListener('dragenter', onEnter);
  target.addEventListener('dragover', onOver);
  target.addEventListener('dragleave', onLeave);
  target.addEventListener('drop', onDrop);
  window.addEventListener('dragend', hide);
  window.addEventListener('blur', hide);

  return {
    overlay,
    dispose(): void {
      target.removeEventListener('dragenter', onEnter);
      target.removeEventListener('dragover', onOver);
      target.removeEventListener('dragleave', onLeave);
      target.removeEventListener('drop', onDrop);
      window.removeEventListener('dragend', hide);
      window.removeEventListener('blur', hide);
      overlay.remove();
    },
  };
}
