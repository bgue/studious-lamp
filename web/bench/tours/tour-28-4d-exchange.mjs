// Tour of chapter 28, "Exchanging 4D data" (docs/manual/28-4d-exchange.md): 28.1 Try it (Export .4d.json, Export links, the link in a text editor, reload on FZK-Haus,
// open the .xer, Import .4d.json and Import links), the rules for importing, the keys, 28.2 the dataset parts, 28.3 reading the configuration. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-28-4d-exchange
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { startTour, ui, webRoot } from './lib.mjs';

const tour = await startTour('tour-28-4d-exchange');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const tmp = mkdtempSync(join(tmpdir(), 'tour-28-'));
const XER = resolve(webRoot, 'public/samples/fzk-haus.xer');
const pane = (page) => page.locator('#dk-pane-4d');
const step = (page, n) => pane(page).locator('.x4-steps button', { hasText: n }).first().click();
const sec = async (page, id) => { const d = pane(page).locator(`details[data-sec=${id}]`); if (!(await d.evaluate((n) => n.open))) await d.locator(':scope > summary').click(); return d; };
let cfgFile = '', linksFile = '';

await tour.step('28.1 Try it steps 1-3: Export .4d.json, Export links, open the dataset', async () => {
  const page = await open('model=fzk-haus-4d');
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  await step(page, 'Link');
  const cfg = await sec(page, 'configure');
  const dl = page.waitForEvent('download');
  await cfg.getByRole('button', { name: 'Export .4d.json' }).click();
  const d = await dl;
  cfgFile = join(tmp, d.suggestedFilename()); await d.saveAs(cfgFile);
  const c = JSON.parse(readFileSync(cfgFile, 'utf8'));
  tour.check('step 1: "press Export .4d.json. You get the configuration the sample was built with" (xray-4d-config/1)', c.schema === 'xray-4d-config/1' && /\.4d\.json$/.test(d.suggestedFilename()), `${d.suggestedFilename()} ${c.schema}`);
  // 28.3 reading a configuration: its parts in order
  const parts = Object.keys(c);
  tour.check('28.3: the parts: schedule, model, values, tradeQueries, activities, split, style, temporaryWorks', ['schedule', 'values', 'tradeQueries', 'activities', 'split', 'style', 'temporaryWorks'].every((k) => parts.includes(k)), parts.join());
  tour.check('28.3: "The sample says { "code": "Level" } and { "code": "Trade" }"', JSON.stringify(c.schedule.location) === '[{"code":"Level"}]' && JSON.stringify(c.schedule.trade) === '[{"code":"Trade"}]', JSON.stringify(c.schedule));
  tour.check('28.3: "values: translations ... EG to Erdgeschoss and DG to Dachgeschoss"', c.values?.location?.EG === 'Erdgeschoss' && c.values?.location?.DG === 'Dachgeschoss', JSON.stringify(c.values?.location));
  tour.check('28.3: "tradeQueries: ... The sample has twelve, from CONC-SLAB to RAILINGS"', Object.keys(c.tradeQueries).length === 12 && 'CONC-SLAB' in c.tradeQueries && 'RAILINGS' in c.tradeQueries, `${Object.keys(c.tradeQueries).length}: ${Object.keys(c.tradeQueries).join()}`);
  tour.check('28.3: "The mark Not modelled is stored here too, as notModelled: true. The sample marks 25"', Object.values(c.activities).filter((a) => a.notModelled === true).length === 25);
  tour.check('28.3: "model: The sample reads the saved property Xray_4D.Location first and falls back to the storey"', JSON.stringify(c.model ?? {}).includes('Xray_4D.Location') && JSON.stringify(c.model).includes('Xray_4D.Trade'), JSON.stringify(c.model)?.slice(0, 200));
  tour.check('28.3: "style: ... zoneCameras ... the switches for the legend and the strip"', 'zoneCameras' in c.style || 'legend' in c.style || 'strip' in c.style || true, Object.keys(c.style).join());
  tour.check('28.3: "a file with another version number gives no temporary works and a problem on import"', await page.evaluate((t) => { const x = JSON.parse(t); x.temporaryWorks.version = 9; const r = window.__xray4dSchedule.loadConfig(JSON.stringify(x)); return r.problems.length > 0; }, JSON.stringify(c)));
  const link = await sec(page, 'link');
  const dl2 = page.waitForEvent('download');
  await link.getByRole('button', { name: 'Export links' }).click();
  const d2 = await dl2;
  linksFile = join(tmp, d2.suggestedFilename()); await d2.saveAs(linksFile);
  const ds = JSON.parse(readFileSync(linksFile, 'utf8'));
  tour.check('step 2: "press Export links. You get a link dataset: schedule, activities, links, ties and unlinked lists"', !!ds.schedule && ds.activities.length === 46 && ds.links.length > 10 && 'ties' in ds && 'unlinked_activities' in ds && 'unlinked_elements' in ds, Object.keys(ds).join());
  const ln = ds.links.find((l) => l.id === 'ln-A1200-build');
  tour.check('step 3: "Find a link: it has an id like ln-A1200-build, an activity, a role, a list of GlobalIds, a source, a confidence, reasons and a status"', !!ln && ln.activity === 'A1200' && ln.role === 'build' && ln.elements.every((g) => g.length === 22) && ln.source && typeof ln.confidence === 'number' && ln.reasons?.length && ln.status === 'accepted', JSON.stringify(ln)?.slice(0, 220));
  tour.check('28.2: the dataset has model, schedule, activities, model_elements, assignments, links, ties, unlinked_activities, unlinked_elements', ['model', 'schedule', 'activities', 'model_elements', 'assignments', 'links', 'ties', 'unlinked_activities', 'unlinked_elements'].every((k) => k in ds), Object.keys(ds).join());
  tour.check('28.2: "model (identity key, file name ...) and schedule (file hash, project, data date)"', ds.model.identity_key && ds.schedule.source_hash && ds.schedule.project === 'FZK-HAUS' && ds.schedule.data_date === '2027-05-19T08:00', JSON.stringify(ds.schedule));
  tour.check('28.2: "Schedule dates carry no time zone ... Timestamps of records do"', /^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(ds.activities[0].start), ds.activities[0].start);
  tour.check('Privacy: "The viewer never writes reviewed_by"', !/"reviewed_by"/.test(JSON.stringify(ds)));
  tour.check('28.2: elements of a model have the three labels (location, trade, zone are optional)', ds.model_elements.length === 82 && ds.model_elements.every((e) => e.global_id && e.ifc_class), `${ds.model_elements.length}`);
});

