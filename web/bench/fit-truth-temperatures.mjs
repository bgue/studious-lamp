// Refits the shipped temperatures of calibrationDefaults.ts against a MEASURED truth (xray-truth/1) instead of rule labels.
//
//   cd web && node bench/fit-truth-temperatures.mjs --bench <truth-bench.json> --truth ../models/Process-Plant.truth.json [--out fit.json] [--seed 20240611]
//
// Input: the raw scores that real-classify-truth.mjs keeps per signature (truth-bench.json, perSignature.<arm>.<sig>.rawScores). One sample per
// element (the raw scores of its signature's representative, the label from the truth), so the fit is weighted by element count; a second pass uses
// one sample per signature (the majority truth of its elements). Cross-validation is k-fold BY SIGNATURE (a seeded shuffle of the signatures, fold =
// position mod k), so the elements of one signature never sit on both sides. Every sample is scored with the temperature fitted on the other folds.
// A temperature is shipped for a question only when, out of fold, it lowers the NLL and does not raise the ECE, against both T = 1 and the value
// that ships today (see decideShip). Questions: discipline, sub_discipline (asked under the true discipline), masterformat. building_element has no
// truth in the file and is left as it is.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const a = process.argv.slice(2);
const args = {};
for (let i = 0; i < a.length; i++) if (a[i].startsWith('--')) args[a[i].slice(2)] = a[++i];
if (!args.bench || !args.truth) throw new Error('Usage: --bench <truth-bench.json> --truth <truth.json> [--out fit.json] [--seed N] [--min 0.6] [--folds 5]');
const SEED = Number(args.seed ?? 20240611);
const K = Number(args.folds ?? 5);
const MIN = Number(args.min ?? 0.6);
const bench = JSON.parse(readFileSync(resolve(args.bench), 'utf8'));
const truthOf = JSON.parse(readFileSync(resolve(args.truth), 'utf8')).elements;

const mulberry32 = (seed) => () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const folds = (() => {
  const sigs = bench.signatures.map((s) => s.signature).sort();
  const rnd = mulberry32(SEED);
  for (let i = sigs.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [sigs[i], sigs[j]] = [sigs[j], sigs[i]]; }
  return new Map(sigs.map((s, i) => [s, i % K]));
})();

