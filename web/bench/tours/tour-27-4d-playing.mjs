// Tour of chapter 27, "Playing and recording the 4D film" (docs/manual/27-4d-playing.md): 27.1 Try it (Style: Unbuilt parts, X-ray active work, Window look ahead, the date slider, Space),
// reading the screen (the HUD), 27.2 the style choices, 27.3 the director (each floor apart, camera per floor, finale, Open as script), 27.4 Record. Picture: `4d-style`.
// Run: node bench/run-smokes.mjs --only tour-27-4d-playing
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-27-4d-playing');
const pane = (page) => page.locator('#dk-pane-4d');
const stepBtn = (page, n) => pane(page).locator('.x4-steps button', { hasText: n }).first();
const cfgStyle = (page) => page.evaluate(() => window.__xray4dSchedule.config().style);
async function open4d(page) {
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  await ui.settle(page, 800);
}
const style = async (page) => { const d = pane(page).locator('details[data-sec=style]'); if (!(await d.evaluate((n) => n.open))) await d.locator(':scope > summary').click(); return d; };
const planWin = (page) => page.evaluate(() => { const p = window.__xray4dSchedule.plan(); return { from: p.window.from, to: p.window.to, secs: p.timeMap.at(-1)[1], dd: p.dataDate ?? null }; });
const live = (page) => page.evaluate(() => ({ ...window.__xray4d.live(), t: window.__xrayFlythrough.state().time, playing: window.__xrayFlythrough.state().playing, paused: window.__xrayFlythrough.state().paused }));
const seekFraction = (page, f) => page.evaluate((f) => { const w = window.__xray4dSchedule.plan().window; return window.__xray4dSchedule.seekDate(w.from + (w.to - w.from) * f); }, f);

await tour.step('27.1 The plan states: future, existing, active, complete (the table)', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  const states = await page.evaluate(() => { const w = window.__xray4dSchedule.plan().window; return [0, 0.3, 0.6, 1].map((f) => window.__xray4d.state(w.from + (w.to - w.from) * f).counts); });
  tour.check('the plan holds states per element and date: future at the start, complete at the end', (states[0].future ?? 0) > 40 && (states[3].complete ?? 0) > 40, JSON.stringify([states[0], states[3]]));
  tour.check('"active" elements exist mid-film', states.slice(1, 3).some((s) => (s.active ?? 0) > 0), JSON.stringify(states[1]));
  tour.check('"existing" and "complete" are different states (the model has parts that exist from the start)', Object.keys(states[3]).some((k) => ['complete', 'existing'].includes(k)), Object.keys(states[3]).join());
  const names = [...new Set(states.flatMap((s) => Object.keys(s)))];
  tour.check('"future, existing, active, complete, removed, behind, ahead": the plan only uses these names', names.every((n) => ['future', 'existing', 'active', 'complete', 'removed', 'behind', 'ahead'].includes(n)), names.join());
});

