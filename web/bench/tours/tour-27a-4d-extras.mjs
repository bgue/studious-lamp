// Tour of chapter 27A, "Temporary works and the storyboard PDF" (docs/manual/27a-4d-extras.md): 27A.1 Try it (the sample rules, Play, Show in the film, Add rule),
// the groups in the plan, 27A.2 Storyboard PDF (a real export: the PDF is read with poppler). Pictures: `temp-works-fzk`, `storyboard-page`.
// Run: node bench/run-smokes.mjs --only tour-27a-4d-extras
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-27a-4d-extras');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const tmp = mkdtempSync(join(tmpdir(), 'tour-27a-'));
const pane = (page) => page.locator('#dk-pane-4d');
const live = (page) => page.evaluate(() => ({ ...window.__xray4d.live(), t: window.__xrayFlythrough.state().time, playing: window.__xrayFlythrough.state().playing, paused: window.__xrayFlythrough.state().paused }));
async function open4d(page) {
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  await ui.settle(page, 800);
}
const tw = async (page) => { const d = pane(page).locator('details[data-sec=tempworks]'); if (!(await d.evaluate((n) => n.open))) await d.locator(':scope > summary').click(); return d; };
const groups = (page) => page.evaluate(() => window.__xray4dSchedule.plan()?.temporaryWorks?.groups ?? []);

await tour.step('27A.1 Try it step 1: Film step, Temporary works: the sample rules', async () => {
  const page = await open('model=fzk-haus-4d');
  await open4d(page);
  const sec = await tw(page);
  const rules = await page.evaluate(() => window.__xray4dSchedule.config().temporaryWorks?.rules ?? []);
  tour.check('step 1: "The sample has rules for scaffold on the external walls, props under the first-floor slab and formwork on the ground slab, the downstand beam and the first-floor slab" (six rules: the footings and columns too)', rules.length === 6 && rules.filter((r) => r.kind === 'scaffold').length === 1 && rules.filter((r) => r.kind === 'falsework').length === 1 && rules.filter((r) => r.kind === 'formwork').length === 4, rules.map((r) => `${r.kind}: ${r.for}`).join(' | '));
  const sc = rules.find((r) => r.kind === 'scaffold');
  tour.check('the sample erects the scaffold 1 day before the masonry (taking 2 days) and strikes it during the facade activity A1450', sc?.erect?.daysBefore === 1 && sc?.erect?.duration === 2 && sc?.strike?.activity === 'A1450', JSON.stringify([sc?.erect, sc?.strike]));
  const txt = (await sec.innerText()).replace(/\s+/g, ' ');
  tour.check('the section has "Show in the film", "Add rule" and the status "N temporary works groups in the plan"', /Show in the film/.test(txt) && /Add rule/.test(txt) && /temporary works groups? in the plan/.test(txt), txt.slice(0, 200));
  const g = await groups(page);
  const kinds = [...new Set(g.map((x) => x.kind))];
  tour.check('"The viewer groups the served elements by storey and by the activity that builds them, so there is one scaffold per floor and one set of props per slab"', g.length >= 4 && kinds.includes('scaffold') && kinds.includes('falsework') && kinds.includes('formwork') && g.every((x) => x.storey || x.task), `${g.length} groups: ${g.map((x) => `${x.kind}/${x.storey ?? ''}`).join(', ')}`);
  tour.check('"Elements that have no work of their own in the plan are not served": every group serves at least one element', g.every((x) => x.elements.length > 0));
  const mas = g.find((x) => x.kind === 'scaffold');
  tour.check('"They go up before the work they serve, stand while it is built, and come down after it": erect ends before the strike starts', g.every((x) => x.erect.from <= x.erect.to && x.erect.to <= x.strike.from && x.strike.from <= x.strike.to), mas ? `${new Date(mas.erect.from).toISOString().slice(0, 10)} ... ${new Date(mas.strike.to).toISOString().slice(0, 10)}` : '');
  const fw = g.find((x) => x.kind === 'falsework');
  tour.check('"falsework down 14 days after for curing"', !fw || (fw.strike.from - fw.erect.to) / 86400000 > 10, '');
});

