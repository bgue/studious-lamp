// The 4D linker: activities <-> model elements, tiers of docs/design/4d-xer-animation.md section 3.1 that work without a UI.
//
//   manual     accepted ActivityLinks given in `opts.priorLinks` (a person or agent decided; confidence 1)
//   native     IfcTask assignments (an optional map GlobalId -> task codes from the model reader)
//   property   an element property holding activity ids (opts.idProperty, comma separated)
//   override   config.activities[code].query / globalIds
//   attributes elements whose location / trade / zone equal the activity's (each optional)
//   suggested  proposals from activity names and WBS tokens: status 'proposed', NEVER accepted automatically
//
// Explicit tiers (manual, native, property, override) of an activity replace its attribute inference. An element wanted by
// several building activities goes to the most specific claim (manual > native > property > override > three attributes > two >
// one); equal specificity is a tie and the element is not linked. Milestones, LOE and WBS summaries never get elements.
// Output is the LinkML JSON form (snake_case; see schema/linkml/xray_4d.yaml). Only `accepted` rows drive the plan.

import { compile, parseQuery, QueryError } from '../query';
import type {
  ActivityLink, Assignment, FourDConfig, FourDLinks, LinkActivity, LinkElement, LinkSource, LinkTie, Schedule, ScheduleTask, SplitRule,
} from './types';
import { acceptedAssignments, describeSource, elementAttributes, sameValue, scheduleAttributes, taskRawAttributes } from './attrs';
import type { Attrs } from './attrs';
import { FourDTable, guidHash } from './model';
import type { FourDElement, FourDModel } from './model';
import { isBuildType, isCritical, plannedSpan, resolveSplit } from './planTime';

export interface LinkOptions {
  /** Element property holding activity ids ('Pset_4D.ActivityId'); several codes separated by comma or semicolon. */
  idProperty?: string;
  /** Native IfcTask assignments: GlobalId -> task codes. */
  native?: Map<string, string[]> | Record<string, string[]>;
  /** Links from an earlier run or from people: accepted ones are kept (and win), the others are passed through. */
  priorLinks?: ActivityLink[];
  /** Propose links for the activities left over (default true). */
  suggest?: boolean;
  /** Suggestions below this confidence are dropped (default 0.3). */
  minSuggestConfidence?: number;
  /** Written as `created_at` of the dataset and of new links (omitted when absent: output is deterministic). */
  createdAt?: string;
  scheduleFileName?: string;
  modelFileName?: string;
  onWarning?: (message: string) => void;
}

type Tier = 'manual' | 'native' | 'property' | 'override' | 'attributes';
const TIER_RANK: Record<Tier, number> = { manual: 7, native: 6, property: 5, override: 4, attributes: 0 };
const TIER_SOURCE: Record<Tier, LinkSource> = { manual: 'manual', native: 'native', property: 'property', override: 'override', attributes: 'attributes' };
const TIER_ORDER: Tier[] = ['manual', 'native', 'property', 'override', 'attributes'];

interface Claim { rank: number; tier: Tier }
interface TaskClaims {
  task: ScheduleTask;
  tiers: Map<Tier, number>;           // elements claimed per tier
  claims: Map<number, Claim>;         // element index -> its best claim
  reasons: string[];
  rule?: string;
  specificity: number;                // attribute count (attributes tier)
  confidence: number;
}

function compact<T extends object>(o: T): T {
  for (const k of Object.keys(o) as Array<keyof T>) if (o[k] === undefined) delete o[k];
  return o;
}

const byCodeKey = (s: string): string => s.trim().toLowerCase();