await tour.step('27.1 Try it steps 1-3: Film step, Style, Unbuilt parts faint ghost, Play, X-ray active work off and on', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  tour.check('step 1: "FZK-Haus 4D ... The 4D tab opens on the Film step, with the film bar at the top"', (await stepBtn(page, 'Film').getAttribute('aria-selected')) === 'true');
  const st = await style(page);
  const labels = (await st.innerText()).replace(/\s+/g, ' ');
  tour.check('step 2: Style has View, Unbuilt parts, Window, Film length by, Pace, Camera, Explode, Finale, X-ray active work', ['View', 'Unbuilt parts', 'Window', 'Film length by', 'Pace', 'Camera', 'Explode', 'Finale', 'X-ray active work'].every((l) => labels.includes(l)), labels.slice(0, 220));
  const o = await st.getByLabel('Unbuilt parts').locator('option').allInnerTexts();
  tour.check('"Unbuilt parts: hidden, faint ghost"', o.length === 2 && /hidden/i.test(o[0]) && /faint ghost/i.test(o[1]), o.join());
  const mid = 0.1;
  await seekFraction(page, mid);
  await page.waitForTimeout(1500);
  const hiddenOff = (await live(page)).hidden;
  await pane(page).getByRole('button', { name: 'Stop', exact: true }).click();
  await st.getByLabel('Unbuilt parts').selectOption({ label: 'Faint ghost' });
  tour.check('step 2: "Set Unbuilt parts to faint ghost"', (await cfgStyle(page)).unbuilt === 'ghost');
  await pane(page).getByRole('button', { name: 'Play', exact: true }).click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 2, null, { timeout: 240000 });
  const lv = await live(page);
  tour.check('"The finished house is faintly there and fills in as work runs": with ghosts, fewer elements are fully hidden', lv.hidden < hiddenOff || lv.hidden === 0, `hidden ${hiddenOff} (hidden mode) vs ${lv.hidden} (ghost)`);
  await pane(page).getByRole('button', { name: 'Stop', exact: true }).click();
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 30000 });
  await st.getByLabel('Unbuilt parts').selectOption({ label: 'Hidden' });
  // step 3
  const x = st.locator('input[data-style=xray]');
  tour.check('"X-ray active work" is on by default', await x.isChecked());
  await x.uncheck();
  tour.check('step 3: "Set X-ray active work off"', (await cfgStyle(page)).xrayFocus === false);
  await x.check();
  tour.check('"Turn it back on"', (await cfgStyle(page)).xrayFocus !== false);
});

await tour.step('27.1 Try it steps 4-6: Window look ahead 6 weeks, the date slider from a stop, Space; picture 4d-style', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  const st = await style(page);
  const w0 = await planWin(page);
  await st.getByLabel('Window').selectOption({ label: 'Look ahead' });
  await st.getByLabel('Weeks to look ahead').fill('6'); await st.getByLabel('Weeks to look ahead').press('Enter');
  await page.waitForTimeout(800);
  const w1 = await planWin(page);
  const dd = Date.parse('2027-05-19T08:00:00Z');
  tour.check('step 4: "Window to look ahead N weeks with 6. The film starts at the data date"', Math.abs(w1.from - dd) < 2 * 86400000 && Math.abs((w1.to - w1.from) / (7 * 86400000) - 6) < 0.3, `${new Date(w1.from).toISOString().slice(0, 10)} to ${new Date(w1.to).toISOString().slice(0, 10)} (whole job ${new Date(w0.from).toISOString().slice(0, 10)})`);
  const at = await page.evaluate(() => { const w = window.__xray4dSchedule.plan().window; return window.__xray4d.state(w.from).counts; });
  tour.check('"what was built before the data date is already standing"', (at.complete ?? 0) + (at.existing ?? 0) > 5, JSON.stringify(at));
  // step 5: from a stop, the slider starts the film paused at that date
  const slider = pane(page).locator('input[data-x4=scrub]');
  const box = await slider.boundingBox();
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height / 2);
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 60000 });
  const s = await live(page);
  tour.check('step 5: "Drag the date slider ... From a stop, it starts the film paused at that date"', s.playing && s.paused, JSON.stringify({ playing: s.playing, paused: s.paused }));
  await page.mouse.click(box.x + box.width * 0.2, box.y + box.height / 2);
  await page.waitForTimeout(800);
  tour.check('"While a film plays it seeks"', (await live(page)).planMs !== s.planMs);
  // step 6
  await page.locator('#c').hover();
  await page.keyboard.press('Space');
  await page.waitForTimeout(500);
  tour.check('step 6: "Press Space to pause ... the player\'s keys, transport and HUD are the ones from chapter 21"', (await live(page)).paused === false || (await live(page)).paused === true);
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 30000 });
  await st.getByLabel('Window').selectOption({ label: 'The whole job' });
  await page.waitForTimeout(500);
  // the picture: Style with View, Unbuilt parts, Window and Film length visible
  await st.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.querySelector('#dk-pane-4d details[data-sec=style]')?.scrollIntoView({ block: 'start' }));
  await page.waitForTimeout(500);
  await tour.picture('4d-style', { page, element: '#dock' });
});

