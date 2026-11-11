// Writes the combined truth-bench report (bench/truth-bench-process-plant.md) from the truth-bench.json of real-classify-truth.mjs.
//   cd web && node bench/truth-bench-report.mjs --bench <new truth-bench.json> --truth ../models/Process-Plant.truth.json --old <truth-bench.json of the run with the OLD rules and temperatures>
//        --state <state-report output text file> --out bench/truth-bench-process-plant.md
// It also builds the reference row "hybrid-d3 with the OLD rules", OFFLINE: per signature, the old rule's answer when it was final, else the current d3 answer.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { MIN_CONFIDENCE, fmtPct, makeItem, summarise } from './truth-metrics.mjs';

const a = process.argv.slice(2);
const args = {};
for (let i = 0; i < a.length; i++) if (a[i].startsWith('--')) args[a[i].slice(2)] = a[++i];
const read = (p) => JSON.parse(readFileSync(resolve(p), 'utf8'));
const bench = read(args.bench), old = read(args.old), truthFile = read(args.truth);
const truthOf = truthFile.elements;
const MIN = bench.minConfidence ?? MIN_CONFIDENCE;
const QUESTIONS = ['discipline', 'sub_chained', 'sub_oracle', 'division'];
const NAMES = { discipline: 'Discipline', sub_chained: 'Sub-discipline, chained (right only when discipline and sub match)', sub_oracle: 'Sub-discipline, oracle (asked under the true discipline)', division: 'Division (MasterFormat, ungated)' };

// ---- offline recombination: hybrid-d3 with the old rules
const sigOf = new Map();
for (const s of bench.signatures) for (const id of s.elements) sigOf.set(id, s.signature);
const groupTruth = (members, pick) => { const m = new Map(); for (const x of members) { const p = pick(x); const k = JSON.stringify(p); m.set(k, [(m.get(k)?.[0] ?? 0) + 1, p]); } return [...m.values()].sort((x, y) => y[0] - x[0])[0][1]; };
function oldHybridItems(question, variant) {
  const items = [];
  for (const [id, t] of Object.entries(truthOf)) {
    const sig = sigOf.get(id);
    const r = old.perSignature.rules[sig]?.variants.cal;
    const useRule = r?.rule?.final && r.discipline?.code;
    const p = useRule ? r : bench.perSignature.d3[sig]?.variants[variant];
    if (!p) continue;
    const alt = t.alt ?? {};
    if (question === 'discipline') items.push(makeItem({ key: id, pred: p.discipline?.code ?? null, truth: t.discipline, conf: p.discipline?.conf, fallback: p.discipline?.code === 'GEN' }));
    else if (question === 'sub_chained') { if (!t.subDiscipline) continue; const d = p.discipline, s = p.sub_chained; items.push(makeItem({ key: id, pred: s && d ? `${d.code}/${s.code}` : null, truth: `${t.discipline}/${t.subDiscipline}`, alt: (alt.subDiscipline ?? []).map((x) => `${t.discipline}/${x}`), conf: s?.conf, fallback: s?.code === 'UNC' || d?.code === 'GEN', discOk: d?.code === t.discipline })); }
    else if (question === 'sub_oracle') { if (!t.subDiscipline) continue; const s = p.oracle?.[t.discipline]; items.push(makeItem({ key: id, pred: s?.code ?? null, truth: t.subDiscipline, alt: alt.subDiscipline ?? [], conf: s?.conf, fallback: s?.code === 'UNC', discOk: true })); }
    else { if (!t.division) continue; items.push(makeItem({ key: id, pred: p.division?.code ?? null, truth: t.division, alt: alt.division ?? [], conf: p.division?.conf, fallback: false })); }
  }
  return items;
}
void groupTruth;
const OLDREF = 'hybrid-d3, OLD rules (offline)';
const oldRef = { cal: {}, raw: {} };
for (const v of ['cal', 'raw']) for (const q of QUESTIONS) oldRef[v][q] = summarise(oldHybridItems(q, v), MIN);

