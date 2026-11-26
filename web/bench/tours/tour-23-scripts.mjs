// Tour of chapter 23, "Animation scripts" (docs/manual/23-scripts.md): 23.1 a first script (Run, Pause, Stop, IfcTank, together, Examples, Save, Export, Import),
// 23.2 fades, loops and reading errors (the messages table), 23.3 the statement reference (each documented statement compiles). No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-23-scripts
import { readFileSync } from 'node:fs';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-23-scripts');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const tmp = mkdtempSync(join(tmpdir(), 'tour-23-'));
const dist = (a, b) => Math.hypot(...a.p.map((v, i) => v - b.p[i]));
const sstate = (page) => page.evaluate(() => window.__xrayScript.state());
const hud = (page) => page.evaluate(() => window.__xrayFlythrough.hudState().last);
async function setScript(page, text) {
  await ui.tab(page, 'Script');
  await page.getByLabel('Animation script').fill(text);
  await page.waitForTimeout(400);
}
const run = (page) => page.getByRole('button', { name: 'Run', exact: true }).click();
const problems = (page) => page.locator('[data-script-errors] button').allInnerTexts();
const waitRunning = (page) => page.waitForFunction(() => window.__xrayScript.state().running, null, { timeout: 150000 });
const moved = async (page, from, min = 0.5, ms = 120000) => { for (let t = 0; t < ms && dist(from, await ui.cam(page)) < min; t += 400) await page.waitForTimeout(400); };
const waitDone = (page, t = 90000) => page.waitForFunction(() => !window.__xrayScript.state().running, null, { timeout: t });

const FIRST = `-- A walk around the pumps
mode ghost
fly to class IfcPump over 3 seconds
caption "The pumps" "Seen through the rest of the plant" for 3 seconds
`;

await tour.step('23.1 Try it steps 1-4: open Script, type the first script, Run, Pause, Stop', async () => {
  const page = await open('model=process-plant');
  await ui.tab(page, 'Script');
  tour.check('step 1: "Open the Script tab of the right sidebar"', await page.getByLabel('Animation script').isVisible());
  await setScript(page, FIRST);
  tour.check('"Press Run (or Ctrl+Enter)": the script has no problems', (await sstate(page)).errors === 0, JSON.stringify(await problems(page)));
  const lit0 = await ui.litMode(page);
  const cam0 = await ui.cam(page);
  await run(page);
  await waitRunning(page);
  await moved(page, cam0, 1);
  tour.check('step 3: "The look changes to Ghost"', (await ui.litMode(page)) === 'Ghost', `${lit0} -> ${await ui.litMode(page)}`);
  await page.waitForFunction(() => window.__xrayFlythrough.hudState().last?.caption?.title === 'The pumps', null, { timeout: 150000 }).catch(() => {});
  const h = await hud(page);
  tour.check('step 3: "the camera flies to the pumps in 3 seconds, and the caption shows for 3"', dist(cam0, await ui.cam(page)) > 1 && h?.caption?.title === 'The pumps', `moved ${dist(cam0, await ui.cam(page)).toFixed(1)} m; caption ${h?.caption?.title}`);
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.waitForTimeout(400);
  const c1 = await ui.cam(page); await page.waitForTimeout(1000);
  tour.check('step 4: "Press Pause to hold it"', (await sstate(page)).paused && dist(c1, await ui.cam(page)) < 0.05);
  tour.check('the button reads Resume while paused', (await page.getByRole('button', { name: 'Resume', exact: true }).count()) === 1);
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await waitDone(page, 20000);
  await ui.settle(page, 600);
  tour.check('step 4: "Stop to end it. The model goes back to how it was"', (await ui.litMode(page)) === lit0 && dist(cam0, await ui.cam(page)) < 0.05, `${await ui.litMode(page)} vs ${lit0}`);
  // step 5: IfcTank
  await setScript(page, FIRST.replace('IfcPump', 'IfcTank'));
  const cam1 = await ui.cam(page);
  await run(page); await waitRunning(page); await moved(page, cam1, 1);
  const tankCam = await ui.cam(page);
  await page.getByRole('button', { name: 'Stop', exact: true }).click(); await waitDone(page, 20000);
  tour.check('step 5: "Change IfcPump to IfcTank, press Run again": the camera goes elsewhere', dist(cam1, tankCam) > 1, `moved ${dist(cam1, tankCam).toFixed(1)} m`);
});

