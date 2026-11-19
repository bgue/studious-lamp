// The "Raise issues from results" block of the penetrations and clearance drawers: the counts (new / already raised / not found in
// the latest run), the button, the question above the batch limit, progress with Stop, and "Close n not found". DOM only; the work
// is in clashRaise.ts. Docs: docs-features/issues.md.

import { button, note, row, section, statusLine } from '../tools/ui';
import { el } from '../ui/dom';
import type { IssuesController } from './controller';
import { CLASH_LABEL, MAX_BATCH, countsOf, countsText } from './clash';
import type { ClashCheck } from './clash';
import { clashSource, closeNotFound, previewClashes, raiseClashes } from './clashRaise';
import type { ClashReport } from './clashRaise';

/** The batch limit: raising more new results than this asks first. A variable so that a smoke test can lower it. */
export const clashConfig = { maxBatch: MAX_BATCH };

export const issuesController = (): IssuesController | null => (window as unknown as { __xrayIssues?: { controller: IssuesController } }).__xrayIssues?.controller ?? null;

export function describeReport(r: ClashReport): string {
  const bits = [`${r.raised.length} raised`, `${r.counts.already} already raised`];
  if (r.skipped) bits.push(`${r.skipped} left out (top ${r.raised.length + r.failed.length} by severity)`);
  if (r.flagged) bits.push(`${r.flagged} marked "Not found in latest run"`);
  if (r.backAgain) bits.push(`${r.backAgain} found again`);
  if (r.failed.length) bits.push(`${r.failed.length} failed`);
  if (r.cancelled) bits.push('stopped');
  return bits.join(', ');
}

export interface ClashSection {
  root: HTMLElement;
  update(): void;
}

export function buildClashSection(check: ClashCheck): ClashSection {
  const root = el('div', 'xt-clash', { 'data-clash-section': check, 'data-help-key': 'Issues panel/Raise issues from results' });
  const counts = el('div', 'xt-note', { 'data-clash-counts': '' });
  const progress = statusLine('');
  progress.setAttribute('data-clash-progress', '');
  const ask = el('div', 'xt-clash-ask', { 'data-clash-ask': '' });
  const raiseBtn = button('Raise issues from results', () => void start(), { primary: true, title: `Make an issue of each ${CLASH_LABEL[check]} result: both elements, the view on the pair and a sketch tied to it. Results already raised are skipped.` });
  raiseBtn.setAttribute('data-act', 'clash-raise');
  const closeBtn = button('Close 0 not found', () => {
    const c = issuesController();
    const src = clashSource(check);
    if (c && src) progress.set(`${closeNotFound(c, src)} issues closed`);
    update();
  }, { title: 'Set the status of the issues the latest run no longer reports to Closed' });
  closeBtn.setAttribute('data-act', 'clash-close');
  const stopBtn = button('Stop', () => { signal.cancelled = true; }, { title: 'Stop after the issue in hand' });
  stopBtn.setAttribute('data-act', 'clash-stop');
  let signal = { cancelled: false };
  let busy = false;
  root.append(section('Issues'), counts, row(raiseBtn, closeBtn, stopBtn), ask, progress);

  async function run(limit: number | undefined): Promise<void> {
    const c = issuesController();
    const src = clashSource(check);
    if (!c || !src || busy) return;
    busy = true;
    signal = { cancelled: false };
    ask.textContent = '';
    update();
    try {
      const rep = await raiseClashes(c, src, { ...(limit !== undefined ? { limit } : {}), signal, onProgress: (d, t) => progress.set(`Raising issues ${d} / ${t}`) });
      progress.set(describeReport(rep));
    } catch (e) {
      progress.set(e instanceof Error ? e.message : String(e));
    } finally {
      busy = false;
      update();
    }
  }

  function start(): void {
    const c = issuesController();
    const src = clashSource(check);
    if (!c || !src) return;
    const plan = previewClashes(c, src);
    if (!plan) { progress.set('Run the check first'); return; }
    const n = plan.fresh.length;
    if (n > clashConfig.maxBatch) {
      ask.textContent = '';
      const box = el('div', 'xt-confirm', { role: 'alertdialog' });
      box.appendChild(el('div', undefined, undefined, `${n} new results. That many issues take a while to make and fill the list. Raise only the ${clashConfig.maxBatch} worst, or all of them?`));
      const top = button(`Raise top ${clashConfig.maxBatch} by severity`, () => void run(clashConfig.maxBatch), { primary: true });
      top.setAttribute('data-act', 'clash-raise-top');
      const all = button(`Raise all ${n}`, () => void run(undefined));
      all.setAttribute('data-act', 'clash-raise-all');
      const cancel = button('Cancel', () => { ask.textContent = ''; });
      cancel.setAttribute('data-act', 'clash-ask-cancel');
      box.appendChild(row(top, all, cancel));
      ask.appendChild(box);
      return;
    }
    void run(undefined);
  }

  function update(): void {
    const c = issuesController();
    const src = clashSource(check);
    const plan = c && src ? previewClashes(c, src) : null;
    const why = !c ? 'The Issues panel is not available in this build' : src?.disabledReason() ?? (!plan ? 'Run the check first' : null);
    raiseBtn.setDisabled(busy ? 'Raising issues' : why ?? false);
    const k = plan ? countsOf(plan) : null;
    counts.textContent = k ? countsText(k) : (why ?? '');
    const n = plan?.toClose.length ?? 0;
    closeBtn.textContent = `Close ${n} not found`;
    closeBtn.setDisabled(busy ? 'Raising issues' : n === 0 ? 'Nothing to close: every raised issue is still found, or already closed' : false);
    stopBtn.style.display = busy ? '' : 'none';
    if (!busy && ask.firstChild && plan && plan.fresh.length <= clashConfig.maxBatch) ask.textContent = '';
  }
  update();
  // Follow the issues (a raise from a script, a delete, a status change): until the drawer is rebuilt and this block leaves the page.
  let seen = false;
  const off = issuesController()?.onChange(() => {
    if (busy) return;
    if (root.isConnected) { seen = true; update(); } else if (seen) off?.();
  });
  root.appendChild(note('One issue per result, found again by check and element pair: raising after a re-run adds only the new ones. Results a re-run no longer reports get a note and can be closed here.'));
  return { root, update };
}
