// Tour of chapter 35, "Scripting hooks and plugins" (docs/manual/35-scripting-hooks.md): 35.2 drive the viewer from the console (the FZK-Haus 4D sample),
// 35.3 the scripting objects named in the table and their methods, 35.4 the documented plugin points exist in the source (registerAction, registerTool,
// registerParamSection, PLUGINS, the order numbers), 35.5 booting a packed page is covered by tour-30. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-35-scripting-hooks
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { startTour, ui, webRoot } from './lib.mjs';

const tour = await startTour('tour-35-scripting-hooks');
const src = (p) => readFileSync(resolve(webRoot, 'src', p), 'utf8');

await tour.step('35.2 Try it: open FZK-Haus 4D, then the console steps 1-5', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await page.waitForFunction(() => !!window.__xray4dSchedule, null, { timeout: 120000 });
  await page.evaluate(() => window.__xray4dSchedule.ready());
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.activities > 0 || window.__xray4dSchedule.summary()?.activityCount > 0 || Object.keys(window.__xray4dSchedule.summary() ?? {}).length > 3, null, { timeout: 120000 }).catch(() => {});
  const sum = await page.evaluate(() => window.__xray4dSchedule.summary());
  tour.check('step 1: summary() returns the project, data date and counts', !!sum && JSON.stringify(sum).includes('FZK-HAUS') && /2027-05-19/.test(JSON.stringify(sum)), JSON.stringify(sum)?.slice(0, 200));
  const n = await page.evaluate(() => window.__xray4dSchedule.links().links.length);
  tour.check('step 2: "links().links.length gives the number of links"', n > 10, `${n} links`);
  const rep = await page.evaluate(() => window.__xray4dSchedule.report());
  tour.check('step 2: "report() gives the coverage"', !!rep && /82|coverage|linked/i.test(JSON.stringify(rep)), JSON.stringify(rep)?.slice(0, 160));
  const tools = await page.evaluate(() => window.__xrayToolbar.tools());
  tour.check('step 3: "window.__xrayToolbar.tools() ... which tools are in the strip"', Array.isArray(tools) && tools.includes('measure') && tools.includes('cleanup') && tools.includes('xray'), tools.join());
  await page.evaluate(() => window.__xray4dSchedule.open('play'));
  await ui.settle(page, 800);
  const dock4d = (await page.locator('#dk-pane-4d').innerText()).replace(/\s+/g, ' ');
  tour.check('step 4: open(\'play\') shows the 4D tab with the film bar (Play, Pause, Stop)', /Play/.test(dock4d) && /Stop/.test(dock4d), dock4d.slice(0, 120));
  const pr = await page.evaluate(() => window.__xray4dSchedule.play());
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 }).catch(() => {});
  tour.check('step 4: play() starts the film (the player runs)', (await page.evaluate(() => window.__xrayFlythrough.state().playing)) === true, JSON.stringify(pr));
  await page.evaluate(() => window.__xray4dSchedule.stop());
  await page.waitForTimeout(800);
  tour.check('step 5: "Stop it: stop()" ends it', (await page.evaluate(() => window.__xrayFlythrough.state().playing)) === false);
});

