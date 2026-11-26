// The pipeline commands of xray-4d: link, plan, render, pack, all. Registered into the command table by tools/xray-4d.mjs
// (makeCommands). Progress goes to stderr (io.err), results to stdout or -o.
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..', '..');
const fmtMs = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + ' s' : Math.round(n) + ' ms');
const fmtKB = (n) => (n >= 1048576 ? (n / 1048576).toFixed(2) + ' MB' : (n / 1024).toFixed(1) + ' KB');

export const EXIT_COVERAGE = 4;
export const EXIT_RENDER = 5;

export function makeCommands({ loadParser, CliError, EXIT_OK, EXIT_USAGE, EXIT_INPUT, parseArgs }) {
  const usage = (m) => new CliError(m, EXIT_USAGE);
  const input = (m) => new CliError(m, EXIT_INPUT);
  const fail = (m, code) => new CliError(m, code);

  // ------------------------------------------------------------ inputs
  function readFile(path, what) {
    const p = resolve(path);
    if (!existsSync(p) || !statSync(p).isFile()) throw input(`cannot read ${what} ${path}`);
    return readFileSync(p);
  }
  function readJson(path, what) {
    const text = readFile(path, what).toString('utf8').replace(/^\uFEFF/, '');
    try {
      return JSON.parse(text);
    } catch (e) {
      throw input(`${what} ${path} is not valid JSON (${e.message})`);
    }
  }

  /** The 4D configuration: JSON only (no YAML parser is installed in node_modules, and none is added); style defaults filled in. */
  function loadConfig(path, parser) {
    if (/\.ya?ml$/i.test(path)) throw input(`${path}: YAML configs are not supported (no YAML parser is installed); write the config as JSON (.4d.json)`);
    const c = readJson(path, 'config');
    if (!c || typeof c !== 'object' || Array.isArray(c)) throw input(`config ${path} must be a JSON object`);
    if (c.schema !== undefined && c.schema !== 'xray-4d-config/1') throw input(`config ${path}: unsupported schema "${c.schema}" (expected xray-4d-config/1)`);
    if (!c.schedule || !c.model) throw input(`config ${path}: "schedule" and "model" sections are required (see web/public/samples/fzk-haus.4d.json)`);
    return { ...c, schema: 'xray-4d-config/1', style: { ...parser.DEFAULT_STYLE, ...(c.style ?? {}) } };
  }

  function loadSchedule(path, parser, project) {
    const bytes = new Uint8Array(readFile(path, 'schedule'));
    try {
      return parser.parseXer(bytes, { project });
    } catch (e) {
      throw input(`${basename(path)}: ${e.message}`);
    }
  }

  /** The model through the node IFC reader: { model (FourDModel), bytes, expressIds, globalIdOf, schema }. */
  async function loadModel(path, parser, io) {
    const { convertIfcFiles } = await import(pathToFileURL(join(webRoot, 'tools', 'pack', 'convert.mjs')).href);
    const bytes = new Uint8Array(readFile(path, 'model'));
    const t0 = performance.now();
    let res;
    try {
      res = await convertIfcFiles([{ name: basename(path), bytes }]);
    } catch (e) {
      throw input(`cannot read ${basename(path)}: ${String(e.message ?? e).split('\n')[0]}`);
    }
    const model = parser.fromSidecar(res.sidecar, { name: basename(path).replace(/\.(ifczip|ifc)$/i, '') });
    const expressIds = new Map();
    const globalIdOf = new Map();
    for (const e of res.sidecar.elements) if (e.expressId !== undefined) { expressIds.set(e.globalId, e.expressId); globalIdOf.set(e.expressId, e.globalId); }
    io.err(`model ${basename(path)}: ${model.elements.length} elements, ${res.files[0]?.schema ?? '?'}, read in ${fmtMs(performance.now() - t0)}`);
    return { model, bytes, expressIds, globalIdOf, schema: res.files[0]?.schema ?? '' };
  }

  const out = (args, io, text, what) => {
    if (args.out) {
      mkdirSync(dirname(resolve(args.out)), { recursive: true });
      writeFileSync(resolve(args.out), text);
      io.err(`wrote ${what} ${args.out} (${fmtKB(Buffer.byteLength(text))})`);
    } else io.out(text.replace(/\n$/, ''));
  };

  async function writeIfc(parser, m, schedule, links, plan, view, path, io) {
    const skip = parser.workScheduleSkipReason(m.schema);
    if (skip) {
      io.err(`xray-4d: warning: ${skip}`);
      return false;
    }
    const { save, warnings } = parser.buildWorkSchedule({ schedule, links, expressIds: m.expressIds, ...(plan ? { plan } : {}), view });
    for (const w of warnings) io.err(`xray-4d: warning: ${w}`);
    if (!save) {
      io.err('xray-4d: warning: no accepted link with elements: nothing to write to the IFC');
      return false;
    }
    const w = await parser.writeWorkSchedule(m.bytes, save);
    mkdirSync(dirname(resolve(path)), { recursive: true });
    writeFileSync(resolve(path), w.bytes);
    io.err(`wrote IFC ${path}: ${save.tasks.length} tasks, ${save.sequences.length} sequences, ${w.lines} lines${w.replaced ? ' (earlier XRAY block replaced)' : ''}`);
    return true;
  }

  // ------------------------------------------------------------ link
  async function doLink(args, io) {
    const [modelPath, xerPath] = args._;
    if (!modelPath || !xerPath || args._.length > 2) throw usage('link needs a model and a schedule: xray-4d link model.ifc schedule.xer --config map.4d.json -o links.json');
    if (!args.config) throw usage('link needs --config <map.4d.json>');
    const minCov = args['min-coverage'] === undefined ? undefined : Number(args['min-coverage']);
    if (minCov !== undefined && !(minCov >= 0 && minCov <= 1)) throw usage('--min-coverage needs a number from 0 to 1');
    const parser = await loadParser();
    const config = loadConfig(args.config, parser);
    const schedule = loadSchedule(xerPath, parser, args.project ?? config.schedule.project);
    const m = await loadModel(modelPath, parser, io);
    const assignments = [];
    let priorLinks = [];
    if (args.assignments) {
      const doc = readJson(args.assignments, 'assignments');
      if (!Array.isArray(doc.assignments)) throw input(`assignments ${args.assignments}: no "assignments" list (a LinkML LinkDataset from the mapping tool)`);
      assignments.push(...doc.assignments);
    }
    if (args.prior) {
      const doc = readJson(args.prior, 'prior links');
      if (!Array.isArray(doc.links)) throw input(`prior links ${args.prior}: no "links" list (a links.json)`);
      priorLinks = doc.links;
      if (Array.isArray(doc.assignments) && !args.assignments) assignments.push(...doc.assignments);
    }
    // native IFC 4D (IfcTask + assignments) of the model itself
    const nativeText = new TextDecoder('latin1').decode(m.bytes);
    const nat = parser.readNativeTasks(nativeText, m.globalIdOf);
    if (nat.tasks > 0) io.err(`native IFC 4D: ${nat.tasks} tasks, ${nat.native.size} elements assigned`);
    const props4d = m.model.elements.filter((e) => Object.keys(e.props).some((k) => k.startsWith('Xray_4D.'))).length;
    if (props4d > 0) io.err(`Xray_4D properties on ${props4d} elements (read through the config's model sources)`);
    let idProperty = args['id-property'];
    if (!idProperty && m.model.elements.some((e) => e.props['Xray_4D.ActivityIds'])) {
      idProperty = 'Xray_4D.ActivityIds';
      io.err('activity ids found in Xray_4D.ActivityIds: used as the id property');
    }
    const warnings = [];
    const links = parser.linkSchedule(schedule, m.model, config, assignments, {
      ...(idProperty ? { idProperty } : {}), native: nat.native, priorLinks, suggest: args['no-suggest'] ? false : true,
      scheduleFileName: basename(xerPath), modelFileName: basename(modelPath), onWarning: (w) => { warnings.push(w); io.err(`xray-4d: warning: ${w}`); },
    });
    const report = parser.buildReport(schedule, links, m.model, { config });
    const cov = report.coverage.elements;
    const acts = report.coverage.activities;
    io.err(`coverage: elements ${(cov.byCount * 100).toFixed(1)} % by count, ${(cov.byVolume * 100).toFixed(1)} % by volume (${cov.linked} of ${cov.considered}); activities ${acts.linked} of ${acts.total} linked`);
    out(args, io, JSON.stringify(links, null, 2) + '\n', 'links');
    if (args.report) {
      mkdirSync(dirname(resolve(args.report)), { recursive: true });
      writeFileSync(resolve(args.report), parser.renderReportHtml(report));
      io.err(`wrote report ${args.report}`);
    }
    if (args['write-ifc']) await writeIfc(parser, m, schedule, links, null, 'planned', args['write-ifc'], io);
    if (minCov !== undefined && cov.byCount < minCov) {
      io.err(`xray-4d: element coverage ${(cov.byCount * 100).toFixed(1)} % is below --min-coverage ${(minCov * 100).toFixed(1)} %`);
      return EXIT_COVERAGE;
    }
    return EXIT_OK;
  }

  // ------------------------------------------------------------ plan
  const parseSeconds = (text, flag) => {
    const m = /^(\d+(?:\.\d+)?)\s*(s|sec|m|min)?$/i.exec(String(text).trim());
    if (!m) throw usage(`${flag} needs a length like 120s or 2m, got "${text}"`);
    const v = Number(m[1]) * (m[2] && m[2].toLowerCase().startsWith('m') ? 60 : 1);
    if (!(v > 0)) throw usage(`${flag} must be above zero`);
    return v;
  };
  function parseWindow(text) {
    if (text === 'all') return { kind: 'all' };
    let m = /^lookahead:(\d+)\s*w?$/i.exec(text);
    if (m) return { kind: 'lookahead', from: 'dataDate', weeks: Number(m[1]) };
    m = /^range:(\d{4}-\d\d-\d\d(?:T\d\d:\d\d)?)\.\.(\d{4}-\d\d-\d\d(?:T\d\d:\d\d)?)$/.exec(text);
    if (m) return { kind: 'range', from: m[1], to: m[2] };
    throw usage(`--window expects all, lookahead:6w or range:2027-05-01..2027-07-01, got "${text}"`);
  }
  function parsePace(text) {
    const m = /^(\d+(?:\.\d+)?)\s*(d|w)\s*=\s*(\d+(?:\.\d+)?)\s*s?$/i.exec(String(text).trim());
    if (!m) throw usage(`--pace expects schedule time per video second like 1w=2s or 3d=1s, got "${text}"`);
    const days = Number(m[1]) * (m[2].toLowerCase() === 'w' ? 7 : 1);
    const secs = Number(m[3]);
    if (!(days > 0) || !(secs > 0)) throw usage('--pace values must be above zero');
    return days / secs;
  }

  async function doPlan(args, io) {
    const [modelPath, xerPath, linksPath] = args._;
    if (!modelPath || !xerPath || !linksPath || args._.length > 3) throw usage('plan needs a model, a schedule and links: xray-4d plan model.ifc schedule.xer links.json --config map.4d.json -o build.4d.json');
    if (!args.config) throw usage('plan needs --config <map.4d.json>');
    if (args.length && args.pace) throw usage('use --length or --pace, not both');
    if (args.view && !['planned', 'actual', 'variance'].includes(args.view)) throw usage(`--view must be planned, actual or variance, got "${args.view}"`);
    const parser = await loadParser();
    const config = loadConfig(args.config, parser);
    const style = { ...config.style };
    if (args.view) style.view = args.view;
    if (args.window) style.window = parseWindow(args.window);
    if (args.length) { style.length = parseSeconds(args.length, '--length'); delete style.daysPerSecond; }
    if (args.pace) { style.daysPerSecond = parsePace(args.pace); delete style.length; }
    const schedule = loadSchedule(xerPath, parser, args.project ?? config.schedule.project);
    const baseline = args.baseline ? loadSchedule(args.baseline, parser, args.project ?? config.schedule.project) : undefined;
    const links = readJson(linksPath, 'links');
    if (!Array.isArray(links.links)) throw input(`links ${linksPath}: no "links" list (a links.json from xray-4d link)`);
    const m = await loadModel(modelPath, parser, io);
    if (links.model?.identity_key && links.model.identity_key !== m.model.identityKey) {
      io.err(`xray-4d: warning: links.json was made for another model (${links.model.identity_key}, this one is ${m.model.identityKey}); elements are matched by GlobalId`);
    }
    if (links.schedule?.source_hash && links.schedule.source_hash !== schedule.sourceHash) io.err('xray-4d: warning: links.json was made for another schedule file (hash differs)');
    const t0 = performance.now();
    const plan = parser.buildPlan(schedule, links, m.model, style, { ...(baseline ? { baseline } : {}), config });
    const secs = plan.timeMap.length ? plan.timeMap[plan.timeMap.length - 1][1] : 0;
    io.err(`plan: view ${style.view}, ${plan.elements.length} elements, ${plan.tasks.length} activities, ${plan.milestones.length} milestones, ${secs.toFixed(1)} s, ${fmtMs(performance.now() - t0)}`);
    out(args, io, JSON.stringify(plan) + '\n', 'plan');
    if (args['write-ifc']) await writeIfc(parser, m, schedule, links, plan, style.view, args['write-ifc'], io);
    return EXIT_OK;
  }

  // ------------------------------------------------------------ script parameters and libraries
  /** `--param name=value` (repeatable) as { name: value }. */
  function parseParamArgs(list) {
    const out = {};
    for (const a of list ?? []) {
      const eq = String(a).indexOf('=');
      if (eq < 1) throw usage(`--param needs name=value, got "${a}"`);
      out[String(a).slice(0, eq).trim()] = String(a).slice(eq + 1);
    }
    return out;
  }
  /** `--use-dir folder`: the .xrayanim files of the folder, by name without the extension, for `use "name"` lines. */
  function readUseDir(dir) {
    if (!dir) return {};
    const d = resolve(dir);
    if (!existsSync(d) || !statSync(d).isDirectory()) throw input(`--use-dir ${dir} is not a folder`);
    const out = {};
    for (const f of readdirSync(d).sort()) if (/\.xrayanim$/i.test(f)) out[f.replace(/\.xrayanim$/i, '')] = readFileSync(join(d, f), 'utf8').replace(/^\uFEFF/, '');
    return out;
  }

  // ------------------------------------------------------------ pack (and the page `render` drives)
  const planName = (p) => basename(p).replace(/\.4d\.json$|\.json$/i, '') || 'plan';

  async function packPage(modelPath, planPath, scriptPath, outPath, extra, io, libFiles = []) {
    for (const [p, w] of [[modelPath, 'model'], [planPath, 'plan'], ...(scriptPath ? [[scriptPath, 'script']] : [])]) readFile(p, w);
    const { run, } = await import(pathToFileURL(join(webRoot, 'tools', 'xray-pack.mjs')).href);
    const { PackError } = await import(pathToFileURL(join(webRoot, 'tools', 'pack', 'lib.mjs')).href);
    const argv = [modelPath, '--plans', planPath, '-o', outPath, '--force', ...(scriptPath ? ['--scripts', [scriptPath, ...libFiles].join(',')] : []), ...extra];
    try {
      const code = await run(argv, { out: (s) => io.err(s), err: (s) => io.err(s) });
      if (code !== 0) throw input(`xray-pack failed (exit ${code})`);
    } catch (e) {
      if (e instanceof PackError) throw input(e.message);
      throw e;
    }
  }

  async function doPack(args, io) {
    const [modelPath, planPath] = args._;
    if (!modelPath || !planPath || args._.length > 2) throw usage('pack needs a model and a plan: xray-4d pack model.ifc build.4d.json [--script film.xrayanim] [--loop] -o build.html');
    if (!args.out) throw usage('pack needs -o <build.html>');
    const name = planName(planPath);
    const params = parseParamArgs(args.param);
    if (Object.keys(params).length && !args.script) throw usage('--param needs --script');
    if (args['use-dir'] && !args.script) throw usage('--use-dir needs --script');
    // the libraries of the folder are packed with the script, so its `use "name"` lines find them in the page
    const libFiles = args['use-dir'] ? Object.keys(readUseDir(args['use-dir'])).map((n) => join(resolve(args['use-dir']), `${n}.xrayanim`)).filter((f) => resolve(f) !== resolve(args.script)) : [];
    await packPage(modelPath, planPath, args.script, args.out, ['--autoplay', `plan:${name}`, '--kiosk', ...Object.entries(params).flatMap(([k, v]) => ['--script-param', `${k}=${v}`]), ...(args.loop ? ['--loop'] : []), ...(args.title ? ['--title', args.title] : [])], io, libFiles);
    return EXIT_OK;
  }

  // ------------------------------------------------------------ render
  function loadPlaywright() {
    const req = createRequire(import.meta.url);
    for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(webRoot, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean)) {
      try { return req(c); } catch { /* next */ }
    }
    return null;
  }

  async function doRender(args, io) {
    const [modelPath, planPath] = args._;
    if (!modelPath || !planPath || args._.length > 2) throw usage('render needs a model and a plan: xray-4d render model.ifc build.4d.json [--script film.xrayanim] --size 1920x1080 --fps 30 -o build.mp4');
    if (!args.out) throw usage('render needs -o <build.mp4|build.webm|frames.zip>');
    const size = args.size ?? '1920x1080';
    if (!/^\d{2,5}x\d{2,5}$/.test(size)) throw usage(`--size needs WIDTHxHEIGHT like 1920x1080, got "${size}"`);
    const fps = args.fps === undefined ? 30 : Number(args.fps);
    if (!Number.isInteger(fps) || fps < 1 || fps > 120) throw usage('--fps needs a whole number from 1 to 120');
    const ext = (/\.(mp4|webm|zip)$/i.exec(args.out)?.[1] ?? '').toLowerCase();
    const format = args.format ?? (ext === 'zip' ? 'png' : ext || 'auto');
    if (!['mp4', 'webm', 'png', 'auto'].includes(format)) throw usage(`--format must be mp4, webm or png, got "${format}"`);
    if (args.hud && !['on', 'off'].includes(args.hud)) throw usage('--hud must be on or off');
    const pw = loadPlaywright();
    if (!pw) throw fail('render needs Playwright (npm package "playwright" with a Chromium); it was not found. Set PLAYWRIGHT_MODULE to its path.', EXIT_RENDER);
    const plan = readJson(planPath, 'plan');
    if (plan.schema !== 'xray-4d-plan/1') throw input(`plan ${planPath}: not a 4D plan (schema ${plan.schema ?? 'missing'})`);
    const name = planName(planPath);
    const scriptText = args.script ? readFile(args.script, 'script').toString('utf8') : null;
    const params = parseParamArgs(args.param);
    const libraries = readUseDir(args['use-dir']);
    if (Object.keys(params).length && !args.script) throw usage('--param needs --script');
    if (args['use-dir'] && !args.script) throw usage('--use-dir needs --script');

    const dir = mkdtempSync(join(tmpdir(), 'xray-4d-render-'));
    const t0 = performance.now();
    try {
      const page = join(dir, 'page.html');
      io.err('assembling the viewer page ...');
      await packPage(modelPath, planPath, args.script, page, [], io);
      let browser;
      try {
        browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-unsafe-webgpu'] });
      } catch (e) {
        throw fail(`cannot start Chromium: ${String(e.message ?? e).split('\n')[0]}`, EXIT_RENDER);
      }
      try {
        const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, acceptDownloads: true });
        const p = await ctx.newPage();
        p.setDefaultTimeout(0);
        const pageErrors = [];
        p.on('pageerror', (e) => pageErrors.push(e.message));
        p.on('console', (m) => { if (m.type() === 'error') pageErrors.push(m.text()); });
        await p.goto(pathToFileURL(page).href);
        await p.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000, polling: 300 });
        const err = await p.evaluate('window.__xrayError');
        if (err) throw fail(`the viewer did not start: ${err}`, EXIT_RENDER);
        await p.waitForFunction('!!window.__xrayRecord && !!window.__xray4dFilm && !!window.__xrayScript', null, { timeout: 60000, polling: 300 });
        const built = await p.evaluate(({ name, scriptText, params, libraries }) => {
          const f = window.__xray4dFilm(name, scriptText, false, { params, libraries });
          if (!f.score) return { error: f.warning };
          window.__film = f.score;
          return { seconds: f.score.duration, cues: f.score.cues.length, warning: f.warning };
        }, { name, scriptText, params, libraries });
        if (built.error) throw fail(built.error, EXIT_RENDER);
        if (built.warning) io.err(`xray-4d: warning: ${built.warning}`);
        const frames = Math.max(1, Math.round(built.seconds * fps));
        io.err(`rendering ${frames} frames (${built.seconds.toFixed(1)} s at ${fps} fps, ${size}, ${format}) ...`);
        const tick = setInterval(async () => {
          try {
            const t = await p.evaluate(() => document.querySelector('[data-record-status]')?.textContent ?? '');
            if (t) io.err(`  ${t.trim()}`);
          } catch { /* page busy or closed */ }
        }, 5000);
        let res;
        let dl;
        try {
          [dl, res] = await Promise.all([
            p.waitForEvent('download', { timeout: 0 }),
            p.evaluate(({ size, fps, format, hud }) => window.__xrayRecord.run(window.__film, { size, fps, format, hud, name: 'film' }), { size, fps, format, hud: args.hud !== 'off' }),
          ]);
        } finally {
          clearInterval(tick);
        }
        if (!res.ok) throw fail(`render failed: ${res.message}`, EXIT_RENDER);
        mkdirSync(dirname(resolve(args.out)), { recursive: true });
        await dl.saveAs(resolve(args.out));
        const bytes = statSync(resolve(args.out)).size;
        const f = res.file ?? {};
        io.err(`wrote ${args.out}: ${f.frames ?? frames} frames, ${f.width ?? '?'}x${f.height ?? '?'}, ${fmtKB(bytes)}, ${fmtMs(performance.now() - t0)}`);
        if (pageErrors.length) io.err(`xray-4d: warning: ${pageErrors.length} page error${pageErrors.length > 1 ? 's' : ''}, the first: ${pageErrors[0]}`);
        io.out(JSON.stringify({ file: args.out, frames: f.frames ?? frames, width: f.width, height: f.height, fps, bytes, seconds: built.seconds, ms: Math.round(performance.now() - t0) }));
      } finally {
        await browser.close();
      }
    } catch (e) {
      if (e instanceof CliError) throw e;
      throw fail(`render failed: ${String(e.message ?? e).split('\n')[0]}`, EXIT_RENDER);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
    return EXIT_OK;
  }

  // ------------------------------------------------------------ all
  async function doAll(args, io) {
    const [modelPath, xerPath] = args._;
    if (!modelPath || !xerPath || args._.length > 2) throw usage('all needs a model and a schedule: xray-4d all model.ifc schedule.xer --config map.4d.json -o out/');
    if (!args.config) throw usage('all needs --config <map.4d.json>');
    if (!args.out) throw usage('all needs -o <output directory>');
    const dir = resolve(args.out);
    mkdirSync(dir, { recursive: true });
    const stage = (s) => io.err(`--- ${s}`);
    const shared = { config: args.config, project: args.project };
    stage('link');
    const code = await doLink({ _: [modelPath, xerPath], ...shared, out: join(dir, 'links.json'), report: join(dir, 'link-report.html'), 'min-coverage': args['min-coverage'], assignments: args.assignments, prior: args.prior, 'id-property': args['id-property'], 'write-ifc': args['write-ifc'] ? join(dir, 'model.4d.ifc') : undefined }, io);
    if (code !== EXIT_OK) return code;
    stage('plan');
    await doPlan({ _: [modelPath, xerPath, join(dir, 'links.json')], ...shared, out: join(dir, 'build.4d.json'), view: args.view, baseline: args.baseline, window: args.window, length: args.length, pace: args.pace }, io);
    const planPath = join(dir, 'build.4d.json');
    if (!args['no-render']) {
      stage('render');
      await doRender({ _: [modelPath, planPath], out: join(dir, `build.${args.format === 'webm' ? 'webm' : 'mp4'}`), size: args.size, fps: args.fps, format: args.format, hud: args.hud, script: args.script, param: args.param, 'use-dir': args['use-dir'] }, io);
    }
    stage('pack');
    await doPack({ _: [modelPath, planPath], out: join(dir, 'build.html'), script: args.script, param: args.param, 'use-dir': args['use-dir'], loop: args.loop }, io);
    io.err(`done: ${dir}`);
    return EXIT_OK;
  }

  const COMMON = { '--config': 'string', '--project': 'string' };
  const cfgHelp = '  --config FILE    the 4D configuration (JSON, .4d.json; YAML is not supported: no YAML parser is installed)';
  return {
    link: {
      summary: 'link activities to model elements (links.json), with a coverage report and optional IFC write-back',
      usage: 'xray-4d link <model.ifc> <schedule.xer> --config map.4d.json [--assignments a.json] [--prior links.json] [--id-property P] [--min-coverage 0.9] [--write-ifc out.ifc] [--report r.html] -o links.json',
      options: { ...COMMON, '--assignments': 'string', '--prior': 'string', '--id-property': 'string', '--min-coverage': 'string', '--write-ifc': 'string', '--report': 'string', '--out': 'string', '--no-suggest': 'bool' },
      optionHelp: [cfgHelp, '  --project NAME   the schedule project (when the .xer holds several)',
        '  --assignments F  a LinkML dataset (the mapping tool\'s export): its assignments (location, trade, zone) are used',
        '  --prior FILE     an earlier links.json: accepted links are kept, the others passed through',
        '  --id-property P  element property holding activity ids, comma separated (default Xray_4D.ActivityIds when elements have it)',
        '  --min-coverage X exit 4 when the share of elements linked (by count) is below X (0..1); the files are still written',
        '  --write-ifc FILE write a copy of the model with IfcWorkSchedule, IfcTask, IfcTaskTime and assignments (IFC4 / IFC4X3; IFC2X3 is skipped with a warning)',
        '  --report FILE    the link report (self-contained HTML)', '  --no-suggest     do not propose links from names', '  -o, --out FILE  links.json (default: standard output)'],
      run: doLink,
    },
    plan: {
      summary: 'build the 4D plan (build.4d.json): per-element states over time, time map, milestones',
      usage: 'xray-4d plan <model.ifc> <schedule.xer> <links.json> --config map.4d.json [--view planned|actual|variance] [--baseline b.xer] [--window all|lookahead:6w|range:A..B] [--length 120s | --pace 1w=2s] [--write-ifc out.ifc] -o build.4d.json',
      options: { ...COMMON, '--view': 'string', '--baseline': 'string', '--window': 'string', '--length': 'string', '--pace': 'string', '--write-ifc': 'string', '--out': 'string' },
      optionHelp: [cfgHelp, '  --project NAME   the schedule project', '  --view V         planned (default from the config), actual or variance',
        '  --baseline FILE  a baseline .xer, matched by activity ID', '  --window W       all, lookahead:6w (from the data date) or range:2027-05-01..2027-07-01',
        '  --length T       film length, 120s or 2m          --pace P   schedule time per video second, 1w=2s or 3d=1s',
        '  --write-ifc FILE also write the model copy with the work schedule (the plan\'s view dates are the task dates)', '  -o, --out FILE  build.4d.json (default: standard output)'],
      run: doPlan,
    },
    render: {
      summary: 'render the 4D film to mp4, webm or a PNG zip (headless Chromium, frame by frame)',
      usage: 'xray-4d render <model.ifc> <build.4d.json> [--script film.xrayanim [--param name=value ...] [--use-dir folder]] [--size 1920x1080] [--fps 30] [--format mp4|webm|png] [--hud on|off] -o build.mp4',
      options: { '--script': 'string', '--param': 'list', '--use-dir': 'string', '--size': 'string', '--fps': 'string', '--format': 'string', '--hud': 'string', '--out': 'string' },
      optionHelp: ['  --script FILE    an .xrayanim script whose cues (camera, captions) play with the plan',
        '  --param N=V      a value for a "param" line of the script (repeatable), like --param floor="Level 2"; a name the script does not declare is a warning',
        '  --use-dir DIR    resolve the script\'s `use "Name"` lines against the .xrayanim files of this folder (name = file name without the extension)', '  --size WxH       default 1920x1080', '  --fps N          1 to 120, default 30',
        '  --format F       mp4, webm or png (a zip of frames); default from the file extension', '  --hud on|off     composite the HUD (date, progress, captions); default on', '  -o, --out FILE  the video file (required)',
        'Needs Playwright with Chromium. Exit 5 when the render fails.'],
      run: doRender,
    },
    pack: {
      summary: 'a self-contained kiosk page (one .html) that autoplays the 4D film',
      usage: 'xray-4d pack <model.ifc> <build.4d.json> [--script film.xrayanim [--param name=value ...] [--use-dir folder]] [--loop] [--title T] -o build.html',
      options: { '--script': 'string', '--param': 'list', '--use-dir': 'string', '--loop': 'bool', '--title': 'string', '--out': 'string' },
      optionHelp: ['  --script FILE    an .xrayanim script whose cues play with the plan', '  --param N=V      a value for a "param" line of the script (repeatable)', '  --use-dir DIR    the folder of .xrayanim libraries for the script\'s `use` lines (packed with it)', '  --loop           play again and again', '  --title T        page title', '  -o, --out FILE  the page (required)'],
      run: doPack,
    },
    all: {
      summary: 'link, plan, render and pack in one run, stopping at the first failure',
      usage: 'xray-4d all <model.ifc> <schedule.xer> --config map.4d.json -o out/ [--no-render] [--min-coverage 0.9] [--write-ifc] [--script F] [--view V] [--window W] [--length T] [--size S] [--fps N]',
      options: { ...COMMON, '--assignments': 'string', '--prior': 'string', '--id-property': 'string', '--min-coverage': 'string', '--write-ifc': 'bool', '--view': 'string', '--baseline': 'string', '--window': 'string', '--length': 'string', '--pace': 'string', '--script': 'string', '--param': 'list', '--use-dir': 'string', '--size': 'string', '--fps': 'string', '--format': 'string', '--hud': 'string', '--loop': 'bool', '--no-render': 'bool', '--out': 'string' },
      optionHelp: [cfgHelp, '  -o, --out DIR    output directory: links.json, link-report.html, build.4d.json, build.mp4, build.html (model.4d.ifc with --write-ifc)', '  --no-render      skip the video', '  other options    as for link, plan, render and pack'],
      run: doAll,
    },
  };
}
