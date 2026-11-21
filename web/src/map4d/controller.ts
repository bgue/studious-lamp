// The 4D mapping tool's state and actions (no DOM): the assignments of the model on screen, the value lists, the suggestions, the
// coverage and the temporary colouring. The panel (panel.ts) draws it; plugins/map4d.ts installs it and exposes window.__xray4dMap.
// Assignments persist per model in IndexedDB (store.ts), are written into the IFC as Xray_4D (src/ifcsave) and are read back from
// the `Xray_4D.*` hover properties when a saved model is opened.

import type { ViewerApp } from '../app';
import type { ClassifyResult } from '../classify/types';
import { loadedIdentity, identityKey } from '../markup/scope';
import { MemoryStorage, loadSets } from '../selectionSets';
import type { SelectionSet, StorageLike } from '../selectionSets';
import { runQuery } from '../query';
import type { Assignment, AttributeKind, FourDLinks } from '../schedule/types';
import type { ElementId, SceneModel } from '../types';
import { ATTRIBUTES, acceptedValues, assign as assignRecords, decide, mergeAssignments, normalise, proposed, renameValue, unassign, valueCounts } from './assignments';
import type { ElementValues } from './assignments';
import { assignmentsFromProps, newFromProps, saveMap } from './ifcio';
import { exportDataset, importDataset } from './linkio';
import type { ImportOutcome } from './linkio';
import { MapStore } from './store';
import type { MapRecord } from './store';
import { suggest as makeSuggestions } from './suggest';
import type { SuggestElement } from './suggest';
import { resolveTarget } from './targets';
import type { Target } from './targets';
import { DEFAULT_CLASS_TRADE, DISCIPLINE_TRADE, absorb, cleanValue, addValue, colourOf, copyLists, defaultLists, hexToRgb, knownValues, removeFromList, renameInList, setColour } from './values';
import type { ValueDef, ValueLists } from './values';

export interface Coverage {
  total: number;
  attributes: Record<AttributeKind, { assigned: number; unassigned: number; proposed: number; values: Array<{ value: string; count: number }> }>;
}

export interface SuggestSummary { proposed: number; byAttribute: Record<AttributeKind, number> }

const UNASSIGNED_RGB: [number, number, number] = [0.36, 0.38, 0.42];
const PREVIEW_RGB: [number, number, number] = [1, 0.62, 0.12];

function storage(): StorageLike {
  try { const s = window.localStorage; s.getItem('xray.probe'); return s; } catch { return new MemoryStorage(); }
}

interface ClassifyLike { results(): ClassifyResult[] }

export class Map4dController {
  assignments: Assignment[] = [];
  values: ValueLists = defaultLists();
  classTrade: Record<string, string> = { ...DEFAULT_CLASS_TRADE };
  colourBy: AttributeKind | null = null;
  /** Where the last restore came from: false without IndexedDB. */
  persistent = false;
  private readonly store = new MapStore();
  private key: string | null = null;
  private token = 0;
  private ready_: Promise<void> = Promise.resolve();
  private listeners = new Set<() => void>();
  private tintSaved: Map<number, [number, number, number]> | null = null;
  private previewSaved: Map<number, [number, number, number]> | null = null;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private zoneCache: { model: SceneModel; map: Map<string, string[]> } | null = null;

  constructor(private readonly app: ViewerApp) {}

  ready(): Promise<void> { return this.ready_; }
  onChange(cb: () => void): () => void { this.listeners.add(cb); return () => this.listeners.delete(cb); }
  private emit(): void { for (const l of [...this.listeners]) l(); }

  get model(): SceneModel | null { return this.app.loaded ? this.app.controller.model : null; }

  // ------------------------------------------------------------ the model changed