const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const C = await server.ssrLoadModule('/src/classify/calibrate.ts');
  const CD = await server.ssrLoadModule('/src/classify/calibrationDefaults.ts');
  const MODEL_ID = { xsmall: 'decision:MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', base2: 'decision:MoritzLaurer/deberta-v3-base-zeroshot-v2.0', d3: 'd3' };
  const QUESTIONS = ['discipline', 'sub_discipline', 'masterformat'];
  const majority = (xs) => { const m = new Map(); for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1); return [...m].sort((p, q) => q[1] - p[1] || (p[0] < q[0] ? -1 : 1))[0][0]; };

  /** Samples {sig, w, sample} of a question for an arm: by element, or by signature (the majority truth). */
  function samplesOf(arm, q, perSignature) {
    const out = [];
    for (const g of bench.signatures) {
      const e = bench.perSignature[arm][g.signature];
      if (!e) continue;
      const labelled = g.elements.map((id) => truthOf[id]).filter(Boolean);
      const groups = perSignature ? [{ key: g.signature, ts: [majorityTruth(labelled)], w: 1 }] : labelled.map((t) => ({ key: g.signature, ts: [t], w: 1 }));
      for (const { key, ts, w } of groups) {
        const t = ts[0];
        let raw, label;
        if (q === 'discipline') { raw = e.rawScores.main?.questions?.discipline; label = t.discipline; }
        else if (q === 'masterformat') { raw = e.rawScores.main?.questions?.masterformat; label = t.division; }
        else { raw = e.rawScores[`sub:${t.discipline}`]?.questions?.sub_discipline; label = t.subDiscipline; }
        if (!raw?.logits || !label) continue;
        const keys = Object.keys(raw.logits);
        const idx = keys.indexOf(label);
        if (idx < 0) continue;
        out.push({ sig: key, w, sample: { logits: keys.map((k) => raw.logits[k]), label: idx } });
      }
    }
    return out;
  }
  const majorityTruth = (ts) => ({ discipline: majority(ts.map((t) => t.discipline)), subDiscipline: majority(ts.map((t) => t.subDiscipline ?? '')) || null, division: majority(ts.map((t) => t.division)) });

  const metricsOf = (items, Ts) => {
    const m = C.measure(items.map((x) => x.sample), Ts, MIN);
    return { n: m.n, accuracy: m.accuracy, nll: m.nll, ece: m.ece, cover: m.clearShare, precision: m.clearAccuracy };
  };

  const report = {};
  for (const arm of ['xsmall', 'base2', 'd3']) {
    if (!bench.perSignature[arm]) continue;
    const shipped = CD.SHIPPED_TEMPERATURES[MODEL_ID[arm]]?.temperatures ?? {};
    report[arm] = {};
    for (const q of QUESTIONS) {
      const r = (report[arm][q] = { shippedNow: shipped[q] ?? null });
      for (const weighting of ['element', 'signature']) {
        const items = samplesOf(arm, q, weighting === 'signature');
        if (items.length < 8) { r[weighting] = { n: items.length, skipped: true }; continue; }
        const nSig = new Set(items.map((x) => x.sig)).size;
        const foldT = [];
        for (let f = 0; f < K; f++) foldT.push(C.fitTemperature(items.filter((x) => folds.get(x.sig) !== f).map((x) => x.sample)).T);
        const Tall = C.fitTemperature(items.map((x) => x.sample)).T;
        const oof = items.map((x) => foldT[folds.get(x.sig)]);
        const cur = shipped[q] ?? 1;
        r[weighting] = {
          n: items.length, signatures: nSig, Tall, foldT,
          at1: metricsOf(items, 1), atShipped: metricsOf(items, cur), oof: metricsOf(items, oof),
        };
      }
      // Ship decision on the element-weighted numbers; the signature-weighted pass must not contradict it on NLL.
      const e = r.element, s = r.signature;
      if (!e || e.skipped) { r.decision = { ship: false, reason: 'too few samples' }; continue; }
      const eps = 1e-9;
      const beats = (x, ref) => x.nll < ref.nll - eps && x.ece <= ref.ece + eps;
      const vs1 = beats(e.oof, e.at1);
      const vsCur = r.shippedNow === null ? vs1 : beats(e.oof, e.atShipped);
      const sigOk = !s || s.skipped || s.oof.nll <= s.at1.nll + eps;
      const curBeats1 = r.shippedNow !== null && beats(e.atShipped, e.at1);
      const T = Math.round(e.Tall * 100) / 100;
      r.decision = vs1 && vsCur && sigOk
        ? { ship: true, T, reason: 'out-of-fold NLL lower and ECE not higher than both T = 1 and the value shipped today' }
        : curBeats1 && sigOk
          ? { ship: true, T: r.shippedNow, keep: true, reason: 'the new fit does not beat the value shipped today, which itself beats T = 1 on the truth' }
          : { ship: false, T: null, reason: vs1 ? 'the fit beats T = 1 but not the value shipped today' : 'no temperature improves both NLL and ECE out of fold over T = 1' };
      // What the user gets after the decision: a new fit (out of fold), the value kept as it is, or no scaling (T = 1).
      r.after = r.decision.ship ? (r.decision.keep ? { how: 'kept', ...e.atShipped } : { how: 'new fit, out of fold', ...e.oof }) : { how: 'T = 1', ...e.at1 };
    }
  }
  const text = JSON.stringify(report, null, 1);
  if (args.out) writeFileSync(resolve(args.out), text);

  const f = (x, d = 3) => (Number.isFinite(x) ? x.toFixed(d) : '-');
  const p = (x) => (Number.isFinite(x) ? `${(x * 100).toFixed(0)}%` : '-');
  const lines = [`seed ${SEED}, ${K} folds by signature, min confidence ${MIN}`, ''];
  for (const [arm, qs] of Object.entries(report)) for (const [q, r] of Object.entries(qs)) for (const w of ['element', 'signature']) {
    const x = r[w];
    if (!x || x.skipped) { lines.push(`${arm} ${q} ${w}: n=${x?.n ?? 0} skipped`); continue; }
    const row = (name, m) => `${name} NLL ${f(m.nll)} ECE ${f(m.ece)} cover ${p(m.cover)} prec ${p(m.precision)} acc ${p(m.accuracy)}`;
    lines.push(`${arm} ${q} ${w} n=${x.n} sig=${x.signatures} Tall=${f(x.Tall, 2)} foldT=[${x.foldT.map((t) => f(t, 2)).join(',')}] shipped=${r.shippedNow ?? '-'}`);
    lines.push(`   ${row('T=1   ', x.at1)}`, `   ${row('shipped', x.atShipped)}`, `   ${row('oof    ', x.oof)}`);
    if (w === 'element') lines.push(`   => ${JSON.stringify(r.decision)}`);
  }
  lines.push('', 'Before (shipped today) and after (out of fold for a new fit), element-weighted, cover and precision at ' + MIN, '', '| model | question | shipped now | ship | before cover | before prec | before ECE | after cover | after prec | after ECE | after is |', '|---|---|---|---|---|---|---|---|---|---|---|');
  for (const [arm, qs] of Object.entries(report)) for (const [q, r] of Object.entries(qs)) {
    if (!r.element || r.element.skipped) continue;
    const b = r.element.atShipped, af = r.after;
    lines.push(`| ${arm} | ${q} | ${r.shippedNow ?? '1 (none)'} | ${r.decision.ship ? (r.decision.keep ? `${r.decision.T} (kept)` : r.decision.T) : 'none'} | ${p(b.cover)} | ${p(b.precision)} | ${f(b.ece, 2)} | ${p(af.cover)} | ${p(af.precision)} | ${f(af.ece, 2)} | ${af.how} |`);
  }
  console.log(lines.join('\n'));
} finally {
  await server.close();
}