await tour.step('23.1 Try it step 6: together, orbit and caption at once; select nothing', async () => {
  const page = await open('model=process-plant');
  const text = `-- A walk around the pumps
mode ghost
fly to class IfcPump over 3 seconds
together
  orbit 120 degrees about class IfcPump over 6 seconds
  caption "Four pumps" "Seen from every side" for 6 seconds
end together
select nothing
`;
  await setScript(page, text);
  tour.check('step 6: the script with a together block compiles', (await sstate(page)).errors === 0, JSON.stringify(await problems(page)));
  const dur = (await sstate(page)).duration;
  tour.check('"each line starts when the line before it has ended ... together ... lasts as long as the longest": 3 s + 6 s = 9 s', Math.abs(dur - 9) < 0.6, `duration ${dur}`);
  await run(page); await waitRunning(page);
  await page.waitForFunction(() => window.__xrayFlythrough.hudState().last?.caption?.title === 'Four pumps', null, { timeout: 40000 }).catch(() => {});
  const cA = await ui.cam(page); await moved(page, cA, 0.05); const cB = await ui.cam(page);
  tour.check('the camera orbits while the caption shows', (await hud(page))?.caption?.title === 'Four pumps' && dist(cA, cB) > 0.05, `caption ${(await hud(page))?.caption?.title}, moved ${dist(cA, cB).toFixed(2)}`);
  await page.getByRole('button', { name: 'Stop', exact: true }).click(); await waitDone(page, 20000);
});

await tour.step('23.1 Try it steps 7-8: Examples, name and Save, Export, Import', async () => {
  const page = await open('model=process-plant');
  await ui.tab(page, 'Script');
  await page.getByRole('button', { name: 'Examples', exact: true }).click();
  const items = await page.getByRole('menuitem').allInnerTexts();
  tour.check('step 7: "Open the Examples menu": a walk around the pumps, peel back slabs, highlight each set, change the look over time', ['pumps', 'slabs', 'set', 'look'].every((w) => items.some((i) => new RegExp(w, 'i').test(i))), items.join(' | '));
  await page.getByRole('menuitem', { name: /walk around the pumps/i }).click();
  await page.waitForTimeout(500);
  tour.check('an example loads into the editor', /IfcPump/.test(await page.getByLabel('Animation script').inputValue()));
  await setScript(page, FIRST);
  await page.getByLabel('Script name').fill('Pump walk');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.waitForTimeout(400);
  const saved = await page.evaluate(() => window.__xrayScript.list().map((s) => s.name));
  tour.check('step 8: "Give the script a name and click Save"', saved.includes('Pump walk'), saved.join());
  const dl = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  const d = await dl;
  const f = join(tmp, d.suggestedFilename()); await d.saveAs(f);
  tour.check('step 8: "Export to get a <name>.xrayanim file"', /\.xrayanim$/.test(d.suggestedFilename()) && /Pump walk|pump-walk/i.test(d.suggestedFilename()), d.suggestedFilename());
  tour.check('the file is the script text', /fly to class IfcPump/.test(readFileSync(f, 'utf8')));
  await page.getByLabel('Animation script').fill('');
  await page.getByLabel('Import a script file').setInputFiles(f);
  await page.waitForTimeout(600);
  tour.check('step 8: "Import reads such a file"', /fly to class IfcPump/.test(await page.getByLabel('Animation script').inputValue()));
  // a reload brings the text back: saved scripts are kept in this browser per model
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true', null, { timeout: 240000 });
  await ui.tab(page, 'Script');
  tour.check('"Saved scripts: kept in this browser, per model, together with the text you were editing, so a reload brings it back"', /fly to class IfcPump/.test(await page.getByLabel('Animation script').inputValue()) && (await page.evaluate(() => window.__xrayScript.list().some((s) => s.name === 'Pump walk'))));
  tour.check('"Record: compiles the script and opens the video dialog"', (await page.getByRole('button', { name: 'Record', exact: true }).count()) === 1);
});

