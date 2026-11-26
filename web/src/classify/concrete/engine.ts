// The concrete engine: for the elements of the concrete family, the five XR_Concrete* sets. Measured geometry first (no model), then
// roles, method, reinforcement type and slab scheme by manual choice, rule, cache and, last, ONE question per signature to the
// decision model (the same providers, calibration and review threshold as the facets). Exposure is never asked of the model.
// Pure TypeScript, no DOM. Design: docs/design/concrete-classification.md. Docs: docs-features/classify.md, "Concrete".

import { answersFromRaw, rawOfAnswers } from '../calibrate';
import type { Temperatures } from '../calibrate';
import { choiceQuestion, readChoice } from '../jevAdapter';
import type { ChoiceAnswer, Questions } from '../jevAdapter';
import { DEFAULT_MIN_MARGIN, topMargin } from '../review';
import { isAbort, withBackoff } from '../retry';
import type { RetryOptions } from '../retry';
import { buildState, DEFAULT_MAX_STATE_BYTES, signatureOf } from '../state';
import { ProviderError } from '../types';
import type { ClassifyInput, DecisionModel } from '../types';
import { MemoryFacetCache } from '../facets/engine';
import type { FacetCache } from '../facets/engine';
import type { FacetFieldValue, FacetSource } from '../facets/defs';
import type { OrientationMesh } from '../facets/orientation';
import { concreteGeometry, facesText, vecText } from './geometry';
import type { Box6, ConcreteGeometry, GeometryOptions } from './geometry';
import { contactGraph, pourGroups } from './contacts';
import type { ContactGraph } from './contacts';
import { assignMarks } from './marks';
import {
  CONCRETE_FINAL, allowedRoles, defaultRole, frameKindOfClass, frameKindOfRole, groundSidesRole, isConcreteFamily, isGroundRole, methodRule, ratioEstimate,
  reinforcementRule, roleRule, schemeRule,
} from './rules';
import type { RoleContext } from './rules';
import { defaultCoverTable, specOf } from './spec';
import type { CoverTable, Standard } from './spec';
import { propOf } from '../facets/facetRules';
import {
  CONCRETE_SCHEME, METHOD_CODES, Q_CONCRETE, REINFORCEMENT_CODES, ROLE_CODES, SLAB_SCHEMES, labelOf,
} from './defs';
import type { ConcreteFacetId, ConcreteFacetResult, ConcreteSet } from './defs';

export { CONCRETE_SCHEME };

/** What the viewer lends about one element. */
export interface ConcreteItem {
  input: ClassifyInput;
  /** World-space triangles in the viewer frame (called twice: measure, then formwork with the final role). `dispose` frees a copy. */
  mesh?: () => (OrientationMesh & { dispose?: () => void }) | null;
  /** Storey index, 0 = lowest storey; null or absent: none. */
  storey?: number | null;
  belowGround?: boolean;
  /** Placement facet code (EXT, INT, BOUNDARY). */
  placement?: string;
  /** Plan direction out of the exterior face of a wall. */
  outward?: readonly [number, number] | null;
  /** Material facet code, when known. */
  material?: string;
  /** Orientation facet class, when measured. */
  orientation?: string;
  /** A tendon runs through or beside the element. */
  tendonNearby?: boolean;
  shape?: () => string;
}

export interface ConcreteOptions {
  provider?: DecisionModel | null;
  cache?: FacetCache;
  /** Manual choices by GlobalId (ConcreteElement, ConcreteMethod, ConcreteReinforcement); they win and are never asked again. */
  manual?: ReadonlyMap<string, ConcreteSet>;
  /** Which sets to return. Default: all. */
  enabled?: Partial<Record<ConcreteFacetId, boolean>>;
  temperatures?: Temperatures;
  minMargin?: number;
  ruleFinal?: number;
  /** A decision below this confidence needs review. */
  minConfidence?: number;
  concurrency?: number;
  maxStateBytes?: number;
  retry?: RetryOptions;
  signal?: AbortSignal;
  dry?: boolean;
  /** Ground level in the viewer frame (y up = IFC Z). Absent: nothing lies against the ground. */
  groundLevel?: number;
  cover?: CoverTable;
  defaultStandard?: Standard;
  /** Called now and then in the long loops so the page stays responsive. */
  yieldFn?: () => Promise<void>;
  onProgress?: (p: { step: string; done: number; total: number }) => void;
}