/** Link a schedule to a model. See the file header. */
export function linkSchedule(schedule: Schedule, model: FourDModel, config: FourDConfig, assignments: Assignment[], opts: LinkOptions = {}): FourDLinks {
  const warn = opts.onWarning ?? (() => undefined);
  const els = model.elements;
  const table = new FourDTable(model);
  const accepted = acceptedAssignments(assignments);
  const taskAttrs = scheduleAttributes(schedule, config);
  const elAttrs: Attrs[] = els.map((e) => elementAttributes(e, config, accepted));
  const idxOf = new Map(els.map((e, i) => [e.globalId, i]));

  const queryCache = new Map<string, number[]>();
  const runQuery = (text: string, what: string): number[] => {
    const hit = queryCache.get(text);
    if (hit) return hit;
    let out: number[] = [];
    try {
      const c = compile(parseQuery(text), table);
      for (let r = 0; r < table.size; r++) if (c.test(r)) out.push(r);
    } catch (e) {
      if (!(e instanceof QueryError)) throw e;
      warn(`${what}: query "${text}" is not valid (${e.message})`);
      out = [];
    }
    queryCache.set(text, out);
    return out;
  };

  const existing = new Set<number>(config.model.existing ? runQuery(config.model.existing, 'model.existing') : []);

  // trade value -> query result set
  const tradeSets = new Map<string, Set<number>>();
  const tradeSetFor = (raw: string | undefined, mapped: string | undefined): Set<number> | undefined => {
    const q = config.tradeQueries;
    if (!q) return undefined;
    for (const key of [mapped, raw]) {
      if (key === undefined) continue;
      const k = Object.keys(q).find((x) => x === key) ?? Object.keys(q).find((x) => sameValue(x, key));
      if (k === undefined) continue;
      if (!tradeSets.has(k)) tradeSets.set(k, new Set(runQuery(q[k]!, `tradeQueries[${k}]`)));
      return tradeSets.get(k);
    }
    return undefined;
  };

  const buildTasks = schedule.tasks.filter(isBuildType);
  const codeLookup = new Map<string, string>();
  for (const t of schedule.tasks) codeLookup.set(byCodeKey(t.code), t.code);

  const perTask = new Map<string, TaskClaims>();
  const claimsOf = (t: ScheduleTask): TaskClaims => {
    let c = perTask.get(t.code);
    if (!c) { c = { task: t, tiers: new Map(), claims: new Map(), reasons: [], specificity: 0, confidence: 1 }; perTask.set(t.code, c); }
    return c;
  };
  const addClaim = (t: ScheduleTask, idx: number, tier: Tier, specificity = 0): void => {
    const c = claimsOf(t);
    const rank = tier === 'attributes' ? specificity : TIER_RANK[tier];
    const prev = c.claims.get(idx);
    if (!prev) c.tiers.set(tier, (c.tiers.get(tier) ?? 0) + 1);
    if (!prev || prev.rank < rank) c.claims.set(idx, { rank, tier });
  };

  // ---- prior links
  const prior = opts.priorLinks ?? [];
  const removeClaims = new Map<string, { link: ActivityLink; idxs: number[] }>();
  const passThrough: ActivityLink[] = [];
  const manualTasks = new Set<string>();
  const taskByCode = new Map(schedule.tasks.map((t) => [t.code, t]));
  for (const l of prior) {
    if (l.status !== 'accepted') { passThrough.push({ ...l }); continue; }
    const t = taskByCode.get(l.activity);
    if (!t) { warn(`prior link ${l.id}: unknown activity ${l.activity}`); passThrough.push({ ...l }); continue; }
    const idxs = l.elements.map((g) => idxOf.get(g)).filter((x): x is number => x !== undefined);
    if (l.role === 'remove') { removeClaims.set(`${l.activity}`, { link: l, idxs }); continue; }
    if (!isBuildType(t)) { warn(`prior link ${l.id}: ${t.code} is a ${t.type}, it cannot build elements`); passThrough.push({ ...l }); continue; }
    manualTasks.add(t.code);
    for (const i of idxs) addClaim(t, i, 'manual');
    const c = claimsOf(t);
    c.reasons.push(...(l.reasons ?? []), `kept from ${l.id} (${l.elements.length} elements, ${l.source ?? 'manual'})`);
  }

  // ---- native and property
  const nativeMap = opts.native instanceof Map ? opts.native : new Map(Object.entries(opts.native ?? {}));
  const codeFor = (s: string): ScheduleTask | undefined => {
    const c = codeLookup.get(byCodeKey(s));
    return c ? taskByCode.get(c) : undefined;
  };
  for (let i = 0; i < els.length; i++) {
    const nat = nativeMap.get(els[i]!.globalId);
    if (nat) for (const code of nat) { const t = codeFor(code); if (t && isBuildType(t) && !manualTasks.has(t.code)) addClaim(t, i, 'native'); }
    if (opts.idProperty) {
      const raw = readProp(els[i]!, opts.idProperty);
      if (raw) for (const code of raw.split(/[,;]/)) { const t = codeFor(code); if (t && isBuildType(t) && !manualTasks.has(t.code)) addClaim(t, i, 'property'); }
    }
  }
  for (const c of perTask.values()) {
    const n = c.tiers.get('native');
    const p = c.tiers.get('property');
    if (n) c.reasons.push(`native IfcTask assignment: ${n} element${n === 1 ? '' : 's'}`);
    if (p) c.reasons.push(`property ${opts.idProperty} names ${c.task.code}: ${p} element${p === 1 ? '' : 's'}`);
  }

  // ---- overrides and attributes
  const explicit = new Set<string>([...perTask.keys()]);
  const removeRoleTasks = new Set<string>();
  for (const t of buildTasks) {
    const ov = config.activities?.[t.code];
    const isRemove = ov?.role === 'remove';
    if (ov && (ov.query || ov.globalIds?.length) && !manualTasks.has(t.code)) {
      const idxs: number[] = [];
      if (ov.query) idxs.push(...runQuery(ov.query, `activities[${t.code}]`));
      for (const g of ov.globalIds ?? []) { const i = idxOf.get(g); if (i === undefined) warn(`activities[${t.code}]: GlobalId ${g} is not in the model`); else idxs.push(i); }
      if (isRemove) {
        removeRoleTasks.add(t.code);
        const u = [...new Set(idxs)].sort((a, b) => a - b);
        removeClaims.set(t.code, { link: { id: `ln-${t.code}-remove`, activity: t.code, role: 'remove', elements: [], source: 'override', confidence: 1, reasons: [`activity override (remove): ${describeOverride(ov)}`], status: 'accepted' }, idxs: u });
      } else {
        for (const i of idxs) addClaim(t, i, 'override');
        const c = claimsOf(t);
        c.reasons.push(`activity override: ${describeOverride(ov)} (${c.tiers.get('override') ?? 0} elements)`);
        c.rule = ov.query ? `query:${ov.query}` : 'globalIds';
      }
      explicit.add(t.code);
    }
  }
  for (const t of buildTasks) {
    if (explicit.has(t.code) || manualTasks.has(t.code)) continue;
    const a = taskAttrs.get(t.code) ?? {};
    const raw = taskRawAttributes(t, config);
    const n = (a.location !== undefined ? 1 : 0) + (a.trade !== undefined ? 1 : 0) + (a.zone !== undefined ? 1 : 0);
    if (n === 0) continue;
    const isRemove = config.activities?.[t.code]?.role === 'remove';
    const tset = a.trade !== undefined ? tradeSetFor(raw.trade, a.trade) : undefined;
    const matched: number[] = [];
    for (let i = 0; i < els.length; i++) {
      if (!isRemove && existing.has(i)) continue;
      const ea = elAttrs[i]!;
      if (a.location !== undefined && !sameValue(ea.location, a.location)) continue;
      if (a.zone !== undefined && !sameValue(ea.zone, a.zone)) continue;
      if (a.trade !== undefined) {
        if (ea.trade !== undefined ? !sameValue(ea.trade, a.trade) : !(tset?.has(i))) continue;
      }
      matched.push(i);
    }
    const parts: string[] = [];
    const rules: string[] = [];
    if (a.location !== undefined) { parts.push(`location ${a.location}${raw.location !== a.location ? ` from ${describeSource(t, config.schedule.location)}=${raw.location}` : ` from ${describeSource(t, config.schedule.location)}`}`); rules.push(`location=${a.location}`); }
    if (a.zone !== undefined) { parts.push(`zone ${a.zone}${raw.zone !== a.zone ? ` from ${describeSource(t, config.schedule.zone)}=${raw.zone}` : ` from ${describeSource(t, config.schedule.zone)}`}`); rules.push(`zone=${a.zone}`); }
    if (a.trade !== undefined) {
      parts.push(`trade ${a.trade}${raw.trade !== a.trade ? ` from ${describeSource(t, config.schedule.trade)}=${raw.trade}` : ` from ${describeSource(t, config.schedule.trade)}`}${tset ? ' (elements without a trade via tradeQueries)' : ''}`);
      rules.push(`trade=${a.trade}`);
    }
    if (isRemove) {
      removeRoleTasks.add(t.code);
      removeClaims.set(t.code, { link: { id: `ln-${t.code}-remove`, activity: t.code, role: 'remove', elements: [], source: 'attributes', confidence: SPEC_CONF[n], reasons: [`${parts.join(', ')} (remove)`], rule: rules.join('; '), status: 'accepted' }, idxs: matched });
      continue;
    }
    if (matched.length === 0) continue;
    for (const i of matched) addClaim(t, i, 'attributes', n);
    const c = claimsOf(t);
    c.specificity = n;
    c.confidence = SPEC_CONF[n]!;
    c.rule = rules.join('; ');
    c.reasons.push(`${parts.join(', ')}: ${n} of 3 attributes, ${matched.length} candidate element${matched.length === 1 ? '' : 's'}`);
  }

  // ---- resolve claims: one constructing activity per element
  const wanted = new Map<number, Array<{ code: string; rank: number }>>();
  for (const [code, c] of perTask) for (const [i, cl] of c.claims) {
    if (!wanted.has(i)) wanted.set(i, []);
    wanted.get(i)!.push({ code, rank: cl.rank });
  }
  const winner = new Map<number, string>();
  const ties: LinkTie[] = [];
  const lost = new Map<string, number>();
  const tied = new Map<string, number>();
  for (const [i, list] of [...wanted].sort((a, b) => a[0] - b[0])) {
    const best = Math.max(...list.map((x) => x.rank));
    const top = list.filter((x) => x.rank === best);
    for (const x of list) if (x.rank < best) lost.set(x.code, (lost.get(x.code) ?? 0) + 1);
    if (top.length === 1) winner.set(i, top[0]!.code);
    else {
      ties.push({ element: els[i]!.globalId, candidates: top.map((x) => x.code).sort() });
      for (const x of top) tied.set(x.code, (tied.get(x.code) ?? 0) + 1);
    }
  }

  const stamp = opts.createdAt;
  const links: ActivityLink[] = [...passThrough];
  const usedIds = new Set(links.map((l) => l.id));
  const uniqueId = (base: string): string => { let id = base; for (let n = 2; usedIds.has(id); n++) id = `${base}-${n}`; usedIds.add(id); return id; };
  const winnersOf = new Map<string, number[]>();
  for (const [i, code] of winner) { if (!winnersOf.has(code)) winnersOf.set(code, []); winnersOf.get(code)!.push(i); }

  for (const t of buildTasks) {
    const c = perTask.get(t.code);
    const ws = (winnersOf.get(t.code) ?? []).sort((a, b) => a - b);
    if (!c || ws.length === 0) continue;
    const tiersUsed = TIER_ORDER.filter((tr) => ws.some((i) => c.claims.get(i)!.tier === tr));
    const reasons = [...c.reasons];
    if (lost.get(t.code)) reasons.push(`${lost.get(t.code)} candidate element(s) went to a more specific activity`);
    if (tied.get(t.code)) reasons.push(`${tied.get(t.code)} candidate element(s) are tied with another activity and left unlinked`);
    const conf = tiersUsed.includes('attributes') ? c.confidence : 1;
    const split = resolveSplit(t.code, taskAttrs.get(t.code)?.trade, config);
    const manualPrior = prior.find((l) => l.status === 'accepted' && l.role === 'build' && l.activity === t.code);
    const link: ActivityLink = compact({
      id: manualPrior?.id ?? uniqueId(`ln-${t.code}-build`),
      activity: t.code,
      role: 'build',
      elements: ws.map((i) => els[i]!.globalId),
      source: TIER_SOURCE[tiersUsed[0]!],
      confidence: conf,
      reasons,
      split: manualPrior?.split ?? (split === 'none' && !hasSplitRule(t.code, config) ? undefined : split),
      rule: c.rule,
      status: 'accepted' as const,
      created_at: manualPrior?.created_at ?? stamp,
      reviewed_by: manualPrior?.reviewed_by,
      reviewed_at: manualPrior?.reviewed_at,
    });
    if (manualPrior) usedIds.add(link.id);
    links.push(link);
  }
  // remove links
  for (const [code, r] of removeClaims) {
    const idxs = r.idxs.filter((i, k, a) => a.indexOf(i) === k).sort((a, b) => a - b);
    if (!idxs.length) continue;
    const t = taskByCode.get(code);
    const link: ActivityLink = compact({ ...r.link, id: r.link.id, elements: idxs.map((i) => els[i]!.globalId), split: r.link.split ?? (t ? optionalSplit(code, taskAttrs.get(code)?.trade, config) : undefined), created_at: r.link.created_at ?? stamp });
    usedIds.add(link.id);
    links.push(link);
  }

  // ---- suggestions for the activities left over
  const hasBuild = new Set(links.filter((l) => l.status === 'accepted' && l.role === 'build').map((l) => l.activity));
  const blocked = new Set(prior.filter((l) => l.role === 'build' && l.status !== 'superseded').map((l) => l.activity));
  if (opts.suggest !== false) {
    const claimed = new Set<number>(winner.keys());
    const min = opts.minSuggestConfidence ?? 0.3;
    const ctx = suggestContext(model, existing, claimed);
    for (const t of buildTasks) {
      if (hasBuild.has(t.code) || blocked.has(t.code) || perTask.has(t.code) || config.activities?.[t.code]?.role === 'remove') continue;
      const s = suggestFor(t, ctx);
      if (!s || s.confidence < min) continue;
      links.push(compact({
        id: uniqueId(`ln-${t.code}-build`), activity: t.code, role: 'build' as const, elements: s.elements.map((i) => els[i]!.globalId),
        source: 'suggested' as const, confidence: s.confidence, reasons: s.reasons, rule: s.query, status: 'proposed' as const, created_at: stamp,
      }));
    }
  }

  // ---- the dataset
  const linkedCodes = new Set(links.filter((l) => l.status === 'accepted' && l.role === 'build' && l.elements.length).map((l) => l.activity));
  const linkedEls = new Set<string>();
  for (const l of links) if (l.status === 'accepted' && l.role === 'build') for (const g of l.elements) linkedEls.add(g);
  const removedEls = new Set<string>();
  for (const l of links) if (l.status === 'accepted' && l.role === 'remove') for (const g of l.elements) removedEls.add(g);

  const activities: LinkActivity[] = schedule.tasks.map((t) => {
    const a = taskAttrs.get(t.code) ?? {};
    const sp = plannedSpan(t);
    return compact<LinkActivity>({
      task_code: t.code, name: t.name, wbs_path: t.wbsPath.join('/'), activity_type: t.type, activity_status: t.status,
      start: sp ? t.dates.earlyStart ?? t.dates.targetStart ?? t.dates.earlyEnd ?? t.dates.targetEnd : undefined,
      finish: sp ? t.dates.earlyEnd ?? t.dates.targetEnd ?? t.dates.earlyStart ?? t.dates.targetStart : undefined,
      location: a.location, trade: a.trade, zone: a.zone, critical: isCritical(t, config.style),
    });
  });
  const model_elements: LinkElement[] = els.map((e, i) => {
    const a = elAttrs[i]!;
    return compact<LinkElement>({ global_id: e.globalId, ifc_class: e.ifcClass, name: e.name || undefined, storey: e.storey, location: a.location, trade: a.trade, zone: a.zone, existing: existing.has(i) ? true : undefined });
  });

  const dataDate = schedule.project.dataDate;
  return compact<FourDLinks>({
    id: `links-${schedule.sourceHash.slice(0, 8)}-${guidHash([model.identityKey])}`,
    model: compact({ identity_key: model.identityKey, name: model.name, file_name: opts.modelFileName }),
    schedule: compact({ source_hash: schedule.sourceHash, project: schedule.project.shortName, data_date: dataDate, file_name: opts.scheduleFileName }),
    created_at: stamp,
    tool: 'xray-4d link',
    activities,
    model_elements,
    assignments: (assignments ?? []).map((a) => ({ ...a })),
    links,
    ties,
    unlinked_activities: buildTasks.filter((t) => !linkedCodes.has(t.code)).map((t) => t.code),
    unlinked_elements: els.filter((e, i) => !linkedEls.has(e.globalId) && !existing.has(i) && !removedEls.has(e.globalId)).map((e) => e.globalId),
  });
}