await tour.step('23.2 Try it 1: peel slabs with fades (Synth 5k)', async () => {
  const page = await open('model=synth5k');
  const storeys = await page.evaluate(() => window.__xray.app.controller.model.storeys.map((s) => s.name));
  tour.check('"The storey names must be those of your model": Synth 5k has Level 4 and Level 5', ['Level 4', 'Level 5'].every((s) => storeys.includes(s)), storeys.join());
  await setScript(page, `put 1.5 into fade
mode solid
fly to everything over 3 seconds
hide where class = IfcSlab and storey = "Level 5" fading over fade seconds
wait 0.5 seconds
hide where class = IfcSlab and storey = "Level 4" fading over fade seconds
show everything fading over 2 seconds
`);
  tour.check('the fading script compiles with no error', (await sstate(page)).errors === 0, JSON.stringify(await problems(page)));
  const dur = (await sstate(page)).duration;
  tour.check('"hide ... fading over N seconds takes N seconds, and the next line waits for it": 3 + 1.5 + 0.5 + 1.5 + 2 = 8.5 s', Math.abs(dur - 8.5) < 0.5, `duration ${dur}`);
});

await tour.step('23.2 Try it 2-3: visit each pump (repeat for each element); each set; text join', async () => {
  const page = await open('model=process-plant');
  const nPumps = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcPump').length);
  await setScript(page, `repeat for each element in class IfcPump
  together
    fly to it over 2 seconds margin 3
    label it with name for 2 seconds
  end together
end repeat
fly to everything over 3 seconds
`);
  const st = await sstate(page);
  tour.check('step 2: the pump loop compiles', st.errors === 0, JSON.stringify(await problems(page)));
  tour.check('"expands to one pass per element": duration = pumps x 2 s + 3 s', Math.abs(st.duration - (nPumps * 2 + 3)) < 0.6, `${nPumps} pumps, ${st.duration} s`);
  await setScript(page, `repeat for each set in sets
  select it
  fly to it over 2 seconds
  caption it for 2 seconds
end repeat
select nothing
`);
  tour.check('step 3: the set loop compiles (no sets: zero passes)', (await sstate(page)).errors === 0, JSON.stringify(await problems(page)));
  await setScript(page, `repeat 3 times
  caption "Pump " & index for 1 seconds
end repeat
`);
  const r = await page.evaluate(() => window.__xrayScript.compile('repeat 3 times\n  caption "Pump " & index for 1 seconds\nend repeat'));
  tour.check('"Inside repeat, index counts from 1. Join text with &": the captions read "Pump 1", "Pump 2", "Pump 3"', r.errors.length === 0 && JSON.stringify(r.score).includes('Pump 1') && JSON.stringify(r.score).includes('Pump 3'), r.errors.map((e) => e.message).join());
});

await tour.step('23.2 Try it 4 and the messages table: mistakes on purpose, the Problems list', async () => {
  const page = await open('model=process-plant');
  await setScript(page, 'flyto everything');
  const p = await problems(page);
  tour.check('step 4: "Write flyto everything and look at the Problems list"', p.length >= 1 && /do not know the statement `flyto`/.test(p.join(' ')), p.join(' | '));
  const tab = (await page.getByRole('tab', { name: /^Script/ }).innerText()).replace(/\s+/g, ' ');
  tour.check('"The tab button shows the number of errors"', /1/.test(tab) || (await page.locator('#dk-tab-script, [data-tab=script]').first().innerText().catch(() => '')).includes('1'), tab);
  await page.getByLabel('Animation script').fill('line one is a comment\nflyto everything');
  await page.locator('[data-script-errors] button').first().click();
  await page.waitForTimeout(300);
  const msgs = [
    ['flyto everything', /do not know the statement `flyto`/, 'I do not know the statement `flyto`'],
    ['storey = Level 2', null, null],
    ['together\n  wait 1', /`together` on line 1 has no `end together`/, 'The `together` on line 2 has no `end together`'],
    ['wait 1\nend repeat', /`end repeat` has no block to close/, '`end repeat` has no block to close'],
    ['wait pause', /do not know the name `pause`/, 'I do not know the name `pause`'],
    ['caption it for 1 seconds', /`it` has no meaning here/, '`it` has no meaning here'],
    ['select set "Pmps"', /no selection set named "Pmps"/, 'There is no selection set named "Pmps"'],
    ['set no.such.setting to 3', /do not know the setting/, 'I do not know the setting'],
    ['fly to everything margin 7', /margin 7 is outside 1 to 6/, 'The margin 7 is outside 1 to 6'],
    ['hide where class = IfcSlab and storey = Level 2', /Unexpected "2"/, 'In the criteria: Unexpected "2": expected AND, OR or the end of the query.'],
  ];
  for (const [text, re, said] of msgs) {
    if (!re) continue;
    const r = await page.evaluate((t) => window.__xrayScript.compile(t).errors.map((e) => `${e.severity}: ${e.message}`), text);
    tour.check(`the messages table: "${said}"`, r.some((m) => re.test(m)), r.join(' | ').slice(0, 200));
  }
  const many = await page.evaluate(() => window.__xrayScript.compile('repeat 500 times\n  repeat 11 times\n    caption "x" for 1 seconds\n  end repeat\nend repeat').errors.map((e) => e.message));
  tour.check('"The script makes more than 5000 steps. Use fewer or smaller loops"', many.some((m) => /more than 5000 steps/.test(m)), many.join(' | ').slice(0, 160));
  const w = await page.evaluate(() => window.__xrayScript.compile('set no.such.setting to 3').errors);
  tour.check('"Warnings do not stop the script. Errors do": an unknown setting is a warning', w.length > 0 && w.every((e) => e.severity === 'warning'), JSON.stringify(w.map((e) => e.severity)));
});

