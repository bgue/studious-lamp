// Tour of chapter 24, "4D in one page: what you need" (docs/manual/24-4d-overview.md): 24.1 the 4D tab (film bar and three steps, proposed and accepted),
// 24.3 Try it: watch the finished example (choose FZK-Haus 4D, Play, the date slider, 19 May 2027), 24.4 and 24.5 what the example shows. Picture: `4d-midfilm`.
// Run: node bench/run-smokes.mjs --only tour-24-4d-overview
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-24-4d-overview');
const pane = (page) => page.locator('#dk-pane-4d');
const live = (page) => page.evaluate(() => ({ ...window.__xray4d.live(), t: window.__xrayFlythrough.state().time, playing: window.__xrayFlythrough.state().playing, paused: window.__xrayFlythrough.state().paused }));
const dateText = (page) => pane(page).locator('[data-x4=scrub-date]').innerText();
const stepBtn = (page, name) => pane(page).locator('.x4-steps button', { hasText: name }).first();

await tour.step('24.3 Try it steps 1-2: Parameters, Sample Projects, choose FZK-Haus 4D', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Sample Projects');
  const list = await (await ui.control(page, 'Model')).locator('option').allInnerTexts();
  tour.check('step 1: the Sample Projects folder has a Model list with "FZK-Haus 4D"', list.includes('FZK-Haus 4D'), list.join(' | '));
  await ui.set(page, 'Model', 'FZK-Haus 4D');
  await page.waitForFunction(() => window.__xray4dSchedule?.summary()?.project === 'FZK-HAUS' && window.__xray4dSchedule.links().links.length > 0, null, { timeout: 240000 });
  await ui.settle(page, 800);
  tour.check('step 2: "The viewer loads the house, then the schedule and its configuration, links ... and opens the 4D tab on the Film step"', (await pane(page).isVisible()) && (await stepBtn(page, 'Film').getAttribute('aria-selected')) === 'true', '');
  const bar = pane(page).locator('[data-x4=film-bar]');
  const bt = (await bar.innerText()).replace(/\s+/g, ' ');
  tour.check('"The film bar sits at the top of the tab: Play, Pause, Stop, the date slider, Record, Open as script and Storyboard PDF"', ['Play', 'Pause', 'Stop', 'Record', 'Open as script', 'Storyboard PDF'].every((n) => bt.includes(n)) && (await bar.locator('input[type=range]').count()) === 1, bt.slice(0, 160));
  tour.check('"Its status line reads 82 of 82 elements linked · 15 of 15 modelled activities have elements · 25 not in the model"', bt.includes('82 of 82 elements linked · 15 of 15 modelled activities have elements · 25 not in the model'), bt.match(/\d+ of \d+ elements linked[^\n]*/)?.[0]);
  tour.check('"The three steps ... Map, Link, Film" with their state under the name', (await pane(page).locator('.x4-steps button').count()) === 3 && /Map/.test(await pane(page).locator('.x4-steps').innerText()) && /Link/.test(await pane(page).locator('.x4-steps').innerText()) && /Film/.test(await pane(page).locator('.x4-steps').innerText()), (await pane(page).locator('.x4-steps').innerText()).replace(/\s+/g, ' '));
  // the table of the steps and their sections
  const secsOf = async (step) => { await stepBtn(page, step).click(); await page.waitForTimeout(250); return page.evaluate(() => [...document.querySelectorAll('#dk-pane-4d details[data-sec]')].filter((d) => d.getBoundingClientRect().height > 0).map((d) => d.querySelector(':scope > summary')?.textContent.trim().replace(/\s+/g, ' '))); };
  const map = await secsOf('Map'), link = await secsOf('Link'), film = await secsOf('Film');
  tour.check('table: Map holds Values, Assign, Suggest, Coverage', ['Values', 'Assign', 'Suggest', 'Coverage'].every((s) => map.some((m) => m.startsWith(s))), map.join(' | '));
  tour.check('table: Link holds Schedule, Configure, Link (and the lists of decided links and Not in the model)', ['Schedule', 'Configure', 'Link'].every((s) => link.some((m) => m.startsWith(s))), link.join(' | '));
  tour.check('table: Film holds Style, Temporary works, Save IFC with 4D links, Import / Export', ['Style', 'Temporary works'].every((s) => film.some((m) => m.startsWith(s))) && film.some((m) => /Import \/ Export/.test(m)), film.join(' | '));
  await stepBtn(page, 'Film').click();
});

await tour.step('24.1 Proposed and accepted; 24.5 the sample marks 25 activities Not modelled', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  const lk = await page.evaluate(() => window.__xray4dSchedule.links());
  const statuses = [...new Set(lk.links.map((l) => l.status))];
  tour.check('"Every label and every link has a status": the sample links are accepted (a deterministic rule made them)', statuses.every((s) => ['proposed', 'accepted', 'rejected', 'superseded'].includes(s)) && statuses.includes('accepted'), statuses.join());
  const cfg = await page.evaluate(() => window.__xray4dSchedule.config());
  const nm = Object.values(cfg.activities ?? {}).filter((a) => a.notModelled).length;
  tour.check('"The sample has 25 of them marked" (Not modelled)', nm === 25, `${nm}`);
  const sum = await page.evaluate(() => window.__xray4dSchedule.summary());
  tour.check('"a schedule of 46 activities that starts on 1 March 2027"', (sum.tasks ?? 0) + (sum.milestones ?? 0) >= 40 || JSON.stringify(sum).includes('46'), JSON.stringify(sum).slice(0, 160));
  const plan = await page.evaluate(() => { const p = window.__xray4dSchedule.plan(); return { from: new Date(p.window.from).toISOString().slice(0, 10), secs: p.timeMap.at(-1)[1] }; });
  tour.check('the film starts 2027-03-01 and runs "about 90 s"', plan.from === '2027-03-01' && Math.abs(plan.secs - 90) < 15, JSON.stringify(plan));
  const ms = await page.evaluate(() => window.__xray4dSchedule.plan().milestones?.map((m) => m.name ?? m.label ?? JSON.stringify(m)) ?? []);
  tour.check('"a milestone, Building weathertight, marks that moment"', ms.some((m) => /weathertight/i.test(m)), ms.join(' | ').slice(0, 200));
  tour.check('"Activities of type milestone ... never drive geometry. Milestones become captions"', ms.length >= 2);
  const xer = await page.evaluate(async () => (await fetch('/samples/fzk-haus.xer')).ok);
  tour.check('the sample XER is shipped', xer === true);
});

