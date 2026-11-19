// Revision plugin: snapshot triggers, the detection banner, "Compare with…", the session lifecycle and window.__xrayRevision for scripts
// and the smoke tests. The panel is plugins/revisionWalk.ts, mounted through the PanelHost (src/ui/panelHost.ts); the logic is
// src/revision/controller.ts over the pure modules of src/revision. Nothing here is a setting: no params section, no preset, no link.
// Docs: docs-features/revision.md.
//
//   window.__xrayRevision = { candidates(), snapshots(), start(baseKey), resume(), state(), decide(key, verdict), bulk(ruleId), report(),
//                             walk, items(), status(), commit(), snapshotNow(), compare() }

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { RevisionController } from '../revision/controller';
import type { Banner } from '../revision/controller';
import type { RevisionStatus } from '../revision/status';
import type { RevisionCandidate } from '../revision/snapshot';
import type { RevisionSession } from '../revision/types';
import { showToast } from '../ui/keymapView';
import { el } from '../ui/dom';
import { floatingPanelHost } from '../ui/panelHost';
import type { PanelHost } from '../ui/panelHost';
import { classifyService } from './classify';
import { ensureRevisionWalkStyle, RevisionWalkPanel } from './revisionWalk';
import type { RevisionWalkState } from './revisionWalk';

declare global {
  interface Window {
    __xrayRevision?: RevisionApi;
  }
}

export interface RevisionApi {
  candidates(): Promise<RevisionCandidate[]>;
  snapshots(): Promise<Array<{ key: string; name: string; savedAt: string; elements: number; reviewed: number }>>;
  /** "Review changes": compare with the stored snapshot, carry the unchanged decisions over, open the walk. */
  start(baseKey: string): Promise<RevisionSession | null>;
  resume(): Promise<boolean>;
  state(): {
    busy: string;
    banner: { kind: string; message: string } | null;
    persistent: boolean;
    walking: boolean;
    session: { key: string; status: string; base: string; head: string; counts: RevisionSession['diff']['counts']; carried: RevisionSession['carried']; progress: ReturnType<NonNullable<RevisionController['state']>['progress']> } | null;
    walk: RevisionWalkState;
  };
  decide(key: string, verdict: 'accepted' | 'rejected'): boolean;
  bulk(ruleId: string): number;
  report(): { csv: string; summary: string; names: { csv: string; summary: string } } | null;
  items(): Array<{ key: string; title: string; category: string; elements: number }>;
  commit(note?: string): Promise<{ commitId: string | null; changes: number; carried: number; attachments: number }>;
  /** The `extra.revision` of the IFC save plan: the revision status of every element of the model on screen (null without a session). */
  status(): Promise<Map<string, RevisionStatus> | null>;
  snapshotNow(force?: boolean): Promise<boolean>;
  walk: { open(): void; close(): void; state(): RevisionWalkState; goto(i: number): void };
  controller: RevisionController;
}

let ctl: RevisionController | null = null;
let panel: RevisionWalkPanel | null = null;
export const revisionController = (): RevisionController | null => ctl;

export const revisionPlugin: AppPlugin = {
  name: 'revision',
  install(app: ViewerApp) {
    const svc = classifyService();
    if (!svc) return;
    const c = new RevisionController(app, svc);
    ctl = c;
    // Where the panel sits is decided here and only here. To use the right-hand sidebar instead, see the adapter in src/ui/panelHost.ts.
    const host: PanelHost = floatingPanelHost(app);
    const walk = new RevisionWalkPanel(app, c, host);
    panel = walk;
    c.onWalkReady = () => walk.open();
    c.onWalkClose = () => walk.dispose();

    const banner = new BannerView(app, c);
    c.onChange(() => banner.render());

    const flush = (): void => { void c.saver?.flush(); };
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
    window.addEventListener('pagehide', flush);

    const api: RevisionApi = {
      candidates: async () => { await c.ready; const id = c.identity(); if (!id) return []; const els = app.controller.model.elements; const { guidSketch, classHistogramOf } = await import('../revision/snapshot'); return c.store!.candidates({ identity: id, guidSketch: guidSketch(els.map((e) => e.globalId)), classHistogram: classHistogramOf(els.map((e) => e.ifcClass)) }); },
      snapshots: () => c.snapshots(),
      start: (key) => c.start(key),
      resume: () => c.resume(),
      state: () => ({
        busy: c.busy,
        banner: c.banner ? { kind: c.banner.kind, message: c.banner.message } : null,
        persistent: c.persistent,
        walking: c.walking,
        session: c.state ? { key: c.state.session.key, status: c.state.session.status, base: c.state.session.baseName, head: c.state.session.head.name, counts: c.state.session.diff.counts, carried: c.state.session.carried, progress: c.state.progress() } : null,
        walk: walk.state(),
      }),
      decide: (key, verdict) => { const e = c.entry(key); if (!e) return false; c.decide([e], { verdict }); return true; },
      bulk: (id) => { const rule = c.bulkRules().find((r) => r.id === id); return rule ? c.applyBulk(rule) : 0; },
      report: () => c.report(),
      items: () => walk.list(),
      commit: (note) => c.commit(note),
      status: () => c.storedStatus(),
      snapshotNow: (force) => c.snapshotNow(force),
      walk: { open: () => walk.open(), close: () => walk.close(), state: () => walk.state(), goto: (i) => walk.goto(i) },
      controller: c,
    };
    window.__xrayRevision = api;

    registerAction({
      id: 'revision.walk', label: 'Revision: review changes (walk)', group: 'Tools', keys: ['Shift+v'],
      description: 'Open the revision walk: confirm what changed between an earlier model and this one.',
      enabled: () => !!app.loaded,
      run: () => {
        if (c.walking) { walk.open(); return; }
        void c.findResumable().then((s) => {
          if (s) void c.resume(s);
          else if (c.banner?.kind === 'candidate') void c.start(c.banner.candidate.key);
          else banner.compare();
        });
      },
    });
    registerAction({
      id: 'revision.compare', label: 'Revision: compare with an earlier model…', group: 'Tools', keys: [],
      description: 'Pick a stored earlier model, or an IFC file, to compare with this one.',
      enabled: () => !!app.loaded, run: () => banner.compare(),
    });
    registerAction({
      id: 'revision.report', label: 'Revision: export the report', group: 'Tools', keys: [],
      description: 'Save the revision report (a CSV and a summary) for the open walk.',
      enabled: () => c.walking,
      run: () => { const r = c.report(); if (r) { import('../tools/csv').then(({ downloadText }) => { downloadText(r.names.csv, r.csv); setTimeout(() => downloadText(r.names.summary, r.summary, 'text/markdown;charset=utf-8'), 300); }).catch(() => undefined); } else showToast('Open a revision walk first', 1400); },
    });
  },
  onModel() {
    void ctl?.onModel();
  },
};