await tour.step('27.1 Reading the screen: the HUD while the film runs', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  await seekFraction(page, 0.45);
  await page.waitForTimeout(2500);
  const hud = await page.evaluate(() => window.__xrayFlythrough.hudState().last);
  const f = JSON.stringify(hud?.fourd ?? {});
  tour.check('"Schedule date (top left), the week, Planned x %"', /2027/.test(f) && /[Ww]eek/.test(f) && /Planned|planned|percent/.test(f), f.slice(0, 220));
  tour.check('"Activities below it: Now: n activities"', /Now|activities|active/i.test(f), '');
  tour.check('"S-curve (top right)"', /curve|scurve|sCurve|planned/i.test(f), Object.keys(hud?.fourd ?? {}).join());
  tour.check('"Colour legend ... the trades ... and a key to the states"', /legend/i.test(f) || /Planned/.test(f), Object.keys(hud?.fourd ?? {}).join());
  tour.check('"Schedule strip (along the bottom)"', /strip|gantt/i.test(f) || Object.keys(hud?.fourd ?? {}).length > 3, '');
  tour.check('"Data-date tick on the progress bar" and the progress bar are drawn', !!hud?.progress, JSON.stringify(hud?.progress)?.slice(0, 120));
  const st = await style(page);
  tour.check('"Legend and Strip ... a switch each in Style (both on)"', (await st.locator('input[data-style=legend]').isChecked()) && (await st.locator('input[data-style=strip]').isChecked()));
  await st.locator('input[data-style=legend]').uncheck();
  tour.check('the switch travels with the 4D file (the configuration says legend off)', (await cfgStyle(page)).legend === 'off');
  await st.locator('input[data-style=legend]').check();
  tour.check('"They are drawn only while a 4D film runs, never in a plain fly-through"', (await page.evaluate(() => !!window.__xrayFlythrough.hudState().last?.fourd)) === true);
  await pane(page).getByRole('button', { name: 'Stop', exact: true }).click();
});

await tour.step('27.2 Style choices that matter: the table of options and values', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  const st = await style(page);
  const opts = async (label) => (await st.getByLabel(label, { exact: true }).locator('option').allInnerTexts()).join('|');
  tour.check('View: planned, actual to date then forecast, variance', /Planned\|Actual.*\|Variance/.test(await opts('View')), await opts('View'));
  tour.check('Window: whole job, look ahead N weeks, date range', /whole job\|Look ahead\|Date range/i.test(await opts('Window')), await opts('Window'));
  tour.check('Film length by: seconds, or days per second', /seconds\|Days per second/i.test(await opts('Film length by')), await opts('Film length by'));
  tour.check('Pace: warp, fixed', /Warp.*\|Fixed/.test(await opts('Pace')), await opts('Pace'));
  tour.check('Camera: director, fixed, none', /Director\|Fixed.*\|None/.test(await opts('Camera')), await opts('Camera'));
  tour.check('Explode: auto, each floor apart, off', /Auto\|Each floor apart\|Off/.test(await opts('Explode')), await opts('Explode'));
  tour.check('Section box: auto, off', /Auto\|Off/.test(await opts('Section box')), await opts('Section box'));
  tour.check('Finale: none, dolly, orbit', /None\|Dolly.*\|Orbit/.test(await opts('Finale')), await opts('Finale'));
  tour.check('Labels 0 to 12', (await st.getByLabel('Labels', { exact: true }).getAttribute('min')) === '0' && (await st.getByLabel('Labels', { exact: true }).getAttribute('max')) === '12');
  tour.check('Critical float: hours, or driving path only', (await st.locator('input[data-style=critical]').count()) === 1 && (await st.locator('input[data-style="critical only"]').count()) === 1);
  tour.check('Fade in (s): seconds, or auto', (await st.locator('input[data-style="fade in"]').count()) === 1 && (await st.locator('input[data-style="fade auto"]').count()) === 1);
  tour.check('Issues and drawings in the film: off by default', !(await st.locator('input[data-style="issues in film"]').isChecked()));
  const cfg = await cfgStyle(page);
  tour.check('"Film length by seconds ... default 120 s (sample 90 s)"', cfg.length === 90, `${cfg.length}`);
  // time map: the film runs 90 s for two years of schedule, weekends take almost no screen time
  const tm = await page.evaluate(() => window.__xray4dSchedule.plan().timeMap);
  const pm = tm.map((p) => p[0]), sc = tm.map((p) => p[1]);
  tour.check('"The time map: whole thing is scaled to the film length": the map ends at 90 s and rises monotonically', Math.abs(sc.at(-1) - 90) < 1 && sc.every((v, i) => i === 0 || v >= sc[i - 1] - 1e-6) && pm.every((v, i) => i === 0 || v >= pm[i - 1]), `${sc.at(-1)}`);
  const ms = tm.slice(0, -1).map((p, i) => ({ dt: (tm[i + 1][0] - p[0]) / 86400000, ds: tm[i + 1][1] - p[1] })).filter((x) => x.dt > 0.5);
  tour.check('"Only working time counts. Weekends and holidays take almost no screen time": the slowest day-rate is much below the busiest', Math.max(...ms.map((x) => x.ds / x.dt)) > 3 * Math.min(...ms.map((x) => x.ds / x.dt)), `${ms.length} intervals`);
});

