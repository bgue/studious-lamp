// Headless smoke for the 4D schedule workflow of the 4D tab (src/map4d/schedule*.ts, window.__xray4dSchedule): open the sample XER by the file
// input, build the configuration in the UI (Level -> location with EG/DG -> Erdgeschoss/Dachgeschoss, Trade -> the trade queries of the sample
// config), link (100 % of the elements), unlinked elements and their selection, a suggestion with Accept / Reject kept across a new run, the report,
// the style, play (waiting on the player's clock) with the hidden counts falling, scrub, Record, Save IFC with the links and ActivityIds read back
// from the saved file, the stored work after a reload, the FZK-Haus 4D entry of the Sample Projects menu, the phone layout, help keys, no console errors.
// Screenshots: bench/4d-schedule.png (desktop), bench/4d-schedule-phone.png (phone bottom sheet).
// Usage: SMOKE_PORT=5870 XRAY_VITE_CACHE_DIR=/tmp/xray-vite-sched4d node bench/smoke-4d-schedule.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5870);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-4d-schedule-'));
const FZK = resolve(root, '..', 'models', 'AC20-FZK-Haus.ifc');
const XER = resolve(root, 'public', 'samples', 'fzk-haus.xer');
const SAMPLE = JSON.parse(readFileSync(resolve(root, 'public', 'samples', 'fzk-haus.4d.json'), 'utf8'));

let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = createRequire(import.meta.url)(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));

let failed = false;
let passed = 0;
const check = (name, ok, detail = '') => { if (!ok) failed = true; else passed++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`); };
const errors = [];
let browser;

const newPage = async (viewport, tag, model = 'building') => {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(90000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${tag}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[${tag} pageerror] ${e.message}`));
  await page.addInitScript(() => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; });
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForFunction('window.__xray4dSchedule && window.__xray4dMap && window.__xray4d && window.__xrayIfcSave && window.__xrayFlythrough', null, { timeout: 60000 });
  return { ctx, page };
};

const openFile = async (page, file, label) => {
  await page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').setValue(''));
  await page.setInputFiles('#xray-open-file-input', file);
  await page.waitForFunction(() => {
    const s = window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue();
    return /^Loaded \d+ elements/.test(s) || /fail|error|cannot|not a valid/i.test(s);
  }, null, { timeout: 180000 });
  const st = await page.evaluate(() => ({ status: window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue(), model: window.__xray.app.modelName, n: window.__xray.app.controller.model.elements.length }));
  check(`${label} opens`, /^Loaded/.test(st.status), JSON.stringify(st));
  await page.evaluate(async () => { await window.__xray4dMap.ready(); await window.__xray4dSchedule.ready(); });
  return st;
};

/** Wait on the player's clock, not on wall time: the software renderer is slow. */
const waitClock = (page, seconds, timeout = 240000) => page.waitForFunction((s) => { const st = window.__xrayFlythrough.state(); return st.time >= s || (!st.playing && st.time > 0); }, seconds, { timeout });
const live = (page) => page.evaluate(() => ({ ...window.__xray4d.live(), t: window.__xrayFlythrough.state().time, playing: window.__xrayFlythrough.state().playing }));

