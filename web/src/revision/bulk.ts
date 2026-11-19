// Bulk rules of the revision walk (design 3.6): each rule selects diff entries, the UI shows the count and highlights them before the
// rule is applied as one undo step. Pure: `selectBulk` only filters.

import type { ResultSource } from '../classify/types';
import { stripFederation } from './snapshot';
import type { BulkRule, DiffEntry, ModelSnapshot } from './types';

/** What a rule needs to know about an entry beyond the entry itself. */
export interface BulkInfo {
  ifcClass: string;
  storey: string;
  /** Issues and sketches attached to the element. */
  attachments: number;
  /** The head result needs review (new and re-run elements). */
  needsReview: boolean;
  source?: ResultSource;
}

export interface BulkContext {
  infoOf(entry: DiffEntry): BulkInfo;
}

/** Defaults of the shipped rules; the numbers are editable in the UI. maxMoveMm is millimetres, the rule stores metres. */
export const BULK_DEFAULTS = { maxMoveMm: 10, minScore: 0.95 } as const;

export const BULK_RULE_IDS = ['placement-moves', 'property-only', 'rematch-high', 'deleted-clean', 'new-by-rules', 'current-filter'] as const;

export function shippedRules(p: { maxMoveMm?: number; minScore?: number } = {}): BulkRule[] {
  const mm = p.maxMoveMm ?? BULK_DEFAULTS.maxMoveMm;
  const score = p.minScore ?? BULK_DEFAULTS.minScore;
  return [
    { id: 'placement-moves', label: `Accept placement-only moves up to ${mm} mm`, category: 'changed', flagsWithin: ['placement'], maxMove: mm / 1000, excludeRotated: true },
    { id: 'property-only', label: 'Accept property-only changes that do not affect the classification', category: 'changed', flagsWithin: ['properties'], classifyAffected: false },
    { id: 'rematch-high', label: `Accept rematches with score ${score.toFixed(2)} or more`, category: 'rematched', minScore: score },
    { id: 'deleted-clean', label: 'Acknowledge deletions with nothing attached', category: 'deleted', noAttachments: true },
    { id: 'new-by-rules', label: 'Accept new elements classified by a rule and not needing review', category: 'new', needsReview: false, rulesOnly: true },
    { id: 'current-filter', label: 'Everything in the current filter' },
  ];
}

export function selectBulk(entries: readonly DiffEntry[], rule: BulkRule, ctx: BulkContext): DiffEntry[] {
  return entries.filter((e) => {
    if (rule.category && e.category !== rule.category) return false;
    if (rule.flagsWithin) {
      if (e.flags.length === 0) return false;
      if (!e.flags.every((f) => rule.flagsWithin!.includes(f))) return false;
    }
    if (rule.maxMove !== undefined && !(e.move !== undefined && e.move <= rule.maxMove + 1e-12)) return false;
    if (rule.excludeRotated && e.rotated) return false;
    if (rule.minScore !== undefined && !((e.score ?? 0) >= rule.minScore - 1e-12)) return false;
    if (rule.classifyAffected !== undefined && e.classifyAffected !== rule.classifyAffected) return false;
    const needs = rule.noAttachments !== undefined || rule.needsReview !== undefined || rule.rulesOnly || rule.storey !== undefined || rule.ifcClass !== undefined;
    if (needs) {
      const info = ctx.infoOf(e);
      if (rule.noAttachments && info.attachments > 0) return false;
      if (rule.needsReview !== undefined && info.needsReview !== rule.needsReview) return false;
      if (rule.rulesOnly && info.source !== 'rules') return false;
      if (rule.storey !== undefined && info.storey !== rule.storey) return false;
      if (rule.ifcClass !== undefined && info.ifcClass !== rule.ifcClass) return false;
    }
    return true;
  });
}

/** A BulkContext over the two snapshots. `attachments` counts issues and sketches by GlobalId (default: none). */
export function bulkContextOf(base: ModelSnapshot, head: ModelSnapshot, attachments: (globalId: string) => number = () => 0): BulkContext {
  const idx = (s: ModelSnapshot): Map<string, number> => new Map(s.globalId.map((g, i) => [g, i]));
  const bi = idx(base), hi = idx(head);
  return {
    infoOf(e) {
      const inHead = e.category !== 'deleted';
      const s = inHead ? head : base;
      const i = (inHead ? hi : bi).get((inHead ? e.head : e.base)!) ?? -1;
      const r = i >= 0 ? s.results[i] : null;
      return {
        ifcClass: i >= 0 ? s.ifcClass[i]! : '',
        storey: (i >= 0 ? s.storey[i]?.name : '') ?? '',
        attachments: attachments(stripFederation(e.base ?? e.head ?? '')) + (e.base && e.head && e.base !== e.head ? attachments(e.head) : 0),
        needsReview: r ? r.needsReview : true,
        ...(r ? { source: r.source } : {}),
      };
    },
  };
}