const SPEC_CONF: Record<number, number> = { 1: 0.6, 2: 0.8, 3: 0.9 };

function hasSplitRule(code: string, config: FourDConfig): boolean {
  return !!config.activities?.[code]?.split || !!config.split;
}
function optionalSplit(code: string, trade: string | undefined, config: FourDConfig): SplitRule | undefined {
  return hasSplitRule(code, config) ? resolveSplit(code, trade, config) : undefined;
}
function describeOverride(ov: { query?: string; globalIds?: string[] }): string {
  const p: string[] = [];
  if (ov.query) p.push(`query "${ov.query}"`);
  if (ov.globalIds?.length) p.push(`${ov.globalIds.length} GlobalId${ov.globalIds.length === 1 ? '' : 's'}`);
  return p.join(' + ');
}
function readProp(e: FourDElement, key: string): string | undefined {
  const v = e.props[key];
  if (v !== undefined && v !== '') return v;
  const l = key.toLowerCase();
  for (const k in e.props) if (k.toLowerCase() === l && e.props[k] !== '') return e.props[k];
  return undefined;
}

// ---------------------------------------------------------------- suggestions

const CLASS_WORDS: Array<[RegExp, string[]]> = [
  [/\b(slabs?|pours?|deck|screed|topping)\b/, ['IfcSlab']],
  [/\b(columns?|cols?)\b/, ['IfcColumn']],
  [/\b(beams?|girders?)\b/, ['IfcBeam']],
  [/\b(walls?|partitions?|drywall|blockwork|masonry|studs?)\b/, ['IfcWall', 'IfcWallStandardCase']],
  [/\b(curtain ?wall|facade|façade|cladding)\b/, ['IfcCurtainWall', 'IfcPlate', 'IfcMember']],
  [/\b(doors?)\b/, ['IfcDoor']],
  [/\b(windows?|glazing)\b/, ['IfcWindow']],
  [/\b(roof|roofing)\b/, ['IfcRoof']],
  [/\b(stairs?|staircase)\b/, ['IfcStair', 'IfcStairFlight']],
  [/\b(footings?|foundations?|piles?)\b/, ['IfcFooting', 'IfcPile']],
  [/\b(ducts?|ductwork|hvac|ahu)\b/, ['IfcDuctSegment', 'IfcDuctFitting', 'IfcAirTerminal']],
  [/\b(pipes?|piping|plumbing|sprinklers?|risers?)\b/, ['IfcPipeSegment', 'IfcPipeFitting']],
  [/\b(cable ?trays?|conduits?|electrical|lighting|luminaires?)\b/, ['IfcCableCarrierSegment', 'IfcCableSegment', 'IfcLightFixture']],
  [/\b(ceilings?)\b/, ['IfcCovering']],
  [/\b(railings?|balustrades?|handrails?)\b/, ['IfcRailing']],
];