try {
  let up = false;
  for (let i = 0; i < 100 && !up; i++) {
    try { up = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  if (!up) throw new Error('vite did not start:\n' + viteLog);
  browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ---------------------------------------------------------------- desktop: the workflow on the FZK-Haus IFC
  const { ctx, page } = await newPage({ width: 1600, height: 950 }, 'desktop');
  const opened = await openFile(page, FZK, 'AC20-FZK-Haus.ifc');
  await page.evaluate(() => window.__xray4dSchedule.open('schedule'));
  await page.waitForSelector('#dk-pane-4d .x4');
  const secs = await page.evaluate(() => [...document.querySelectorAll('#dk-pane-4d details[data-sec]')].map((d) => d.getAttribute('data-sec')));
  check('the 4D tab keeps the mapping sections and adds Schedule, Configure, Link, Style and Play before Import / Export', ['values', 'assign', 'suggest', 'coverage', 'schedule', 'configure', 'link', 'style', 'play', 'io'].every((s, i) => secs[i] === s), secs.join());

  // 1. load the schedule by the file input
  await page.setInputFiles('#dk-pane-4d input[data-x4=xer-input]', XER);
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 30000 });
  const sum = await page.evaluate(() => window.__xray4dSchedule.summary());
  check('the XER is read: project, data date, counts, code types', sum.project === 'FZK-HAUS' && sum.dataDate === '2027-05-19T08:00' && sum.tasks > 20 && ['Level', 'Phase', 'Trade'].every((n) => sum.codeTypes.some((c) => c.name === n)), JSON.stringify({ ...sum, hash: undefined }));
  await page.waitForFunction(() => /FZK-HAUS/.test(document.querySelector('#dk-pane-4d [data-x4=schedule-summary]')?.textContent ?? ''));
  const shown = await page.locator('#dk-pane-4d [data-x4=schedule-summary]').innerText();
  check('the summary is drawn in the tab', /FZK-HAUS/.test(shown) && /2027-05-19/.test(shown) && /Level/.test(shown) && /Trade/.test(shown), shown.replace(/\s+/g, ' ').slice(0, 160));

  // 2. configure in the UI
  const guessed = await page.evaluate(() => window.__xray4dSchedule.config().schedule);
  check('a first guess picks Level for the location and Trade for the trade', JSON.stringify(guessed.location) === '[{"code":"Level"}]' && JSON.stringify(guessed.trade) === '[{"code":"Trade"}]', JSON.stringify(guessed));
  await page.locator('#dk-pane-4d select[aria-label="Location from"]').selectOption('');
  check('Not used clears a source', (await page.evaluate(() => window.__xray4dSchedule.config().schedule.location)).length === 0);
  await page.locator('#dk-pane-4d select[aria-label="Location from"]').selectOption('code:Level');
  await page.locator('#dk-pane-4d select[aria-label="Trade from"]').selectOption('code:Trade');
  const opts = await page.locator('#dk-pane-4d select[aria-label="Zone from"] option').allTextContents();
  check('the source lists come from the schedule: code types and WBS levels', opts.includes('Activity code: Level') && opts.includes('Activity code: Trade') && opts.some((o) => /^WBS level 1/.test(o)), opts.join('|'));
  // value table: Level -> storey names of the model
  const storeys = await page.evaluate(() => window.__xray.app.controller.model.storeys.map((s) => s.name));
  check('the model has the storeys the sample config maps to', storeys.includes('Erdgeschoss') && storeys.includes('Dachgeschoss'), storeys.join());
  await page.locator('#dk-pane-4d [data-value="EG"] input').fill('Erdgeschoss');
  await page.locator('#dk-pane-4d [data-value="EG"] input').press('Enter');
  await page.locator('#dk-pane-4d [data-value="DG"] input').fill('Dachgeschoss');
  await page.locator('#dk-pane-4d [data-value="DG"] input').press('Enter');
  check('the value table maps EG and DG to the model storeys', JSON.stringify(await page.evaluate(() => window.__xray4dSchedule.config().values?.location)) === JSON.stringify({ EG: 'Erdgeschoss', DG: 'Dachgeschoss' }));
  // trade queries with live counts
  for (const [k, q] of Object.entries(SAMPLE.tradeQueries)) {
    const inp = page.locator(`#dk-pane-4d [data-trade="${k}"] input[type=text]`);
    await inp.fill(q);
    await inp.press('Enter');
  }
  await page.waitForFunction((n) => document.querySelector('#dk-pane-4d [data-trade="WINDOWS"] .x4-count')?.textContent === String(n), await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcWindow').length), { timeout: 10000 }).catch(() => undefined);
  const cnt = await page.locator('#dk-pane-4d [data-trade="WINDOWS"] .x4-count').innerText();
  const wantWin = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcWindow').length);
  check('a trade query shows its live count', Number(cnt) === wantWin && wantWin > 0, `${cnt} vs ${wantWin}`);
  const cfg = await page.evaluate(() => window.__xray4dSchedule.config());
  check('the UI built the sample configuration (sources, values, trade queries)', JSON.stringify(cfg.schedule.location) === JSON.stringify(SAMPLE.schedule.location) && JSON.stringify(cfg.schedule.trade) === JSON.stringify(SAMPLE.schedule.trade) && JSON.stringify(cfg.values) === JSON.stringify(SAMPLE.values) && JSON.stringify(cfg.tradeQueries) === JSON.stringify(SAMPLE.tradeQueries));
  // the sample's remaining parts (split rules, colours) come in as a configuration file: export, then import
  const exported = await page.evaluate(() => window.__xray4dSchedule.exportConfig());
  check('the configuration exports as .4d.json', JSON.parse(exported).schema === 'xray-4d-config/1');
  const imp = await page.evaluate((t) => { const r = window.__xray4dSchedule.loadConfig(t); return { ok: !!r.config, problems: r.problems.length }; }, readFileSync(resolve(root, 'public', 'samples', 'fzk-haus.4d.json'), 'utf8'));
  check('a .4d.json is imported', imp.ok && imp.problems === 0);
  const imp2 = await page.evaluate(() => window.__xray4dSchedule.loadConfig('{"schema":"nope"}'));
  check('a file that is no configuration is refused with a reason', !imp2.config && imp2.problems.length === 1);

  // 3. link
  await page.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.report() !== null);
  const sumL = await page.evaluate(() => window.__xray4dSchedule.report().coverage);
  check('linking covers every element (100 %)', sumL.elements.linked === sumL.elements.considered && sumL.elements.considered === opened.n && sumL.elements.unlinked === 0 && sumL.elements.tied === 0, JSON.stringify(sumL.elements));
  await page.waitForFunction(() => /Elements/.test(document.querySelector('#dk-pane-4d [data-x4=link-coverage]')?.textContent ?? ''));
  const covText = await page.locator('#dk-pane-4d [data-x4=link-coverage]').innerText();
  check('the coverage is drawn with elements and activities', /Elements/.test(covText) && /100 %/.test(covText) && /activities/i.test(covText), covText.replace(/\s+/g, ' ').slice(0, 200));
  const popup = page.waitForEvent('popup');
  await page.locator('#dk-pane-4d button', { hasText: 'Open report' }).click();
  const rp = await popup;
  await rp.waitForLoadState();
  const rtext = await rp.content();
  check('Open report shows the link report in a new window', /<table/.test(rtext) && /FZK-HAUS/.test(rtext) && /Coverage/i.test(rtext), `${rtext.length} bytes`);
  await rp.close();

  // 4. unlinked elements: drop the WINDOWS query, link again, select the unlinked elements
  await page.locator('#dk-pane-4d [data-trade="WINDOWS"] input[type=text]').fill('');
  await page.locator('#dk-pane-4d [data-trade="WINDOWS"] input[type=text]').press('Enter');
  await page.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).click();
  const gap = await page.evaluate(() => ({ s: window.__xray4dSchedule.report().coverage.elements, groups: window.__xray4dSchedule.report().unlinkedElements.map((g) => `${g.ifcClass}|${g.count}`), noEl: window.__xray4dSchedule.report().unlinkedActivities.length }));
  check('without the windows query the windows are unlinked, in a group by class', gap.s.unlinked === wantWin && gap.groups.filter((g) => g.startsWith('IfcWindow|')).reduce((a, g) => a + Number(g.split('|')[1]), 0) === wantWin, JSON.stringify(gap));
  await page.locator('#dk-pane-4d button', { hasText: 'Select unlinked' }).click();
  check('Select unlinked selects them', (await page.evaluate(() => window.__xray.app.selection.length)) === wantWin);
  await page.evaluate(() => window.__xray.app.selectIds([]));
  await page.waitForSelector('#dk-pane-4d [data-x4=unlinked-groups] button');
  const g0 = await page.locator('#dk-pane-4d [data-x4=unlinked-groups] .x4-item').first().innerText();
  await page.locator('#dk-pane-4d [data-x4=unlinked-groups] button', { hasText: 'Select' }).first().click();
  const gsel = await page.evaluate(() => window.__xray.app.selection.length);
  check('a group of the list selects its elements by its query', gsel > 0 && gsel <= wantWin && g0.includes(String(gsel)), `${gsel} of ${g0.replace(/\s+/g, ' ')}`);
  // The Link step lists the open gaps and, apart, the activities marked "not modelled" (the sample marks 25).
  const actLists = await page.locator('#dk-pane-4d [data-x4=unlinked-activities] summary').allInnerTexts();
  check('activities without elements are listed: the open gaps and "Not in the model"', gap.noEl > 0 && actLists.length >= 1 && actLists.length <= 2 && (actLists.some((t) => /Not in the model \(\d+\)/.test(t)) || actLists.some((t) => /without elements/.test(t))), `${gap.noEl}: ${actLists.join(' | ')}`);
  await page.locator('#dk-pane-4d [data-trade="WINDOWS"] input[type=text]').fill(SAMPLE.tradeQueries.WINDOWS);
  await page.locator('#dk-pane-4d [data-trade="WINDOWS"] input[type=text]').press('Enter');
  await page.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).click();
  check('with the query back every element links again', (await page.evaluate(() => window.__xray4dSchedule.report().coverage.elements.unlinked)) === 0);

  // 5. suggestions: no sources, so every activity is left for suggestions; Accept / Reject, kept by the next run
  await page.locator('#dk-pane-4d select[aria-label="Location from"]').selectOption('');
  await page.locator('#dk-pane-4d select[aria-label="Trade from"]').selectOption('');
  await page.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).click();
  const prop0 = await page.evaluate(() => window.__xray4dSchedule.links().links.filter((l) => l.status === 'proposed').map((l) => ({ id: l.id, activity: l.activity, n: l.elements.length })));
  check('the activities left over get suggestions to review', prop0.length >= 4, `${prop0.length} proposed: ${prop0.slice(0, 4).map((p) => p.activity).join()}`);
  await page.waitForSelector(`#dk-pane-4d [data-link="${prop0[0].id}"] button[aria-label="Accept link"]`);
  await page.locator(`#dk-pane-4d [data-link="${prop0[0].id}"] button[aria-label="Accept link"]`).click();
  await page.locator(`#dk-pane-4d [data-link="${prop0[1].id}"] button[aria-label="Reject link"]`).click();
  const st1 = await page.evaluate((ids) => Object.fromEntries(ids.map((id) => [id, window.__xray4dSchedule.links().links.find((l) => l.id === id)?.status])), [prop0[0].id, prop0[1].id]);
  check('Accept and Reject change the status of the links', st1[prop0[0].id] === 'accepted' && st1[prop0[1].id] === 'rejected', JSON.stringify(st1));
  await page.waitForFunction((id) => document.querySelector(`#dk-pane-4d [data-x4=decided-links] [data-link="${id}"]`), prop0[1].id);
  check('a decided link leaves the review list and shows under Decided links', (await page.locator(`#dk-pane-4d [data-x4=link-suggestions] [data-link="${prop0[0].id}"]`).count()) === 0 && (await page.locator(`#dk-pane-4d [data-x4=decided-links] [data-link="${prop0[1].id}"]`).count()) === 1);
  await page.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).click();
  const st2 = await page.evaluate((a) => { const l = window.__xray4dSchedule.links().links; return { acc: l.find((x) => x.activity === a[0])?.status, rej: l.filter((x) => x.activity === a[1]).map((x) => x.status) }; }, [prop0[0].activity, prop0[1].activity]);
  check('the next run keeps the decisions: accepted stays accepted, rejected is not suggested again', st2.acc === 'accepted' && st2.rej.length > 0 && st2.rej.every((x) => x === 'rejected'), JSON.stringify(st2));
  await page.locator('#dk-pane-4d [data-sec=link] details > summary', { hasText: 'Decided links' }).click();
  await page.locator(`#dk-pane-4d [data-x4=decided-links] [data-link="${prop0[1].id}"] button[aria-label="Reopen link"]`).click();
  check('Reopen puts a rejected link back to proposed', (await page.evaluate((id) => window.__xray4dSchedule.links().links.find((l) => l.id === id)?.status, prop0[1].id)) === 'proposed');
  // back to the rules: the accepted suggestion is taken back, and the rules make every link again
  await page.evaluate((id) => window.__xray4dSchedule.decide(id, 'proposed'), prop0[0].id);
  await page.locator('#dk-pane-4d select[aria-label="Location from"]').selectOption('code:Level');
  await page.locator('#dk-pane-4d select[aria-label="Trade from"]').selectOption('code:Trade');
  await page.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).click();
  const back0 = await page.evaluate(() => ({ cov: window.__xray4dSchedule.report().coverage.elements, src: [...new Set(window.__xray4dSchedule.links().links.filter((l) => l.status === 'accepted').map((l) => l.source))] }));
  check('with the sources back the rules link every element again', back0.cov.unlinked === 0 && back0.cov.byCount === 1 && back0.src.join() === 'attributes', JSON.stringify(back0));

  // links export / import
  const exL = await page.evaluate(() => window.__xray4dSchedule.exportLinks());
  const ds = JSON.parse(exL);
  check('the links export as a LinkML dataset with schedule, activities, links', ds.schedule?.project === 'FZK-HAUS' && ds.activities.length > 20 && ds.links.length >= 10 && ds.model.identity_key && !exL.includes('reviewed_by'), `${ds.activities?.length} activities, ${ds.links?.length} links, ${ds.schedule?.project}`);
  const imL = await page.evaluate((t) => { const n0 = window.__xray4dSchedule.links().links.length; const r = window.__xray4dSchedule.importLinks(t); return { r, n0, n1: window.__xray4dSchedule.links().links.length }; }, exL);
  check('the exported links import again with the same count', imL.r.links === ds.links.length && imL.r.problems.length === 0 && !imL.r.otherSchedule && imL.n1 === imL.n0, JSON.stringify(imL));

  // 6. style
  await page.evaluate(() => window.__xray4dSchedule.step('film')); // Style is in step 3
  await page.locator('#dk-pane-4d [data-sec=style] > summary').click();
  await page.locator('#dk-pane-4d select[data-style=unbuilt]').selectOption('ghost');
  await page.locator('#dk-pane-4d select[data-style=window]').selectOption('lookahead');
  await page.locator('#dk-pane-4d input[data-style=weeks]').fill('8');
  await page.locator('#dk-pane-4d input[data-style=weeks]').press('Enter');
  await page.locator('#dk-pane-4d select[data-style=pace]').selectOption('fixed');
  await page.locator('#dk-pane-4d select[data-style=explode]').selectOption('off');
  await page.locator('#dk-pane-4d input[data-style=labels]').fill('2');
  await page.locator('#dk-pane-4d input[data-style=labels]').press('Enter');
  const sty = await page.evaluate(() => window.__xray4dSchedule.config().style);
  check('the style controls change the configuration', sty.unbuilt === 'ghost' && sty.window.kind === 'lookahead' && sty.window.weeks === 8 && sty.pace === 'fixed' && sty.explode === 'off' && sty.labels === 2, JSON.stringify(sty).slice(0, 200));
  await page.locator('#dk-pane-4d select[data-style=unbuilt]').selectOption('hidden');
  await page.locator('#dk-pane-4d select[data-style=window]').selectOption('all');
  await page.locator('#dk-pane-4d select[data-style=pace]').selectOption('warp');
  await page.locator('#dk-pane-4d select[data-style=explode]').selectOption('auto');
  await page.locator('#dk-pane-4d select[data-style=view]').selectOption('planned');
  await page.locator('#dk-pane-4d input[data-style=labels]').fill('3');
  await page.locator('#dk-pane-4d input[data-style=labels]').press('Enter');
  await page.locator('#dk-pane-4d select[data-style="pace mode"]').selectOption('length');
  await page.locator('#dk-pane-4d input[data-style="pace value"]').fill('24');
  await page.locator('#dk-pane-4d input[data-style="pace value"]').press('Enter');
  const sty2 = await page.evaluate(() => window.__xray4dSchedule.config().style);
  check('the style goes back to the defaults with a film of 24 seconds', sty2.unbuilt === 'hidden' && sty2.window.kind === 'all' && sty2.view === 'planned' && sty2.length === 24 && sty2.daysPerSecond === undefined && sty2.camera === 'director', JSON.stringify(sty2).slice(0, 200));
  const tradeColours = await page.locator('#dk-pane-4d [data-x4=trade-colours] input[type=color]').count();
  check('trade colours are listed (from the mapping tool or the configuration)', tradeColours >= 5, `${tradeColours}`);

  // 7. play: hidden counts fall over time
  await page.locator('#dk-pane-4d [data-sec=play] > summary').scrollIntoViewIfNeeded();
  const planInfo = await page.evaluate(() => { const p = window.__xray4dSchedule.plan(); return { n: p.elements.length, secs: p.timeMap.at(-1)[1], name: window.__xray4d.plans(), style: p.style.length, colours: Object.keys(p.style.colours).length }; });
  check('the plan covers every element, runs 24 seconds and is registered by name', planInfo.n === opened.n && Math.abs(planInfo.secs - 24) < 0.5 && planInfo.name.some((n) => n.startsWith('4d:')) && planInfo.colours >= 5, JSON.stringify(planInfo));
  await page.locator('#dk-pane-4d button', { hasText: /^Play$/ }).click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  const note = await page.evaluate(() => ({ note: window.__xray4dSchedule.note, playing: window.__xray4dSchedule.playing }));
  check('Play starts the film through the score player', note.playing);
  const s0 = await live(page);
  await waitClock(page, 8);
  const s1 = await live(page);
  await waitClock(page, 16);
  const s2 = await live(page);
  check('while the film plays, the hidden count falls and the completed count rises', s0.hidden >= s1.hidden && s1.hidden > s2.hidden && s2.completed > s1.completed && s0.hidden > s2.hidden + 5, JSON.stringify({ s0, s1, s2 }));
  check('the HUD plan time advances with the clock', s2.planMs > s1.planMs && s1.planMs >= s0.planMs, `${s0.planMs} ${s1.planMs} ${s2.planMs}`);
  if (note.note) {
    const cn = await page.locator('#dk-pane-4d [data-x4=camera-note]').innerText();
    check('without a director the film says so and keeps the camera', /director/i.test(note.note) && /director/i.test(cn), note.note);
  } else check('a director is present: its cues were added to the score', true, 'director found');
  // pause / resume / stop
  await page.locator('#dk-pane-4d button', { hasText: /^Pause$/ }).click();
  const pt = await page.evaluate(() => window.__xrayFlythrough.state());
  check('Pause holds the clock', pt.paused === true);
  await page.locator('#dk-pane-4d button', { hasText: /^Resume$/ }).click();
  check('Resume goes on', (await page.evaluate(() => window.__xrayFlythrough.state().paused)) === false);
  // scrub by schedule date
  const win = await page.evaluate(() => ({ from: window.__xray4dSchedule.plan().window.from, to: window.__xray4dSchedule.plan().window.to }));
  await page.evaluate(() => { const r = document.querySelector('#dk-pane-4d input[data-x4=scrub]'); r.value = '0'; r.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForFunction(() => window.__xray4d.live().planMs !== null && window.__xrayFlythrough.state().time < 4, null, { timeout: 60000 });
  await page.waitForTimeout(600);
  const early = await live(page);
  await page.evaluate(() => { const r = document.querySelector('#dk-pane-4d input[data-x4=scrub]'); r.value = '1000'; r.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 20, null, { timeout: 60000 });
  await page.waitForTimeout(600);
  const late = await live(page);
  check('the date slider seeks the film: the end has fewer hidden elements than the start', early.hidden > late.hidden && late.hidden < 5 && early.planMs < late.planMs, JSON.stringify({ early, late }));
  const dateText = await page.locator('#dk-pane-4d [data-x4=scrub-date]').innerText();
  check('the slider shows the schedule date', /^\d{4}-\d{2}-\d{2}/.test(dateText), dateText);
  await page.screenshot({ path: resolve(here, '4d-schedule.png') });
  if (await page.evaluate(() => window.__xrayFlythrough.state().playing)) await page.locator('#dk-pane-4d button', { hasText: /^Stop$/ }).click();
  check('Stop ends the film', (await page.evaluate(() => window.__xrayFlythrough.state().playing)) === false);
  // seek by date through the API while stopped: starts paused at the date
  const ok = await page.evaluate((m) => window.__xray4dSchedule.seekDate(m), (win.from + win.to) / 2);
  await page.waitForTimeout(500);
  const mid = await page.evaluate(() => ({ st: window.__xrayFlythrough.state(), live: window.__xray4d.live() }));
  check('seeking by date while stopped starts the film paused at that date', ok && mid.st.playing && mid.st.paused && mid.live.planMs > win.from && mid.live.planMs < win.to, JSON.stringify(mid.live));
  await page.locator('#dk-pane-4d button', { hasText: /^Stop$/ }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('#dk-pane-4d button')].find((b) => b.textContent === 'Stop')?.disabled === true, null, { timeout: 5000 }).then(() => check('Stop is off when nothing plays', true), () => check('Stop is off when nothing plays', false));

  // 8. record: the existing video export dialog for this score
  await page.locator('#dk-pane-4d button', { hasText: /^Record$/ }).click();
  await page.waitForSelector('[data-record-dialog]');
  const sub = await page.locator('[data-record-dialog] .rc-stat').innerText();
  check('Record opens the video export dialog for the 4D film', /4D schedule/.test(sub), sub);
  await page.locator('[data-record-dialog] button', { hasText: 'Cancel' }).click();
  await page.waitForFunction(() => !document.querySelector('[data-record-dialog]'));

  // 9. help keys on every control of the tab
  const help = await page.evaluate(() => {
    const ctl = [...document.querySelectorAll('#dk-pane-4d button, #dk-pane-4d input, #dk-pane-4d select, #dk-pane-4d summary')].filter((c) => c.id !== 'x4-values');
    const missing = ctl.filter((c) => !c.getAttribute('data-help-key') || !window.__xrayHelp.lookup(c.getAttribute('data-help-key'))).map((c) => `${c.tagName} ${c.getAttribute('aria-label') ?? c.textContent} ${c.getAttribute('data-help-key')}`);
    return { n: ctl.length, missing };
  });
  check('every control of the 4D tab has help text', help.n > 80 && help.missing.length === 0, `${help.n} controls; ${JSON.stringify(help.missing.slice(0, 5))}`);

  // 10. save IFC with the links; ActivityIds in the saved file
  await page.locator('#dk-pane-4d [data-sec=play] > summary').scrollIntoViewIfNeeded();
  await page.locator('#dk-pane-4d button', { hasText: 'Save IFC with 4D links' }).click();
  const dlg = page.locator('.xis-box');
  await dlg.waitFor();
  const box = dlg.locator('label.xis-check', { hasText: 'Include 4D location, trade and zone' });
  check('the Save IFC dialog opens with the 4D box on', (await box.count()) === 1 && (await box.locator('input').isChecked()));
  const planOn = await page.evaluate(() => window.__xrayIfcSave.plan());
  const accepted = await page.evaluate(() => window.__xray4dSchedule.activityIds().size);
  check('the save plan counts every linked element', planOn.fourDElements === accepted && accepted > 0, `${planOn.fourDElements} vs ${accepted}`);
  const dlp = page.waitForEvent('download');
  await dlg.locator('button.primary').click();
  const dl = await dlp;
  const outPath = join(tmp, dl.suggestedFilename());
  await dl.saveAs(outPath);
  const out = readFileSync(outPath).toString('latin1');
  check('the saved file holds ActivityIds as IfcText with task codes', out.includes("'Xray_4D'") && out.includes("'ActivityIds'") && /IFCTEXT\('[A-Z0-9-]+(,[A-Z0-9-]+)*'\)/.test(out), `${(out.match(/IFCTEXT\('[^']*'\)/g) ?? []).slice(0, 3).join(' ')}`);
  await page.waitForFunction(() => /Saved AC20/.test(document.querySelector('.xis-box')?.textContent ?? ''));
  await dlg.locator('button', { hasText: 'Close' }).click();
  const codes = await page.evaluate(() => [...new Set([...window.__xray4dSchedule.activityIds().values()].flatMap((v) => v.split(',')))].sort());
  const wsTasks = (out.match(/=IFCTASK\(/g) ?? []).length;
  check('the saved file holds the work schedule: IfcWorkSchedule "Xray 4D" with a task per linked activity and IfcRelAssignsToProduct', /IFCWORKSCHEDULE\('[^']+',[^,]*,'Xray 4D'/.test(out) && wsTasks >= codes.length && /IFCRELASSIGNSTOPRODUCT\(/.test(out), `${wsTasks} tasks for ${codes.length} linked activities`);

  // 11. the stored work comes back after a reload
  await page.evaluate(async () => { await window.__xray4dSchedule.flush(); await window.__xray4dMap.flush(); });
  const keep = await page.evaluate(() => ({ cfg: JSON.stringify(window.__xray4dSchedule.config()), links: window.__xray4dSchedule.links().links.length, proj: window.__xray4dSchedule.summary().project }));
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  await page.waitForFunction('window.__xray4dSchedule', null, { timeout: 60000 });
  await openFile(page, FZK, 'AC20-FZK-Haus.ifc again');
  const back = await page.evaluate(() => ({ cfg: JSON.stringify(window.__xray4dSchedule.config()), links: window.__xray4dSchedule.links()?.links.length, proj: window.__xray4dSchedule.summary()?.project, rep: window.__xray4dSchedule.report()?.coverage.elements.byCount }));
  check('after a reload the configuration, the schedule and the links of the model come back from the browser', back.cfg === keep.cfg && back.links === keep.links && back.proj === keep.proj && back.rep > 0.99, JSON.stringify({ links: back.links, proj: back.proj, rep: back.rep, same: back.cfg === keep.cfg }));
  const p2 = await page.evaluate(() => { const p = window.__xray4dSchedule.plan(); return 'error' in p ? p.error : p.elements.length; });
  check('the restored work builds a plan without loading anything', p2 === opened.n, String(p2));

  // 12. reopen the saved IFC: the links come back from ActivityIds (source property)
  const reopened = await openFile(page, outPath, 'the saved file');
  const hasProps = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.props && typeof e.props['Xray_4D.ActivityIds'] === 'string').length);
  check('the saved model reopens with ActivityIds in the element properties', reopened.n === opened.n && hasProps === accepted, `${hasProps} elements`);
  await page.evaluate(async () => { window.__xray4dSchedule.reset(); await window.__xray4dSchedule.ready(); });
  const rl = await page.evaluate(async (xer) => {
    const bytes = Uint8Array.from(atob(xer), (c) => c.charCodeAt(0));
    window.__xray4dSchedule.load(bytes, 'fzk-haus.xer');
    window.__xray4dSchedule.setConfig({ ...window.__xray4dSchedule.config(), schedule: { location: [], trade: [] }, values: undefined, tradeQueries: undefined });
    const r = window.__xray4dSchedule.link();
    const l = window.__xray4dSchedule.links().links.filter((x) => x.status === 'accepted');
    return { r, sources: [...new Set(l.map((x) => x.source))], n: l.length, codes: [...new Set(l.map((x) => x.activity))].sort() };
  }, readFileSync(XER).toString('base64'));
  // the saved file carries both the IfcTask links (native) and ActivityIds (property); native is the stronger tier
  check('with no configuration, linking the saved file restores the accepted links from the file (native IfcTask links)', rl.sources.length > 0 && rl.sources.every((x) => x === 'native' || x === 'property') && rl.sources.includes('native') && rl.r.elements.linked === opened.n && JSON.stringify(rl.codes) === JSON.stringify(codes), JSON.stringify({ sources: rl.sources, n: rl.n, linked: rl.r.elements?.linked }));
  await ctx.close();

  // ---------------------------------------------------------------- the sample menu entry, on the served app
  const s = await newPage({ width: 1600, height: 950 }, 'sample');
  const sp = s.page;
  const menu = await sp.evaluate(() => { const c = window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'model'); return [...c.$select.options].map((o) => [o.value, o.textContent]); });
  check('the Sample Projects menu lists FZK-Haus 4D after FZK-Haus', menu.findIndex((m) => m[1] === 'FZK-Haus 4D') === menu.findIndex((m) => m[1] === 'FZK-Haus') + 1 && menu.some((m) => m[1] === 'FZK-Haus 4D'), JSON.stringify(menu.slice(0, 4)));
  await sp.evaluate(() => window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'model').setValue('fzk-haus-4d'));
  await sp.waitForFunction(() => window.__xray.app.modelName === 'fzk-haus' && window.__xray4dSchedule.report()?.coverage.elements.byCount > 0.99, null, { timeout: 180000 });
  const smp = await sp.evaluate(() => ({ sum: window.__xray4dSchedule.summary(), cov: window.__xray4dSchedule.report().coverage.elements, tab: window.__xrayRightSidebar.state(), playOpen: document.querySelector('#dk-pane-4d details[data-sec=play]').open, plans: window.__xray4d.plans(), n: window.__xray.app.controller.model.elements.length }));
  check('FZK-Haus 4D loads the model, the sample schedule and configuration, and links every element', smp.sum.project === 'FZK-HAUS' && smp.cov.linked === smp.n && smp.cov.unlinked === 0, JSON.stringify(smp.cov));
  check('it leaves the 4D tab open on Play with the plan ready', smp.tab.tab === '4d' && !smp.tab.collapsed && smp.playOpen && smp.plans.some((p) => p.startsWith('4d:')), JSON.stringify(smp.tab));
  const nm = await sp.evaluate(() => ({ step: window.__xray4dSchedule.step(), tabs: [...document.querySelectorAll('#dk-pane-4d [role=tablist] [role=tab]')].map((t) => t.textContent), act: window.__xray4dSchedule.report().coverage.activities, status: document.querySelector('#dk-pane-4d [data-x4=film-status]')?.textContent, cfg: Object.values(window.__xray4dSchedule.config().activities ?? {}).filter((a) => a.notModelled).length }));
  check('the 4D tab shows three steps and starts a linked sample on Film', nm.tabs.length === 3 && /^1 Map/.test(nm.tabs[0]) && /^3 Film/.test(nm.tabs[2]) && nm.step === 'film', JSON.stringify(nm.tabs));
  check('the sample marks its 25 activities without elements as not in the model; coverage does not count them as a gap', nm.cfg === 25 && nm.act.notModelled === 25 && nm.act.unlinked === 0 && nm.act.total === 15 && /15 of 15 modelled activities have elements . 25 not in the model/.test(nm.status ?? ''), JSON.stringify(nm.act) + ' ' + nm.status);
  await sp.locator('#dk-pane-4d button', { hasText: /^Play$/ }).click();
  await sp.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  await waitClock(sp, 3);
  const sl = await live(sp);
  check('the sample plays: elements are hidden and the clock runs', sl.hidden > 0 && sl.t >= 1, JSON.stringify(sl));
  await sp.locator('#dk-pane-4d button', { hasText: /^Stop$/ }).click();
  // drag and drop of an .xer onto the viewer
  await sp.evaluate(() => window.__xray4dSchedule.reset());
  const dropped = await sp.evaluate(async (b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], 'dropped.xer', { type: 'text/plain' }));
    for (const type of ['dragenter', 'dragover', 'drop']) document.dispatchEvent(new DragEvent(type, { dataTransfer: dt, bubbles: true, cancelable: true }));
    await new Promise((r) => setTimeout(r, 800));
    return window.__xray4dSchedule.summary();
  }, readFileSync(XER).toString('base64'));
  check('an .xer dropped on the viewer is read by the 4D tab', dropped?.project === 'FZK-HAUS' && dropped.fileName === 'dropped.xer', JSON.stringify(dropped && { p: dropped.project, f: dropped.fileName }));
  await s.ctx.close();

  // ---------------------------------------------------------------- phone
  const phone = await newPage({ width: 390, height: 800 }, 'phone');
  const pp = phone.page;
  await pp.evaluate(() => window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'model').setValue('fzk-haus-4d'));
  await pp.waitForFunction(() => window.__xray.app.modelName === 'fzk-haus' && window.__xray4dSchedule.report()?.coverage.elements.byCount > 0.99, null, { timeout: 180000 });
  await pp.evaluate(() => window.__xray4dSchedule.open('play'));
  await pp.waitForSelector('#dk-pane-4d .x4', { state: 'visible' });
  await pp.evaluate(() => window.__xray4dSchedule.step('link'));
  await pp.locator('#dk-pane-4d [data-sec=configure] > summary').click();
  await pp.evaluate(() => window.__xray4dSchedule.step('film'));
  await pp.locator('#dk-pane-4d [data-sec=style] > summary').click();
  await pp.waitForTimeout(500);
  const lay = await pp.evaluate(() => {
    const d = document.getElementById('dock').getBoundingClientRect();
    const p = document.querySelector('#dk-pane-4d .x4');
    const over = [...p.querySelectorAll('button, input, select, table')].filter((e) => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > innerWidth + 1).map((e) => `${e.tagName} ${e.getAttribute('aria-label') ?? e.textContent}`.slice(0, 40));
    return { dockW: d.width, vw: innerWidth, scrollW: p.scrollWidth, clientW: p.clientWidth, tab: window.__xrayRightSidebar.state(), over, docScroll: document.documentElement.scrollWidth };
  });
  check('on a phone the schedule sections sit in the bottom sheet with no sideways scroll', lay.tab.tab === '4d' && lay.tab.phone && lay.dockW >= lay.vw - 40 && lay.scrollW <= lay.clientW + 1 && lay.over.length === 0 && lay.docScroll <= lay.vw + 1, JSON.stringify(lay));
  const tap = await pp.evaluate(() => [...document.querySelectorAll('#dk-pane-4d button, #dk-pane-4d select')].filter((e) => e.getBoundingClientRect().height > 0 && e.getBoundingClientRect().height < 28).length);
  check('controls are at least 28 px high on a phone', tap === 0, `${tap} smaller`);
  await pp.locator('#dk-pane-4d [data-sec=play] > summary').scrollIntoViewIfNeeded();
  await pp.screenshot({ path: resolve(here, '4d-schedule-phone.png') });
  await phone.ctx.close();

  const real = errors.filter((e) => !/favicon|Failed to load resource.*404/i.test(e));
  check('no console errors', real.length === 0, real.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('FAIL', e && e.stack ? e.stack : e);
} finally {
  await browser?.close().catch(() => undefined);
  vite.kill();
}
console.log(`${passed} checks passed${failed ? ', FAILED' : ''}`);
process.exit(failed ? 1 : 0);