await tour.step('23.3 The statement reference: each documented statement compiles', async () => {
  const page = await open('model=process-plant');
  const good = [
    'fly to class IfcPump over 2 seconds ease linear margin 2', 'orbit 90 degrees about class IfcPump over 3 seconds', 'orbit -45 degrees', 'set cinematic.glowStrength to 1.2 over 2 seconds',
    'mode cutaway', 'apply preset "coordination"', 'show everything', 'hide class IfcPump fading over 1 seconds', 'isolate class IfcPump fading over 1 seconds', 'select class IfcPump', 'select nothing',
    'caption "Title" "More text" for 3 seconds', 'label class IfcPump with name, class, storey, material, globalid, type for 2 seconds', 'hover class IfcPump for 2 seconds', 'wait 2',
    'repeat 3 times\n wait 1\nend repeat', 'put 2 into x\nwait x * 2 + 1', 'tint class IfcPump red fading over 1 seconds', 'tint class IfcPump off', 'explode storeys by 1.5 over 2 seconds', 'explode radial', 'collapse over 1 seconds',
    'focus class IfcPump', 'focus nothing', 'section box around class IfcPump over 1 seconds', 'section box off', 'show issues', 'hide drawings', 'fade new elements over 1.5 seconds',
    'param floor default "Level 1"\nwait 1',
  ];
  const bad = [];
  for (const g of good) {
    const e = await page.evaluate((t) => window.__xrayScript.compile(t).errors.filter((x) => x.severity === 'error').map((x) => x.message), g);
    if (e.length) bad.push(`${g.split('\n')[0]} -> ${e[0]}`);
  }
  tour.check(`"the summary" table: ${good.length} statements compile without an error`, bad.length === 0, bad.join(' ; ').slice(0, 400));
  const defaults = await page.evaluate(() => ['fly to everything', 'orbit 90 degrees', 'caption "x"', 'hover everything', 'explode storeys', 'collapse', 'section box off'].map((t) => window.__xrayScript.compile(t).score?.duration ?? null));
  tour.check('default times: fly 2 s, orbit 3 s, caption 3 s, hover 2 s, explode 2 s, collapse 2 s, section box 1.5 s', JSON.stringify(defaults.map((d) => d && +d.toFixed(2))) === JSON.stringify([2, 3, 3, 2, 2, 2, 1.5]), JSON.stringify(defaults));
  const api = await page.evaluate(() => Object.keys(window.__xrayScript).sort());
  tour.check('"window.__xrayScript offers compile(text), run(text), list(), save(name, text), load(name) and state()"', ['compile', 'run', 'list', 'save', 'load', 'state'].every((k) => api.includes(k)), api.join());
  const unknown = await page.evaluate(() => window.__xrayScript.compile('schedule "No such plan" over 5 seconds').errors.map((e) => e.message));
  tour.check('4D statements: an unknown plan name is reported', unknown.length > 0, unknown.join(' | ').slice(0, 140));
  const big = await page.evaluate(() => window.__xrayScript.compile('repeat 501 times\n wait 1\nend repeat').errors.map((e) => e.message));
  tour.check('"a loop ... at most 500 times"', big.length > 0, big.join(' | ').slice(0, 140));
});

await tour.finish();