// ---------------------------------------------------------------- the banner

class BannerView {
  private readonly root: HTMLElement;
  private comparing = false;
  private options: Array<{ key: string; label: string }> = [];
  private chosen = '';
  private file: HTMLInputElement | null = null;

  constructor(private readonly app: ViewerApp, private readonly ctl: RevisionController) {
    ensureBannerStyle();
    this.root = el('div', 'xrr-banner', { role: 'status', 'data-testid': 'revision-banner' });
    this.root.hidden = true;
    (app.canvas.parentElement ?? document.body).appendChild(this.root);
  }

  compare(): void {
    void this.ctl.snapshots().then((list) => {
      this.options = list.map((s) => ({ key: s.key, label: `${s.name} (saved ${s.savedAt.slice(0, 10)}, ${s.reviewed} reviewed)` }));
      this.chosen = this.options[0]?.key ?? '';
      this.comparing = true;
      this.render();
    });
  }

  private btn(label: string, act: string, fn: () => void, primary = false): HTMLButtonElement {
    const b = el('button', `xrw-btn${primary ? ' primary' : ''}`, { type: 'button', 'data-act': act, 'data-help': `Revision banner/${label.replace(/…$/, '')}` }, label);
    b.addEventListener('click', fn);
    return b;
  }

  render(): void {
    const c = this.ctl;
    const b: Banner | null = c.banner;
    this.root.replaceChildren();
    this.root.classList.toggle('err', b?.kind === 'notice' && b.error === true);
    if (c.busy) {
      this.root.append(el('div', 'xrr-msg', { 'data-role': 'busy' }, `${c.busy}...`));
      this.root.hidden = false;
      return;
    }
    if (this.comparing) {
      const sel = el('select', undefined, { 'aria-label': 'Earlier model', 'data-role': 'compare-select' });
      if (this.options.length === 0) sel.appendChild(el('option', undefined, { value: '' }, 'No earlier model is stored yet'));
      for (const o of this.options) sel.appendChild(el('option', undefined, { value: o.key }, o.label));
      sel.value = this.chosen;
      sel.addEventListener('change', () => { this.chosen = sel.value; });
      this.file ??= (() => {
        const f = el('input', undefined, { type: 'file', accept: '.ifc,.ifczip', hidden: '', 'data-role': 'compare-file' });
        f.addEventListener('change', () => { const file = f.files?.[0]; f.value = ''; if (file) { this.comparing = false; void this.ctl.startFromFile(file); } });
        this.root.ownerDocument.body.appendChild(f);
        return f;
      })();
      this.root.append(
        el('div', 'xrr-msg', undefined, 'Compare this model with'), sel,
        this.btn('Review changes', 'compare-go', () => { if (this.chosen) { this.comparing = false; void this.ctl.start(this.chosen); } }, true),
        this.btn('Compare with an IFC file…', 'compare-file', () => this.file?.click()),
        this.btn('Cancel', 'compare-cancel', () => { this.comparing = false; this.render(); }),
      );
      this.root.hidden = false;
      return;
    }
    if (!b) { this.root.hidden = true; return; }
    this.root.append(el('div', 'xrr-msg', { 'data-role': 'banner-text' }, b.message));
    if (b.kind === 'candidate') {
      this.root.append(
        this.btn('Review changes', 'review-changes', () => void c.start(b.candidate.key), true),
        this.btn('Not a revision', 'not-revision', () => c.dismissBanner()),
        this.btn('Compare with…', 'compare', () => this.compare()),
      );
    } else if (b.kind === 'resume') {
      this.root.append(this.btn('Resume', 'resume', () => void c.resume(b.session), true), this.btn('Dismiss', 'dismiss', () => c.dismissBanner()));
    } else {
      this.root.append(this.btn('OK', 'dismiss', () => c.dismissBanner()));
    }
    this.root.hidden = false;
  }
}

function ensureBannerStyle(): void {
  ensureRevisionWalkStyle();
}
