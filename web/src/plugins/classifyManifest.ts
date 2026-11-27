// The "Export manifest..." options panel, shared by the review walk (History tab) and the Classification drawer: the format (JSON or a
// short Markdown summary) and two opt-in boxes, both off by default. The file never holds API keys or tokens. See classify/manifest.ts.

import type { ClassifyService } from '../classify/service';
import { manifestJson, manifestMarkdown } from '../classify/manifest';
import { downloadText } from '../tools/csv';
import { el } from '../ui/dom';

export interface ManifestPanelOptions {
  /** Class names of the host (the walk and the drawer style their own buttons). */
  cls: { box: string; btn: string; primary: string; row: string };
  /** The model's file name, for the name of the saved file. */
  modelName: string;
  /** Called after a save (message) or a failure (error), and on Cancel (no message). */
  done(r: { message?: string; error?: string } | null): void;
}

export function buildManifestPanel(svc: ClassifyService, o: ManifestPanelOptions): HTMLElement {
  const box = el('div', o.cls.box, { 'data-role': 'manifest-panel', 'aria-label': 'Export manifest' });
  box.appendChild(el('div', undefined, undefined, 'Export manifest: counts by source, code and confidence, the review actions and a from-to table of corrections. No API keys, no tokens.'));
  const fmt = (v: 'json' | 'md', label: string, on: boolean): HTMLElement => {
    const l = el('label');
    const i = el('input', undefined, { type: 'radio', name: 'xrw-manifest-format', value: v, 'data-role': `manifest-${v}` });
    i.checked = on;
    l.append(i, el('span', undefined, undefined, label));
    return l;
  };
  const json = fmt('json', 'JSON (xray-classification-manifest/1)', true);
  const md = fmt('md', 'Markdown summary', false);
  const mk = (role: string, label: string, title: string): { l: HTMLElement; i: HTMLInputElement } => {
    const l = el('label');
    l.title = title;
    const i = el('input', undefined, { type: 'checkbox', 'data-role': role });
    i.checked = false;
    l.append(i, el('span', undefined, undefined, label));
    return { l, i };
  };
  const per = mk('manifest-per-element', 'List the corrections element by element (JSON only)', 'One row for each correction that a person made: GlobalId, class, name, what changed, before and after, note and time. Off by default.');
  const names = mk('manifest-reviewer-names', 'Include reviewer names', 'Adds the names or initials of the reviewers. A name is personal data. Off by default.');
  const save = el('button', o.cls.primary, { type: 'button', 'data-act': 'manifest-save' }, 'Save manifest');
  save.addEventListener('click', () => {
    try {
      const asMd = (md.querySelector('input') as HTMLInputElement).checked;
      const m = svc.manifest({ perElement: per.i.checked && !asMd, reviewerNames: names.i.checked });
      const base = `classification-manifest-${o.modelName || 'model'}`;
      if (asMd) downloadText(`${base}.md`, manifestMarkdown(m), 'text/markdown;charset=utf-8');
      else downloadText(`${base}.json`, manifestJson(m), 'application/json');
      o.done({ message: `Saved the manifest (${asMd ? 'Markdown' : 'JSON'}).` });
    } catch (e) {
      o.done({ error: e instanceof Error ? e.message : String(e) });
    }
  });
  const cancel = el('button', o.cls.btn, { type: 'button', 'data-act': 'manifest-cancel' }, 'Cancel');
  cancel.addEventListener('click', () => o.done(null));
  const r = el('div', o.cls.row);
  r.append(save, cancel);
  box.append(json, md, per.l, names.l, r);
  return box;
}
