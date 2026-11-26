// Tour of chapter 23A, "Scripts that decide: logic, text and reuse" (docs/manual/23a-script-logic.md): 23A.1 if / count / repeat while, 23A.2 handlers and functions,
// 23A.3 issues and drawings and fades, 23A.4 facts, text, lists and maths, 23A.5 param and use. The scripts of the Try it blocks are typed into the Script tab and Run;
// what each one makes is read from the compiled score (the captions and the duration). No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-23a-script-logic
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-23a-script-logic');
const sstate = (page) => page.evaluate(() => window.__xrayScript.state());
const problems = (page) => page.locator('[data-script-errors] button').allInnerTexts();
async function setScript(page, text) {
  await ui.tab(page, 'Script');
  await page.getByLabel('Animation script').fill(text);
  await page.waitForTimeout(500);
}
/** Compile in the page; return { errors, captions (title and text of each caption cue), duration }. */
const compile = (page, text, params) => page.evaluate(([t, p]) => {
  const r = window.__xrayScript.compile(t, p ? { params: p } : undefined);
  const caps = [];
  const walk = (o) => { if (!o || typeof o !== 'object') return; if (Array.isArray(o)) return o.forEach(walk); if (o.kind === 'caption' || (o.title !== undefined && o.text !== undefined && o.at !== undefined)) caps.push(`${o.title ?? ''}|${o.text ?? ''}`); Object.values(o).forEach(walk); };
  walk(r.score?.cues ?? r.score);
  return { errors: r.errors.filter((e) => e.severity === 'error').map((e) => e.message), warnings: r.errors.filter((e) => e.severity === 'warning').map((e) => e.message), caps, duration: r.score?.duration ?? null, text: JSON.stringify(r.score ?? {}) };
}, [text, params]);
const waitRunning = (page) => page.waitForFunction(() => window.__xrayScript.state().running, null, { timeout: 30000 });
const waitDone = (page, t = 90000) => page.waitForFunction(() => !window.__xrayScript.state().running, null, { timeout: t });

await tour.step('23A.1 Try it: if there are class IfcPump; change to IfcDoor: the else line plays', async () => {
  const page = await tour.open('model=process-plant');
  const nPumps = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcPump').length);
  const T = (cls) => `if there are class ${cls} then
  fly to class ${cls} over 3 seconds
  caption "Pumps" "There are " & the count of class ${cls} for 3 seconds
else
  caption "No pumps" for 2 seconds
end if
`;
  await setScript(page, T('IfcPump'));
  tour.check('the if script has no problems in the Problems list', (await sstate(page)).errors === 0, JSON.stringify(await problems(page)));
  const a = await compile(page, T('IfcPump'));
  tour.check('"The caption names the number of pumps"', a.errors.length === 0 && a.text.includes(`There are ${nPumps}`), `pumps ${nPumps}; ${a.text.match(/There are \d+/)?.[0]}`);
  tour.check('"The script looks at the model while you press Run ... the lines that do not apply are never written": 3 s', Math.abs(a.duration - 3) < 0.2, `${a.duration}`);
  const b = await compile(page, T('IfcDoor'));
  tour.check('"Change IfcPump to IfcDoor and Run again: the else line plays"', b.text.includes('No pumps') && !b.text.includes('There are') && Math.abs(b.duration - 2) < 0.2, `duration ${b.duration}`);
  await setScript(page, T('IfcPump'));
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await waitRunning(page);
  await page.waitForFunction(() => window.__xrayFlythrough.hudState().last?.caption?.text?.startsWith('There are'), null, { timeout: 40000 }).catch(() => {});
  const cap = await page.evaluate(() => window.__xrayFlythrough.hudState().last?.caption);
  tour.check('Run: the caption on screen reads "There are N"', new RegExp(`^There are ${nPumps}$`).test(cap?.text ?? ''), JSON.stringify(cap && { t: cap.title, x: cap.text }));
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await waitDone(page, 20000);
  const w = await compile(page, `put 1 into gap
repeat while gap < 10
  caption "Pause of " & gap & " seconds" for 1 seconds
  wait gap
  put gap * 2 into gap
end repeat
`);
  tour.check('"repeat while": gap 1, 2, 4, 8 gives four passes of (1 + gap) s = 1+1, 1+2, 1+4, 1+8 = 19 s', w.errors.length === 0 && Math.abs(w.duration - 19) < 0.3, `${w.errors.join()} ${w.duration}`);
  const one = await compile(page, 'if the count of class IfcPump > 3 then caption "A big pump room" for 2 seconds');
  tour.check('"One-line form: if the count of class IfcPump > 3 then caption ..."', one.errors.length === 0, one.errors.join());
  const lp = await compile(page, 'repeat with i from 1 to 5 by 2\n  wait 1\nend repeat\nrepeat with j from 3 down to 1\n  wait 1\nend repeat');
  tour.check('"repeat with i from 1 to 5 (add by 2, or down to)": 3 + 3 passes', lp.errors.length === 0 && Math.abs(lp.duration - 6) < 0.2, `${lp.errors.join()} ${lp.duration}`);
  const ex = await compile(page, 'repeat with i from 1 to 5\n  if i = 3 then exit repeat\n  if i = 1 then next repeat\n  wait 1\nend repeat');
  tour.check('"exit repeat leaves a loop. next repeat skips to the next pass": only i = 2 waits', ex.errors.length === 0 && Math.abs(ex.duration - 1) < 0.2, `${ex.errors.join()} ${ex.duration}`);
  const inf = await compile(page, 'put 1 into n\nrepeat while n > 0\n  wait 1\nend repeat');
  tour.check('"A loop stops after 500 passes, with a message that names its line"', inf.errors.concat(inf.warnings).some((m) => /500/.test(m)), inf.errors.concat(inf.warnings).join(' | ').slice(0, 160));
  const act = await compile(page, 'if there are active then wait 1');
  tour.check('"the count of and there are ... cannot count active, completed or critical"', act.errors.length > 0, act.errors.join(' | ').slice(0, 160));
  const deep = await compile(page, Array.from({ length: 9 }, (_, i) => `${' '.repeat(i)}if 1 = 1 then`).join('\n') + '\nwait 1\n' + Array.from({ length: 9 }, () => 'end if').join('\n'));
  tour.check('"Blocks nest at most 8 deep"', deep.errors.length > 0, deep.errors.join(' | ').slice(0, 140));
});

