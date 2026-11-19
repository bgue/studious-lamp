// Keeps the 3D sketches and the issues of each model across reloads. The session objects stay the truth: this watches the markup
// and BCF controllers, writes what changed to the work store (debounced), and on a model load puts the saved sketches and issues
// of that model back. Records are per model, keyed by identityKey (markup/scope.ts), so a sketch made on one model never shows on
// another. Sheet sketches are not handled here: the sheets store keeps those. Nothing leaves IndexedDB. See docs-features/issues.md.

import type { ViewerApp } from '../app';
import type { BcfController } from '../bcf/controller';
import type { BcfDocument, BcfTopic } from '../bcf/model';
import type { MarkupController } from '../markup/controller';
import { isSheetSet, sanitizeSet } from '../markup/model';
import type { MarkupSet, ModelIdentity } from '../markup/model';
import { identityKey, loadedIdentity, scopeOf } from '../markup/scope';
import { WorkStore } from './store';
import type { WorkDocument, WorkRecord } from './store';

export const SAVE_DELAY_MS = 800;

/** A topic without its session-only parts, safe to hand to the store. */
export function portableTopic(t: BcfTopic): BcfTopic {
  return { ...t, viewpoints: t.viewpoints.map((v) => { const { captureSeeThrough: _c, ...rest } = v; return rest; }) };
}

/** What one model's record holds, from the session. */
export interface Group {
  model: ModelIdentity | null;
  sets: MarkupSet[];
  topics: BcfTopic[];
}

/**
 * The sets and topics of the session, grouped per model. An item that names no model belongs to the model that was loaded when it was
 * first seen (remembered in `home`, so that it stays with that model when another one is loaded); without either it is not kept.
 */
export function groupByModel(sets: readonly MarkupSet[], topics: readonly BcfTopic[], now: ModelIdentity | null, home: WeakMap<object, ModelIdentity> = new WeakMap()): Map<string, Group> {
  const out = new Map<string, Group>();
  const at = (item: object, owner: ModelIdentity | null | undefined): Group | null => {
    let id = owner ?? home.get(item) ?? null;
    if (!id && now) {
      id = { ...now };
      home.set(item, id);
    }
    if (!id) return null;
    const k = identityKey(id);
    let g = out.get(k);
    if (!g) {
      g = { model: { ...id }, sets: [], topics: [] };
      out.set(k, g);
    }
    return g;
  };
  for (const s of sets) {
    if (isSheetSet(s) || s.readonly) continue;
    at(s, s.model)?.sets.push(s);
  }
  for (const t of topics) at(t, t.model)?.topics.push(t);
  return out;
}

/** The documents a group's topics refer to, as metadata only (no bytes). */
export function documentsOf(topics: readonly BcfTopic[], docs: readonly BcfDocument[]): WorkDocument[] {
  const want = new Set(topics.flatMap((t) => t.documentReferences.map((r) => r.target)));
  return docs.filter((d) => want.has(d.guid) && !!d.sha256).map((d) => ({ guid: d.guid, filename: d.filename, sha256: d.sha256!, ...(d.description ? { description: d.description } : {}) }));
}

export function recordOf(key: string, g: Group, docs: readonly BcfDocument[], saved = new Date().toISOString()): WorkRecord {
  return { schema: 'xray-work/1', key, model: g.model, saved, sets: g.sets.map((s) => JSON.parse(JSON.stringify(s)) as MarkupSet), topics: g.topics.map(portableTopic), documents: documentsOf(g.topics, docs) };
}

/** A cheap signature of a record's content (snapshots count by length) to skip writes that change nothing. */
export function signature(rec: Pick<WorkRecord, 'sets' | 'topics' | 'documents'>): string {
  return JSON.stringify([rec.sets, rec.topics, rec.documents], (_k, v) => (v instanceof Uint8Array ? `bytes:${v.length}` : v instanceof Set ? undefined : v));
}

export class WorkPersistence {
  readonly store: WorkStore;
  /** src/plugins sets these two: when the sheets store is read, and the bytes of a PDF by its SHA-256 (for the documents of issues). */
  sheetsReady: (() => Promise<void>) | null = null;
  bytesOfPdf: ((sha256: string) => Promise<Uint8Array | null>) | null = null;
  status = '';
  private readonly known = new Set<string>();
  private readonly lastSig = new Map<string, string>();
  private readonly home = new WeakMap<object, ModelIdentity>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private restoring: Promise<void> | null = null;
  private chain: Promise<void> = Promise.resolve();
  private enabled = false;

  constructor(readonly app: ViewerApp, readonly markup: MarkupController, readonly bcf: BcfController, store: WorkStore = new WorkStore()) {
    this.store = store;
    markup.onChange(() => this.schedule());
    bcf.onChange(() => this.schedule());
    if (typeof window !== 'undefined') {
      window.addEventListener('pagehide', () => { void this.save(); });
      document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') void this.save(); });
    }
  }

  get persistent(): boolean {
    return this.store.persistent;
  }

  private now(): ModelIdentity | null {
    return loadedIdentity(this.app as never);
  }

  // ---------------------------------------------------------------- saving