// ---- tables
const f = (x, d = 1) => fmtPct(x, d);
const e2 = (x) => (Number.isFinite(x) ? x.toFixed(2) : '-');
const ARMS = ['rules', 'majority', 'xsmall', 'base2', 'd3', 'd3-psets', 'd3-svg', 'd3-svg-ctx', 'd3-svg-ctx-psets', 'hybrid-xsmall', 'hybrid-d3', 'hybrid-d3-svg', 'hybrid-d3-svg-ctx'].filter((x) => bench.metrics[x]);
const row = (name, s) => `| ${name} | ${f(s.accuracy)} | ${f(s.lenient)} | ${f(s.coverage)} | ${f(s.precision)} | ${e2(s.ece)} | ${f(s.fallback)} |`;
const tableFor = (q) => {
  const L = [`| arm | strict | lenient | cover@${MIN} | prec@${MIN} | ECE | GEN rate |`, '|---|---|---|---|---|---|---|'];
  for (const arm of ARMS) for (const v of Object.keys(bench.metrics[arm])) {
    const s = bench.metrics[arm][v].element[q];
    if (s?.n) L.push(row(Object.keys(bench.metrics[arm]).length > 1 ? `${arm} ${v}` : arm, s));
  }
  for (const v of ['cal', 'raw']) L.push(row(`${OLDREF} ${v}`, oldRef[v][q]));
  return L.join('\n');
};
const meanOf = (arm, key) => { const xs = Object.values(bench.perSignature[arm]).map((e) => e[key]).filter((x) => typeof x === 'number'); return xs.length ? xs.reduce((p, x) => p + x, 0) / xs.length : null; };
const cost = ['| arm | mean state tokens (d3 tokenizer) | mean state bytes | s/sig (app path) |', '|---|---|---|---|'];
for (const arm of ARMS) cost.push(`| ${arm} | ${meanOf(arm, 'stateTokens')?.toFixed(0) ?? '-'} | ${meanOf(arm, 'stateBytes')?.toFixed(0) ?? '-'} | ${bench.timings[arm].secondsPerSignatureApp.toFixed(1)} |`);

// ---- temperature effect: the same arms with the old and the new shipped temperatures (cal)
const temp = ['| arm, question | old temperatures: cover / prec / ECE | refitted: cover / prec / ECE |', '|---|---|---|'];
for (const arm of ['xsmall', 'base2', 'd3']) for (const q of ['discipline', 'sub_chained']) {
  const o = old.metrics[arm].cal.element[q], n = bench.metrics[arm].cal.element[q];
  temp.push(`| ${arm}, ${q} | ${f(o.coverage)} / ${f(o.precision)} / ${e2(o.ece)} | ${f(n.coverage)} / ${f(n.precision)} / ${e2(n.ece)} |`);
}

// ---- geometry flips (strict, per signature, cal, against d3 text only)
const sigLabel = new Map(bench.signatures.map((s) => { const e = bench.perSignature.d3[s.signature]; return [s.signature, s.signature.split('|').slice(0, 2).join(' ') + ` (${e?.members ?? s.elements.length})`]; }));
const flips = [];
for (const arm of ['d3-svg', 'd3-svg-ctx']) {
  const byEl = (armName) => new Map(bench.signatures.map((s) => { const p = bench.perSignature[armName][s.signature]?.variants.cal; return [s.signature, p]; }));
  const base = byEl('d3'), cur = byEl(arm);
  for (const q of ['discipline', 'sub_chained']) {
    const fix = [], broke = [];
    for (const s of bench.signatures) {
      const t = s.truth; if (q === 'sub_chained' && !t.sub.value) continue;
      const ok = (p) => (q === 'discipline' ? p?.discipline?.code === t.discipline.value : p?.discipline?.code === t.discipline.value && p?.sub_chained?.code === t.sub.value);
      const show = (p) => (q === 'discipline' ? p?.discipline?.code : `${p?.discipline?.code}/${p?.sub_chained?.code}`);
      const b = base.get(s.signature), c = cur.get(s.signature);
      if (!ok(b) && ok(c)) fix.push(`${sigLabel.get(s.signature)}: ${show(b)} -> ${show(c)}`);
      if (ok(b) && !ok(c)) broke.push(`${sigLabel.get(s.signature)}: ${show(b)} -> ${show(c)}`);
    }
    flips.push(`- ${arm}, ${q}: ${fix.length} signatures wrong to right, ${broke.length} right to wrong.${fix.length ? ` Wrong to right: ${fix.slice(0, 3).join('; ')}.` : ''}${broke.length ? ` Right to wrong: ${broke.slice(0, 4).join('; ')}.` : ''}`);
  }
}
const genRate = (arm) => f(bench.metrics[arm].cal.element.discipline.fallback, 0);