await tour.step('23A.2 Try it: handler showFloor and function plural', async () => {
  const page = await tour.open('model=synth5k');
  const HANDLER = `on showFloor name
  if there are (where class = IfcWall and storey = name) then
    show where storey = name fading over 0.5 seconds
    fly to where storey = name over 2 seconds
    caption name for 2 seconds
  end if
end showFloor

hide everything
repeat with i from 1 to 5
  showFloor "Level " & i
end repeat
show everything fading over 1 seconds
`;
  const storeysWithWalls = await page.evaluate(() => { const s = new Set(); for (const e of window.__xray.app.controller.model.elements) if (e.ifcClass === 'IfcWall' || e.ifcClass === 'IfcWallStandardCase') s.add(e.storey); return [...s].filter((x) => /^Level [1-5]$/.test(x ?? '')).length; });
  const h = await compile(page, HANDLER);
  tour.check('step "Run it on Synth 5k": the handler script compiles', h.errors.length === 0, h.errors.join(' | ').slice(0, 200));
  const expected = storeysWithWalls * 2 + 1;
  tour.check('"The film visits each floor that has walls and skips the rest": each floor 2 s (fly) + 2 s (caption) in sequence, plus the 1 s fade', h.duration >= expected - 0.1, `${storeysWithWalls} floors with walls; duration ${h.duration}`);
  await setScript(page, HANDLER);
  tour.check('the Problems list is empty', (await sstate(page)).errors === 0, JSON.stringify(await problems(page)));
  const fn = await compile(page, `function plural n
  if n = 1 then return n & " pump"
  return n & " pumps"
end plural
caption "The plant" "It has " & plural(the count of class IfcPump) for 3 seconds
`);
  tour.check('"A function returns a value instead": the caption text is "It has N pumps"', fn.errors.length === 0 && /It has \d+ pumps/.test(fn.text), `${fn.errors.join()} ${fn.text.match(/It has [^"]*/)?.[0]}`);
  const own = await compile(page, 'on pause\n  wait 1\nend pause');
  tour.check('"Their names cannot be words of the language" (a handler named like a statement is refused)', own.errors.length > 0 || own.warnings.length > 0, own.errors.join(' | ').slice(0, 120));
  const late = await compile(page, 'sayHi\non sayHi\n  caption "hi" for 1 seconds\nend sayHi');
  tour.check('"A handler may stand below the lines that call it"', late.errors.length === 0 && late.duration > 0.9, late.errors.join());
  const wrong = await compile(page, 'on two a b\n  wait 1\nend two\ntwo 1');
  tour.check('"A call with the wrong number of values names its line in the Problems list"', wrong.errors.length > 0 && /line|two/i.test(wrong.errors.join()), wrong.errors.join(' | ').slice(0, 140));
});