  /** Save soon: changes arrive in bursts (typing, dragging), so one write follows a quiet moment. */
  schedule(): void {
    if (!this.enabled || this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.save();
    }, SAVE_DELAY_MS);
  }

  /** Write what changed now (and wait for it). Does nothing until the saved items of the loaded model were read back. */
  save(): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.chain = this.chain.then(() => this.write()).catch(() => undefined);
    return this.chain;
  }

  private async write(): Promise<void> {
    if (!this.enabled) return;
    const groups = groupByModel(this.markup.sets, this.bcf.topics, this.now(), this.home);
    for (const [key, g] of groups) {
      if (this.known.has(key)) continue;
      // A model not seen in this session yet (items imported from another model): keep what was saved before.
      this.known.add(key);
      const old = await this.store.get(key);
      if (!old) continue;
      const sets = new Set(g.sets.map((s) => s.id));
      const topics = new Set(g.topics.map((t) => t.guid));
      for (const raw of old.sets) if (!sets.has(raw.id)) g.sets.push(raw);
      for (const t of old.topics) if (!topics.has(t.guid)) g.topics.push(t);
    }
    for (const key of this.known) {
      const g = groups.get(key);
      if (!g || (!g.sets.length && !g.topics.length)) {
        if (this.lastSig.get(key) !== '') {
          await this.store.delete(key);
          this.lastSig.set(key, '');
        }
        continue;
      }
      const rec = recordOf(key, g, this.bcf.project.documents);
      const sig = signature(rec);
      if (this.lastSig.get(key) === sig) continue;
      await this.store.put(rec);
      this.lastSig.set(key, sig);
    }
  }

  // ---------------------------------------------------------------- restoring

  /** After a model load: put the saved sketches and issues of this model back. Saving starts when this is done. */
  onModel(): Promise<void> {
    const id = this.now();
    if (!id) return Promise.resolve();
    const loaded = this.app.loaded;
    const run = async (): Promise<void> => {
      await this.sheetsReady?.().catch(() => undefined);
      const key = identityKey(id);
      const rec = await this.store.get(key);
      if (this.app.loaded !== loaded) return; // another model arrived while reading
      this.known.add(key);
      if (rec) await this.apply(rec);
      if (this.app.loaded !== loaded) return;
      this.lastSig.set(key, rec ? '\u0000unsynced' : '');
      this.enabled = true;
    };
    const p = (this.restoring ?? Promise.resolve()).then(run).catch(() => { this.enabled = true; });
    this.restoring = p;
    return p;
  }

  whenRestored(): Promise<void> {
    return this.restoring ?? Promise.resolve();
  }

  private async apply(rec: WorkRecord): Promise<void> {
    let sketches = 0;
    for (const raw of rec.sets) {
      const r = sanitizeSet(raw);
      if (typeof r === 'string' || isSheetSet(r.set)) continue;
      if (this.markup.get(r.set.id)) continue;
      if (!r.set.model && rec.model) this.home.set(r.set, rec.model);
      this.markup.adoptSet(r.set);
      sketches++;
    }
    const topics = rec.topics.filter((t) => !!t && typeof t.guid === 'string' && Array.isArray(t.viewpoints));
    if (rec.model) for (const t of topics) if (!t.model) this.home.set(t, rec.model);
    const docs = await this.pendingDocs(rec.documents);
    const n = this.bcf.adoptTopics(topics, docs);
    if (n || sketches) {
      this.status = `${sketches} sketch${sketches === 1 ? '' : 'es'} and ${n} issue${n === 1 ? '' : 's'} from the last session`;
      this.markup.setStatus(this.status);
    }
  }

  /** The PDFs of the saved issues, with bytes from the sheets store; one whose bytes are gone is left out. */
  private async pendingDocs(docs: readonly WorkDocument[]): Promise<BcfDocument[]> {
    const out: BcfDocument[] = [];
    for (const d of docs) {
      const bytes = await this.bytesOfPdf?.(d.sha256).catch(() => null);
      if (bytes) out.push({ guid: d.guid, filename: d.filename, data: bytes, sha256: d.sha256, ...(d.description ? { description: d.description } : {}) });
    }
    return out;
  }

  // ---------------------------------------------------------------- clearing

  /** What "Clear all sketches and issues for this model" would remove: 3D sketches and issues that belong to the loaded model. */
  counts(): { sketches: number; issues: number } {
    const now = this.now();
    return {
      sketches: this.markup.sets.filter((s) => !isSheetSet(s) && !s.readonly && scopeOf(s.model, now).visible).length,
      issues: this.bcf.topics.filter((t) => scopeOf(t.model, now).visible).length,
    };
  }

  /** Remove the 3D sketches and issues of the loaded model from the session and from the saved copy. The caller asks first. */
  async clearModel(): Promise<{ sketches: number; issues: number }> {
    const now = this.now();
    const n = this.counts();
    for (const t of [...this.bcf.topics]) if (scopeOf(t.model, now).visible) this.bcf.deleteTopic(t.guid);
    for (const s of [...this.markup.sets]) if (!isSheetSet(s) && !s.readonly && scopeOf(s.model, now).visible) this.markup.deleteSet(s.id);
    this.markup.setStatus(`Cleared ${n.sketches} sketch${n.sketches === 1 ? '' : 'es'} and ${n.issues} issue${n.issues === 1 ? '' : 's'} for this model`);
    await this.save();
    return n;
  }

  /** Forget the saved copy of every model (scripts and tests). The session is left as it is until the next change. */
  async wipe(): Promise<void> {
    for (const k of await this.store.keys()) await this.store.delete(k);
    this.lastSig.clear();
  }

  /** Remove every 3D sketch and issue from the session, whatever model it belongs to, and forget every saved copy (scripts and tests that boot again in the same browser). */
  async reset(): Promise<void> {
    for (const t of [...this.bcf.topics]) this.bcf.deleteTopic(t.guid);
    for (const s of [...this.markup.sets]) if (!isSheetSet(s) && !s.readonly) this.markup.deleteSet(s.id);
    await this.save();
    await this.wipe();
  }
}