export interface ConcreteStats {
  /** Elements in the concrete family. */
  elements: number;
  calls: number;
  signatures: number;
  bySource: Record<string, Partial<Record<FacetSource | 'cache', number>>>;
  needsReview: number;
  errors: string[];
  aborted: boolean;
  models: Record<string, number>;
  usage: { input_tokens: number; output_tokens: number };
}

export interface ConcreteRun {
  results: Map<string, ConcreteSet>;
  /** Measured geometry by GlobalId (the final one, with the role's frame and the contacts). */
  geometry: Map<string, ConcreteGeometry>;
  stats: ConcreteStats;
}

const INSTRUCTIONS = {
  role: 'This BIM element is concrete. Choose its structural role. Decide from its IFC class, name, type, predefined type, its measured size and what it bears on or carries.',
  method: 'Choose how this concrete BIM element is made: cast in place, precast, post-tensioned, tilt-up or composite deck (concrete on a metal deck). Decide from its name, type, properties and role.',
  reinforcement: 'Choose the reinforcement type of this concrete BIM element: reinforced, post-tensioned, fibre reinforced or plain (unreinforced). Decide from its name, type, role and properties.',
  scheme: 'Choose how this concrete slab is reinforced: one-way (it spans mainly in one direction) or two-way. Decide from the measured span ratio, its supports, name and role.',
} as const;

const r2 = (n: number): number => Math.round(n * 100) / 100;

/** A piece mark or Tag a person can read: not empty, not an IFC GUID (22 characters) or a UUID, not longer than 40 characters. */
export const isReadableMark = (s: string): boolean => {
  const t = s.trim();
  return t.length > 0 && t.length <= 40 && !/^[0-9a-f]{32}$/i.test(t.replace(/-/g, '')) && !/^[0-9A-Za-z_$]{22}$/.test(t);
};

/** Sentence for an option. */
const optionText = (list: ReadonlyArray<{ code: string; label: string }>, codes: readonly string[]): Record<string, string> => {
  const o: Record<string, string> = {};
  for (const c of codes) o[c] = list.find((x) => x.code === c)?.label ?? c;
  return o;
};

interface Decided { code: string; confidence: number; source: FacetSource; model?: string; needsReview: boolean; probabilities?: Record<string, number>; rationale?: string }

interface Work {
  item: ConcreteItem;
  id: string;
  input: ClassifyInput;
  g1: ConcreteGeometry | null;
  geo: ConcreteGeometry | null;
  restsOn: string[];
  carries: string[];
  role: Decided | null;
  method: Decided | null;
  reinf: Decided | null;
  scheme: Decided | null;
}

interface Open {
  w: Work;
  /** The codes the model may choose from. */
  options: readonly string[];
  /** Facts that change the answer, beyond the element's own signature. */
  sig: string;
  weak: Decided | null;
  extra?: Record<string, string | number | boolean>;
}

const classesOf = (ids: readonly string[], by: Map<string, Work>): string[] => [...new Set(ids.map((i) => by.get(i)?.input.ifcClass ?? '').filter(Boolean))].sort();

