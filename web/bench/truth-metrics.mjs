// Pure metric functions of bench/real-classify-truth.mjs (no I/O, no app imports), so that tests can import them.
//
// An ITEM is one scored answer to one question for one element (or one signature):
//   { key, pred, truth, ok, okLenient, conf, abstain, fallback, discOk? }
// `ok` strict, `okLenient` also accepts the truth's alternates, `conf` in 0..1 (rules: 1), `abstain` = no answer (counts as wrong,
// is left out of coverage and ECE), `fallback` = the answer is the schema's GEN/UNC fallback (or an abstain).

export const MIN_CONFIDENCE = 0.6;

/** Strict and lenient judgement of one answer. `alt` is the list of acceptable alternates (may be undefined). */
export function judge(pred, truth, alt = []) {
  const ok = pred !== null && pred !== undefined && pred === truth;
  const okLenient = ok || (pred !== null && pred !== undefined && (alt ?? []).includes(pred));
  return { ok, okLenient };
}

/** Build an item. `pred === null` is an abstain. */
export function makeItem({ key, pred, truth, alt = [], conf = 1, fallback = false, discOk }) {
  const abstain = pred === null || pred === undefined;
  const { ok, okLenient } = judge(pred, truth, alt);
  return { key, pred: abstain ? null : pred, truth, ok, okLenient, conf: abstain ? 0 : conf, abstain, fallback: abstain || fallback, ...(discOk === undefined ? {} : { discOk }) };
}

const rate = (num, den) => (den ? num / den : NaN);

export const accuracy = (items) => rate(items.filter((i) => i.ok).length, items.length);
export const lenientAccuracy = (items) => rate(items.filter((i) => i.okLenient).length, items.length);

/** Share of items that are answers with confidence at or above `min`. */
export const coverage = (items, min = MIN_CONFIDENCE) => rate(items.filter((i) => !i.abstain && i.conf >= min).length, items.length);

/** Accuracy among the answers that clear `min` (NaN when none does). `lenient` switches the judgement. */
export function precisionAtMin(items, min = MIN_CONFIDENCE, lenient = false) {
  const clear = items.filter((i) => !i.abstain && i.conf >= min);
  return rate(clear.filter((i) => (lenient ? i.okLenient : i.ok)).length, clear.length);
}

export const fallbackRate = (items) => rate(items.filter((i) => i.fallback).length, items.length);

/** Expected calibration error with `bins` equal-width bins over confidence (strict correctness; abstains left out). Confidence 1 goes in the last bin. */
export function ece(items, bins = 10) {
  const xs = items.filter((i) => !i.abstain);
  if (!xs.length) return NaN;
  const acc = new Array(bins).fill(0);
  const conf = new Array(bins).fill(0);
  const n = new Array(bins).fill(0);
  for (const i of xs) {
    const b = Math.min(bins - 1, Math.max(0, Math.floor(i.conf * bins)));
    n[b]++; conf[b] += i.conf; acc[b] += i.ok ? 1 : 0;
  }
  let e = 0;
  for (let b = 0; b < bins; b++) if (n[b]) e += (n[b] / xs.length) * Math.abs(acc[b] / n[b] - conf[b] / n[b]);
  return e;
}

/** The `k` most frequent wrong (truth -> pred) pairs. An abstain shows as "(abstain)". */
export function topConfusions(items, k = 5) {
  const m = new Map();
  for (const i of items) {
    if (i.ok) continue;
    const key = `${i.truth} -> ${i.abstain ? '(abstain)' : i.pred}`;
    m.set(key, (m.get(key) ?? 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, k).map(([pair, count]) => ({ pair, count }));
}

/** All the numbers for one set of items. */
export function summarise(items, min = MIN_CONFIDENCE) {
  return {
    n: items.length,
    accuracy: accuracy(items),
    lenient: lenientAccuracy(items),
    coverage: coverage(items, min),
    precision: precisionAtMin(items, min),
    precisionLenient: precisionAtMin(items, min, true),
    ece: ece(items),
    fallback: fallbackRate(items),
    confusions: topConfusions(items, 5),
  };
}

/**
 * Chained versus oracle sub-discipline (or division) bookkeeping. Both lists hold items with the same keys; the chained items carry
 * `discOk` (was the model's own discipline right?). It tells how much of the gap is the discipline answer feeding the next question.
 */
export function compareChainedOracle(chained, oracle) {
  const by = new Map(oracle.map((i) => [i.key, i]));
  const r = { n: 0, bothRight: 0, chainedOnly: 0, oracleOnly: 0, bothWrong: 0, chainedWrongDiscipline: 0, lostToDiscipline: 0, chainedAccuracy: NaN, oracleAccuracy: NaN, chainedAccuracyGivenDisciplineRight: NaN, gap: NaN };
  let discRight = 0, discRightAndRight = 0;
  for (const c of chained) {
    const o = by.get(c.key);
    if (!o) continue;
    r.n++;
    if (c.ok && o.ok) r.bothRight++;
    else if (c.ok) r.chainedOnly++;
    else if (o.ok) { r.oracleOnly++; if (c.discOk === false) r.lostToDiscipline++; }
    else r.bothWrong++;
    if (c.discOk === false) r.chainedWrongDiscipline++;
    if (c.discOk !== false) { discRight++; if (c.ok) discRightAndRight++; }
  }
  r.chainedAccuracy = rate(r.bothRight + r.chainedOnly, r.n);
  r.oracleAccuracy = rate(r.bothRight + r.oracleOnly, r.n);
  r.chainedAccuracyGivenDisciplineRight = rate(discRightAndRight, discRight);
  r.gap = r.oracleAccuracy - r.chainedAccuracy;
  return r;
}

/** Most frequent value (ties: the first seen). */
export function mostFrequent(values) {
  const m = new Map();
  for (const v of values) if (v !== null && v !== undefined) m.set(v, (m.get(v) ?? 0) + 1);
  let best = null, n = 0;
  for (const [v, c] of m) if (c > n) { best = v; n = c; }
  return { value: best, count: n, share: values.length ? n / values.length : NaN };
}

/** Plain FNV-1a hash of a string, as 8 hex digits (cache keys are built from sha1 in the script; this one is for tests and fold splits). */
export function fnv(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0).toString(16).padStart(8, '0');
}

/** Per-signature truth of a group of elements: the most frequent label (ties: the first), with the alternates of the first element that has it. */
export function groupTruth(members, pick) {
  const labels = members.map(pick).map((x) => x?.value ?? null);
  const top = mostFrequent(labels).value;
  const first = members.map(pick).find((x) => x && x.value === top);
  return { value: top, alt: first?.alt ?? [] };
}

export const fmtPct = (x, d = 0) => (Number.isFinite(x) ? `${(x * 100).toFixed(d)}%` : '-');