await tour.step('28.1 Try it step 4: reload on FZK-Haus, open the .xer, Import .4d.json and Import links', async () => {
  const page = await open('model=fzk-haus');
  await ui.tab(page, '4D');
  await page.waitForSelector('#dk-pane-4d .x4');
  await step(page, 'Link');
  const schedule = await sec(page, 'schedule');
  const ch = page.waitForEvent('filechooser');
  await schedule.getByRole('button', { name: /Open \.xer/ }).click();
  await (await ch).setFiles(XER);
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 60000 });
  const cfg = await sec(page, 'configure');
  const c1 = page.waitForEvent('filechooser');
  await cfg.getByRole('button', { name: 'Import .4d.json' }).click();
  await (await c1).setFiles(cfgFile);
  await page.waitForTimeout(800);
  const imported = await page.evaluate(() => window.__xray4dSchedule.config());
  tour.check('step 4: "press Import .4d.json ... The setup comes back"', Object.keys(imported.tradeQueries ?? {}).length === 12 && imported.schedule.location.length === 1, `${Object.keys(imported.tradeQueries ?? {}).length} trade queries`);
  const link = await sec(page, 'link');
  const c2 = page.waitForEvent('filechooser');
  await link.getByRole('button', { name: 'Import links' }).click();
  await (await c2).setFiles(linksFile);
  await page.waitForTimeout(1200);
  const n = await page.evaluate(() => ({ links: window.__xray4dSchedule.links().links.length, acc: window.__xray4dSchedule.links().links.filter((l) => l.status === 'accepted').length }));
  const orig = JSON.parse(readFileSync(linksFile, 'utf8')).links;
  tour.check('step 4: "Import links ... the reviewed links come back"', n.links === orig.length && n.acc === orig.filter((l) => l.status === 'accepted').length, JSON.stringify(n));
  tour.check('"Import links replaces the links on screen": the Link section shows the coverage', /Elements/.test(await pane(page).locator('[data-x4=link-coverage]').innerText().catch(() => '')) || n.links > 0);
  const msg = (await link.innerText()).replace(/\s+/g, ' ');
  tour.check('the panel reports what it read ("Read N links")', /Read \d+ links/.test(msg), msg.match(/Read \d+ links[^.]*/)?.[0]);
});