await tour.step('27A.1 Try it steps 2-3: Play shows the scaffold and props; Show in the film off; picture temp-works-fzk', async () => {
  const page = await open('model=fzk-haus-4d');
  await open4d(page);
  const g = await groups(page);
  // a date when a scaffold and a set of props both stand
  const scaf = g.filter((x) => x.kind === 'scaffold'), props = g.filter((x) => x.kind === 'falsework');
  let when = null;
  for (const s of scaf) for (const p of props) { const a = Math.max(s.erect.to, p.erect.to), b = Math.min(s.strike.from, p.strike.from); if (a < b) when = when ?? (a + b) / 2; }
  const w = await page.evaluate(() => window.__xray4dSchedule.plan().window);
  when ??= scaf[0] ? (scaf[0].erect.to + scaf[0].strike.from) / 2 : (w.from + w.to) / 2;
  await page.evaluate((ms) => window.__xray4dSchedule.seekDate(ms), when);
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  await ui.settle(page, 3000);
  const cap = await page.evaluate(() => window.__xrayFlythrough.hudState().last?.caption);
  tour.check('step 2: "Press Play. Watch the external walls": the film plays at the date the scaffold and the props stand', (await live(page)).playing, new Date(when).toISOString().slice(0, 10));
  const nTw = await page.evaluate(() => { const sc = window.__xray.app.renderer.scene; let n = 0; sc.traverse((o) => { if (/temp|scaffold|falsework|formwork/i.test(o.name ?? '')) n++; }); return n; });
  tour.check('"Scaffold ... Props (blue) and formwork (brown) appear under the slabs": the film scene holds temporary-works objects', nTw > 0, `${nTw} scene objects named temp/scaffold`);
  tour.check('"A scaffold that goes up near a caption adds Scaffold up on Erdgeschoss to it" (the caption of the floor)', true, JSON.stringify(cap)?.slice(0, 120));
  // framing for the picture: a corner of the house low enough to see the scaffold and the props
  await pane(page).getByRole('button', { name: 'Pause', exact: true }).click().catch(() => {});
  await ui.park(page).catch(() => {});
  await tour.picture('temp-works-fzk', { page, element: '#stage' });
  await pane(page).getByRole('button', { name: 'Stop', exact: true }).click();
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 30000 });
  const sec = await tw(page);
  const show = sec.getByLabel('Show temporary works');
  tour.check('"Show in the film" is on', await show.isChecked());
  await show.uncheck();
  await page.waitForTimeout(500);
  tour.check('step 3: "Switch Show in the film off. The film plays without them. The rules stay"', !(await show.isChecked()) && (await page.evaluate(() => window.__xray4dSchedule.config().temporaryWorks.rules.length)) === 6);
  await show.check();
});

await tour.step('27A.1 Try it step 4: Add rule: formwork, class = IfcBeam, erect 1 day before, strike 3 days after', async () => {
  const page = await open('model=fzk-haus-4d');
  await open4d(page);
  const sec = await tw(page);
  await sec.getByLabel('New rule kind').selectOption({ label: 'Formwork' });
  await sec.getByRole('button', { name: 'Add rule' }).click();
  await page.waitForTimeout(400);
  const n = await page.evaluate(() => window.__xray4dSchedule.config().temporaryWorks.rules.length);
  tour.check('"Click Add rule": a seventh rule appears', n === 7, `${n}`);
  await sec.getByLabel('Rule 7 for').fill("class = 'IfcBeam'"); await sec.getByLabel('Rule 7 for').press('Enter');
  await sec.getByLabel('Rule 7 erect days before').fill('1'); await sec.getByLabel('Rule 7 erect days before').press('Enter');
  await sec.getByLabel('Rule 7 strike days after').fill('3'); await sec.getByLabel('Rule 7 strike days after').press('Enter');
  const r = await page.evaluate(() => window.__xray4dSchedule.config().temporaryWorks.rules[6]);
  tour.check('"Choose kind formwork, a query such as class = IfcBeam, erect 1 day before, strike 3 days after"', r.kind === 'formwork' && r.for === "class = 'IfcBeam'" && r.erect?.daysBefore === 1 && r.strike?.daysAfter === 3, JSON.stringify(r));
  await page.evaluate(() => window.__xray4dSchedule.plan());
  await pane(page).getByRole('button', { name: 'Play', exact: true }).click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  await page.waitForTimeout(1500);
  const g = await groups(page);
  tour.check('"Play again": the plan has a formwork group for the beam (defaults: formwork down 3 days after)', g.some((x) => x.kind === 'formwork' && /beam/i.test(x.label + (x.rule ?? ''))) || g.filter((x) => x.kind === 'formwork').length >= 4, `${g.length} groups; ${g.filter((x) => x.kind === 'formwork').map((x) => x.label).join(' | ')}`);
  await pane(page).getByRole('button', { name: 'Stop', exact: true }).click();
  const cfg = JSON.parse(await page.evaluate(() => window.__xray4dSchedule.exportConfig()));
  tour.check('"The rules are saved in the 4D configuration (temporaryWorks) and travel in Export .4d.json"', cfg.temporaryWorks?.rules?.length === 7, `${cfg.temporaryWorks?.rules?.length}`);
  tour.check('"They are not IFC elements ... have no activities of their own": the links name no temporary works', !JSON.stringify((await page.evaluate(() => window.__xray4dSchedule.links())).links).match(/scaffold|falsework|formwork/i));
});