await tour.step('23A.3 Issues, drawings and fades', async () => {
  const page = await tour.open('model=process-plant');
  for (const s of ['show issues', 'hide issues', 'show drawings', 'hide drawings']) {
    const r = await compile(page, s);
    tour.check(`"Say ${s}"`, r.errors.length === 0, r.errors.join());
  }
  const f = await compile(page, 'fade new elements over 1.5 seconds\nhide class IfcPump\nwait 1');
  tour.check('"fade new elements over 1.5 seconds sets how long elements fade in or out from that line on"', f.errors.length === 0 && /1\.5/.test(f.text), f.errors.join());
  const s4 = await compile(page, 'schedule "Plan" over 60 seconds fade 0.8 seconds');
  tour.check('"In a 4D line, schedule "Plan" over 60 seconds fade 0.8 seconds": the fade option is part of the grammar (only the unknown plan is reported)', !s4.errors.some((m) => /fade/i.test(m)), s4.errors.join(' | ').slice(0, 160));
});

await tour.step('23A.4 Try it: facts, text, lists and maths', async () => {
  const page = await tour.open('model=process-plant');
  const walls = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => /IfcWall/.test(e.ifcClass)).length);
  const FACTS = `repeat for each element in class IfcWall
  put property "Pset_WallCommon.FireRating" of it into rating
  if rating contains "60" then
    caption the name of it && "has" && rating for 1 seconds
  end if
end repeat
`;
  const r = await compile(page, FACTS);
  tour.check('step 1: the fire-rating script compiles on the Process plant (5 walls)', r.errors.length === 0 && walls >= 1, `${walls} walls; ${r.errors.join(' | ').slice(0, 160)}`);
  const lst = await compile(page, `put "Level 3, Level 1, Level 2" into floors
put sort items of floors into ordered
repeat for each item floor in ordered
  caption floor && "of" && the number of items in floors for 1 seconds
end repeat
`);
  tour.check('step 2: the list script gives three captions, sorted: "Level 1 of 3", "Level 2 of 3", "Level 3 of 3"', lst.errors.length === 0 && ['Level 1 of 3', 'Level 2 of 3', 'Level 3 of 3'].every((t) => lst.text.includes(t)) && lst.text.indexOf('Level 1 of 3') < lst.text.indexOf('Level 3 of 3'), `${lst.errors.join()} ${(lst.text.match(/Level \d of \d/g) ?? []).join()}`);
  const val = async (expr) => { const c = await compile(page, `caption "r" & (${expr}) for 1 seconds`); return c.errors.length ? `ERR ${c.errors[0]}` : (c.text.match(/"title":"r([^"]*)"/)?.[1] ?? c.text.match(/r(-?[0-9.]+)/)?.[1] ?? '?'); };
  const maths = { 'round(2.567, 1)': '2.6', 'round(2.5)': '3', 'trunc(2.9)': '2', 'floor(2.9)': '2', 'ceil(2.1)': '3', 'abs(-4)': '4', 'min(3, 2)': '2', 'max(3, 2)': '3', 'sqrt(16)': '4', '7 mod 3': '1', '7 div 2': '3', '2 ^ 3': '8' };
  const bad = [];
  for (const [e, want] of Object.entries(maths)) { const got = await val(e); if (got !== want) bad.push(`${e} = ${got} (want ${want})`); }
  tour.check('"Maths: round, trunc, floor, ceil, abs, min, max, sqrt, mod, div, ^" give the documented values', bad.length === 0, bad.join('; '));
  const dz = await compile(page, 'put 1 / 0 into x\nwait x');
  const sq = await compile(page, 'put sqrt(-1) into x\nwait x');
  tour.check('"Division by zero, or the root of a negative number, is an error"', dz.errors.length > 0 && sq.errors.length > 0, `${dz.errors[0]} | ${sq.errors[0]}`);
  const r1 = await compile(page, 'put random(6) into x\ncaption "x" & x for 1 seconds');
  const r2 = await compile(page, 'put random(6) into x\ncaption "x" & x for 1 seconds');
  tour.check('"The numbers are seeded from the script text, so the same script always makes the same film"', r1.text === r2.text && r1.errors.length === 0);
  const seed = await compile(page, 'set the random seed to 7\nput random(1000) into x\ncaption "x" & x for 1 seconds');
  tour.check('"set the random seed to 7 picks another"', seed.errors.length === 0 && seed.text !== r1.text);
  const txt = await compile(page, 'put "Pump 1" into n\nif n begins with "pump" and n ends with "1" and "UMP" is in n and "z" is not in n then caption "yes" for 1 seconds');
  tour.check('"The tests contains, begins with, ends with, is in and is not in ignore capitals"', txt.errors.length === 0 && txt.text.includes('yes'), txt.errors.join());
  const chunks = await compile(page, 'put "a, b, c" into x\nput item 2 of x into y\nput word 1 of "hello world" into z\nput char 1 to 3 of "abcdef" into c\ncaption y & z & c for 1 seconds');
  tour.check('"item 2 of x, word 3 of x, line 1 of x, char 1 to 3 of x" read pieces', chunks.errors.length === 0 && /b ?hello ?abc/.test(chunks.text.replace(/\s/g, ' ')) || chunks.text.includes('bhelloabc') || chunks.text.includes('b hello'), `${chunks.errors.join()} ${chunks.text.match(/"title":"[^"]*"/)?.[0]}`);
  const noModel = await compile(page, 'repeat for each item i in the names of class IfcPump\n  wait 0.1\nend repeat');
  tour.check('"the names of class IfcPump gives all the names, separated by commas"', noModel.errors.length === 0, noModel.errors.join());
});