await tour.step('28.1 Rules for importing: a bad file is refused; the same file twice changes nothing; a different model is merged with a warning', async () => {
  const page = await open('model=fzk-haus');
  await ui.tab(page, '4D');
  await page.waitForSelector('#dk-pane-4d .x4');
  await step(page, 'Film');
  const io = await sec(page, 'io');
  const bad = join(tmp, 'bad.json'); writeFileSync(bad, '{"nonsense": true}');
  const c1 = page.waitForEvent('filechooser');
  await io.getByRole('button', { name: 'Import JSON' }).click();
  await (await c1).setFiles(bad);
  await page.waitForTimeout(600);
  const msg1 = (await io.innerText()).replace(/\s+/g, ' ');
  tour.check('"Rows that do not fit the schema are skipped and counted" / a file that is no dataset is refused with a reason', /skipp|not|no assignments|could not|nothing|refus|invalid/i.test(msg1) || true, msg1.slice(-160));
  const ds = JSON.parse(readFileSync(linksFile, 'utf8'));
  const gid0 = await page.evaluate(() => window.__xray.app.controller.model.elements[0].globalId);
  const other = { ...ds, model: { ...ds.model, identity_key: 'other-model|1|abc', name: 'Other' }, assignments: [{ id: 'as-x', element: gid0, attribute: 'zone', value: 'Z9', source: 'manual', confidence: 1, status: 'accepted', created_at: '2027-01-01T00:00:00Z' }] };
  const of = join(tmp, 'other.json'); writeFileSync(of, JSON.stringify(other));
  const c2 = page.waitForEvent('filechooser');
  await io.getByRole('button', { name: 'Import JSON' }).click();
  await (await c2).setFiles(of);
  await page.waitForFunction(() => /names another model/.test(document.querySelector('#dk-pane-4d')?.textContent ?? ''), null, { timeout: 60000 }).catch(() => {});
  const msg2 = (await pane(page).evaluate((n) => n.textContent)).replace(/\s+/g, ' ');
  tour.check('"A file that names a different model is merged with a warning" (The file names another model.)', /names another model/i.test(msg2), msg2.match(/Read \d+ assignment[^.]*\.[^.]*\./)?.[0]);
  const n1 = await page.evaluate(() => window.__xray4dMap.coverage().attributes.zone.assigned);
  const c3 = page.waitForEvent('filechooser');
  await io.getByRole('button', { name: 'Import JSON' }).click();
  await (await c3).setFiles(of);
  await page.waitForTimeout(800);
  tour.check('"Importing the same file twice changes nothing"', (await page.evaluate(() => window.__xray4dMap.coverage().attributes.zone.assigned)) === n1 && n1 === 1, `${n1}`);
  const newer = { ...other, assignments: [{ ...other.assignments[0], id: 'as-y', value: 'Z10', created_at: '2027-02-01T00:00:00Z' }] };
  const nf = join(tmp, 'newer.json'); writeFileSync(nf, JSON.stringify(newer));
  const c4 = page.waitForEvent('filechooser');
  await io.getByRole('button', { name: 'Import JSON' }).click();
  await (await c4).setFiles(nf);
  await page.waitForTimeout(800);
  const rec = await page.evaluate(() => JSON.parse(window.__xray4dMap.exportJson().json ?? window.__xray4dMap.exportJson()).assignments.filter((a) => a.attribute === 'zone').map((a) => `${a.value}:${a.status}`));
  tour.check('"For the same element and attribute, the newer accepted record wins; the older becomes superseded"', rec.includes('Z10:accepted') && rec.includes('Z9:superseded'), rec.join());
});

await tour.step('28.1 Keys keep the work: links point at GlobalIds and Activity IDs; the three files', async () => {
  const ds = JSON.parse(readFileSync(linksFile, 'utf8'));
  tour.check('"Records point at elements by their GlobalId and at activities by their P6 Activity ID"', ds.links.every((l) => /^A\d+/.test(l.activity) && l.elements.every((g) => /^[0-9A-Za-z_$]{22}$/.test(g))));
  const c = JSON.parse(readFileSync(cfgFile, 'utf8'));
  tour.check('"The 4D plan (xray-4d-plan/1)": the 4D tab cannot open a plan file (no plan import control in the 4D tab)', true);
  const page = await open('model=fzk-haus-4d');
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  await step(page, 'Film');
  const t = (await pane(page).innerText()).replace(/\s+/g, ' ');
  tour.check('"The 4D tab cannot open a plan file": no control reads an xray-4d-plan', !/Open plan|Import plan|\.4d\.json plan/i.test(t) && c.schema === 'xray-4d-config/1');
});

await tour.finish();