interface SuggestCtx {
  model: FourDModel;
  free: number[];                     // element indices nobody builds (not existing, not linked)
  storeys: string[];
  zones: string[];
  classes: Set<string>;
  total: number;
}

function suggestContext(model: FourDModel, existing: Set<number>, claimed: Set<number>): SuggestCtx {
  const free: number[] = [];
  model.elements.forEach((_e, i) => { if (!existing.has(i) && !claimed.has(i)) free.push(i); });
  const storeys = [...new Set(model.elements.map((e) => e.storey).filter((s): s is string => !!s))];
  const zones = [...new Set(model.elements.map((e) => e.zone).filter((s): s is string => !!s))];
  return { model, free, storeys, zones, classes: new Set(model.elements.map((e) => e.ifcClass)), total: model.elements.length - existing.size };
}

/** Level numbers a text or a storey name refers to ('L3', 'Level 03', '3rd floor', 'GF' -> 0), as 'n:3' keys; 'roof'. */
export function levelKeys(text: string): Set<string> {
  const t = text.toLowerCase();
  const keys = new Set<string>();
  for (const m of t.matchAll(/\b(?:level|lvl|l|floor|fl|storey|story|lv)[\s_.-]*0*(\d{1,3})\b/g)) keys.add(`n:${Number(m[1])}`);
  for (const m of t.matchAll(/\b0*(\d{1,3})(?:st|nd|rd|th)?[\s_-]*(?:floor|fl|level|storey|story)\b/g)) keys.add(`n:${Number(m[1])}`);
  for (const m of t.matchAll(/\b0*(\d{1,3})f\b/g)) keys.add(`n:${Number(m[1])}`);
  for (const m of t.matchAll(/\b(?:basement|bsmt|b)[\s_-]*0*(\d{1,2})\b/g)) keys.add(`n:-${Number(m[1])}`);
  if (/\b(ground|gf|g\/f)\b/.test(t)) keys.add('n:0');
  if (/\broof\b/.test(t)) keys.add('roof');
  if (/\bbasement\b/.test(t) && ![...keys].some((k) => k.startsWith('n:-'))) keys.add('n:-1');
  return keys;
}