await tour.step('23A.5 Try it: param and use; the Parameters form', async () => {
  const page = await tour.open('model=synth5k');
  const P = `param floor default "Level 1"
param pause default 3
fly to where storey = floor over 3 seconds
caption "Now showing" && floor for pause seconds
`;
  await setScript(page, P);
  const st = await sstate(page);
  tour.check('"A Parameters form appears above Run in the Script tab with floor and pause"', st.params.length === 2 && st.params.map((p) => p.name).sort().join() === 'floor,pause', JSON.stringify(st.params));
  tour.check('"Parameters" is a visible heading of the form', /Parameters/i.test(await page.locator('#dock').innerText()));
  tour.check('defaults: floor "Level 1" and pause 3 give 3 + 3 = 6 s', Math.abs(st.duration - 6) < 0.3, `${st.duration}`);
  const input = page.getByLabel('floor', { exact: true }).first();
  if (await input.count()) { await input.fill('Level 2'); await input.press('Tab'); }
  else await page.evaluate(() => window.__xrayScript.setParams({ floor: 'Level 2' }));
  await page.waitForTimeout(400);
  const c = await compile(page, P, { floor: 'Level 2' });
  tour.check('"Change floor and run again": the caption follows the value', c.text.includes('Now showing') && c.text.includes('Level 2'), c.text.match(/Level \d/)?.[0]);
  const unk = await compile(page, P, { nope: 1 });
  tour.check('"A value for a name the script does not declare is a warning"', unk.warnings.length > 0 && unk.errors.length === 0, unk.warnings.join(' | ').slice(0, 120));
  await page.getByRole('button', { name: 'Examples', exact: true }).click();
  const items = await page.getByRole('menuitem').allInnerTexts();
  tour.check('"The Examples menu has One script, any floor and Label the fire-rated walls"', items.some((i) => /any floor/i.test(i)) && items.some((i) => /fire-rated walls/i.test(i)), items.join(' | '));
  await page.getByRole('menuitem', { name: /any floor/i }).click();
  await page.waitForTimeout(600);
  tour.check('an example with param loads with its form', (await sstate(page)).params.length >= 1 && (await sstate(page)).errors === 0, JSON.stringify((await sstate(page)).params));
  // use: a library of another saved script
  await page.evaluate(() => window.__xrayScript.save('Floor helpers', 'on hello\n  caption "hello" for 1 seconds\nend hello'));
  const u = await compile(page, 'use "Floor helpers"\nhello');
  tour.check('"use "Floor helpers" pulls in the handlers and functions of another saved script"', u.errors.length === 0 && u.text.includes('hello'), u.errors.join());
  const miss = await compile(page, 'use "No such library"');
  tour.check('"A missing library ... is an error"', miss.errors.length > 0, miss.errors.join(' | ').slice(0, 120));
  const own = await compile(page, 'use "Floor helpers"\non hello\n  caption "mine" for 1 seconds\nend hello\nhello');
  tour.check('"If your script has a handler of the same name, yours wins, with a warning"', own.errors.length === 0 && own.warnings.length > 0 && own.text.includes('mine'), `${own.errors.join()} ${own.warnings.join(' | ').slice(0, 100)}`);
});

await tour.finish();
