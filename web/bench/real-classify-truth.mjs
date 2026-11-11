// Scores the element classifiers against a MEASURED ground truth (xray-truth/1, from the model generator) instead of against our own rules.
//
//   cd web && NODE_USE_ENV_PROXY=1 node bench/real-classify-truth.mjs --model process-plant --truth ../models/Process-Plant.truth.json \
//        --arms rules,majority,xsmall,base2,d3 [--limit N] [--out <dir>] [--geometry <geometry.json> --geometry-mode isolated|context]
//
// Arms (run one after the other, each cached per signature in <out>/cache/<arm>.json, so a crash or a rerun redoes nothing):
//   rules     the app's rules (classByRules + resolveRule), confidence 1, no match = abstain
//   majority  the most frequent truth class per question (trivial baseline, confidence = the class share)
//   xsmall    MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33 (q8), the app default
//   base2     MoritzLaurer/deberta-v3-base-zeroshot-v2.0 (fp32)
//   d3        d3-edge, text only, onnxruntime-node with the warsang export
//   d3svg     d3 with the app's geometryText svg; only with --geometry (a geometry.json from bench/d3/make-bench-pictures.mjs with GEOMETRY_ONLY=1)
// Models run through the app's code (vite SSR): buildInputs, signatureOf, buildState, mainQuestions/subQuestions, decodeAnswers, the sub-discipline
// strategy of the pipeline and the shipped temperatures of calibrationDefaults.ts. Every model arm is scored twice: "cal" = shipped temperatures
// (the app's `auto` mode), "raw" = T 1.
//
// Questions: discipline; sub_chained (the app: the sub-discipline question is asked under the model's own discipline answer, top 2 when unsure, and counts
// right only when discipline AND sub match); sub_oracle (asked under the TRUE discipline, bare sub code); division (the masterformat question as the model
// answers it, ungated); division_app (as the app shows it: only when building_element >= 0.5, otherwise no division). The app asks the division in the same
// request as the discipline, so it has no chained/oracle variant.
//
// Env: TRANSFORMERS_NODE, ORT_NODE, D3_DIR (defaults point into the session scratchpad), MIN_CONF (0.6).
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';
import { MIN_CONFIDENCE, compareChainedOracle, fmtPct, groupTruth, makeItem, mostFrequent, summarise } from './truth-metrics.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const SCRATCH = '/tmp/claude-0/-home-user-studious-lamp/d3dc753b-6b35-532c-aed4-18bc78aeb28a/scratchpad';
const MIN = Number(process.env.MIN_CONF ?? MIN_CONFIDENCE);

// ---------------------------------------------------------------- arguments
const args = (() => {
  const a = process.argv.slice(2);
  const o = { arms: 'rules,majority,xsmall,base2,d3', out: join(SCRATCH, 'bench-truth') };
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--count') o.count = true;
    else if (a[i].startsWith('--')) o[a[i].slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = a[++i];
  }
  return o;
})();
if (!args.model) throw new Error('Usage: --model <sidecar name> --truth <truth.json> --arms rules,majority,xsmall,base2,d3 [--limit N] [--out dir]');
if (!args.truth && !args.count) throw new Error('--truth is required.');
const ARMS = args.arms.split(',').map((s) => s.trim()).filter(Boolean);
const KNOWN = ['rules', 'majority', 'xsmall', 'base2', 'd3', 'd3svg'];
for (const a of ARMS) if (!KNOWN.includes(a)) throw new Error(`Unknown arm "${a}" (known: ${KNOWN.join(', ')}).`);
const OUT = resolve(args.out);
mkdirSync(join(OUT, 'cache'), { recursive: true });
const sha = (s) => createHash('sha1').update(s).digest('hex').slice(0, 16);
const log = (...x) => console.error(...x);