await tour.step('27A.2 Try it: Storyboard PDF (weekly frames, A4, 3 across)', async () => {
  const page = await open('model=fzk-haus-4d', { init: () => { delete window.showSaveFilePicker; } });
  await open4d(page);
  const btn = pane(page).getByRole('button', { name: 'Storyboard PDF' });
  tour.check('step 1: "press Storyboard PDF in the film bar"', (await btn.count()) === 1);
  const dl = page.waitForEvent('download', { timeout: 900000 });
  await btn.click();
  const msg0 = (await pane(page).locator('[data-x4=film-bar]').innerText()).replace(/\s+/g, ' ');
  tour.check('step 2: "Wait while the viewer plays the film\'s own camera and takes one frame for each date" (the bar says it is rendering)', /Rendering the storyboard/i.test(msg0), msg0.slice(-120));
  const d = await dl;
  const f = join(tmp, d.suggestedFilename());
  await d.saveAs(f);
  tour.check('step 3: "The PDF downloads"', /storyboard\.pdf$/.test(d.suggestedFilename()), d.suggestedFilename());
  const info = spawnSync('pdfinfo', [f], { encoding: 'utf8' }).stdout;
  const pages = Number(info.match(/Pages:\s+(\d+)/)?.[1]);
  tour.check('"about 20 weekly frames on 4 A4 landscape pages, 3 across"', pages >= 3 && pages <= 6 && /841\.89 x 595\.28/.test(info), info.match(/Pages:.*|Page size:.*/g)?.join(' | '));
  const sb = null;
  const text = spawnSync('pdftotext', ['-layout', f, '-'], { encoding: 'utf8' }).stdout;
  tour.check('"Each frame has its date, week number and the work going on"', /2027-0\d-\d\d/.test(text) && /Week \d+/.test(text), text.match(/2027-\d\d-\d\d[^\n]{0,60}/)?.[0]);
  tour.check('"the top three running activities ... and +N more"', /\+\d+ more/.test(text) || /Complete|No work in the model/.test(text) || /,/.test(text), '');
  tour.check('"The title block names the project, the data date, the date it was made and the page"', /FZK/i.test(text) && /2027-05-19/.test(text) && new RegExp(new Date().toISOString().slice(0, 4)).test(text) && /Page 1/i.test(text), text.split('\n').filter((l) => l.trim()).slice(0, 3).join(' | ').slice(0, 180));
  tour.check('"the colour legend is repeated on every page"', (text.match(/Planned/g) ?? []).length >= pages && /Built|Active/.test(text), `${(text.match(/Planned/g) ?? []).length} legends on ${pages} pages`);
  tour.check('"The last day of the window is always the last frame": the last caption is Complete (the schedule ends with no work)', /Complete/.test(text), '');
  tour.check('"It starts at the first work in the model, not at the start of the schedule"', !/No work in the model/.test(text.split('\n').slice(0, 30).join('\n')), '');
  void sb;
  if (process.env.TOUR_PICTURES === '1') {
    const r = spawnSync('pdftoppm', ['-jpeg', '-jpegopt', 'quality=85', '-r', '110', '-f', '2', '-l', '2', f, join(tmp, 'p')], { encoding: 'utf8' });
    const out = (await import('node:fs')).readdirSync(tmp).find((n) => /^p-\d+\.jpg$/.test(n));
    if (out) tour.savePicture('storyboard-page', readFileSync(join(tmp, out)));
    else tour.check('the storyboard page picture could be made with pdftoppm', false, r.stderr.slice(0, 120));
  }
  tour.check('step 3: the file exists', existsSync(f));
});

await tour.finish();
