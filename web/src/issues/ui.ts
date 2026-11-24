// The Issues panel (mode `issues`): the list of issues (filter, search, status chips, "Other models (n)") and the detail of the
// chosen issue in the same column. It lives in the sidebar tab "Issues" (and in a bottom sheet on a phone, src/plugins/issues.ts).
// The same builder makes the drawings part of the Views tab (mode `views`): the detail of a view that has a drawing layer, the sheets
// pane, "Open file" and "Other models (n)". DOM only; the logic is in controller.ts.

import { el } from '../ui/dom';
import { button, row, select } from '../tools/ui';
import { DEFAULT_PRIORITIES, DEFAULT_STATUSES } from '../bcf/controller';
import { COLOURS, KIND_LABEL, hasLegacyReview } from '../markup/model';
import type { Markup, MarkupSet } from '../markup/model';
import { PDF_RESOLUTIONS } from '../markup/controller';
import type { PdfResolution } from '../markup/controller';
import type { PageSize } from '../markup/report';
import { buildAttachChip } from '../markup/attachUi';
import { buildViewSwitch } from './viewSwitchUi';
import { openTopicDialog, pickBcfFile } from '../bcf/ui';
import { pickMarkupFile } from '../markup/ui';
import type { BcfTopic, BcfViewpointRef } from '../bcf/model';
import type { IssuesController, StatusFilter } from './controller';
import { isOpenStatus } from './controller';
import { buildReportBlock } from './reportUi';

const STYLE_ID = 'issues-styles';
const CSS = `
.is-root { --is-fg: var(--sb-fg, #dfe6ee); --is-dim: var(--sb-dim, #8d99a8); --is-line: var(--sb-line, #262d3a); --is-hover: var(--sb-hover, #1c2230); --is-sel: var(--sb-sel, #1f4a7a); --is-accent: var(--sb-accent, #3b9cff);
  color: var(--is-fg); font: 12px/1.4 system-ui, sans-serif; display: flex; flex-direction: column; gap: 6px; box-sizing: border-box; padding: 8px; min-height: 0; flex: 1 1 auto; overflow-y: auto; }
.is-root * { box-sizing: border-box; }
.is-root.is-embedded { flex: 0 0 auto; overflow: visible; }
.is-vthumb { width: 56px; height: 35px; object-fit: cover; border-radius: 3px; background: #1b2230; flex: 0 0 auto; }
.is-seg { display: flex; border: 1px solid var(--is-line); border-radius: 6px; overflow: hidden; flex: 0 0 auto; }
.is-seg button { flex: 1 1 0; background: transparent; color: var(--is-dim); border: 0; padding: 6px 4px; font: inherit; font-weight: 600; cursor: pointer; min-height: 30px; }
.is-seg button[aria-selected=true] { background: var(--is-sel); color: #fff; }
.is-seg button + button { border-left: 1px solid var(--is-line); }
.is-in { background: #0e1218; color: var(--is-fg); border: 1px solid var(--is-line); border-radius: 4px; padding: 4px 6px; font: inherit; min-width: 0; width: 100%; }
.is-in:focus { outline: 1px solid var(--is-accent); }
textarea.is-in { resize: vertical; }
.is-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.is-fchip { font: inherit; font-size: 11px; padding: 0 9px; line-height: 20px; border-radius: 10px; border: 1px solid var(--is-line); background: transparent; color: var(--is-fg); cursor: pointer; }
.is-fchip[aria-pressed=true] { background: var(--is-sel); border-color: var(--is-accent); }
.is-list { display: flex; flex-direction: column; border: 1px solid var(--is-line); border-radius: 4px; }
.is-item { padding: 6px 8px; border-bottom: 1px solid var(--is-line); display: flex; flex-direction: column; gap: 3px; cursor: pointer; background: transparent; color: inherit; font: inherit; text-align: left; border-left: 0; border-right: 0; border-top: 0; width: 100%; }
.is-item:last-child { border-bottom: 0; }
.is-item:hover { background: var(--is-hover); }
.is-item.sel { background: var(--is-sel); }
.is-t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.is-meta { color: var(--is-dim); font-size: 11px; }
.is-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.is-tag { display: inline-block; padding: 0 7px; border-radius: 9px; font-size: 10.5px; line-height: 16px; border: 1px solid transparent; white-space: nowrap; background: #2a303c; color: #c3ccd8; }
.is-tag.open { background: #4a3a12; color: #ffd37a; } .is-tag.progress { background: #14365c; color: #8cc4ff; } .is-tag.done { background: #16401f; color: #8fe0a0; }
.is-tag.high { background: #5a1f1f; color: #ffa5a5; } .is-tag.link { background: #14365c; color: #8cc4ff; } .is-tag.lbl { border-color: var(--is-line); background: transparent; color: var(--is-dim); }
.is-empty { color: var(--is-dim); padding: 10px; text-align: center; }
.is-banner { border: 1px solid #8a6a1c; background: #3a2e10; color: #ffe2a0; border-radius: 6px; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.is-head { display: flex; align-items: center; gap: 6px; }
.is-head .is-title { flex: 1 1 auto; min-width: 0; font-weight: 700; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.is-h { color: var(--is-dim); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 4px; }
.is-snap { width: 100%; max-height: 190px; object-fit: contain; border-radius: 4px; border: 1px solid var(--is-line); display: block; background: #0e1218; }
.is-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 6px; }
.is-card { border: 1px solid var(--is-line); border-radius: 5px; padding: 4px; cursor: pointer; display: flex; flex-direction: column; gap: 3px; background: transparent; color: inherit; font: inherit; text-align: left; }
.is-card:hover { background: var(--is-hover); } .is-card.sel { border-color: var(--is-accent); background: var(--is-sel); }
.is-card img, .is-card .is-nothumb { width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: 3px; background: #0e1218; display: flex; align-items: center; justify-content: center; color: var(--is-dim); font-size: 10px; }
.is-vp { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; border: 1px solid var(--is-line); border-radius: 4px; padding: 4px 6px; }
.is-comment { border-left: 2px solid var(--is-line); padding: 1px 0 1px 7px; }
.is-comment .who { color: var(--is-dim); font-size: 10.5px; }
.is-mk { padding: 4px 6px; border-bottom: 1px solid var(--is-line); display: flex; flex-direction: column; gap: 3px; cursor: pointer; }
.is-mk:last-child { border-bottom: 0; } .is-mk:hover { background: var(--is-hover); } .is-mk.sel { background: var(--is-sel); }
.is-mk-h { display: flex; gap: 6px; align-items: center; }
.is-num { min-width: 22px; height: 22px; border-radius: 11px; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 11px; color: #fff; padding: 0 4px; flex: none; }
.is-x { border: 0; background: transparent; color: var(--is-dim); cursor: pointer; font-size: 16px; line-height: 1; padding: 0 4px; margin-left: auto; }
.is-x:hover { color: #ff8a8a; }
.is-legacy { border: 1px dashed var(--is-line); border-radius: 5px; padding: 6px; display: flex; flex-direction: column; gap: 4px; color: var(--is-dim); }
.is-confirm { border: 1px solid #8a3a3a; background: #3a1a1a; border-radius: 6px; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.is-other { border: 1px solid var(--is-line); border-radius: 5px; } .is-other > summary { cursor: pointer; padding: 6px 8px; font-weight: 600; color: var(--is-dim); }
.is-other[open] > summary { border-bottom: 1px solid var(--is-line); }
.is-other-model { padding: 6px 8px; display: flex; flex-direction: column; gap: 4px; border-bottom: 1px solid var(--is-line); } .is-other-model:last-child { border-bottom: 0; }
.is-status { color: var(--is-dim); font-size: 11px; min-height: 14px; }
.is-two { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.is-lbl { color: var(--is-dim); font-size: 10.5px; display: flex; flex-direction: column; gap: 2px; }
.is-root.is-drop::after { content: 'Drop a BCF, PDF or JSON file to open'; position: absolute; inset: 0; background: rgba(31,74,122,0.85); display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px dashed var(--is-accent); text-align: center; padding: 12px; }
`;

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

