// Suggestions for the three attributes, each with a confidence and the reasons (status `proposed`; a person accepts or rejects them).
//   location  the storey that contains the element                      0.90
//   zone      the zone that groups the element                          0.90
//   trade     the IFC class (class table, with material rules)          0.70 (0.85 when a material rule matched)
//             the classifier's discipline                               0.9 x its confidence
//             the classifier's MasterFormat division                    0.85 x its confidence
//             agreeing evidence raises the confidence by 0.05 per extra source (at most 0.99); the best evidence names the trade.
// Pure: no DOM. Tested in tests/map4d-suggest.test.ts.

import type { Assignment, AttributeKind } from '../schedule/types';
import type { ClassifyResult } from '../classify/types';
import { acceptedValues, makeAssignments, newId } from './assignments';
import type { ElementValues } from './assignments';
import { DEFAULT_CLASS_TRADE, DISCIPLINE_TRADE, DIVISION_TRADE } from './values';

export interface SuggestElement {
  globalId: string;
  ifcClass: string;
  name?: string;
  material?: string;
  /** The name of the storey that contains the element. */
  storey?: string | null;
  /** Names of the zones that group the element. */
  zones?: readonly string[];
}

export interface SuggestOptions {
  classTrade?: Readonly<Record<string, string>>;
  disciplineTrade?: Readonly<Record<string, string>>;
  divisionTrade?: Readonly<Record<string, string>>;
  results?: ReadonlyMap<string, ClassifyResult>;
  attributes?: readonly AttributeKind[];
  /** Existing records: an element that already has an accepted value, or the same proposal, gets none. */
  existing?: readonly Assignment[];
  now?: string;
  idGen?: () => string;
}

/** Classes that carry no work of their own. */
export const NO_TRADE_CLASSES: ReadonlySet<string> = new Set(['IfcSpace', 'IfcOpeningElement', 'IfcAnnotation', 'IfcGrid', 'IfcBuildingElementProxy', 'IfcVirtualElement']);

const round2 = (x: number): number => Math.round(x * 100) / 100;
const clamp01 = (x: number): number => Math.max(0, Math.min(1, x));

/** The trade a class gives, and whether a material rule decided it. */
export function tradeOfClass(table: Readonly<Record<string, string>>, ifcClass: string, material?: string): { trade: string; key: string; byMaterial: boolean } | null {
  const mat = (material ?? '').toLowerCase();
  const lc = ifcClass.toLowerCase();
  if (mat) {
    for (const [k, v] of Object.entries(table)) {
      const i = k.indexOf(':');
      if (i < 0 || k.slice(0, i).toLowerCase() !== lc) continue;
      const text = k.slice(i + 1).trim().toLowerCase();
      if (text && mat.includes(text)) return { trade: v, key: k, byMaterial: true };
    }
  }
  for (const [k, v] of Object.entries(table)) if (k.toLowerCase() === lc) return { trade: v, key: k, byMaterial: false };
  return null;
}

interface Evidence { trade: string; confidence: number; reason: string }

/** The trade proposals for one element: the evidence for each trade, the best first. */
export function tradeEvidence(e: SuggestElement, o: SuggestOptions): Evidence[] {
  const out: Evidence[] = [];
  if (!NO_TRADE_CLASSES.has(e.ifcClass)) {
    const c = tradeOfClass(o.classTrade ?? DEFAULT_CLASS_TRADE, e.ifcClass, e.material);
    if (c) out.push({ trade: c.trade, confidence: c.byMaterial ? 0.85 : 0.7, reason: c.byMaterial ? `${e.ifcClass} with material "${e.material}" gives ${c.trade}` : `${e.ifcClass} gives ${c.trade}` });
  }
  const r = o.results?.get(e.globalId);
  if (r) {
    const t = (o.disciplineTrade ?? DISCIPLINE_TRADE)[r.discipline.code];
    if (t) out.push({ trade: t, confidence: round2(0.9 * clamp01(r.discipline.confidence)), reason: `Classifier discipline ${r.discipline.label} (${r.discipline.code}, confidence ${round2(r.discipline.confidence)}) gives ${t}` });
    const div = r.masterformat?.division?.slice(0, 2);
    const dt = div ? (o.divisionTrade ?? DIVISION_TRADE)[div] : undefined;
    if (dt && r.masterformat) out.push({ trade: dt, confidence: round2(0.85 * clamp01(r.masterformat.confidence)), reason: `Classifier MasterFormat division ${r.masterformat.division} ${r.masterformat.title} gives ${dt}` });
  }
  return out;
}

/** Combine evidence into one proposal: the strongest trade, raised when other evidence agrees; disagreeing evidence is named in the reasons. */
export function combine(evidence: readonly Evidence[]): { value: string; confidence: number; reasons: string[] } | null {
  if (evidence.length === 0) return null;
  const by = new Map<string, Evidence[]>();
  for (const ev of evidence) by.set(ev.trade, [...(by.get(ev.trade) ?? []), ev]);
  let best: { trade: string; score: number; list: Evidence[] } | null = null;
  for (const [trade, list] of by) {
    const top = Math.max(...list.map((x) => x.confidence));
    const score = Math.min(0.99, top + 0.05 * (list.length - 1));
    if (!best || score > best.score) best = { trade, score, list };
  }
  const b = best!;
  const reasons = b.list.map((x) => x.reason);
  for (const [trade, list] of by) if (trade !== b.trade) reasons.push(`Not ${trade}: ${list.map((x) => x.reason).join('; ')}`);
  return { value: b.trade, confidence: round2(b.score), reasons };
}

/** Proposed records for the elements. Elements and attributes that already have an accepted value, or the same proposal, are skipped. */
export function suggest(elements: readonly SuggestElement[], o: SuggestOptions = {}): Assignment[] {
  const attrs = new Set(o.attributes ?? (['location', 'trade', 'zone'] as const));
  const have = acceptedValues(o.existing ?? []);
  const pending = new Set((o.existing ?? []).filter((a) => a.status === 'proposed').map((a) => `${a.element}|${a.attribute}|${a.value}`));
  const now = o.now ?? new Date().toISOString();
  const idGen = o.idGen ?? newId;
  const out: Assignment[] = [];
  const push = (e: SuggestElement, attr: AttributeKind, value: string, confidence: number, reasons: string[]): void => {
    if ((have.get(e.globalId) as ElementValues | undefined)?.[attr] !== undefined) return;
    if (pending.has(`${e.globalId}|${attr}|${value}`)) return;
    out.push(...makeAssignments([e.globalId], attr, value, { source: attr === 'trade' && reasons.some((r) => r.startsWith('Classifier')) ? 'classifier' : 'suggested', status: 'proposed', confidence, reasons, now, idGen }));
  };
  for (const e of elements) {
    if (attrs.has('location') && e.storey) push(e, 'location', e.storey, 0.9, [`Contained in storey "${e.storey}"`]);
    if (attrs.has('zone') && e.zones?.length) {
      const z = e.zones[0]!;
      push(e, 'zone', z, e.zones.length === 1 ? 0.9 : 0.7, [e.zones.length === 1 ? `Grouped in zone "${z}"` : `Grouped in zones ${e.zones.map((x) => `"${x}"`).join(', ')}; the first is proposed`]);
    }
    if (attrs.has('trade')) {
      const c = combine(tradeEvidence(e, o));
      if (c) push(e, 'trade', c.value, c.confidence, c.reasons);
    }
  }
  return out;
}