  /** A new model: restore its record, seed the value lists, read Xray_4D back. */
  onModel(): void {
    this.cancelPreview(true);
    this.tintSaved = null; // the renderer state is new
    this.zoneCache = null;
    const my = ++this.token;
    const model = this.model;
    this.assignments = [];
    this.values = defaultLists();
    this.classTrade = { ...DEFAULT_CLASS_TRADE };
    this.key = null;
    if (!model || !this.app.loaded) { this.emit(); return; }
    const identity = loadedIdentity(this.app as never);
    this.key = identityKey(identity);
    this.ready_ = (async () => {
      const rec = await this.store.get(this.key!);
      if (my !== this.token) return;
      this.persistent = this.store.persistent;
      if (rec) {
        this.assignments = normalise(rec.assignments ?? []);
        this.values = rec.values ?? defaultLists();
        this.classTrade = { ...DEFAULT_CLASS_TRADE, ...(rec.classTrade ?? {}) };
      }
      this.seed(false);
      const back = newFromProps(this.assignments, assignmentsFromProps(model.elements));
      if (back.length) {
        this.assignments = mergeAssignments(this.assignments, back).list;
        this.values = absorb(this.values, this.assignments);
      }
      if (back.length || !rec) this.schedulePersist();
      this.emit();
    })();
    this.emit();
  }

  // ------------------------------------------------------------ values

  /** Names of the storeys, the zones and the trades of the classifier that the model offers. */
  modelValues(): Record<AttributeKind, string[]> {
    const m = this.model;
    const location = m ? m.storeys.map((s) => s.name).filter(Boolean) : [];
    const zone = [...new Set([...this.zones().values()].flat())];
    const trade = new Set<string>();
    const results = this.classifyResults();
    if (results) for (const r of results.values()) { const t = classifyTrade(r); if (t) trade.add(t); }
    return { location: [...new Set(location)], zone, trade: [...trade] };
  }

  /** Add the model's own values to the lists (storey names, zone names, trades the classifier suggests). Returns how many were added. */
  seed(emit = true): number {
    const mv = this.modelValues();
    let lists = this.values;
    let n = 0;
    for (const attr of ATTRIBUTES) for (const name of mv[attr]) { const r = addValue(lists, attr, name); if (r.added) { lists = r.lists; n++; } }
    this.values = lists;
    if (n > 0 && emit) { this.schedulePersist(); this.emit(); }
    return n;
  }

  valueList(attr: AttributeKind): ValueDef[] { return knownValues(this.values, this.assignments, attr); }

  addValue(attr: AttributeKind, name: string): boolean {
    const r = addValue(this.values, attr, name);
    if (!r.added) return false;
    this.values = r.lists;
    this.changed();
    return true;
  }

  renameValue(attr: AttributeKind, from: string, to: string): boolean {
    let lists = this.values;
    if (!lists[attr].some((v) => v.name === from)) lists = addValue(lists, attr, from).lists; // a value that came with an import
    const r = renameInList(lists, attr, from, to);
    if (!r.ok) return false;
    this.values = r.lists;
    this.assignments = renameValue(this.assignments, attr, from, cleanValue(to)).list;
    this.changed();
    return true;
  }

  /** Remove a value from the list. A value that elements use stays listed (assignments are never dropped by this). */
  deleteValue(attr: AttributeKind, name: string): boolean {
    if (this.usage(attr).get(name)) return false;
    this.values = removeFromList(this.values, attr, name);
    this.changed();
    return true;
  }

  setColour(attr: AttributeKind, name: string, colour: string): void {
    let lists = this.values;
    if (!lists[attr].some((v) => v.name === name)) lists = addValue(lists, attr, name).lists;
    this.values = setColour(lists, attr, name, colour);
    this.changed();
    if (this.colourBy === attr) this.applyColour();
  }

  usage(attr: AttributeKind): Map<string, number> { return valueCounts(this.assignments, attr); }

  setClassTrade(table: Record<string, string>): void { this.classTrade = { ...table }; this.changed(); }

  // ------------------------------------------------------------ targets

  sets(): SelectionSet[] {
    const m = this.model;
    return m ? loadSets(storage(), this.app.modelName) ?? [] : [];
  }

  resolve(target: Target): { ids: ElementId[]; globalIds: string[]; error?: string } {
    const m = this.model;
    if (!m) return { ids: [], globalIds: [], error: 'No model is open.' };
    const r = resolveTarget(target, { model: m, selection: this.app.selection, sets: this.sets() });
    return { ids: r.ids, globalIds: [...new Set(r.ids.map((i) => m.elements[i]!.globalId))], ...(r.error ? { error: r.error } : {}) };
  }

