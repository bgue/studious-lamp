// Scores the element classifiers against a MEASURED ground truth (xray-truth/1, from the model generator) instead of against our own rules.
//
//   cd web && NODE_USE_ENV_PROXY=1 node bench/real-classify-truth.mjs --model process-plant --truth ../models/Process-Plant.truth.json \
//        --arms rules,majority,xsmall,base2,d3,hybrid-xsmall,hybrid-d3 [--limit N] [--out <dir>] [--geometry <geometry.json>] [--psets-cap N]
//
// --sidecar <path/to/model.json> replaces --model: the element sidecar (xray-model/1) of any model, e.g. one written by tools/ifc2glb.py. --model is then only the
// label (default: the file name without .json). `npm run classify:truth` does the IFC conversion and the truth checks and then calls this script.
//
// Arms (run one after the other, each cached per signature in <out>/cache/<arm>.json, so a crash or a rerun redoes nothing; a model is loaded only when a call
// is not in the cache):
//   rules     the app's rules (classByRules + resolveRule), confidence 1, no match = abstain
//   majority  the most frequent truth class per question (trivial baseline, confidence = the class share)
//   xsmall    MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33 (q8), the app default
//   base2     MoritzLaurer/deberta-v3-base-zeroshot-v2.0 (fp32)
//   d3        d3-edge, text only, state cap 2000 bytes (the app default), onnxruntime-node with the warsang export
//   d3-psets  d3 with the full property sets: the state cap raised until no signature is truncated (--psets-cap, default: the largest full state, rounded up)
//   d3-svg    d3 plus the app's SVG geometry text of the element alone      (needs --geometry <geometry.json>)
//   d3-svg-ctx      d3 plus the SVG with the element in its bounding box with the elements around it
//   d3-svg-ctx-psets  the same with the full property sets
//   hybrid-<arm>  the app's REAL pipeline (classifyInputs with rules on: a final rule is used as it is, for discipline, sub and division together; the model answers the
//                 rest) over every element, with the model of <arm> served from that arm's cache (it calls the model only for a state that the cache does not have)
// geometry.json comes from bench/d3/make-bench-pictures.mjs with GEOMETRY_ONLY=1 REPS_FILE=<out>/reps.json (written by every run of this script).
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
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';
import { MIN_CONFIDENCE, compareChainedOracle, fmtPct, groupTruth, makeItem, mostFrequent, summarise } from './truth-metrics.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const SCRATCH = '/tmp/claude-0/-home-user-studious-lamp/d3dc753b-6b35-532c-aed4-18bc78aeb28a/scratchpad';
const MIN = Number(process.env.MIN_CONF ?? MIN_CONFIDENCE);
const D3_STATE_CAP = 2000;

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
if (args.sidecar && !args.model) args.model = basename(args.sidecar).replace(/\.json$/i, '');
if (!args.model) throw new Error('Usage: --model <sidecar name in public/models> | --sidecar <path/to/sidecar.json>  --truth <truth.json> --arms rules,majority,xsmall,base2,d3 [--limit N] [--out dir]');
if (!args.truth && !args.count) throw new Error('--truth is required.');
const ARMS = args.arms.split(',').map((s) => s.trim()).filter(Boolean);
const BASE_ARMS = ['xsmall', 'base2', 'd3', 'd3-psets', 'd3-svg', 'd3-svg-ctx', 'd3-svg-ctx-psets'];
const KNOWN = ['rules', 'majority', ...BASE_ARMS, ...BASE_ARMS.map((b) => `hybrid-${b}`)];
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
  // A bundled model by name (public/models/<name>.json), or any sidecar file by path (the same SceneModel that sidecarModel builds).
  const sidecarFromFile = async (file) => {
    const L = await server.ssrLoadModule('/src/model/loader.ts');
    const j = JSON.parse(readFileSync(resolve(file), 'utf8'));
    const elements = j.elements.map((r, i) => L.normaliseRecord(r, i));
    return { schema: 'xray-model/1', units: 'm', originShift: j.originShift ?? [0, 0, 0], storeys: j.storeys ?? [], elements, relations: L.normaliseRelations(j.relations), byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])) };
  };
  const model = args.sidecar ? await sidecarFromFile(args.sidecar) : H.sidecarModel(args.model);
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
  // The representatives, for bench/d3/make-bench-pictures.mjs (REPS_FILE): the same element the arms send to the model.
  writeFileSync(join(OUT, 'reps.json'), JSON.stringify(groups.map((g) => ({ model: args.model, signature: g.sig, gid: g.rep.id, ifcClass: g.rep.ifcClass, members: g.members.length }))));
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
  // An arm may share the cache file of another (`cacheAs`): the key holds the state itself, so a state that differs is simply a miss.
  const loadCache = (arm) => {
    const f = join(OUT, 'cache', `${arm}.json`);
    let c = { arm, model: args.model, entries: {}, meta: { wallMs: 0, loadMs: 0 } };
    try { if (existsSync(f)) { const j = JSON.parse(readFileSync(f, 'utf8')); if (j.arm === arm) c = j; } } catch { /* start over */ }
    c.meta ??= { wallMs: 0, loadMs: 0 };
    const save = () => { writeFileSync(`${f}.tmp`, JSON.stringify(c)); renameSync(`${f}.tmp`, f); };
    return { c, save };
  };

  /** The state of a signature's representative as the app builds it for a request: buildState under the cap, then the SVG geometry text in front (pipeline.ts). */
  const stateOf = (rep, maxState, geometryOf) => {
    let state = C.buildState(rep, maxState);
    if (geometryOf) { const geo = geometryOf(rep); if (geo) state = { geometry: `${geo.legend} ${geo.svg.replace(/\n/g, ' ')}`, ...state }; }
    return state;
  };
  const bytesOf = (v) => Buffer.byteLength(JSON.stringify(v));

  /** A provider that is loaded on its first call: an arm whose calls are all cached never loads its model. */
  const lazyProvider = (arm, make) => {
    let loaded = null;
    return {
      provider: arm,
      loadMs: () => loaded?.loadMs ?? 0,
      loaded: () => !!loaded,
      async decide(state, questions, signal, extra) {
        loaded ??= await make();
        return loaded.p.decide(state, questions, signal, extra);
      },
      async dispose() { const l = loaded; loaded = null; try { await l?.p.dispose?.(); } catch { /* ignore */ } },
    };
  };

  async function runModelArm(arm, { provider, modelId, maxState, geometryOf, tokensOf, cacheAs }) {
    const { c, save } = loadCache(cacheAs ?? arm);
    const shipped = CD.SHIPPED_TEMPERATURES[modelId]?.temperatures ?? {};
    const variants = { cal: shipped, raw: {} };
    const ctl = new AbortController();
    const t0 = Date.now();
    const out = new Map();
    let done = 0;
    for (const g of groups) {
      const state = stateOf(g.rep, maxState, geometryOf);
      const h = sha(`${args.model}|${cacheAs ?? arm}|${g.sig}|${JSON.stringify(state)}`);
      const call = async (key, questions) => {
        const k = `${h}|${key}`;
        if (c.entries[k]) return c.entries[k];
        const t = Date.now();
        const a = await provider.decide(state, questions, ctl.signal);
        const e = { raw: K.rawOfAnswers(a), ms: Date.now() - t, tokens: a.usage?.input_tokens ?? null };
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
      const entry = { sig: g.sig, hash: h, rep: g.rep.id, members: g.members.length, variants: {}, rawScores: {}, stateBytes: bytesOf(state), stateTokens: tokensOf ? tokensOf(state) : null };
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
    return { entries: out, timing: { wallMsTotal: c.meta.wallMs, wallMsThisRun: Date.now() - t0, loadMs: provider.loadMs?.() ?? 0 }, cache: c, save, variants };
  }

  /**
   * The hybrid arm: the app's own pipeline (classifyInputs, rules on) over every element, with the model served from the cache of the base arm.
   * A final rule decides an element completely; any other element is answered by the model of the base arm, through the signature cache of the pipeline.
   */
  async function runHybrid(arm, base, baseRun, def, provider) {
    const c = baseRun.cache, save = baseRun.save;
    const shipped = CD.SHIPPED_TEMPERATURES[def.modelId]?.temperatures ?? {};
    const variants = { cal: shipped, raw: {} };
    const hashOfState = new Map();
    for (const g of groups) hashOfState.set(JSON.stringify(stateOf(g.rep, def.maxState, def.geometryOf)), { sig: g.sig, h: baseRun.entries.get(g.sig).hash });
    const codesOf = (questions) => {
      const sub = questions[Q.Q_SUB];
      if (!sub) return null;
      const keys = Object.keys(sub.criteria);
      let codes;
      if (keys[0].includes(Q.COMBINED_SEP)) codes = [...new Set(keys.map((k) => k.split(Q.COMBINED_SEP)[0]))];
      else codes = [schema.disciplines.find((d) => d.subDisciplines.length === keys.length && d.subDisciplines.every((x) => keys.includes(x.code)))?.code];
      if (!codes[0] || JSON.stringify(Q.subQuestions(schema, codes)) !== JSON.stringify(questions)) throw new Error('hybrid: cannot tell which sub-discipline codes a question covers');
      return codes;
    };
    let served = 0, called = 0;
    const cached = {
      provider: `hybrid:${base}`,
      async decide(state, questions, signal, extra) {
        const hit = hashOfState.get(JSON.stringify(state));
        const codes = codesOf(questions);
        const key = hit ? `${hit.h}|${codes ? `sub:${codes.join('+')}` : 'main'}` : null;
        if (key && c.entries[key]) { served++; return K.answersFromRaw(c.entries[key].raw, {}); }
        called++;
        const a = await provider.decide(state, questions, signal, extra);
        if (key) { c.entries[key] = { raw: K.rawOfAnswers(a), ms: 0, tokens: a.usage?.input_tokens ?? null }; save(); }
        return a;
      },
    };
    const out = new Map(groups.map((g) => [g.sig, { sig: g.sig, rep: g.rep.id, members: g.members.length, variants: {}, byElement: {}, msApp: 0, msAll: 0, stateBytes: baseRun.entries.get(g.sig).stateBytes, stateTokens: baseRun.entries.get(g.sig).stateTokens }]));
    const t0 = Date.now();
    const bySource = {};
    for (const [vn, temps] of Object.entries(variants)) {
      const run = await C.classifyInputs(elements, {
        schema, provider: cached, minConfidence: schema.minConfidence, rules: true, cache: new C.MemoryCache(), temperatures: temps, concurrency: 1,
        subDiscipline: P.SUB_STRATEGIES['top2-when-unsure'], maxStateBytes: def.maxState,
        ...(def.geometryOf ? { geometry: (rep) => def.geometryOf(rep) } : {}),
      });
      const byId = new Map(run.results.map((r) => [r.id, r]));
      bySource[vn] = run.stats.bySource;
      if (run.stats.errors.length) log(`  [${arm}] ${vn}: ${run.stats.errors.join('; ')}`);
      for (const g of groups) {
        const e = out.get(g.sig);
        const be = (e.byElement[vn] = {});
        const baseEntry = baseRun.entries.get(g.sig);
        for (const m of g.members) {
          const r = byId.get(m.id);
          const pred = { discipline: null, sub_chained: null, division: null, division_app: null, oracle: {}, source: r?.source ?? null };
          if (r) {
            pred.discipline = ans(r.discipline.code, r.discipline.confidence);
            pred.sub_chained = r.subDiscipline ? ans(r.subDiscipline.code, r.subDiscipline.confidence) : null;
            pred.division_app = r.masterformat ? ans(r.masterformat.division, r.masterformat.confidence) : null;
            if (r.source === 'rules') {
              pred.division = pred.division_app;
              for (const td of trueDiscs(g)) pred.oracle[td] = pred.sub_chained;
            } else {
              // From the model: the ungated division and the oracle sub are the base arm's answers for this signature, as the pipeline decoded them.
              const bp = baseEntry.variants[vn];
              pred.division = bp.division;
              pred.oracle = bp.oracle;
            }
          }
          be[m.id] = pred;
        }
        e.variants[vn] = be[g.rep.id];
        if (vn === 'cal') { const viaModel = be[g.rep.id]?.source && be[g.rep.id].source !== 'rules'; e.msApp = viaModel ? baseEntry.msApp ?? 0 : 0; e.msAll = viaModel ? baseEntry.msAll ?? 0 : 0; }
      }
    }
    log(`  [${arm}] served ${served} model calls from the cache of ${base}, ${called} new`);
    return { entries: out, timing: { wallMsTotal: Date.now() - t0, wallMsThisRun: Date.now() - t0, loadMs: 0 }, bySource };
  }

  // ------------------------------------------------------------ the arms
  async function runRules() {
    const t0 = Date.now();
    const out = new Map();
    // Per element, as the app does (the rules read the name and properties of each element, not only those of the signature's representative).
    const predOf = (i, g) => {
      const hit = C.classByRules(i);
      const building = C.isBuildingContext(i);
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
      return pred;
    };
    for (const g of groups) {
      const be = {};
      for (const m of g.members) be[m.id] = predOf(m, g);
      out.set(g.sig, { sig: g.sig, rep: g.rep.id, members: g.members.length, variants: { cal: be[g.rep.id] ?? predOf(g.rep, g) }, byElement: { cal: be }, msApp: 0, msAll: 0 });
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
  const D3DIR = need('D3_DIR', join(SCRATCH, 'd3web'));
  const d3Provider = async () => {
    const { readFile } = await import('node:fs/promises');
    const D3 = await server.ssrLoadModule('/src/classify/providers/d3.ts');
    const ort = await import(pathToFileURL(need('ORT_NODE', join(SCRATCH, 'ortnode/node_modules/onnxruntime-node/dist/index.js'))).href);
    const tjs = await import(pathToFileURL(need('TRANSFORMERS_NODE', join(SCRATCH, 'ortnode/node_modules/@huggingface/transformers/dist/transformers.node.mjs'))).href);
    const source = { has: async () => true, read: async (f) => new Uint8Array(await readFile(join(D3DIR, f))) };
    const fetchImpl = async (url) => {
      const f = String(url).split('/resolve/')[1]?.split('/').slice(1).join('/');
      try { return new Response(await readFile(join(D3DIR, f)), { status: 200 }); } catch { return new Response('', { status: 404 }); }
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
  // Tokens of the state as d3 reads it (the Qwen tokenizer of the export): the text of the state in the prompt, without the question.
  let tokenizerPromise = null;
  const d3Tokenizer = async () => {
    tokenizerPromise ??= (async () => {
      const tjs = await import(pathToFileURL(need('TRANSFORMERS_NODE', join(SCRATCH, 'ortnode/node_modules/@huggingface/transformers/dist/transformers.node.mjs'))).href);
      const F = await server.ssrLoadModule('/src/classify/providers/d3Format.ts');
      const tok = new tjs.PreTrainedTokenizer(JSON.parse(readFileSync(join(D3DIR, 'tokenizer.json'), 'utf8')), JSON.parse(readFileSync(join(D3DIR, 'tokenizer_config.json'), 'utf8')));
      return (state) => tok.encode(F.d3Describe(state), { add_special_tokens: false }).length;
    })();
    return tokenizerPromise;
  };

  const MODELS = { xsmall: ['MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', 'q8'], base2: ['MoritzLaurer/deberta-v3-base-zeroshot-v2.0', 'fp32'] };
  const geometry = args.geometry ? JSON.parse(readFileSync(resolve(args.geometry), 'utf8')) : null;
  // The cap that leaves no signature truncated: the largest state at full detail (level 0), rounded up to 500 bytes.
  const fullBytes = Math.max(...groups.map((g) => bytesOf(C.buildState(g.rep, 10_000_000))));
  const PSETS_CAP = Number(args.psetsCap ?? Math.ceil(fullBytes / 500) * 500);
  log(`largest full state ${fullBytes} bytes; psets cap ${PSETS_CAP}`);
  const defOf = (base) => {
    if (base === 'xsmall' || base === 'base2') return { kind: 'decision', maxState: 4000, modelId: `decision:${MODELS[base][0]}`, geometryOf: null };
    const geo = base.includes('-svg-ctx') ? 'context' : base.includes('-svg') ? 'isolated' : null;
    const maxState = base.endsWith('psets') ? PSETS_CAP : D3_STATE_CAP;
    // The -psets arms read the same cache as their plain twin: with no truncation at the lower cap the states are byte for byte the same and every call is a hit.
    return { kind: 'd3', maxState, modelId: 'd3', geometryOf: geo ? (i) => geometry?.[`${args.model}|${i.id}`]?.[geo] ?? null : null, geo, cacheAs: base.endsWith('-psets') ? base.slice(0, -6) : null };
  };
  const results = {};
  const timings = {};
  const baseRuns = {};
  const providers = {};
  const providerFor = (base) => (providers[base] ??= lazyProvider(base, () => (defOf(base).kind === 'd3' ? d3Provider() : decisionProvider(...MODELS[base]))));
  const runBase = async (base) => {
    if (baseRuns[base]) return baseRuns[base];
    const def = defOf(base);
    if (def.geo && !geometry) throw new Error(`arm ${base} needs --geometry <geometry.json> (bench/d3/make-bench-pictures.mjs with GEOMETRY_ONLY=1 REPS_FILE=<out>/reps.json).`);
    if (def.geo) { const miss = groups.filter((g) => !geometry[`${args.model}|${g.rep.id}`]?.[def.geo]); if (miss.length) throw new Error(`${miss.length} representatives have no ${def.geo} geometry in ${args.geometry}.`); }
    const tokensOf = def.kind === 'd3' ? await d3Tokenizer() : null;
    const r = await runModelArm(base, { provider: providerFor(base), modelId: def.modelId, maxState: def.maxState, geometryOf: def.geometryOf, tokensOf, cacheAs: def.cacheAs });
    baseRuns[base] = r;
    return r;
  };
  try {
    for (const arm of ARMS) {
      log(`\n== arm ${arm}`);
      let r;
      if (arm === 'rules') r = await runRules();
      else if (arm === 'majority') r = await runMajority();
      else if (arm.startsWith('hybrid-')) {
        const base = arm.slice(7);
        const br = await runBase(base);
        r = await runHybrid(arm, base, br, defOf(base), providerFor(base));
        r.timing.loadMs = br.timing.loadMs;
      } else r = await runBase(arm);
      results[arm] = r;
      timings[arm] = r.timing;
      if (providers[arm]?.loaded()) { timings[arm].loadMs = providers[arm].loadMs(); await providers[arm].dispose(); }
    }
  } finally {
    for (const p of Object.values(providers)) await p.dispose();
  }
  for (const [arm, r] of Object.entries(results)) if (r.bySource) timings[arm].bySource = r.bySource;

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
      // A hybrid arm answers per element (a final rule can decide one element of a signature and not another); the other arms per signature.
      const p = e?.byElement?.[variant]?.[s.key] ?? e?.variants[variant] ?? null;
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
  const meanOf = (arm, key) => { const xs = [...results[arm].entries.values()].map((e) => e[key]).filter((x) => typeof x === 'number'); return xs.length ? xs.reduce((p, x) => p + x, 0) / xs.length : null; };
  md.push('## Summary (per element)', '', `Strict accuracy per question; cover/prec at ${MIN} for the discipline and the chained sub-discipline; ECE and GEN/UNC rate of the discipline; mean state bytes and tokens of the representative (tokens: d3 arms, the Qwen tokenizer on the state text); s/sig as in the tables below. hybrid-*: the app's pipeline with final rules, see the arm list in bench/real-classify-truth.mjs.`, '',
    `| arm | discipline | sub chained | sub oracle | division | division (app) | disc cover | disc prec | sub cover | sub prec | disc ECE | disc GEN | state B | state tok | s/sig |`, '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|');
  for (const arm of Object.keys(results)) for (const variant of Object.keys(metrics[arm])) {
    const m = metrics[arm][variant].element;
    const name = Object.keys(metrics[arm]).length > 1 ? `${arm} ${variant}` : arm;
    const sb = meanOf(arm, 'stateBytes'), st = meanOf(arm, 'stateTokens');
    md.push(`| ${name} | ${f(m.discipline.accuracy, 1)} | ${f(m.sub_chained.accuracy, 1)} | ${f(m.sub_oracle.accuracy, 1)} | ${f(m.division.accuracy, 1)} | ${f(m.division_app.accuracy, 1)} | ${f(m.discipline.coverage, 1)} | ${f(m.discipline.precision, 1)} | ${f(m.sub_chained.coverage, 1)} | ${f(m.sub_chained.precision, 1)} | ${Number.isFinite(m.discipline.ece) ? m.discipline.ece.toFixed(2) : '-'} | ${f(m.discipline.fallback, 1)} | ${sb === null ? '' : Math.round(sb)} | ${st === null ? '' : Math.round(st)} | ${variant === 'raw' ? '' : (timings[arm].secondsPerSignatureApp ?? 0).toFixed(1)} |`);
  }
  md.push('');
  for (const arm of Object.keys(results)) if (timings[arm].bySource) md.push(`${arm}: elements by source, cal ${JSON.stringify(timings[arm].bySource.cal)}`);
  md.push('');
  for (const q of QUESTIONS) {
    md.push(`## ${q}${q === 'sub_chained' ? ' (right only when discipline and sub match)' : q === 'division_app' ? ' (only when building_element >= 0.5)' : ''}`, '', 'Per element', '', rows(q, 'element'), '', 'Per signature', '', rows(q, 'signature'), '');
  }
  md.push('## Chained versus oracle sub-discipline', '', '| arm | level | chained | oracle | gap | chained, discipline right | chained wrong discipline | oracle right, chained wrong | of which discipline wrong |', '|---|---|---|---|---|---|---|---|---|');
  for (const arm of Object.keys(results)) for (const variant of Object.keys(metrics[arm])) for (const level of ['element', 'signature']) {
    const c = metrics[arm][variant].chaining[level];
    md.push(`| ${Object.keys(metrics[arm]).length > 1 ? `${arm} ${variant}` : arm} | ${level} | ${f(c.chainedAccuracy)} | ${f(c.oracleAccuracy)} | ${Number.isFinite(c.gap) ? (c.gap * 100).toFixed(0) : '-'} pts | ${f(c.chainedAccuracyGivenDisciplineRight)} | ${c.chainedWrongDiscipline}/${c.n} | ${c.oracleOnly} | ${c.lostToDiscipline} |`);
  }
  // Flips against the text-only d3: per signature (the truth of a signature = the majority of its elements), cal variant, strict.
  if (results['d3']) {
    const others = Object.keys(results).filter((x) => x !== 'd3' && x.startsWith('d3-') && !x.endsWith('-psets'));
    const sigLabel = new Map(groups.map((g) => [g.sig, `${g.rep.ifcClass} ${g.rep.type?.name ?? g.rep.name} (${g.members.length})`]));
    if (others.length) {
      md.push('', '## Flips against d3 (text only), per signature, cal', '');
      for (const arm of others) for (const q of ['discipline', 'sub_chained']) {
        const base = new Map(itemsFor(q, 'cal', results['d3'].entries, sigSubjects, false).map((i) => [i.key, i]));
        const cur = new Map(itemsFor(q, 'cal', results[arm].entries, sigSubjects, false).map((i) => [i.key, i]));
        const fix = [], broke = [];
        for (const [k, b] of base) { const c = cur.get(k); if (!c) continue; if (!b.ok && c.ok) fix.push(`${sigLabel.get(k)}: ${b.pred} -> ${c.pred}`); if (b.ok && !c.ok) broke.push(`${sigLabel.get(k)}: ${b.pred} -> ${c.pred} (truth ${c.truth})`); }
        md.push(`- ${arm}, ${q}: ${fix.length} signatures wrong to right, ${broke.length} right to wrong.${fix.length ? ` Fixed, e.g. ${fix.slice(0, 4).join('; ')}.` : ''}${broke.length ? ` Broken, e.g. ${broke.slice(0, 4).join('; ')}.` : ''}`);
      }
    }
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