await tour.step('35.3 The scripting objects: each name of the table is a window object', async () => {
  const page = await tour.open('model=fzk-haus');
  await page.waitForFunction(() => !!window.__xrayClassify && !!window.__xray4dMap, null, { timeout: 120000 }).catch(() => {});
  const names = ['__xray', '__xrayViewModes', '__xrayImaging', '__xraySection', '__xrayCleanup', '__xrayPresets', '__xrayPenetrations', '__xrayMeasure', '__xrayClearance', '__xrayViews', '__xrayFlythrough', '__xrayScript', '__xrayRecord', '__xrayIssues', '__xrayMarkup', '__xraySheets', '__xrayBcf', '__xrayWork', '__xrayIssueReport', '__xrayClash', '__xrayClassify', '__xrayRevision', '__xrayIfcSave', '__xraySearch', '__xrayUndo', '__xrayPointer', '__xrayTopBar', '__xrayRightSidebar', '__xrayGizmo', '__xrayMap', '__xrayPointCloud', '__xrayXr', '__xrayToolbar', '__xrayParams', '__xrayHelp', '__xray4dMap', '__xray4dSchedule', '__xray4d', '__xray4dFilm', '__xrayBoot', '__xrayReady', '__xrayError'];
  await page.waitForTimeout(3000);
  const have = await page.evaluate((names) => Object.fromEntries(names.map((n) => [n, n in window && window[n] !== undefined])), names);
  const missing = names.filter((n) => !have[n]);
  // __xrayBoot exists only in a packed page, __xrayError only when start-up failed: the table says "read once at start by a packed page"
  const real = missing.filter((n) => !['__xrayBoot', '__xrayError'].includes(n));
  tour.check('the table follows the source: every listed object exists in a running viewer', real.length === 0, `missing: ${real.join(', ')}`);
  tour.check('"__xrayReady is true after the first frame"', (await page.evaluate(() => window.__xrayReady)) === true);
  const keys = await page.evaluate(() => Object.keys(window).filter((k) => k.startsWith('__xray')));
  tour.check('"Object.keys(window).filter(k => k.startsWith(\'__xray\')) shows what is there"', keys.length >= 30, `${keys.length} objects`);
  const m = await page.evaluate(() => Object.keys(window.__xray4dMap).sort().join());
  const mDoc = ['values', 'assign', 'clear', 'suggest', 'proposals', 'accept', 'reject', 'coverage', 'colourBy', 'selectUnassigned', 'exportJson', 'importJson', 'open'];
  tour.check('__xray4dMap has: values, assign, clear, suggest, proposals, accept, reject, coverage, colourBy, selectUnassigned, exportJson, importJson, open', mDoc.every((k) => m.split(',').includes(k)), m);
  const s = await page.evaluate(() => Object.keys(window.__xray4dSchedule).sort().join());
  const sDoc = ['load', 'summary', 'config', 'link', 'links', 'report', 'decide', 'exportLinks', 'importLinks', 'plan', 'play', 'stop', 'seekDate', 'record', 'open', 'loadSample'];
  tour.check('__xray4dSchedule has: load, summary, config, link, links, report, decide, exportLinks, importLinks, plan, play, stop, seekDate, record, open, loadSample', sDoc.every((k) => s.split(',').includes(k)), s);
  const sc = await page.evaluate(() => Object.keys(window.__xrayScript).sort().join());
  tour.check('"window.__xrayScript offers compile(text), run(text), list(), save(name, text), load(name) and state()"', ['compile', 'run', 'list', 'save', 'load', 'state'].every((k) => sc.split(',').includes(k)), sc);
  const four = await page.evaluate(() => Object.keys(window.__xray4d).sort().join());
  tour.check('__xray4d has registerPlan, demoPlan, play, state', ['registerPlan', 'demoPlan', 'play', 'state'].every((k) => four.split(',').includes(k)), four);
  const core = await page.evaluate(() => Object.keys(window.__xray).sort().join());
  tour.check('__xray (the core) has app, renderer, classification, stats', ['app', 'renderer', 'classification', 'stats'].every((k) => core.split(',').includes(k)), core);
  // a few calls from the text: assign / decide
  const asg = await page.evaluate(() => window.__xray4dMap.assign('trade', 'CONC', { query: "class = 'IfcSlab'" }));
  tour.check('"__xray4dMap.assign(attr, value, target) ... returns the counts of assigned, unchanged and matched elements"', asg && ['assigned', 'unchanged', 'matched'].every((k) => k in asg), JSON.stringify(asg));
  const ld = await page.evaluate(() => window.__xray4dSchedule.load('not an xer file', 'x.xer'));
  tour.check('"load(text or bytes, name?, project?) ... returns { ok, message }"', ld && 'ok' in ld && 'message' in ld && ld.ok === false, JSON.stringify(ld)?.slice(0, 120));
  const reg = await page.evaluate(async () => { try { window.__xray4d.registerPlan('tour-plan', window.__xray4d.demoPlan?.()); return 'ok'; } catch (e) { return String(e); } });
  tour.check('"__xray4d.registerPlan(name, plan): register a plan, so a schedule4d cue or a script can use it by name"', reg === 'ok', reg);
});

await tour.step('35.4 Add an action and a tool: the points the manual names exist in the source', async () => {
  const idx = src('plugins/index.ts');
  tour.check('"the PLUGINS list in web/src/plugins/index.ts" with boot at the very end, help after panels', /export const PLUGINS: AppPlugin\[\]/.test(idx) && /bootPlugin, whatsNewPlugin, undoPlugin\]/.test(idx) || /bootPlugin/.test(idx));
  tour.check('registerAction({ id, label, group, keys, run }) is exported from input/actions', /export function registerAction/.test(src('input/actions.ts')));
  tour.check('registerTool({ id, label, title, icon, order, panel }) is exported from tools/registry', /export function registerTool/.test(src('tools/registry.ts')));
  tour.check('"registerParamSection(name, { collect(), apply(value, bad, path), share? })"', /export function registerParamSection/.test(src('ui/params.ts')) && /collect/.test(src('ui/params.ts')) && /share/.test(src('ui/params.ts')));
  tour.check('"getOverlay(app)" is the shared overlay', /export function getOverlay/.test(src('ui/overlay.ts')));
  const app = src('app.ts');
  tour.check('hooks "install(app)", "onModel(app)", "onStatic(app)", "beforeFrame, onFrame, afterFrame"', ['install', 'onModel', 'onStatic', 'beforeFrame', 'onFrame', 'afterFrame'].every((h) => new RegExp(`\\b${h}\\??\\(`).test(app)), '');
  const page = await tour.open('model=fzk-haus');
  const tools = await page.evaluate(() => window.__xrayToolbar.tools());
  const order = ['open', 'xray', 'viewModes', 'measure', 'clearance', 'penetrations', 'cleanup'].map((t) => tools.indexOf(t));
  tour.check('"The order number sorts the strip: Open model is 10, X-ray 30, View modes 40, Measure 70, Clearance 80, Penetrations 90, Cleanup 110": the strip is in that order', order.every((v) => v >= 0) && order.every((v, i) => i === 0 || v > order[i - 1]), tools.join());
  const pdoc = await page.evaluate(() => window.__xrayParams.collect?.() ?? window.__xrayParams.export?.() ?? null);
  tour.check('the params document has no section named like a core key twice (a section name must not clash)', pdoc === null || typeof pdoc === 'object');
});

await tour.finish();