  /** Live count of a criteria query. */
  queryCount(query: string): { count: number; error?: string } {
    const m = this.model;
    if (!m || !query.trim()) return { count: 0 };
    const r = runQuery(m, query);
    return r.error ? { count: 0, error: r.error.message } : { count: r.ids.length };
  }

  // ------------------------------------------------------------ assign

  /** Give the target's elements an accepted value (source manual). Returns how many elements changed. */
  assign(attr: AttributeKind, value: string, target: Target): { assigned: number; unchanged: number; matched: number; error?: string } {
    const v = value.replace(/\s+/g, ' ').trim().slice(0, 255);
    if (!v) return { assigned: 0, unchanged: 0, matched: 0, error: 'The value is empty.' };
    const r = this.resolve(target);
    if (r.error) return { assigned: 0, unchanged: 0, matched: 0, error: r.error };
    const res = assignRecords(this.assignments, r.globalIds, attr, v, { source: 'manual' });
    this.assignments = res.list;
    if (res.assigned > 0) { this.values = addValue(this.values, attr, v).lists; this.changed(); }
    return { assigned: res.assigned, unchanged: res.unchanged, matched: r.globalIds.length };
  }

  clearAssignment(attr: AttributeKind, target: Target): number {
    const r = this.resolve(target);
    const res = unassign(this.assignments, r.globalIds, attr);
    this.assignments = res.list;
    if (res.removed) this.changed();
    return res.removed;
  }

  // ------------------------------------------------------------ suggestions

  private classifyResults(): Map<string, ClassifyResult> | null {
    const c = (window as unknown as { __xrayClassify?: ClassifyLike }).__xrayClassify;
    const list = c?.results();
    return list && list.length ? new Map(list.map((r) => [r.id, r] as const)) : null;
  }

  /** GlobalId -> the zones (system groups named zone) the element belongs to. IfcZone groups come through the model's systems. */
  private zones(): Map<string, string[]> {
    const m = this.model;
    if (!m) return new Map();
    if (this.zoneCache?.model === m) return this.zoneCache.map;
    const map = new Map<string, string[]>();
    for (const s of m.relations.systems) {
      if (!/zone/i.test(s.name)) continue;
      for (const id of s.elements) {
        const g = m.elements[id]?.globalId;
        if (!g) continue;
        const l = map.get(g) ?? [];
        if (!l.includes(s.name)) l.push(s.name);
        map.set(g, l);
      }
    }
    this.zoneCache = { model: m, map };
    return map;
  }

  suggestInputs(): SuggestElement[] {
    const m = this.model;
    if (!m) return [];
    const zones = this.zones();
    const storeyName = new Map(m.storeys.map((s) => [s.id, s.name] as const));
    return m.elements.map((e) => ({ globalId: e.globalId, ifcClass: e.ifcClass, ...(e.name ? { name: e.name } : {}), ...(e.material ? { material: e.material } : {}), storey: e.storey === null ? null : storeyName.get(e.storey) ?? null, ...(zones.has(e.globalId) ? { zones: zones.get(e.globalId)! } : {}) }));
  }

  /** Replace the open proposals by fresh ones: location and zone from containment, trade from the class table and the classifier. */
  suggest(attributes?: readonly AttributeKind[]): SuggestSummary {
    const keep = this.assignments.filter((a) => a.status !== 'proposed' || (attributes && !attributes.includes(a.attribute)));
    const fresh = makeSuggestions(this.suggestInputs(), { classTrade: this.classTrade, results: this.classifyResults() ?? undefined, existing: keep, ...(attributes ? { attributes } : {}) });
    this.assignments = keep.concat(fresh);
    const by: Record<AttributeKind, number> = { location: 0, trade: 0, zone: 0 };
    for (const a of fresh) by[a.attribute]++;
    this.changed();
    return { proposed: fresh.length, byAttribute: by };
  }