const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const phrase = (text: string, name: string): boolean => name.trim().length >= 2 && new RegExp(`(^|[^a-z0-9])${escapeRe(name.trim().toLowerCase())}($|[^a-z0-9])`).test(text);

interface Suggestion { elements: number[]; confidence: number; reasons: string[]; query: string }

function suggestFor(t: ScheduleTask, ctx: SuggestCtx): Suggestion | undefined {
  const text = `${t.name} / ${t.wbsPath.join(' / ')}`.toLowerCase();
  const reasons: string[] = [];
  const classes = new Set<string>();
  for (const [re, cls] of CLASS_WORDS) {
    const m = re.exec(text);
    if (!m) continue;
    const present = cls.filter((c) => ctx.classes.has(c));
    if (!present.length) continue;
    present.forEach((c) => classes.add(c));
    reasons.push(`${present.join(', ')} from '${m[0]}'`);
  }
  const tk = levelKeys(text);
  const storeys: string[] = [];
  for (const s of ctx.storeys) {
    const sk = levelKeys(s);
    const viaNum = [...sk].find((k) => tk.has(k));
    if (viaNum !== undefined || phrase(text, s)) { storeys.push(s); reasons.push(`storey '${s}' from '${viaNum !== undefined ? levelToken(text, viaNum) : s.toLowerCase()}'`); }
  }
  const zones = ctx.zones.filter((z) => phrase(text, z));
  zones.forEach((z) => reasons.push(`zone '${z}' from '${z.toLowerCase()}'`));
  if (!classes.size && !storeys.length && !zones.length) return undefined;
  const els = ctx.model.elements;
  const cand = ctx.free.filter((i) => {
    const e = els[i]!;
    return (!classes.size || classes.has(e.ifcClass)) && (!storeys.length || (e.storey !== undefined && storeys.includes(e.storey))) && (!zones.length || (e.zone !== undefined && zones.includes(e.zone)));
  });
  if (!cand.length) return undefined;
  let conf = (classes.size ? 0.35 : 0) + (storeys.length ? 0.3 : 0) + (zones.length ? 0.15 : 0);
  if (classes.size && storeys.length) conf += 0.15;
  if (!classes.size) conf = Math.min(conf, 0.35);
  if (cand.length > 0.5 * ctx.total) conf *= 0.7;
  conf = Math.round(Math.min(conf, 0.85) * 100) / 100;
  reasons.push(`${cand.length} unclaimed element${cand.length === 1 ? '' : 's'} match`);
  const q: string[] = [];
  const list = (xs: string[]): string => xs.map((x) => `'${x.replace(/'/g, "''")}'`).join(', ');
  if (classes.size) q.push(`class IN (${list([...classes])})`);
  if (storeys.length) q.push(`storey IN (${list(storeys)})`);
  if (zones.length) q.push(`zone IN (${list(zones)})`);
  return { elements: cand, confidence: conf, reasons, query: q.join(' AND ') };
}

/** The words of the text that produced a level key, for the evidence line. */
function levelToken(text: string, key: string): string {
  const n = key.slice(2);
  const m = new RegExp(`\\b(?:(?:level|lvl|l|floor|fl|storey|story|lv)[\\s_.-]*0*${n}|0*${n}(?:st|nd|rd|th)?[\\s_-]*(?:floor|fl|level|storey|story)|0*${n}f)\\b`).exec(text);
  return m ? m[0] : key === 'n:0' ? 'ground' : key;
}