const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const C = await server.ssrLoadModule('/src/classify/index.ts');
  const K = await server.ssrLoadModule('/src/classify/calibrate.ts');
  const Q = await server.ssrLoadModule('/src/classify/questions.ts');
  const J = await server.ssrLoadModule('/src/classify/jevAdapter.ts');
  const P = await server.ssrLoadModule('/src/classify/pipeline.ts');
  const S = await server.ssrLoadModule('/src/classify/schema.ts');
  const CD = await server.ssrLoadModule('/src/classify/calibrationDefaults.ts');
  const H = await server.ssrLoadModule('/tests/classify-helpers.ts');
  const schema = C.defaultSchema();
  const FALLBACK_D = schema.fallbackDiscipline ?? 'GEN';
  const FALLBACK_S = schema.fallbackSubDiscipline ?? 'UNC';

  // ------------------------------------------------------------ 1. inputs and the join
  const model = H.sidecarModel(args.model);
  const inputs = C.buildInputs(model, model.elements.map((e) => e.id));
  const truthFile = args.truth ? JSON.parse(readFileSync(resolve(args.truth), 'utf8')) : { elements: {} };
  if (args.truth && truthFile.format !== 'xray-truth/1') log(`warning: truth format is "${truthFile.format}", expected "xray-truth/1"`);
  const truthOf = truthFile.elements ?? {};
  const noTruth = inputs.filter((i) => !truthOf[i.id]);
  const ids = new Set(inputs.map((i) => i.id));
  const orphanTruth = Object.keys(truthOf).filter((g) => !ids.has(g));
  console.log(`${args.model}: ${inputs.length} elements, ${Object.keys(truthOf).length} truth entries; ${noTruth.length} elements without truth, ${orphanTruth.length} truth entries without an element`);
  if (noTruth.length) log(`  without truth (first 10): ${noTruth.slice(0, 10).map((i) => `${i.ifcClass}:${i.name}`).join('; ')}`);
  if (orphanTruth.length) log(`  truth without element (first 10): ${orphanTruth.slice(0, 10).join(', ')}`);

  // ------------------------------------------------------------ 2. signatures (the app's signatureOf; the first element of a signature is its representative)
  const bySig = new Map();
  for (const i of inputs) {
    const sig = C.signatureOf(i);
    const g = bySig.get(sig) ?? { sig, rep: i, members: [] };
    bySig.set(sig, g);
    if (truthOf[i.id]) g.members.push(i);
  }
  let groups = [...bySig.values()].filter((g) => g.members.length > 0);
  console.log(`${bySig.size} signatures in the model, ${groups.length} with at least one truth element`);
  if (args.count) { console.log(groups.map((g) => `${String(g.members.length).padStart(4)}  ${g.sig}`).join('\n')); process.exit(0); }
  if (args.limit) groups = groups.slice(0, Number(args.limit));
  const sigOfId = new Map();
  for (const g of groups) for (const m of g.members) sigOfId.set(m.id, g.sig);
  const elements = groups.flatMap((g) => g.members);
  const tr = (id) => truthOf[id];

  // ------------------------------------------------------------ truth distributions (majority arm, per-signature truth)
  const allTruth = elements.map((e) => tr(e.id));
  const majDisc = mostFrequent(allTruth.map((t) => t.discipline));
  const subIn = (d) => mostFrequent(allTruth.filter((t) => d === null || t.discipline === d).map((t) => t.subDiscipline));
  const majDiv = mostFrequent(allTruth.map((t) => t.division));

  // ------------------------------------------------------------ helpers shared by the arms
  const choiceOf = (code, confidence, probabilities) => ({ code, label: schema.disciplines.find((d) => d.code === code)?.label ?? code, confidence, probabilities });
  const ans = (code, conf) => (code === null || code === undefined ? null : { code, conf });
  const disciplineOfSub = (d) => schema.disciplines.find((x) => x.code === d);
  const trueDiscs = (g) => [...new Set(g.members.map((m) => tr(m.id).discipline))];

  // A model arm with a cache: calls are keyed by hash(model | signature | state) and the question set.
  const loadCache = (arm) => {
    const f = join(OUT, 'cache', `${arm}.json`);
    let c = { arm, model: args.model, entries: {}, meta: { wallMs: 0, loadMs: 0 } };
    try { if (existsSync(f)) { const j = JSON.parse(readFileSync(f, 'utf8')); if (j.arm === arm) c = j; } } catch { /* start over */ }
    c.meta ??= { wallMs: 0, loadMs: 0 };
    const save = () => { writeFileSync(`${f}.tmp`, JSON.stringify(c)); renameSync(`${f}.tmp`, f); };
    return { c, save };
  };

  async function runModelArm(arm, { provider, modelId, maxState, geometryOf }) {
    const { c, save } = loadCache(arm);
    const shipped = CD.SHIPPED_TEMPERATURES[modelId]?.temperatures ?? {};
    const variants = { cal: shipped, raw: {} };
    const ctl = new AbortController();
    const t0 = Date.now();
    const out = new Map();
    let done = 0;
    for (const g of groups) {
      let state = C.buildState(g.rep, maxState);
      if (geometryOf) { const geo = geometryOf(g.rep); if (geo) state = { geometry: `${geo.legend} ${geo.svg.replace(/\n/g, ' ')}`, ...state }; }
      const h = sha(`${args.model}|${arm}|${g.sig}|${JSON.stringify(state)}`);
      const call = async (key, questions) => {
        const k = `${h}|${key}`;
        if (c.entries[k]) return c.entries[k];
        const t = Date.now();
        const a = await provider.decide(state, questions, ctl.signal);
        const e = { raw: K.rawOfAnswers(a), ms: Date.now() - t };
        c.entries[k] = e;
        save();
        return e;
      };
      const main = await call('main', Q.mainQuestions(schema));
      const used = new Map([['main', main]]);
      const subCall = async (codes) => {
        const sq = Q.subQuestions(schema, codes);
        if (!sq) return null;
        const key = `sub:${codes.join('+')}`;
        const e = await call(key, sq);
        used.set(key, e);
        return e;
      };
      const entry = { sig: g.sig, hash: h, rep: g.rep.id, members: g.members.length, variants: {}, rawScores: {} };
      let appMs = main.ms;
      for (const [vn, temps] of Object.entries(variants)) {
        const pred = { discipline: null, sub_chained: null, division: null, division_app: null, oracle: {}, error: null };
        try {
          const mainAns = K.answersFromRaw(main.raw, temps);
          const d = J.readChoice(mainAns, Q.Q_DISCIPLINE);
          const dChoice = choiceOf(d.choice, d.confidence, d.probabilities);
          const codes = P.SUB_STRATEGIES['top2-when-unsure'](schema, dChoice, schema.minConfidence).filter((x) => disciplineOfSub(x));
          const useCodes = codes.length ? codes : [dChoice.code];
          const subE = await subCall(useCodes);
          if (vn === 'cal' && subE) appMs += subE.ms;
          const dec = C.decodeAnswers(schema, mainAns, subE ? K.answersFromRaw(subE.raw, temps) : null, useCodes);
          pred.discipline = ans(dec.discipline.code, dec.discipline.confidence);
          pred.sub_chained = dec.subDiscipline ? ans(dec.subDiscipline.code, dec.subDiscipline.confidence) : null;
          pred.division_app = dec.masterformat ? ans(dec.masterformat.division, dec.masterformat.confidence) : null;
          const m = J.readChoice(mainAns, Q.Q_MASTERFORMAT);
          pred.division = ans(m.choice, m.confidence);
          for (const td of trueDiscs(g)) {
            const sq = Q.subQuestions(schema, [td]);
            if (!sq) { const only = disciplineOfSub(td)?.subDisciplines; pred.oracle[td] = only?.length === 1 ? ans(only[0].code, 1) : null; continue; }
            const e = await subCall([td]);
            const sa = J.readChoice(K.answersFromRaw(e.raw, temps), Q.Q_SUB);
            pred.oracle[td] = ans(sa.choice, sa.confidence);
          }
        } catch (e) {
          if (ctl.signal.aborted) throw e;
          pred.error = e instanceof Error ? e.message : String(e);
        }
        entry.variants[vn] = pred;
      }
      entry.rawScores = Object.fromEntries([...used.entries()].map(([k, v]) => [k, v.raw]));
      entry.msApp = appMs;
      entry.msAll = [...used.values()].reduce((s, e) => s + e.ms, 0);
      out.set(g.sig, entry);
      done++;
      log(`  [${arm}] ${done}/${groups.length} ${g.sig.slice(0, 60)}  ${(entry.msAll / 1000).toFixed(1)} s`);
    }
    c.meta.wallMs += Date.now() - t0;
    save();
    return { entries: out, timing: { wallMsTotal: c.meta.wallMs, wallMsThisRun: Date.now() - t0, loadMs: c.meta.loadMs } };
  }

  // ------------------------------------------------------------ the arms
  async function runRules() {
    const t0 = Date.now();
    const out = new Map();
    for (const g of groups) {
      const hit = C.classByRules(g.rep);
      const building = C.isBuildingContext(g.rep);
      const d = hit ? C.resolveRule(hit, schema, building) : null;
      const pred = { discipline: null, sub_chained: null, division: null, division_app: null, oracle: {}, rule: hit ? { confidence: hit.confidence, final: hit.confidence >= C.RULE_FINAL, rationale: hit.rationale } : null };
      if (d) {
        pred.discipline = ans(d.discipline, 1);
        pred.sub_chained = ans(d.subDiscipline, 1);
        pred.division_app = ans(d.division, 1);
        const raw = hit.division && S.divisionTitle(schema, hit.division) ? hit.division : null;
        pred.division = ans(raw, 1);
        for (const td of trueDiscs(g)) pred.oracle[td] = ans(d.subDiscipline, 1); // rules do not look at a question: the same sub code, judged against the true discipline
      }
      out.set(g.sig, { sig: g.sig, rep: g.rep.id, members: g.members.length, variants: { cal: pred }, msApp: 0, msAll: 0 });
    }
    return { entries: out, timing: { wallMsTotal: Date.now() - t0, wallMsThisRun: Date.now() - t0, loadMs: 0 } };
  }

  async function runMajority() {
    const out = new Map();
    for (const g of groups) {
      const pred = { discipline: ans(majDisc.value, majDisc.share), sub_chained: null, division: ans(majDiv.value, majDiv.share), division_app: ans(majDiv.value, majDiv.share), oracle: {} };
      const s = subIn(majDisc.value);
      pred.sub_chained = ans(s.value, s.share);
      for (const td of trueDiscs(g)) { const o = subIn(td); pred.oracle[td] = ans(o.value, o.share); }
      out.set(g.sig, { sig: g.sig, rep: g.rep.id, members: g.members.length, variants: { cal: pred }, msApp: 0, msAll: 0 });
    }
    return { entries: out, timing: { wallMsTotal: 0, wallMsThisRun: 0, loadMs: 0 } };
  }

  const need = (k, def) => process.env[k] ?? def;
  const decisionProvider = async (hfModel, dtype) => {
    const D = await server.ssrLoadModule('/src/classify/providers/decision.ts');
    const lib = need('TRANSFORMERS_NODE', join(SCRATCH, 'ortnode/node_modules/@huggingface/transformers/dist/transformers.node.mjs'));
    const p = D.createDecisionProvider({
      model: hfModel, device: 'wasm', dtype, hfEndpoint: 'https://huggingface.co', hypothesis: { ...D.DEFAULT_HYPOTHESES },
      onProgress: (pr) => { if (pr.totalMB && Math.round(pr.progress * 100) % 25 === 0) process.stderr.write(`\r  ${pr.text}      `); },
      loadLib: async () => { const mod = await import(pathToFileURL(lib).href); return { env: mod.env, pipeline: (task, id, o) => mod.pipeline(task, id, { ...o, device: 'cpu' }) }; },
      gpu: async () => ({ present: false, adapter: false, f16: false }),
    });
    const t = Date.now();
    const rep = await p.load();
    log(`\nloaded ${hfModel} (${rep.dtype}) in ${Date.now() - t} ms`);
    return { p, loadMs: Date.now() - t };
  };
  const d3Provider = async () => {
    const { readFile } = await import('node:fs/promises');
    const D3 = await server.ssrLoadModule('/src/classify/providers/d3.ts');
    const ort = await import(pathToFileURL(need('ORT_NODE', join(SCRATCH, 'ortnode/node_modules/onnxruntime-node/dist/index.js'))).href);
    const tjs = await import(pathToFileURL(need('TRANSFORMERS_NODE', join(SCRATCH, 'ortnode/node_modules/@huggingface/transformers/dist/transformers.node.mjs'))).href);
    const DIR = need('D3_DIR', join(SCRATCH, 'd3web'));
    const source = { has: async () => true, read: async (f) => new Uint8Array(await readFile(join(DIR, f))) };
    const fetchImpl = async (url) => {
      const f = String(url).split('/resolve/')[1]?.split('/').slice(1).join('/');
      try { return new Response(await readFile(join(DIR, f)), { status: 200 }); } catch { return new Response('', { status: 404 }); }
    };
    const p = D3.createD3BrowserProvider({
      repo: 'warsang/d3-edge-web', revision: '117fb255e630667ae1736666497e8a1c69c7a066', endpoint: 'https://huggingface.co', device: 'wasm', source, fetchImpl,
      loadOrt: async () => ort, loadTokenizerLib: async () => ({ PreTrainedTokenizer: tjs.PreTrainedTokenizer }),
      sessionOptions: () => ({ executionProviders: ['cpu'], logSeverityLevel: 3 }),
    });
    const t = Date.now();
    await p.load();
    log(`loaded d3-edge (onnxruntime-node, cpu) in ${Date.now() - t} ms`);
    return { p, loadMs: Date.now() - t };
  };

  const MODELS = { xsmall: ['MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', 'q8'], base2: ['MoritzLaurer/deberta-v3-base-zeroshot-v2.0', 'fp32'] };
  const results = {};
  const timings = {};
  const geometry = args.geometry ? JSON.parse(readFileSync(resolve(args.geometry), 'utf8')) : null;
  for (const arm of ARMS) {
    log(`\n== arm ${arm}`);
    let r;
    if (arm === 'rules') r = await runRules();
    else if (arm === 'majority') r = await runMajority();
    else if (arm === 'd3svg' && !geometry) { console.log('arm d3svg skipped: it needs --geometry <geometry.json> (bench/d3/make-bench-pictures.mjs with GEOMETRY_ONLY=1, which needs the headless browser).'); continue; }
    else {
      const isD3 = arm === 'd3' || arm === 'd3svg';
      const { p, loadMs } = isD3 ? await d3Provider() : await decisionProvider(...MODELS[arm]);
      try {
        const mode = args.geometryMode ?? 'context';
        r = await runModelArm(arm, {
          provider: p, maxState: isD3 ? 2000 : 4000,
          modelId: isD3 ? 'd3' : `decision:${MODELS[arm][0]}`,
          geometryOf: arm === 'd3svg' ? (i) => geometry[`${args.model}|${i.id}`]?.[mode] ?? null : null,
        });
        r.timing.loadMs = loadMs;
      } finally { await p.dispose?.(); }
    }
    results[arm] = r;
    timings[arm] = r.timing;
  }

  // ------------------------------------------------------------ 5. scoring
  const QUESTIONS = ['discipline', 'sub_chained', 'sub_oracle', 'division', 'division_app'];
  const sigTruth = (g) => ({
    discipline: groupTruth(g.members, (m) => ({ value: tr(m.id).discipline })),
    sub: groupTruth(g.members, (m) => ({ value: tr(m.id).subDiscipline, alt: tr(m.id).alt?.subDiscipline })),
    division: groupTruth(g.members, (m) => ({ value: tr(m.id).division, alt: tr(m.id).alt?.division })),
  });
  const gOf = new Map(groups.map((g) => [g.sig, g]));

  /** Items of one question for a list of subjects: {key, sig, truth:{discipline,sub,subAlt,division,divAlt}}. */
  function itemsFor(question, variant, entries, subjects, abstainAll) {
    const items = [];
    for (const s of subjects) {
      const e = entries.get(s.sig);
      const p = e?.variants[variant] ?? null;
      const t = s.truth;
      const ofPred = (a) => (abstainAll || !p ? null : a);
      if (question === 'discipline') {
        const a = ofPred(p?.discipline);
        items.push(makeItem({ key: s.key, pred: a?.code ?? null, truth: t.discipline, conf: a?.conf, fallback: a?.code === FALLBACK_D }));
      } else if (question === 'sub_chained') {
        if (!t.sub) continue;
        const d = ofPred(p?.discipline), a = ofPred(p?.sub_chained);
        items.push(makeItem({ key: s.key, pred: a && d ? `${d.code}/${a.code}` : null, truth: `${t.discipline}/${t.sub}`, alt: (t.subAlt ?? []).map((x) => `${t.discipline}/${x}`), conf: a?.conf, fallback: a?.code === FALLBACK_S || d?.code === FALLBACK_D, discOk: d?.code === t.discipline }));
      } else if (question === 'sub_oracle') {
        if (!t.sub) continue;
        const a = ofPred(p?.oracle?.[t.discipline]);
        items.push(makeItem({ key: s.key, pred: a?.code ?? null, truth: t.sub, alt: t.subAlt ?? [], conf: a?.conf, fallback: a?.code === FALLBACK_S, discOk: true }));
      } else {
        if (!t.division) continue;
        const a = ofPred(question === 'division' ? p?.division : p?.division_app);
        items.push(makeItem({ key: s.key, pred: a?.code ?? null, truth: t.division, alt: t.divAlt ?? [], conf: a?.conf, fallback: false }));
      }
    }
    return items;
  }
  const elementSubjects = elements.map((e) => { const t = tr(e.id); return { key: e.id, sig: sigOfId.get(e.id), truth: { discipline: t.discipline, sub: t.subDiscipline, subAlt: t.alt?.subDiscipline, division: t.division, divAlt: t.alt?.division } }; });
  const sigSubjects = groups.map((g) => { const t = sigTruth(g); return { key: g.sig, sig: g.sig, truth: { discipline: t.discipline.value, sub: t.sub.value, subAlt: t.sub.alt, division: t.division.value, divAlt: t.division.alt } }; });

  const metrics = {};
  const confusionItems = {};
  for (const [arm, r] of Object.entries(results)) {
    metrics[arm] = {};
    for (const variant of Object.keys([...r.entries.values()][0]?.variants ?? { cal: 1 })) {
      const m = (metrics[arm][variant] = { element: {}, signature: {}, chaining: {} });
      for (const [level, subjects] of [['element', elementSubjects], ['signature', sigSubjects]]) {
        const itemsByQ = {};
        for (const q of QUESTIONS) { itemsByQ[q] = itemsFor(q, variant, r.entries, subjects, false); m[level][q] = summarise(itemsByQ[q], MIN); }
        m.chaining[level] = compareChainedOracle(itemsByQ.sub_chained, itemsByQ.sub_oracle);
        if (level === 'element' && variant === 'cal') confusionItems[arm] = Object.fromEntries(QUESTIONS.map((q) => [q, m.element[q].confusions]));
      }
    }
    const es = [...r.entries.values()];
    {
      const sigs = es.length;
      timings[arm].signatures = sigs;
      timings[arm].secondsPerSignatureApp = sigs ? es.reduce((s, e) => s + (e.msApp ?? 0), 0) / sigs / 1000 : 0;
      timings[arm].secondsPerSignatureAll = sigs ? es.reduce((s, e) => s + (e.msAll ?? 0), 0) / sigs / 1000 : 0;
    }
  }

  // ------------------------------------------------------------ 6. output
  const f = (x, d = 0) => fmtPct(x, d);
  const rows = (q, level) => {
    const lines = [`| arm | n | strict | lenient | cover@${MIN} | prec@${MIN} | ECE | GEN/UNC/abstain | s/sig |`, '|---|---|---|---|---|---|---|---|---|'];
    for (const arm of Object.keys(results)) for (const variant of Object.keys(metrics[arm])) {
      const s = metrics[arm][variant][level][q];
      if (!s || !s.n) continue;
      const name = Object.keys(metrics[arm]).length > 1 ? `${arm} ${variant}` : arm;
      lines.push(`| ${name} | ${s.n} | ${f(s.accuracy)} | ${f(s.lenient)} | ${f(s.coverage)} | ${f(s.precision)} | ${Number.isFinite(s.ece) ? s.ece.toFixed(2) : '-'} | ${f(s.fallback)} | ${variant === 'raw' ? '' : (timings[arm].secondsPerSignatureApp ?? 0).toFixed(1)} |`);
    }
    return lines.join('\n');
  };
  const md = [];
  md.push(`# Truth bench: ${args.model}`, '');
  md.push(`Truth: ${args.truth ? args.truth : '-'} (${truthFile.generator ?? 'no generator'}; ${truthFile.convention ?? ''}). ${elements.length} elements with truth in ${groups.length} signatures${args.limit ? ` (--limit ${args.limit})` : ''}; ${noTruth.length} elements without truth, ${orphanTruth.length} truth entries without an element.`);
  md.push(`"cal" = shipped temperatures (the app's auto mode), "raw" = T 1. Strict/lenient: lenient also accepts the truth's alt. cover/prec at minConfidence ${MIN}. s/sig = seconds per signature on the app's path (main + chained sub request). Rules and majority have confidence 1 (majority: the class share); a rules no-match is an abstain.`, '');
  for (const q of QUESTIONS) {
    md.push(`## ${q}${q === 'sub_chained' ? ' (right only when discipline and sub match)' : q === 'division_app' ? ' (only when building_element >= 0.5)' : ''}`, '', 'Per element', '', rows(q, 'element'), '', 'Per signature', '', rows(q, 'signature'), '');
  }
  md.push('## Chained versus oracle sub-discipline', '', '| arm | level | chained | oracle | gap | chained, discipline right | chained wrong discipline | oracle right, chained wrong | of which discipline wrong |', '|---|---|---|---|---|---|---|---|---|');
  for (const arm of Object.keys(results)) for (const variant of Object.keys(metrics[arm])) for (const level of ['element', 'signature']) {
    const c = metrics[arm][variant].chaining[level];
    md.push(`| ${Object.keys(metrics[arm]).length > 1 ? `${arm} ${variant}` : arm} | ${level} | ${f(c.chainedAccuracy)} | ${f(c.oracleAccuracy)} | ${Number.isFinite(c.gap) ? (c.gap * 100).toFixed(0) : '-'} pts | ${f(c.chainedAccuracyGivenDisciplineRight)} | ${c.chainedWrongDiscipline}/${c.n} | ${c.oracleOnly} | ${c.lostToDiscipline} |`);
  }
  md.push('', '## Timing', '', '| arm | signatures | load s | wall s (all runs) | s/sig (app path) | s/sig (all calls) |', '|---|---|---|---|---|---|');
  for (const arm of Object.keys(results)) { const t = timings[arm]; md.push(`| ${arm} | ${t.signatures} | ${(t.loadMs / 1000).toFixed(1)} | ${(t.wallMsTotal / 1000).toFixed(1)} | ${t.secondsPerSignatureApp.toFixed(2)} | ${t.secondsPerSignatureAll.toFixed(2)} |`); }
  md.push('', '## Top confusions (per element, cal; truth -> predicted, count)', '');
  for (const q of QUESTIONS) {
    md.push(`### ${q}`, '');
    for (const arm of Object.keys(results)) { const c = confusionItems[arm]?.[q] ?? []; md.push(`- ${arm}: ${c.length ? c.map((x) => `${x.pair} (${x.count})`).join('; ') : 'none'}`); }
    md.push('');
  }
  const text = md.join('\n');
  const jsonSafe = (k, v) => (typeof v === 'number' && !Number.isFinite(v) ? null : v instanceof Map ? Object.fromEntries(v) : v);
  const full = {
    model: args.model, truth: args.truth, minConfidence: MIN, limit: args.limit ?? null, minConfidenceSchema: schema.minConfidence,
    join: { elements: inputs.length, truthEntries: Object.keys(truthOf).length, withoutTruth: noTruth.map((i) => i.id), truthWithoutElement: orphanTruth },
    signatures: groups.map((g) => ({ signature: g.sig, rep: g.rep.id, elements: g.members.map((m) => m.id), truth: sigTruth(g) })),
    timings, metrics,
    perSignature: Object.fromEntries(Object.entries(results).map(([arm, r]) => [arm, Object.fromEntries(r.entries)])),
  };
  writeFileSync(join(OUT, 'truth-bench.json'), JSON.stringify(full, jsonSafe, 1));
  writeFileSync(join(OUT, 'truth-bench.md'), text);
  console.log(text);
} finally {
  await server.close();
}