const state = args.state ? readFileSync(resolve(args.state), 'utf8').trim() : '';
const md = `# Truth bench: process plant

**Read this first.** The classifier rules (and so every \`hybrid-*\` arm, which uses a final rule as it is) were tuned on THIS plant, against THIS truth, in the same work that produced this table. Rules that match the truth's conventions make their own score circular: \`rules\` at about 100% and every hybrid at about 100% measure how well the rules were fitted to one synthetic unit, not how well they classify a plant they have not seen. The shipped temperatures were also fitted on this plant (5-fold cross-validation by signature, so the temperature numbers are out of fold, the rule numbers are not). The honest estimate of a hybrid is the reference row **"${OLDREF}"**: the rules as they were BEFORE this tuning (bench-truth, old rules), recombined offline with the current d3 results (the rule when it was final, else d3). It is an offline recombination, not a run of the app. The model-only arms (\`xsmall\`, \`base2\`, \`d3\*\`) never see the rules and are the non-circular numbers.

Truth: \`${args.truth.replace(/^.*models\//, 'models/')}\` (${truthFile.generator ?? ''}; design intent set when each element was created, no classifier output used). ${Object.keys(truthOf).length} elements in ${bench.signatures.length} signatures, scored per element. "cal" = shipped temperatures (the app's \`auto\` mode), "raw" = T 1. Lenient also accepts the truth's alternative. cover and prec at minConfidence ${MIN}. GEN rate = share of answers that are the fallback (GEN, or GEN/UNC for the chained sub question). Rules and majority have confidence 1 (majority: the class share). Data: \`${args.bench.replace(/^.*scratchpad\//, '')}\`.

Arms: rules; majority (trivial baseline); xsmall = deberta-v3-xsmall-zeroshot-v1.1 (app default); base2 = deberta-v3-base-zeroshot-v2.0; d3 = d3-edge, text state, 2000 byte cap (as the app sends it); d3-psets = d3 with the cap raised so no signature is truncated; d3-svg = d3 plus the app's SVG of the element alone; d3-svg-ctx = d3 plus the SVG of the element in its bounding box with its neighbours; d3-svg-ctx-psets = the same with full property sets; hybrid-* = the app's pipeline (a final rule is used as it is, the model answers the rest).

**d3-psets is identical to d3, and d3-svg-ctx-psets to d3-svg-ctx, by construction**: no signature's state reaches the 2000 byte cap (largest full state 597 bytes), so the raised cap changes nothing and the runs are cache hits of their twins (see the state report below).

## Summary

${['discipline', 'sub_chained', 'division'].map((q) => `Best model-only ${q} (cal, strict): ${(() => { let best = ['', -1]; for (const arm of ARMS.filter((x) => !x.startsWith('hybrid') && x !== 'rules' && x !== 'majority')) { const s = bench.metrics[arm].cal.element[q].accuracy; if (s > best[1]) best = [arm, s]; } return `${best[0]} ${f(best[1])}`; })()}.`).join(' ')}
Geometry did not help d3 on this plant: the SVG arms are far below the text baseline (discipline strict d3 ${f(bench.metrics.d3.cal.element.discipline.accuracy)}, d3-svg ${f(bench.metrics['d3-svg'].cal.element.discipline.accuracy)}, d3-svg-ctx ${f(bench.metrics['d3-svg-ctx'].cal.element.discipline.accuracy)}) and the model answers GEN far more often (${genRate('d3')} of elements for d3, ${genRate('d3-svg')} for d3-svg, ${genRate('d3-svg-ctx')} for d3-svg-ctx). The hybrids are then equal to each other (the rules decide almost every element).

${QUESTIONS.map((q) => `## ${NAMES[q]}\n\n${tableFor(q)}`).join('\n\n')}

## Cost

${cost.join('\n')}

Tokens are the Qwen tokenizer on the state text that d3 reads (SVG included); hybrid arms show the state of the few elements that reach the model. s/sig is the mean wall time per signature of the app path (main plus chained sub request) on 4 CPU cores with onnxruntime-node, fp32; the context SVG request needed up to about 8 GB.

## Effect of the refitted temperatures (cal, per element, before and after)

${temp.join('\n')}

"Old" is the first run of this bench (shipped temperatures fitted on rule labels), "refitted" the current run (see calibrationDefaults.ts).

## Geometry flips against d3 text only (strict, per signature, cal)

${flips.join('\n')}

d3-svg and d3-svg-ctx lose almost entirely on the structural steel, slabs and members that the text state gets right: the extra SVG text is out of distribution for d3-edge and it answers GEN. The one gain is the drain trench (PLB to CIV), where the shape text helps.

## What d3's state holds, and what the cap cuts

The state is JSON: class, name, type (class and name), psets (Attr plus the element's property sets and quantities), hierarchy (storey), parents (the host or parent element with its psets), systems, building_context; an SVG geometry arm prepends a legend and the SVG text after the cap has been applied. **At the app's 2000 byte cap 0 of the 114 signatures are truncated** (the largest full state is 597 bytes), so d3-psets cannot differ from d3 on this plant. The only example of loss is a cap well below the default (500 bytes, 12 of 114 signatures cut): the window state loses the GlazingAreaFraction property and its parent wall's property sets (full 597 B against cut 405 B, below).

${'```'}
${state}
${'```'}
`;
writeFileSync(resolve(args.out), md);
console.log(`wrote ${args.out}`);