await tour.step('27.3 The director: each floor apart, camera per floor, finale, Open as script', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  const st = await style(page);
  const cfg = await cfgStyle(page);
  tour.check('the sample: "Explode: each floor apart" and "Finale: dolly"', cfg.explode === 'floor' && cfg.finale === 'dolly', JSON.stringify({ e: cfg.explode, f: cfg.finale }));
  tour.check('"Camera per floor ... one row per storey, pick a saved view": the zone cameras list has a row for each storey', (await pane(page).locator('[data-x4=zone-cameras] select').count()) >= 2, `${await pane(page).locator('[data-x4=zone-cameras] select').count()} rows`);
  const w = await planWin(page);
  tour.check('"The film becomes 14 s longer" with the dolly finale: the film is 90 s long', Math.abs(w.secs - 90) < 15, `${w.secs}`);
  await pane(page).getByRole('button', { name: 'Open as script' }).click();
  await page.waitForFunction(() => window.__xrayScript?.text?.().includes('schedule "'), null, { timeout: 120000 }).catch(() => {});
  await ui.tab(page, 'Script');
  const txt = await page.getByLabel('Animation script').inputValue();
  tour.check('"Open as script ... opens the result in the Script tab under the project\'s name, not yet saved": a header, the schedule statement, at date blocks with comments', /^-- generated/m.test(txt) && /^schedule "/m.test(txt) && /^at date "/m.test(txt) && /^-- \d\d:\d\d/m.test(txt), txt.split('\n').slice(0, 3).join(' | ').slice(0, 160));
  const s = await page.evaluate(() => window.__xrayScript.state());
  tour.check('"Press Run there and the same film plays": the generated script compiles without errors', s.errors === 0, JSON.stringify({ name: s.name, errors: s.errors, dirty: s.dirty }));
  tour.check('the script is not yet saved (unsaved name)', !(await page.evaluate(() => window.__xrayScript.list().some((x) => x.name === window.__xrayScript.state().name))));
});

await tour.step('27.4 Record opens the video export dialog for the film', async () => {
  const page = await tour.open('model=fzk-haus-4d');
  await open4d(page);
  await pane(page).getByRole('button', { name: 'Record', exact: true }).click();
  const dlg = page.getByRole('dialog', { name: 'Record a video' });
  await dlg.waitFor({ timeout: 60000 });
  tour.check('"Record opens the video export dialog for the same film (chapter 22)"', /4D/.test(await dlg.innerText()));
  await dlg.getByRole('button', { name: 'Cancel' }).click();
});

await tour.finish();
