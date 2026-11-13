// Markup file helpers: the hidden file input (the Sketches panel, the palette action and scripts all use it), opening a PDF
// or JSON file, and the page-level drop of such a file. The sketch panels live in src/issues/ui.ts and the drawing toolbar in
// toolbar.ts. DOM only; logic lives in controller.ts.

import type { MarkupController } from './controller';

export function isMarkupFile(n: string): boolean {
  return /\.pdf$/i.test(n) || /\.json$/i.test(n);
}

let fileInput: HTMLInputElement | null = null;

/** The shared hidden file input (drawer button, panel button and palette action all use it). */
export function markupFileInput(c: MarkupController): HTMLInputElement {
  if (fileInput && document.body.contains(fileInput)) return fileInput;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.pdf,.json,application/pdf,application/json';
  input.style.display = 'none';
  input.setAttribute('data-markup', 'open');
  input.addEventListener('change', () => {
    const f = input.files?.[0];
    input.value = '';
    if (f) void openFile(c, f);
  });
  document.body.appendChild(input);
  fileInput = input;
  return input;
}

export function pickMarkupFile(c: MarkupController): void {
  markupFileInput(c).click();
}

export async function openFile(c: MarkupController, f: File): Promise<void> {
  try {
    const r = await c.importFile(f);
    if (r.warnings.length || !r.ok) {
      c.app.showMessage(r.ok ? `Markup opened. ${r.warnings[0]}` : (r.error ?? 'Could not open the markup file'));
      setTimeout(() => c.app.showMessage(null), 7000);
    }
  } catch (e) {
    c.setStatus(`Could not open the markup file: ${e instanceof Error ? e.message : String(e)}`);
  }
}

/** Window level drop of a PDF or JSON file that is not a model: anywhere on the page. Returns the remover. */
export function installDrop(c: MarkupController): () => void {
  const onDrop = (e: DragEvent): void => {
    const files = Array.from(e.dataTransfer?.files ?? []);
    // A lone .pdf or .json is never a model (models are .ifc or .glb, a .json goes with a .glb), so it is a markup file.
    if (files.length !== 1 || !isMarkupFile(files[0]!.name)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    void openFile(c, files[0]!);
  };
  window.addEventListener('drop', onDrop, true);
  return () => window.removeEventListener('drop', onDrop, true);
}