  proposals(): Assignment[] { return proposed(this.assignments); }

  accept(ids: Iterable<string>): number { return this.decide(ids, 'accepted'); }
  reject(ids: Iterable<string>): number { return this.decide(ids, 'rejected'); }
  private decide(ids: Iterable<string>, status: 'accepted' | 'rejected'): number {
    const r = decide(this.assignments, ids, status);
    this.assignments = r.list;
    if (r.changed) {
      if (status === 'accepted') this.values = absorb(this.values, this.assignments);
      this.changed();
    }
    return r.changed;
  }

  /** Accept every proposal with at least this confidence (optionally for one attribute). */
  acceptAbove(limit: number, attr?: AttributeKind): number {
    return this.accept(this.proposals().filter((a) => (a.confidence ?? 0) >= limit && (!attr || a.attribute === attr)).map((a) => a.id));
  }

  // ------------------------------------------------------------ coverage

  coverage(): Coverage {
    const m = this.model;
    const total = m ? m.elements.length : 0;
    const have = acceptedValues(this.assignments);
    const prop = new Map<string, Set<string>>();
    for (const a of this.assignments) if (a.status === 'proposed') { const k = a.attribute; (prop.get(k) ?? prop.set(k, new Set()).get(k)!).add(a.element); }
    const out = {} as Coverage['attributes'];
    for (const attr of ATTRIBUTES) {
      const counts = new Map<string, number>();
      let assigned = 0;
      if (m) for (const e of m.elements) { const v = have.get(e.globalId)?.[attr]; if (v !== undefined) { assigned++; counts.set(v, (counts.get(v) ?? 0) + 1); } }
      out[attr] = { assigned, unassigned: total - assigned, proposed: prop.get(attr)?.size ?? 0, values: [...counts].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value)) };
    }
    return { total, attributes: out };
  }

  unassignedIds(attr: AttributeKind): ElementId[] {
    const m = this.model;
    if (!m) return [];
    const have = acceptedValues(this.assignments);
    const ids: ElementId[] = [];
    m.elements.forEach((e, i) => { if (have.get(e.globalId)?.[attr] === undefined) ids.push(i); });
    return ids;
  }

  selectUnassigned(attr: AttributeKind): number {
    const ids = this.unassignedIds(attr);
    this.app.selectIds(ids);
    return ids.length;
  }

  // ------------------------------------------------------------ temporary colour

  /** Colour the model by an attribute (or null: back to normal). Removed when the tab is left (`release`). */
  setColourBy(attr: AttributeKind | null): void {
    this.colourBy = attr;
    this.applyColour();
    this.emit();
  }

  applyColour(): void {
    this.restoreColour(false);
    const attr = this.colourBy;
    const m = this.model;
    if (!attr || !m) { this.app.renderer.markDirty(); return; }
    const color = this.app.renderer.state.color;
    const have = acceptedValues(this.assignments);
    const saved = new Map<number, [number, number, number]>();
    const cache = new Map<string, [number, number, number]>();
    m.elements.forEach((e, id) => {
      const o = id * 3;
      saved.set(id, [color[o]!, color[o + 1]!, color[o + 2]!]);
      const v = have.get(e.globalId)?.[attr];
      let c = UNASSIGNED_RGB;
      if (v !== undefined) { c = cache.get(v) ?? hexToRgb(colourOf(this.values, attr, v)); cache.set(v, c); }
      color[o] = c[0]; color[o + 1] = c[1]; color[o + 2] = c[2];
    });
    this.tintSaved = saved;
    this.app.renderer.markDirty();
  }

  private restoreColour(mark = true): void {
    const s = this.tintSaved;
    if (!s) return;
    this.tintSaved = null;
    const color = this.app.renderer.state.color;
    for (const [id, c] of s) { color[id * 3] = c[0]; color[id * 3 + 1] = c[1]; color[id * 3 + 2] = c[2]; }
    if (mark) this.app.renderer.markDirty();
  }

  /** The tab was left: remove the colouring and any preview (the choice of attribute stays for when the tab comes back). */
  release(): void { this.restoreColour(); this.cancelPreview(); }
  /** The tab is back. */
  resume(): void { if (this.colourBy) this.applyColour(); }

  /** Tint the elements a query or target matches, so the person sees what an assignment would touch. */
  preview(ids: readonly ElementId[]): void {
    this.cancelPreview();
    if (ids.length === 0) return;
    const color = this.app.renderer.state.color;
    const saved = new Map<number, [number, number, number]>();
    for (const id of ids) {
      const o = id * 3;
      if (o + 2 >= color.length) continue;
      saved.set(id, [color[o]!, color[o + 1]!, color[o + 2]!]);
      color[o] = PREVIEW_RGB[0]; color[o + 1] = PREVIEW_RGB[1]; color[o + 2] = PREVIEW_RGB[2];
    }
    this.previewSaved = saved;
    this.app.renderer.markDirty();
  }

  cancelPreview(silent = false): void {
    const s = this.previewSaved;
    if (!s) return;
    this.previewSaved = null;
    if (silent) return;
    const color = this.app.renderer.state.color;
    for (const [id, c] of s) { color[id * 3] = c[0]; color[id * 3 + 1] = c[1]; color[id * 3 + 2] = c[2]; }
    this.app.renderer.markDirty();
  }

  // ------------------------------------------------------------ import and export

  exportJson(o: { includeReviewers?: boolean } = {}): { json: string; assignments: number; elements: number; skipped: number } {
    const m = this.model;
    const identity = m ? loadedIdentity(this.app as never) : null;
    const storeyName = new Map((m?.storeys ?? []).map((s) => [s.id, s.name] as const));
    const r = exportDataset({
      model: { identity_key: this.key ?? 'unknown', ...(identity?.name ? { name: identity.name } : {}) },
      elements: (m?.elements ?? []).map((e) => ({ globalId: e.globalId, ifcClass: e.ifcClass, ...(e.name ? { name: e.name } : {}), storey: e.storey === null ? null : storeyName.get(e.storey) ?? null })),
      assignments: this.assignments,
      ...(o.includeReviewers ? { includeReviewers: true } : {}),
    });
    return { json: r.json, assignments: r.assignments, elements: r.elements, skipped: r.skipped };
  }

  datasetObject(): FourDLinks { return JSON.parse(this.exportJson().json) as FourDLinks; }

  importJson(text: string): ImportOutcome {
    const r = importDataset(this.assignments, text, this.key ?? undefined);
    if (r.read > 0) {
      this.assignments = r.list;
      this.values = absorb(this.values, this.assignments);
      this.changed();
    }
    return r;
  }

  // ------------------------------------------------------------ save into the IFC

  /** Accepted values by GlobalId for the save plan. */
  saveMap(): Map<string, ElementValues> { return saveMap(this.assignments); }

  /** Forget everything for this model (the stored record too). */
  reset(): void {
    this.assignments = [];
    this.values = defaultLists();
    this.seed(false);
    this.classTrade = { ...DEFAULT_CLASS_TRADE };
    this.changed();
  }

  // ------------------------------------------------------------ persistence

  private changed(): void {
    this.schedulePersist();
    if (this.colourBy) this.applyColour();
    this.emit();
  }

  private schedulePersist(): void {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => { this.saveTimer = null; void this.flush(); }, 400);
  }

  /** Write the record now. */
  async flush(): Promise<boolean> {
    if (this.saveTimer) { clearTimeout(this.saveTimer); this.saveTimer = null; }
    if (!this.key) return false;
    const identity = this.model ? loadedIdentity(this.app as never) : null;
    const rec: MapRecord = { schema: 'xray-4d-map/1', key: this.key, model: identity, saved: new Date().toISOString(), assignments: this.assignments, values: copyLists(this.values), classTrade: { ...this.classTrade } };
    return this.store.put(rec);
  }
}

/** The trade a classifier result names (its discipline code through the default table), for seeding the trade list. */
function classifyTrade(r: ClassifyResult): string | null {
  return DISCIPLINE_TRADE[r.discipline.code] ?? null;
}