/** The concrete sets of the given elements. Elements outside the concrete family are skipped. Never throws: a failure leaves the weak rule, flagged for review. */
export async function classifyConcrete(items: readonly ConcreteItem[], o: ConcreteOptions = {}): Promise<ConcreteRun> {
  const final = o.ruleFinal ?? CONCRETE_FINAL;
  const minConf = o.minConfidence ?? 0.6;
  const minMargin = o.minMargin ?? DEFAULT_MIN_MARGIN;
  const cache = o.cache ?? new MemoryFacetCache();
  const cover = o.cover ?? defaultCoverTable();
  const on = (f: ConcreteFacetId): boolean => o.enabled?.[f] ?? true;
  const stats: ConcreteStats = { elements: 0, calls: 0, signatures: 0, bySource: {}, needsReview: 0, errors: [], aborted: false, models: {}, usage: { input_tokens: 0, output_tokens: 0 } };
  const ctl = new AbortController();
  const stop = (): void => ctl.abort();
  if (o.signal?.aborted) ctl.abort(); else o.signal?.addEventListener('abort', stop, { once: true });
  const signal = ctl.signal;
  const addError = (m: string): void => { if (stats.errors.length < 20 && !stats.errors.includes(m)) stats.errors.push(m); };
  const count = (f: string, s: FacetSource | 'cache'): void => { const b = (stats.bySource[f] ??= {}); b[s] = (b[s] ?? 0) + 1; };
  const yieldNow = o.yieldFn ?? (async () => {});
  let t0 = Date.now();
  const maybeYield = async (): Promise<void> => { if (Date.now() - t0 > 12) { await yieldNow(); t0 = Date.now(); } };

  const works: Work[] = [];
  for (const item of items) {
    if (!isConcreteFamily(item.input, item.material)) continue;
    works.push({ item, id: item.input.id, input: item.input, g1: null, geo: null, restsOn: [], carries: [], role: null, method: null, reinf: null, scheme: null });
  }
  stats.elements = works.length;
  const byId = new Map(works.map((w) => [w.id, w]));
  const results = new Map<string, ConcreteSet>();
  const geometry = new Map<string, ConcreteGeometry>();
  if (!works.length) { o.signal?.removeEventListener('abort', stop); return { results, geometry, stats }; }

  const measure = (w: Work, kind: ReturnType<typeof frameKindOfClass>, go: GeometryOptions): ConcreteGeometry | null => {
    const mesh = w.item.mesh?.() ?? null;
    if (!mesh) return null;
    try { return concreteGeometry(mesh, kind, go); } catch (e) { addError(`geometry: ${e instanceof Error ? e.message : String(e)}`); return null; } finally { mesh.dispose?.(); }
  };

  // 1. measure, without roles
  let done = 0;
  for (const w of works) {
    if (signal.aborted) break;
    w.g1 = measure(w, frameKindOfClass(w.input.ifcClass), {});
    o.onProgress?.({ step: 'measure', done: ++done, total: works.length });
    await maybeYield();
  }

  // 2. contacts from the bounds
  const graph: ContactGraph = contactGraph(works.filter((w) => w.g1).map((w) => ({ id: w.id, bounds: w.g1!.bounds, storey: w.item.storey ?? null })));
  for (const w of works) { w.restsOn = graph.restsOn.get(w.id) ?? []; w.carries = graph.carries.get(w.id) ?? []; }

  const ground = o.groundLevel;
  const lowest = (w: Work): boolean => (w.item.storey ?? 0) === 0;

  // ---------------------------------------------------------------- the questions
  const ask = async (name: keyof typeof Q_CONCRETE, opens: Open[], list: ReadonlyArray<{ code: string; label: string }>, apply: (op: Open, d: Decided) => void): Promise<void> => {
    const qn = Q_CONCRETE[name];
    const temps: Temperatures = {};
    if (o.temperatures) (temps as Record<string, number | undefined>)[qn] = o.temperatures['discipline'] ?? undefined;
    const askable = !!o.provider && !signal.aborted;
    const fallback = (op: Open): void => { if (op.weak) { apply(op, { ...op.weak, needsReview: true }); count(name, op.weak.source); } };
    if (!opens.length) return;
    if (!askable) { opens.forEach(fallback); return; }
    const groups = new Map<string, Open[]>();
    for (const op of opens) {
      const key = `concrete:${name}|${signatureOf(op.w.input)}#${op.options.join(',')}#${op.sig}`;
      (groups.get(key) ?? groups.set(key, []).get(key)!).push(op);
    }
    const decide = (members: Open[], choice: ChoiceAnswer, modelId: string, fromCache: boolean): void => {
      if (!members[0]!.options.includes(choice.choice)) throw new ProviderError(`The model chose the ${name} code "${choice.choice}", which is not allowed here.`);
      const needs = choice.confidence < minConf || topMargin(choice.probabilities) < minMargin;
      for (const m of members) {
        apply(m, { code: choice.choice, confidence: choice.confidence, source: 'model', model: modelId, needsReview: needs, probabilities: choice.probabilities });
        count(name, fromCache ? 'cache' : 'model');
      }
    };
    const todo: Array<[string, Open[]]> = [];
    for (const [key, members] of groups) {
      const hit = cache.get(key);
      if (hit) { try { const a = answersFromRaw(hit.raw, temps); decide(members, readChoice(a, qn), a.model, true); continue; } catch { /* stale entry: ask again */ } }
      todo.push([key, members]);
    }
    stats.signatures += todo.length;
    if (o.dry) { stats.calls += todo.length; return; }
    let next = 0;
    const worker = async (): Promise<void> => {
      for (;;) {
        if (signal.aborted) return;
        const entry = todo[next++];
        if (!entry) return;
        const [key, members] = entry;
        const rep = members[0]!;
        try {
          let state = buildState(rep.w.input, o.maxStateBytes ?? DEFAULT_MAX_STATE_BYTES);
          const g = rep.w.geo ?? rep.w.g1;
          const known: Record<string, string | number | boolean> = { ...(rep.extra ?? {}) };
          if (rep.w.role) known['role'] = rep.w.role.code;
          if (rep.w.method) known['method'] = rep.w.method.code;
          if (rep.w.item.placement) known['placement'] = rep.w.item.placement;
          if (rep.w.item.belowGround !== undefined) known['below_ground'] = rep.w.item.belowGround;
          if (g) Object.assign(known, { length_m: g.length, width_m: g.width, thickness_m: g.thickness, section: g.sectionShape });
          known['rests_on'] = classesOf(rep.w.restsOn, byId).join(',');
          known['carries'] = classesOf(rep.w.carries, byId).join(',');
          state = { ...state, concrete: known };
          const line = rep.w.item.shape?.();
          if (line) state = { ...state, shape: line };
          const questions: Questions = { [qn]: choiceQuestion(INSTRUCTIONS[name], optionText(list, rep.options)) };
          stats.calls++;
          const answers = await withBackoff(() => o.provider!.decide(state, questions, signal), signal, o.retry);
          stats.models[answers.model] = (stats.models[answers.model] ?? 0) + 1;
          stats.usage.input_tokens += answers.usage?.input_tokens ?? 0;
          stats.usage.output_tokens += answers.usage?.output_tokens ?? 0;
          const raw = rawOfAnswers(answers);
          const a = answersFromRaw(raw, temps);
          decide(members, readChoice(a, qn), answers.model, false);
          cache.set(key, { raw, model: answers.model });
        } catch (e) {
          if (isAbort(e) || signal.aborted) return;
          members.forEach(fallback);
          addError(`${name}: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
    };
    await Promise.all(Array.from({ length: Math.max(1, Math.min(o.concurrency ?? 4, todo.length)) }, () => worker()));
  };

  const manualOf = (w: Work, f: ConcreteFacetId): ConcreteFacetResult | undefined => o.manual?.get(w.id)?.[f];
  const fromManual = (m: ConcreteFacetResult): Decided => ({ code: m.code, confidence: 1, source: 'manual', needsReview: false });

  // 3. roles
  const roleOpen: Open[] = [];
  for (const w of works) {
    const man = manualOf(w, 'ConcreteElement');
    if (man) { w.role = fromManual(man); count('role', 'manual'); continue; }
    const g = w.g1;
    const ctx: RoleContext = {
      restsOn: classesOf(w.restsOn, byId), carries: classesOf(w.carries, byId),
      ...(g ? { length: g.length, width: g.width, thickness: g.thickness, planAspect: g.planAspect, planArea: g.size[0] * g.size[1] } : {}),
      ...(g && ground !== undefined && frameKindOfClass(w.input.ifcClass) !== 'wall' ? { onGround: g.bounds[2] <= ground + 0.3 && (lowest(w) || !!w.item.belowGround) && !w.restsOn.some((id) => /^IfcWall|^IfcColumn|^IfcBeam/.test(byId.get(id)?.input.ifcClass ?? '')) } : {}),
      ...(w.item.belowGround !== undefined ? { belowGround: w.item.belowGround } : {}),
      ...(w.item.placement ? { exposure: w.item.placement } : {}),
      ...(w.item.orientation ? { orientation: w.item.orientation } : {}),
    };
    const r = roleRule(w.input, ctx);
    if (r && r.confidence >= final && allowedRoles(w.input.ifcClass).includes(r.code)) { w.role = { code: r.code, confidence: r.confidence, source: 'rule', needsReview: false, rationale: r.rationale }; count('role', 'rule'); continue; }
    const weak: Decided = r && allowedRoles(w.input.ifcClass).includes(r.code)
      ? { code: r.code, confidence: r.confidence, source: 'rule', needsReview: true, rationale: r.rationale }
      : { code: defaultRole(w.input.ifcClass), confidence: 0.5, source: 'rule', needsReview: true, rationale: 'default for the IFC class, nothing decided it' };
    const sig = [g ? Math.round(g.thickness * 20) : '', g ? Math.min(9, Math.round(g.planAspect)) : '', ctx.onGround ? 'G' : '', ctx.belowGround ? 'B' : '', ctx.restsOn.join('+'), ctx.carries.join('+'), ctx.orientation ?? ''].join('/');
    roleOpen.push({ w, options: allowedRoles(w.input.ifcClass), sig, weak, extra: { onGround: !!ctx.onGround, ...(g ? { span_ratio: g.planAspect } : {}) } });
  }
  await ask('role', roleOpen, ROLE_CODES, (op, d) => { op.w.role = d; });
  for (const w of works) if (!w.role) w.role = { code: defaultRole(w.input.ifcClass), confidence: 0.5, source: 'rule', needsReview: true, rationale: 'default for the IFC class' };

  // 4. final geometry with the role's frame, the contacts and the ground
  done = 0;
  for (const w of works) {
    if (signal.aborted) break;
    const role = w.role!.code;
    const nbs = (graph.touching.get(w.id) ?? []).map((id) => byId.get(id)?.g1).map((g, k) => (g ? { id: (graph.touching.get(w.id) ?? [])[k]!, bounds: g.bounds as Box6 } : null)).filter((x): x is { id: string; bounds: Box6 } => !!x);
    const go: GeometryOptions = { others: nbs };
    if (ground !== undefined && (isGroundRole(role) || groundSidesRole(role))) go.ground = { level: ground, soffit: isGroundRole(role), sides: groundSidesRole(role) };
    if (w.item.outward) go.outward = w.item.outward;
    const lin: Array<[number, number]> = [];
    let allLinear = w.restsOn.length > 0;
    for (const id of w.restsOn) {
      const g = byId.get(id)?.g1;
      if (g && (g.kind === 'wall' || g.kind === 'beam')) { const x = g.frame.x; const l = Math.hypot(x[0], x[1]); if (l > 1e-6) lin.push([x[0] / l, x[1] / l]); else allLinear = false; } else allLinear = false;
    }
    if (frameKindOfRole(role) === 'slab' && allLinear && lin.length) go.supportDirs = lin;
    w.geo = measure(w, frameKindOfRole(role), go) ?? w.g1;
    if (w.geo) geometry.set(w.id, w.geo);
    o.onProgress?.({ step: 'formwork', done: ++done, total: works.length });
    await maybeYield();
  }
  // supports refined by face contact: the element's soffit faces (normal Z <= -0.5 in the local frame) must touch what it bears on
  const restsRefined = new Map<string, string[]>();
  for (const w of works) {
    const g = w.geo;
    if (!g || !g.faces.length) { restsRefined.set(w.id, w.restsOn); continue; }
    const touched = new Set<string>();
    for (const f of g.faces) if (f.normal[2] <= -0.5) for (const t of f.touches) touched.add(t);
    restsRefined.set(w.id, w.restsOn.filter((id) => touched.has(id)));
  }
  const carriesRefined = new Map<string, string[]>();
  for (const [id, list] of restsRefined) for (const b of list) (carriesRefined.get(b) ?? carriesRefined.set(b, []).get(b)!).push(id);
  for (const w of works) { w.restsOn = restsRefined.get(w.id) ?? []; w.carries = (carriesRefined.get(w.id) ?? []).sort(); }

  // 5. method
  const methodOpen: Open[] = [];
  for (const w of works) {
    const man = manualOf(w, 'ConcreteMethod');
    if (man) { w.method = fromManual(man); count('method', 'manual'); continue; }
    const r = methodRule(w.input, { role: w.role!.code, ...(w.item.tendonNearby ? { tendonNearby: true } : {}) });
    if (r.confidence >= final) { w.method = { code: r.code, confidence: r.confidence, source: 'rule', needsReview: false, rationale: r.rationale }; count('method', 'rule'); continue; }
    methodOpen.push({ w, options: METHOD_CODES.map((c) => c.code).filter((c) => c !== 'UNKNOWN'), sig: w.role!.code, weak: { code: r.code, confidence: r.confidence, source: 'rule', needsReview: true, rationale: r.rationale } });
  }
  await ask('method', methodOpen, METHOD_CODES, (op, d) => { op.w.method = d; });
  for (const w of works) if (!w.method) w.method = { code: 'CAST_IN_PLACE', confidence: 0.55, source: 'rule', needsReview: true, rationale: 'default' };

  // 6. reinforcement type, then the slab scheme
  const reinfOpen: Open[] = [];
  for (const w of works) {
    const man = manualOf(w, 'ConcreteReinforcement');
    if (man) { w.reinf = fromManual(man); count('reinforcement', 'manual'); continue; }
    const r = reinforcementRule(w.input, { role: w.role!.code, method: w.method!.code });
    if (r.confidence >= final) { w.reinf = { code: r.code, confidence: r.confidence, source: 'rule', needsReview: false, rationale: r.rationale }; count('reinforcement', 'rule'); continue; }
    reinfOpen.push({ w, options: REINFORCEMENT_CODES.map((c) => c.code).filter((c) => c !== 'UNKNOWN'), sig: `${w.role!.code}#${w.method!.code}`, weak: { code: r.code, confidence: r.confidence, source: 'rule', needsReview: true, rationale: r.rationale } });
  }
  await ask('reinforcement', reinfOpen, REINFORCEMENT_CODES, (op, d) => { op.w.reinf = d; });
  for (const w of works) if (!w.reinf) w.reinf = { code: 'REINFORCED', confidence: 0.5, source: 'rule', needsReview: true, rationale: 'default' };

  const spanRatioOf = (w: Work): number | undefined => {
    const g = w.geo;
    if (!g) return undefined;
    const a = Math.max(g.size[0], g.size[1]), b = Math.min(g.size[0], g.size[1]);
    return b > 1e-6 ? r2(a / b) : undefined;
  };
  const twoSided = (w: Work): boolean => {
    if (!w.restsOn.length) return false;
    const dirs: Array<[number, number]> = [];
    for (const id of w.restsOn) {
      const g = byId.get(id)?.g1;
      if (!g || (g.kind !== 'wall' && g.kind !== 'beam')) return false;
      const l = Math.hypot(g.frame.x[0], g.frame.x[1]);
      if (l < 1e-6) return false;
      dirs.push([g.frame.x[0] / l, g.frame.x[1] / l]);
    }
    return dirs.length >= 2 && dirs.every((d) => Math.abs(d[0] * dirs[0]![0] + d[1] * dirs[0]![1]) >= 0.97);
  };
  const schemeOpen: Open[] = [];
  for (const w of works) {
    const role = w.role!.code;
    const sr = spanRatioOf(w);
    const r = schemeRule({ role, ifcClass: w.input.ifcClass, ...(w.geo ? { thickness: w.geo.thickness } : {}), ...(sr !== undefined ? { spanRatio: sr } : {}), supportsTwoSided: twoSided(w), name: `${w.input.name} ${w.input.type?.name ?? ''}` });
    if (!r) continue;
    if (r.confidence >= final || !/^(ONE_WAY|TWO_WAY)$/.test(r.code)) { w.scheme = { code: r.code, confidence: r.confidence, source: 'rule', needsReview: r.confidence < final, rationale: r.rationale }; continue; }
    schemeOpen.push({ w, options: SLAB_SCHEMES.map((c) => c.code), sig: `${Math.round((sr ?? 1) * 4)}#${w.role!.code}`, weak: { code: r.code, confidence: r.confidence, source: 'rule', needsReview: true, rationale: r.rationale }, extra: { span_ratio: sr ?? 1 } });
  }
  await ask('scheme', schemeOpen, SLAB_SCHEMES, (op, d) => { op.w.scheme = d; });

  // 7. marks and pour groups
  const marks = assignMarks(works.map((w) => {
    const tag = [propOf(w.input, 'PieceMark'), w.input.psets['Attr']?.['Tag']].find((t) => (typeof t === 'string' || typeof t === 'number') && isReadableMark(String(t)));
    const o3 = w.geo?.frame.origin ?? [0, 0, 0];
    return { id: w.id, role: w.role!.code, storey: w.item.storey ?? null, ...(typeof tag === 'string' || typeof tag === 'number' ? { ifcMark: String(tag) } : {}), x: o3[0], y: o3[1] };
  }));
  const groups = pourGroups(works.map((w) => ({ id: w.id, role: w.role!.code, method: w.method!.code, storey: w.item.storey ?? null, x: w.geo?.frame.origin[0] ?? 0, y: w.geo?.frame.origin[1] ?? 0 })), graph.touching);

  // 8. the sets
  const mk = (facet: ConcreteFacetId, d: Decided, label: string, fields: Record<string, FacetFieldValue>): ConcreteFacetResult => ({
    facet, code: d.code, label, confidence: r2(d.confidence), source: d.source, ...(d.model && d.source === 'model' ? { model: d.model } : {}), needsReview: d.needsReview, fields,
    ...(d.probabilities ? { probabilities: d.probabilities } : {}), ...(d.rationale ? { rationale: d.rationale } : {}),
  });
  for (const w of works) {
    const set: ConcreteSet = {};
    const g = w.geo;
    const role = w.role!, method = w.method!, reinf = w.reinf!;
    const spec = specOf(w.input, { role: role.code, ...(w.item.placement ? { placement: w.item.placement } : {}), ...(w.item.belowGround !== undefined ? { belowGround: w.item.belowGround } : {}), ground: isGroundRole(role.code) || groundSidesRole(role.code), cover, ...(o.defaultStandard ? { defaultStandard: o.defaultStandard } : {}) });
    if (on('ConcreteGeometry') && g) {
      const f: Record<string, FacetFieldValue> = {
        Volume: g.volume, VolumeEstimated: g.volumeEstimated, FormworkArea: g.formworkArea, TopArea: g.topArea, SoffitArea: g.soffitArea,
        FrameOrigin: vecText(g.frame.origin), FrameX: vecText(g.frame.x), FrameY: vecText(g.frame.y), FrameZ: vecText(g.frame.z),
        Length: g.length, Width: g.width, Thickness: g.thickness, SectionShape: g.sectionShape, Faces: facesText(g.faces),
      };
      if (w.restsOn.length) f['Supports'] = w.restsOn.slice(0, 20).map((id) => id).join(',');
      if (w.carries.length) f['Carries'] = w.carries.slice(0, 20).join(',');
      set.ConcreteGeometry = mk('ConcreteGeometry', { code: g.volumeEstimated ? 'ESTIMATED' : 'MEASURED', confidence: g.volumeEstimated ? 0.5 : 1, source: 'geometry', needsReview: g.volumeEstimated, rationale: g.volumeEstimated ? 'the mesh is not closed: volume is the bounds volume' : `${g.triangles} triangles` }, g.volumeEstimated ? 'Measured, volume estimated from bounds' : 'Measured', f);
    }
    if (on('ConcreteElement')) {
      const m = marks.get(w.id)!;
      const f: Record<string, FacetFieldValue> = { Mark: m.mark, MarkSource: m.source };
      if (w.item.storey !== null && w.item.storey !== undefined) f['Storey'] = w.item.storey;
      const pg = groups.get(w.id);
      if (pg) f['HostGroup'] = pg;
      set.ConcreteElement = mk('ConcreteElement', role, labelOf(ROLE_CODES, role.code), f);
    }
    if (on('ConcreteMethod')) set.ConcreteMethod = mk('ConcreteMethod', method, labelOf(METHOD_CODES, method.code), {});
    if (on('ConcreteSpec')) set.ConcreteSpec = mk('ConcreteSpec', { code: spec.code, confidence: spec.confidence, source: spec.source, needsReview: spec.needsReview, rationale: spec.rationale }, spec.code, spec.fields);
    if (on('ConcreteReinforcement')) {
      const f: Record<string, FacetFieldValue> = {};
      if (w.scheme) { f['Scheme'] = w.scheme.code; f['SchemeSource'] = w.scheme.source; }
      const ratio = spec.ifcRatio ?? ratioEstimate(role.code, reinf.code);
      f['RatioEstimate'] = ratio;
      f['RatioSource'] = spec.ifcRatio !== undefined ? 'ifc' : 'rule';
      if (g && !g.volumeEstimated) f['MassEstimate'] = Math.round(ratio * g.volume * 10) / 10;
      set.ConcreteReinforcement = mk('ConcreteReinforcement', reinf, labelOf(REINFORCEMENT_CODES, reinf.code), f);
    }
    for (const r of Object.values(set)) if (r.needsReview) stats.needsReview++;
    results.set(w.id, set);
  }
  stats.aborted = signal.aborted;
  o.signal?.removeEventListener('abort', stop);
  cache.flush();
  return { results, geometry, stats };
}