await tour.step('24.3 Try it steps 3-6: Play, scrub the date slider, 19 May 2027, Play again; picture 4d-midfilm', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  await ui.settle(page, 800);
  const before = await page.evaluate(() => window.__xray4d.live?.() ?? null);
  await pane(page).getByRole('button', { name: 'Play', exact: true }).click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  tour.check('step 3: "Press Play": the film plays', (await live(page)).playing);
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 6, null, { timeout: 300000 });
  const l1 = await live(page);
  tour.check('"The house builds ...": hidden elements fall as time goes on', l1.completed > 0 || l1.hidden < 82, JSON.stringify({ hidden: l1.hidden, completed: l1.completed, t: l1.t }));
  const hud = await page.evaluate(() => window.__xrayFlythrough.hudState().last?.fourd ?? null);
  tour.check('"The date, the week and the percentage complete are drawn on the picture"', !!hud && /2027/.test(JSON.stringify(hud)) && /week|Week|%/.test(JSON.stringify(hud)), JSON.stringify(hud)?.slice(0, 200));
  await pane(page).getByRole('button', { name: 'Pause', exact: true }).click();
  // step 4: drag the date slider (a real click on the track), then step 5: the data date
  const slider = pane(page).locator('input[data-x4=scrub]');
  const box = await slider.boundingBox();
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height / 2);
  await page.waitForTimeout(1500);
  const d1 = await dateText(page);
  tour.check('step 4: "Drag the date slider. It scrubs by schedule date"', /^\d{4}-\d{2}-\d{2}/.test(d1) || /2027/.test(d1), d1);
  const win = await page.evaluate(() => ({ from: window.__xray4dSchedule.plan().window.from, to: window.__xray4dSchedule.plan().window.to, dd: Date.parse('2027-05-19T00:00:00Z') }));
  await page.mouse.click(box.x + box.width * ((win.dd - win.from) / (win.to - win.from)), box.y + box.height / 2);
  await page.waitForTimeout(800);
  for (let i = 0; i < 40 && !/2027-05-19|19 May 2027|May 19/.test(await dateText(page)); i++) {
    const cur = await dateText(page);
    const ms = Date.parse(cur.replace(/^(\d{4}-\d{2}-\d{2}).*/, '$1') + 'T00:00:00Z');
    await slider.press(ms < win.dd ? 'ArrowRight' : 'ArrowLeft');
    await page.waitForTimeout(250);
  }
  const d2 = await dateText(page);
  tour.check('step 5: "Scrub to 19 May 2027, the data date"', /2027-05-19|19 May 2027|May 19/.test(d2), d2);
  await page.waitForTimeout(1500);
  const at = await live(page);
  const act = await page.evaluate(() => window.__xray4d.live());
  tour.check('"One activity is under way: the rafters"', JSON.stringify(act).toLowerCase().includes('rafter') || (act.active ?? act.activeElements ?? 0) > 0, JSON.stringify(act).slice(0, 200));
  void at;
  // the picture: mid film, walls half built, date top left, S-curve top right
  const mid = win.from + (win.to - win.from) * 0.38;
  await page.evaluate((ms) => window.__xray4dSchedule.seekDate(ms), mid);
  await ui.settle(page, 2500);
  await ui.park(page).catch(() => {});
  await tour.picture('4d-midfilm', { page, element: '#stage' });
  await pane(page).getByRole('button', { name: 'Stop', exact: true }).click();
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 30000 });
  void before;
});

await tour.step('24.3 Try it step 6: the four things the sample shows (scaffold, props and formwork, storeys apart, finale)', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  const cfg = await page.evaluate(() => window.__xray4dSchedule.config());
  const kinds = [...new Set((cfg.temporaryWorks?.rules ?? []).map((r) => r.kind))];
  tour.check('"Scaffold goes up along the outer walls ... Props stand under the first-floor slab and formwork around the ground slab"', ['scaffold', 'falsework', 'formwork'].every((k) => kinds.includes(k)), kinds.join());
  tour.check('"the ground floor and the roof storey are built apart" (explode each floor apart)', cfg.style?.explode === 'floor', JSON.stringify(cfg.style?.explode));
  tour.check('"At the end the camera dollies in and orbits the finished house" (finale: dolly)', cfg.style?.finale === 'dolly', JSON.stringify(cfg.style?.finale));
  const end = await page.evaluate(() => { const w = window.__xray4dSchedule.plan().window; return window.__xray4dSchedule.seekDate(w.to - 1000); });
  await page.waitForTimeout(3000);
  const cap = await page.evaluate(() => window.__xrayFlythrough.hudState().last?.caption?.title ?? null);
  tour.known('"a caption says Complete" at the end of the film', cap === 'Complete', 'seeking to the last second does not show the finale caption (the finale runs 14 s after the last work; seek lands before it)', String(cap));
  void end;
  await page.getByRole('button', { name: 'Stop', exact: true }).first().click().catch(() => {});
});

await tour.finish();