function when(s: string | undefined): string {
  if (!s) return '';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

function statusClass(s: string): string {
  if (!isOpenStatus(s)) return 'done';
  return /progress|review|active/i.test(s) ? 'progress' : 'open';
}

function priorityClass(p: string): string {
  return /high|critical|urgent|major/i.test(p) ? 'high' : '';
}

const tag = (text: string, cls = ''): HTMLSpanElement => el('span', `is-tag ${cls}`.trim(), undefined, text);

export interface IssuesPanel {
  root: HTMLElement;
  render(): void;
  dispose(): void;
}

/** Build the panel into `host`. */
export function buildIssuesPanel(host: HTMLElement, c: IssuesController, mode: 'issues' | 'views' = 'issues'): IssuesPanel {
  ensureStyles();
  const root = el('div', 'is-root');
  root.id = mode === 'issues' ? 'issues-panel' : 'views-drawings';
  root.setAttribute('data-help-key', mode === 'issues' ? 'Issues panel' : 'Views panel/Drawings');
  if (mode === 'views') root.classList.add('is-embedded');
  host.appendChild(root);
  const urls = new Map<string, { sig: string; url: string }>();
  const drafts = new Map<string, string>();
  let otherOpen = false;
  let raiseTarget = ''; // '' = a new issue
  let bannerDismissed = false;
  let page: PageSize = 'A4';
  const bcf = c.bcf;
  const mk = c.markup;
  // A text box that commits on blur (title, assignee, due date, author) must not rebuild the panel under the click that moves the
  // focus away from it: its change runs `silently`, and the panel only refreshes the status line.
  let hold = 0;
  const silently = (fn: () => void): void => {
    hold++;
    try { fn(); } finally { hold--; }
  };
  const arm = (b: HTMLButtonElement, label: string, run: () => void): void => {
    b.addEventListener('click', () => {
      if (b.dataset['arm'] === '1') run();
      else {
        b.dataset['arm'] = '1';
        b.textContent = 'Click again to confirm';
        setTimeout(() => { b.dataset['arm'] = ''; b.textContent = label; }, 2500);
      }
    });
  };
  const act = (b: HTMLButtonElement, name: string): HTMLButtonElement => {
    b.setAttribute('data-act', name);
    return b;
  };
  const fail = (e: unknown): void => mk.setStatus(e instanceof Error ? e.message : String(e));
  const input = (cls: string, attrs: Record<string, string>, value = ''): HTMLInputElement => {
    const i = el('input', cls, attrs);
    i.value = value;
    i.addEventListener('keydown', (e) => e.stopPropagation());
    return i;
  };
  const draft = (key: string, e: HTMLInputElement | HTMLTextAreaElement): void => {
    e.setAttribute('data-keep', key);
    const have = drafts.get(key);
    if (have !== undefined) e.value = have;
    e.addEventListener('input', () => drafts.set(key, e.value));
  };

  // ---------------------------------------------------------------- the burned snapshot of an issue viewpoint
  async function markedSnapshot(t: BcfTopic, ref: BcfViewpointRef, img: HTMLImageElement): Promise<void> {
    const sig = JSON.stringify([t.pin, ref.annotations, bcf.pinNumber(t), bcf.units]);
    const have = urls.get(ref.guid);
    if (have?.sig === sig) { img.src = have.url; return; }
    const bytes = await bcf.composeSnapshot(t, ref);
    if (!bytes || !img.isConnected) return;
    if (have) URL.revokeObjectURL(have.url);
    const url = URL.createObjectURL(new Blob([bytes as Uint8Array<ArrayBuffer>], { type: ref.snapshotMime ?? 'image/png' }));
    urls.set(ref.guid, { sig, url });
    img.src = url;
  }
  const rawSnapshot = (ref: BcfViewpointRef): string => {
    const k = `raw-${ref.guid}`;
    let u = urls.get(k);
    if (!u) {
      u = { sig: '', url: URL.createObjectURL(new Blob([ref.snapshot as Uint8Array<ArrayBuffer>], { type: ref.snapshotMime ?? 'image/png' })) };
      urls.set(k, u);
    }
    return u.url;
  };

  // ---------------------------------------------------------------- pieces

  function banner(): HTMLElement | null {
    const n = c.legacy().length;
    if (!n || bannerDismissed) return null;
    const b = el('div', 'is-banner', { 'data-banner': 'migrate', role: 'status' });
    b.appendChild(el('div', undefined, { 'data-banner-text': '' }, `${n} view${n === 1 ? ' has' : 's have'} comments or a status. Make ${n === 1 ? 'an issue of it' : 'issues of them'}?`));
    const yes = act(button('Yes, make issues', () => { void c.migrateLegacy(); }, { primary: true, title: 'Make an issue of each view, moving its comments and status. The issue points at the view.' }), 'migrate');
    const no = act(button('Not now', () => { bannerDismissed = true; c.emit(); }, { title: 'Keep the comments and status on the views, read-only' }), 'migrate-later');
    b.appendChild(row(yes, no));
    return b;
  }

  function filterRow(withChips: boolean): HTMLElement[] {
    const out: HTMLElement[] = [];
    const q = input('is-in', { type: 'search', placeholder: 'Search title, description, comments', 'aria-label': 'Search', 'data-keep': 'query', 'data-field': 'query' }, c.query);
    q.addEventListener('input', () => { c.query = q.value; c.emit(); });
    out.push(q);
    if (withChips) {
      const chips = el('div', 'is-chips', { 'data-chips': 'status', role: 'group', 'aria-label': 'Status' });
      const n = (f: StatusFilter): number => (f === 'all' ? bcf.currentTopics.length : bcf.currentTopics.filter((t) => isOpenStatus(t.topicStatus) === (f === 'open')).length);
      for (const [f, label] of [['all', 'All'], ['open', 'Open'], ['closed', 'Closed']] as const) {
        const b = el('button', 'is-fchip', { type: 'button', 'data-status-filter': f, 'aria-pressed': String(c.statusFilter === f) }, `${label} ${n(f)}`);
        b.addEventListener('click', () => { c.statusFilter = f; c.emit(); });
        chips.appendChild(b);
      }
      out.push(chips);
    }
    return out;
  }

  function otherGroup<T>(groups: Array<{ label: string; key: string; items: T[] }>, line: (item: T) => HTMLElement): HTMLElement | null {
    if (!groups.length) return null;
    const n = groups.reduce((a, g) => a + g.items.length, 0);
    const det = el('details', 'is-other', { 'data-other-models': String(n) });
    det.open = otherOpen;
    det.addEventListener('toggle', () => { otherOpen = det.open; });
    det.appendChild(el('summary', undefined, undefined, `Other models (${n})`));
    for (const g of groups) {
      const box = el('div', 'is-other-model', { 'data-model': g.key });
      box.appendChild(el('div', 'is-meta', undefined, `Made on ${g.label}. Hidden on this model.`));
      for (const it of g.items) box.appendChild(line(it));
      det.appendChild(box);
    }
    return det;
  }

  // ---------------------------------------------------------------- issues list

  function issuesList(): HTMLElement[] {
    const out: HTMLElement[] = [];
    const bar = row(
      act(button('New issue', () => openTopicDialog(bcf, (t) => { c.adoptNewIssue(t); }), { primary: true, title: 'Capture the current view and make an issue of it' }), 'new'),
      act(button('Open BCF', () => pickBcfFile(bcf), { title: 'Open a BCF 2.1 or 3.0 file. You can also drop it on the page.' }), 'open'),
    );
    out.push(bar);
    out.push(...filterRow(true));
    const shown = c.visibleIssues();
    if (!shown.length) out.push(el('div', 'is-empty', undefined, bcf.currentTopics.length ? 'No issue matches the filter.' : 'No issues for this model. Open a BCF file, press New issue, or make an issue of a view in the Views tab.'));
    else {
      const list = el('div', 'is-list', { 'data-issue-list': '' });
      for (const t of shown) {
        const item = el('button', `is-item${(c.detail?.kind === 'issue' && c.detail.id === t.guid) || bcf.selectedTopic === t.guid ? ' sel' : ''}`, { type: 'button', 'data-issue': t.guid });
        item.appendChild(el('div', 'is-t', undefined, t.title));
        const tags = el('div', 'is-tags');
        const sc = bcf.scopeOf(t);
        if (sc.tag) tags.appendChild(tag(sc.tag, 'lbl'));
        if (t.topicStatus) tags.appendChild(tag(t.topicStatus, statusClass(t.topicStatus)));
        if (t.priority) tags.appendChild(tag(t.priority, priorityClass(t.priority)));
        const ns = c.sketchesOf(t).length;
        if (ns) tags.appendChild(tag(`${ns} view${ns === 1 ? '' : 's'}`, 'link'));
        if (t.comments.length) tags.appendChild(tag(`${t.comments.length} comment${t.comments.length === 1 ? '' : 's'}`, 'lbl'));
        if (t.assignedTo) tags.appendChild(tag(t.assignedTo, 'lbl'));
        item.appendChild(tags);
        item.addEventListener('click', () => c.openIssue(t.guid));
        list.appendChild(item);
      }
      out.push(list);
    }
    out.push(buildReportBlock(c));
    const other = otherGroup(
      bcf.otherModels().map((g) => ({ label: `${g.model.name} (${g.model.elementCount} elements)`, key: g.key, items: g.items })),
      (t) => {
        const line = el('div', 'is-other-set', { 'data-other-issue': t.guid });
        line.appendChild(el('div', 'is-t', undefined, t.title));
        line.appendChild(row(
          act(button('Open', () => c.openOtherIssue(t.guid), { title: 'Show this issue on this model. It may not fit: its targets are not here.' }), 'other-open'),
          act(button('Move to this model', () => c.moveIssueToModel(t.guid), { title: 'Make this issue and its views belong to the loaded model' }), 'other-move'),
        ));
        const del = act(button('Delete issue', () => undefined, { title: 'Remove this issue from the session' }), 'other-delete');
        arm(del, 'Delete issue', () => c.deleteIssue(t.guid));
        line.appendChild(row(del));
        return line;
      },
    );
    if (other) out.push(other);
    return out;
  }

  // ---------------------------------------------------------------- issue detail

  function issueDetail(t: BcfTopic): HTMLElement[] {
    const out: HTMLElement[] = [];
    const back = act(button('‹ Issues', () => { c.detail = null; c.emit(); }, { title: 'Back to the list' }), 'back');
    const head = el('div', 'is-head');
    head.append(back, el('div', 'is-title', { 'data-issue-title': '' }, t.title));
    out.push(head);
    const first = t.viewpoints.find((v) => v.snapshot);
    if (first?.snapshot) {
      const img = el('img', 'is-snap', { alt: 'Snapshot of the issue view', draggable: 'false' });
      img.src = rawSnapshot(first);
      out.push(img);
      if (first.annotations?.length) void markedSnapshot(t, first, img);
    }
    // status, priority
    const stSel = el('select', 'is-in', { 'aria-label': 'Status', 'data-field': 'status' });
    const statuses = [...new Set([...DEFAULT_STATUSES, ...bcf.project.extensions.topicStatuses, ...bcf.currentTopics.map((x) => x.topicStatus), t.topicStatus].filter(Boolean))];
    for (const s of statuses) stSel.appendChild(el('option', undefined, { value: s }, s));
    stSel.value = t.topicStatus;
    stSel.addEventListener('change', () => bcf.setTopicStatus(t.guid, stSel.value));
    const prSel = el('select', 'is-in', { 'aria-label': 'Priority', 'data-field': 'priority' });
    prSel.appendChild(el('option', undefined, { value: '' }, 'No priority'));
    for (const p of [...new Set([...DEFAULT_PRIORITIES, ...bcf.project.extensions.priorities, t.priority ?? ''].filter(Boolean))]) prSel.appendChild(el('option', undefined, { value: p }, p));
    prSel.value = t.priority ?? '';
    prSel.addEventListener('change', () => bcf.setTopicFields(t.guid, { priority: prSel.value }));
    const two = el('div', 'is-two');
    two.append(labelled('Status', stSel), labelled('Priority', prSel));
    out.push(two);
    const asg = input('is-in', { type: 'text', placeholder: 'Assigned to', 'aria-label': 'Assignee', 'data-field': 'assignee' }, t.assignedTo ?? '');
    asg.addEventListener('change', () => silently(() => bcf.setTopicFields(t.guid, { assignedTo: asg.value })));
    const due = input('is-in', { type: 'date', 'aria-label': 'Due date', 'data-field': 'due' }, (t.dueDate ?? '').slice(0, 10));
    due.addEventListener('change', () => silently(() => bcf.setTopicFields(t.guid, { dueDate: due.value })));
    const two2 = el('div', 'is-two');
    two2.append(labelled('Assignee', asg), labelled('Due', due));
    out.push(two2);
    const tags = el('div', 'is-tags');
    if (t.topicType) tags.appendChild(tag(t.topicType, 'lbl'));
    for (const l of t.labels) tags.appendChild(tag(l, 'lbl'));
    out.push(tags);
    if (t.description) out.push(el('div', undefined, undefined, t.description));

    // views = viewpoints
    out.push(el('div', 'is-h', undefined, `Views (${t.viewpoints.filter((v) => !v.derived).length})`));
    t.viewpoints.forEach((v, i) => {
      if (v.derived) {
        // A Plan or Section written beside the viewpoint of a view: a version of that view, so no drawings of its own.
        const d = el('div', 'is-vp', { 'data-viewpoint': v.guid, 'data-derived': v.derived.kind });
        d.appendChild(el('span', 'is-t', undefined, v.derived.kind === 'plan' ? 'Plan (derived)' : 'Section (derived)'));
        d.appendChild(act(button('Apply', () => { c.applyViewpoint(t, v); }, { title: 'Apply this derived view: an orthographic camera with its clip planes' }), 'apply'));
        const dc = act(button('Clear', () => { bcf.clearViewpoint(); }, { title: 'Undo what the viewpoint changed' }), 'clear');
        dc.disabled = bcf.applied?.viewpoint !== v.guid;
        d.appendChild(dc);
        out.push(d);
        return;
      }
      const s = c.viewpointSketch(v);
      const r = el('div', 'is-vp', { 'data-viewpoint': v.guid });
      const pic = s?.thumb ?? (v.snapshot ? rawSnapshot(v) : '');
      if (pic) r.appendChild(el('img', 'is-vthumb', { src: pic, alt: '', draggable: 'false' }));
      r.appendChild(el('span', 'is-t', undefined, s ? s.title : `View ${i + 1}`));
      const apply = act(button('Apply', () => { c.applyViewpoint(t, v); }, { title: 'Apply this view' }), 'apply');
      apply.disabled = !v.data && !s;
      r.appendChild(apply);
      const clr = act(button('Clear', () => { bcf.clearViewpoint(); }, { title: 'Undo what the view changed: the elements it hid, its colours and its clip planes' }), 'clear');
      clr.disabled = bcf.applied?.viewpoint !== v.guid;
      r.appendChild(clr);
      const canDraw = !!s || !!bcf.shapeView(v);
      const edit = act(button('Edit drawings', () => { c.editViewpoint(t, v); }, { primary: true, title: s ? 'Apply the view and draw on it' : 'Apply the view and draw on it: it joins the Views list' }), 'edit-drawing');
      edit.disabled = !canDraw;
      r.appendChild(edit);
      if (s) r.appendChild(act(button('Open in Views', () => { c.openView(s.id); }, { title: 'Show the view in the Views tab' }), 'open-sketch'));
      else if (v.annotations?.length) r.appendChild(el('span', 'is-meta', undefined, `${v.annotations.length} drawing${v.annotations.length === 1 ? '' : 's'} not editable`));
      r.appendChild(el('span', 'is-meta', { 'data-vp-count': '' }, s ? `${s.markups.length} drawing${s.markups.length === 1 ? '' : 's'}` : v.problem ?? ''));
      out.push(r);
      if (s && c.views.tied(s)) out.push(viewSwitchRow(s));
    });
    const addVp = act(button('Add current view', () => {
      void (async () => {
        try {
          const s = c.viewsHost ? await c.viewsHost.saveCurrent(`${t.title} (view ${t.viewpoints.length + 1})`) : mk.newSet(`${t.title} (view ${t.viewpoints.length + 1})`);
          await c.raise(s.id, { topic: t.guid });
        } catch (e) { fail(e); }
      })();
    }, { title: 'Save the current view and add it to this issue' }), 'add-sketch');
    addVp.disabled = !mk.loaded;
    const pin = act(button('Place pin', () => { window.__xrayBcf?.startPlacement('pin', t.guid); }, { title: 'Click the model to pin this issue' }), 'place-pin');
    const rmPin = t.pin ? act(button('Remove pin', () => bcf.setPin(t.guid, null), { title: 'Remove the pin of this issue' }), 'remove-pin') : null;
    out.push(row(addVp, pin, rmPin));

    // comments and history
    out.push(el('div', 'is-h', undefined, `Comments (${t.comments.length})`));
    for (const cm of t.comments) {
      const box = el('div', 'is-comment', { 'data-comment': cm.guid });
      box.appendChild(el('div', 'who', undefined, `${cm.author || 'unknown'} · ${when(cm.date)}`));
      box.appendChild(el('div', undefined, undefined, cm.text));
      out.push(box);
    }
    const ta = el('textarea', 'is-in', { rows: '2', placeholder: 'Add a comment', 'aria-label': 'Comment', 'data-bcf-comment': '', 'data-field': 'comment' });
    ta.addEventListener('keydown', (e) => e.stopPropagation());
    draft(`comment-${t.guid}`, ta);
    out.push(ta);
    out.push(row(act(button('Add comment', () => {
      if (!ta.value.trim()) return;
      bcf.addComment(t.guid, ta.value);
      drafts.delete(`comment-${t.guid}`);
    }, { title: 'Add the comment, as the author named below' }), 'comment')));
    out.push(el('div', 'is-h', undefined, 'History'));
    const hist = el('div', 'is-meta', { 'data-history': '' });
    const lines = [`Created by ${t.creationAuthor || 'unknown'}, ${when(t.creationDate)}`];
    for (const cm of t.comments) lines.push(`${cm.author || 'unknown'} commented, ${when(cm.date)}`);
    if (t.modifiedDate) lines.push(`Last changed by ${t.modifiedAuthor || 'unknown'}, ${when(t.modifiedDate)}`);
    for (const l of lines) hist.appendChild(el('div', undefined, undefined, l));
    out.push(hist);

    // export
    out.push(el('div', 'is-h', undefined, 'Export'));
    const del = act(button('Delete issue', () => undefined, { title: 'Remove this issue. Its views stay.' }), 'delete-issue');
    arm(del, 'Delete issue', () => c.deleteIssue(t.guid));
    out.push(row(
      act(button('Export BCF 2.1', () => void bcf.download('2.1'), { title: 'Download every issue as BCF 2.1' }), 'export-2.1'),
      act(button('Export BCF 3.0', () => void bcf.download('3.0'), { title: 'Download every issue as BCF 3.0' }), 'export-3.0'),
      del,
    ));
    return out;
  }

  /** `View: 3D · Plan · Section` for a view whose drawings are tied to a 3D construct. */
  function viewSwitchRow(set: MarkupSet): HTMLElement {
    const row = buildViewSwitch({ mode: () => c.views.mode(set), apply: (m) => { if (!c.views.apply(set.id, m)) mk.setStatus('This view needs the model its drawings are tied to'); } }, { labelled: true, helpKey: 'Issues panel/View switch' });
    row.setAttribute('data-view-switch-row', set.id);
    return row;
  }

  function labelled(label: string, control: HTMLElement): HTMLElement {
    const l = el('label', 'is-lbl');
    l.append(el('span', undefined, undefined, label), control);
    return l;
  }

  // ---------------------------------------------------------------- the drawings part of the Views tab

  /** `Open file` and "Other models (n)": what the Views list does not hold. */
  function viewsExtras(): HTMLElement[] {
    const out: HTMLElement[] = [];
    out.push(row(
      act(button('Open file', () => pickMarkupFile(mk), { title: 'Open a PDF or JSON file with views and drawings. You can also drop it on the page.' }), 'open-file'),
    ));
    const other = otherGroup(
      mk.otherModels().map((g) => ({ label: g.label, key: g.key, items: g.items })),
      (s) => {
        const line = el('div', 'is-other-set', { 'data-other-set': s.id });
        line.appendChild(el('div', 'is-t', undefined, `${s.title} (${s.markups.length} drawing${s.markups.length === 1 ? '' : 's'})`));
        const del = act(button('Delete view', () => undefined, { title: 'Remove this view from the session' }), 'other-delete');
        arm(del, 'Delete view', () => mk.deleteSet(s.id));
        line.appendChild(row(
          act(button('Open', () => { mk.openOther(s.id); }, { title: 'Show this view on this model. It may not fit: its targets are not here.' }), 'other-open'),
          act(button('Move to this model', () => { mk.moveToModel(s.id); }, { title: 'Make this view belong to the loaded model and attach its drawings again' }), 'other-move'),
          del,
        ));
        return line;
      },
    );
    if (other) out.push(other);
    return out;
  }

  // ---------------------------------------------------------------- view detail (a view that has a drawing layer)

  function viewDetail(set: MarkupSet): HTMLElement[] {
    const out: HTMLElement[] = [];
    const head = el('div', 'is-head');
    head.append(act(button('‹ Views', () => { c.detail = null; c.emit(); }, { title: 'Back to the list' }), 'back'));
    out.push(head);
    if (set.thumb) out.push(el('img', 'is-snap', { src: set.thumb, alt: 'Thumbnail of the view', draggable: 'false' }));
    const title = input('is-in', { type: 'text', 'aria-label': 'View title', 'data-keep': 'title', 'data-field': 'title' }, set.title);
    title.addEventListener('change', () => silently(() => { mk.renameSet(set.id, title.value); c.viewsHost?.renamed(set.id, set.title); }));
    out.push(title);
    if (c.views.tied(set)) out.push(viewSwitchRow(set)); // near the top: the sheet of a phone scrolls
    const note = input('is-in', { type: 'text', maxlength: '400', placeholder: 'One-line note', 'aria-label': 'View note', 'data-keep': 'note', 'data-field': 'note' }, set.note ?? '');
    note.addEventListener('input', () => mk.setNote(set.id, note.value, { quiet: true }));
    out.push(note);

    // The issue link, both ways.
    const ref = c.issueOf(set.id);
    if (ref) {
      const line = el('div', 'is-vp', { 'data-issue-link': ref.topic.guid });
      line.append(el('span', 'is-meta', undefined, 'In issue:'), el('span', 'is-t', undefined, ref.topic.title), tag(ref.topic.topicStatus, statusClass(ref.topic.topicStatus)));
      line.appendChild(act(button('Open issue', () => { c.openIssue(ref.topic.guid, { apply: false }); }, { title: 'Open the issue this view is in' }), 'open-issue'));
      out.push(line);
    } else {
      const sel = el('select', 'is-in', { 'aria-label': 'Make issue', 'data-field': 'raise-target' });
      sel.appendChild(el('option', undefined, { value: '' }, 'New issue'));
      for (const t of bcf.currentTopics) sel.appendChild(el('option', undefined, { value: t.guid }, `Add to: ${t.title}`));
      sel.value = bcf.currentTopics.some((t) => t.guid === raiseTarget) ? raiseTarget : '';
      sel.addEventListener('change', () => { raiseTarget = sel.value; });
      const raise = act(button('Make issue', () => { void c.raise(set.id, raiseTarget ? { topic: raiseTarget } : {}).catch(fail); }, { primary: true, title: 'Make an issue of this view, or add it to an existing issue. The issue points at the view: it is not a copy.' }), 'raise');
      raise.disabled = !mk.loaded || !c.bcf;
      out.push(row(sel, raise));
    }

    // Edit, restore, update, export.
    const fileBtn = (label: string, fn: () => Promise<unknown> | unknown, o: { title: string; primary?: boolean }, name: string): HTMLButtonElement => {
      const b = act(button(label, () => {
        b.disabled = true;
        Promise.resolve().then(fn).catch(fail).finally(() => { b.disabled = false; });
      }, o), name);
      return b;
    };
    out.push(row(
      act(button(mk.editing && mk.activeId === set.id ? 'Editing…' : set.markups.length ? 'Edit drawings' : 'Draw on this view', () => { c.editSketch(set.id); }, { primary: true, title: 'Show the drawing toolbar and draw on this view' }), 'edit-drawing'),
      act(button('Restore view', () => { void mk.select(set.id, { restore: true }); }, { title: 'Bring back the camera, section, hidden elements and look of this view' }), 'restore'),
      act(button('Update view', () => { try { mk.updateView(set.id); c.viewsHost?.updated(set.id); } catch (e) { fail(e); } }, { title: 'Capture this view again from the current camera. You can undo it.' }), 'update-view'),
    ));
    const pageSel = select<PageSize>('Page size', ['A4', 'Letter'], () => mk.page, (v) => { mk.page = v; page = v; });
    pageSel.update();
    const resLabel = (r: PdfResolution): string => (r === 'screen' ? 'screen' : `${r} dpi`);
    const resSel = select<string>('Picture quality', PDF_RESOLUTIONS.map(resLabel), () => resLabel(mk.pdfResolution), (v) => { mk.pdfResolution = PDF_RESOLUTIONS.find((r) => resLabel(r) === v) ?? 200; });
    resSel.update();
    void page;
    out.push(row(
      fileBtn('Export PDF', () => mk.downloadPdf({ ids: [set.id] }), { title: 'A PDF with the clean view, the marked view and the table of drawings. The JSON is attached.' }, 'export-pdf'),
      fileBtn('Export JSON', () => mk.downloadJson([set.id]), { title: 'The view and its drawings as a JSON file. Drop it on the viewer to restore them.' }, 'export-json'),
    ));
    out.push(row(pageSel.root, resSel.root));

    // Removing.
    if (c.confirmRemove === set.id && ref) {
      const box = el('div', 'is-confirm', { 'data-confirm-remove': set.id, role: 'alertdialog' });
      box.appendChild(el('div', undefined, undefined, `"${set.title}" is a view of the issue "${ref.topic.title}". Delete it? The issue keeps the camera view and loses these drawings.`));
      box.appendChild(row(act(button('Delete view', () => { c.removeSketch(set.id, true); }, { title: 'Delete the view and cut the link' }), 'remove-confirm'), act(button('Keep it', () => c.cancelRemove()), 'remove-cancel')));
      out.push(box);
    } else {
      const del = act(button('Delete view', () => undefined, { title: ref ? 'Delete this view. It is in an issue, so you are asked first.' : 'Delete this view and its drawings' }), 'delete');
      if (ref) del.addEventListener('click', () => { c.removeSketch(set.id); });
      else arm(del, 'Delete view', () => { c.removeSketch(set.id, true); });
      out.push(row(del));
    }

    // Legacy review data: read-only.
    if (hasLegacyReview(set)) {
      const box = el('div', 'is-legacy', { 'data-legacy': set.id });
      box.appendChild(el('div', undefined, undefined, 'Earlier comments and status (read-only). Make an issue of the view to move them.'));
      for (const m of set.markups) {
        if (!m.comments.length && m.status === 'open' && !m.assignee && !m.due) continue;
        const bits = [m.status === 'resolved' ? 'resolved' : '', m.assignee ? `assigned to ${m.assignee}` : '', m.due ? `due ${m.due}` : ''].filter(Boolean).join(', ');
        box.appendChild(el('div', undefined, undefined, `${m.number}. ${KIND_LABEL[m.kind]}${bits ? `: ${bits}` : ''}`));
        for (const cm of m.comments) box.appendChild(el('div', 'is-comment', { 'data-legacy-comment': cm.id }, `${cm.author}, ${when(cm.date)}: ${cm.text}`));
      }
      out.push(box);
    }

    // Link a measurement, then the drawings.
    const meas = mk.measurements();
    if (meas.length) {
      const sel = el('select', 'is-in', { 'aria-label': 'Link a measurement', 'data-field': 'measurement' });
      sel.appendChild(el('option', undefined, { value: '' }, 'Link a measurement...'));
      for (const m of meas) sel.appendChild(el('option', undefined, { value: String(m.id) }, `Measurement ${m.id}: ${m.distance.toFixed(3)} m`));
      sel.addEventListener('change', () => { if (sel.value) mk.linkMeasurement(Number(sel.value), mk.text); });
      out.push(sel);
    }
    out.push(el('div', 'is-h', undefined, `Drawings (${set.markups.length})`));
    if (!set.markups.length) out.push(el('div', 'is-empty', undefined, 'Press Draw on this view, pick a tool and draw.'));
    else {
      const list = el('div', 'is-list');
      for (const m of set.markups) list.appendChild(drawingItem(set, m));
      out.push(list);
    }
    return out;
  }

  function drawingItem(set: MarkupSet, m: Markup): HTMLElement {
    const sel = mk.selected === m.id;
    const item = el('div', `is-mk${sel ? ' sel' : ''}`, { 'data-mk-item': m.id });
    const h = el('div', 'is-mk-h');
    const num = el('span', 'is-num', undefined, String(m.number));
    num.style.background = COLOURS[m.colour];
    if (m.colour === 'yellow') num.style.color = '#111';
    h.append(num, el('span', 'is-meta', undefined, KIND_LABEL[m.kind]));
    const x = el('button', 'is-x', { type: 'button', 'aria-label': `Delete drawing ${m.number}`, title: 'Delete', 'data-act': 'delete-drawing' }, '×');
    x.addEventListener('click', (e) => { e.stopPropagation(); mk.remove(m.id); });
    h.appendChild(x);
    item.appendChild(h);
    if (mk.detached(m, set)) item.appendChild(el('div', 'is-meta', { 'data-detached': '1' }, 'Detached: an element it was attached to is missing or changed in this model. Shown view-locked.'));
    const text = input('is-in', { type: 'text', placeholder: 'Text', 'aria-label': `Text of drawing ${m.number}`, 'data-keep': `t-${m.id}`, 'data-field': 'text' }, m.text);
    text.addEventListener('click', (e) => e.stopPropagation());
    let recorded = false;
    text.addEventListener('focus', () => { recorded = false; });
    text.addEventListener('input', () => {
      if (!recorded) { mk.record(set); recorded = true; }
      mk.patch(m.id, { text: text.value }, { quiet: true });
    });
    item.appendChild(text);
    if (sel) {
      const d = el('div', 'is-mk-h');
      d.addEventListener('click', (e) => e.stopPropagation());
      d.appendChild(buildAttachChip(mk, m, 'panel'));
      item.appendChild(d);
    }
    item.addEventListener('click', () => mk.selectMarkup(sel ? null : m.id));
    return item;
  }

  /** "Clear all drawings and issues for this model": two clicks, the second names what goes. */
  const CLEAR_ARM_MS = 8000;
  let clearArmedAt = 0; // kept here, not on the button: the panel is drawn again on every change
  function clearAll(): HTMLElement | null {
    if (!c.work) return null;
    const n = c.work.counts();
    if (!n.sketches && !n.issues) return null;
    const label = 'Clear all drawings and issues for this model';
    const armed = Date.now() - clearArmedAt < CLEAR_ARM_MS;
    const b = act(button(armed ? `Click again to delete ${n.sketches} view${n.sketches === 1 ? '' : 's'} with drawings and ${n.issues} issue${n.issues === 1 ? '' : 's'}` : label, () => undefined, { title: 'Delete the drawings of the 3D views and the issues of this model, here and in the copy this browser keeps. The saved views and the sheet drawings stay.' }), 'clear-all');
    b.setAttribute('data-help-key', 'Issues panel/Clear everything');
    b.addEventListener('click', () => {
      if (Date.now() - clearArmedAt < CLEAR_ARM_MS) {
        clearArmedAt = 0;
        void c.work?.clear().then(() => c.emit());
      } else {
        clearArmedAt = Date.now();
        c.emit();
        setTimeout(() => c.emit(), CLEAR_ARM_MS + 100);
      }
    });
    return row(b);
  }

  // ---------------------------------------------------------------- render

  const statusText = (): string => (mode === 'issues' ? bcf.status : c.viewFilter === 'sheets' && c.sheetsPane ? c.sheetsPane.status() : mk.status);
  const render = (): void => {
    const focus = document.activeElement as HTMLElement | null;
    const keep = focus && root.contains(focus) ? focus.getAttribute('data-keep') : null;
    const pos = focus && root.contains(focus) && 'selectionStart' in focus ? (focus as HTMLInputElement).selectionStart : null;
    const top = root.scrollTop;
    root.textContent = '';
    const kids: HTMLElement[] = [];
    const d = c.detail;
    if (mode === 'issues') {
      const topic = d?.kind === 'issue' ? bcf.topic(d.id) : undefined;
      kids.push(...(topic ? issueDetail(topic) : issuesList()));
    } else {
      const b = banner();
      if (b) kids.push(b);
      const view = d?.kind === 'view' ? mk.get(d.id) : undefined;
      if (view) kids.push(...viewDetail(view));
      else if (c.viewFilter === 'sheets' && c.sheetsPane) kids.push(...c.sheetsPane.render());
      else kids.push(...viewsExtras());
    }
    for (const k of kids) root.appendChild(k);
    const clear = clearAll();
    if (clear) root.appendChild(clear);
    root.appendChild(el('div', 'is-status', { role: 'status', 'data-issues-status': '' }, statusText()));
    const au = input('is-in', { type: 'text', placeholder: 'Your name (author of drawings and comments)', 'aria-label': 'Author', 'data-keep': 'author' }, mk.author);
    au.addEventListener('change', () => silently(() => mk.setAuthor(au.value)));
    root.appendChild(au);
    root.scrollTop = top;
    if (keep) {
      const f = root.querySelector<HTMLInputElement>(`[data-keep="${keep}"]`);
      if (f) {
        f.focus();
        if (pos !== null && 'setSelectionRange' in f) { try { f.setSelectionRange(pos, pos); } catch { /* not a text field */ } }
      }
    }
  };

  const off = c.onChange(() => {
    if (hold) {
      const st = root.querySelector('[data-issues-status]');
      if (st) st.textContent = statusText();
      return;
    }
    // While a text box of the panel has the keyboard, redraw only when the list changed under it (typing must not lose focus).
    const f = document.activeElement;
    if (f instanceof HTMLElement && root.contains(f) && f.matches('input[data-keep]:not([data-keep=query]), textarea') && c.detail) {
      const st = root.querySelector('[data-issues-status]');
      if (st) st.textContent = statusText();
      return;
    }
    render();
  });
  // Drop a BCF, PDF or JSON file on the panel (the page-level drop does the work).
  const dragOn = (e: DragEvent): void => { if (e.dataTransfer?.types.includes('Files')) root.classList.add('is-drop'); };
  const dragOff = (): void => root.classList.remove('is-drop');
  root.addEventListener('dragover', dragOn);
  root.addEventListener('dragleave', dragOff);
  root.addEventListener('drop', dragOff);
  render();
  return {
    root,
    render,
    dispose: () => {
      off();
      for (const u of urls.values()) URL.revokeObjectURL(u.url);
      urls.clear();
      root.remove();
    },
  };
}
