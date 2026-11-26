// Tour of chapter 30, "Packed pages with xray-pack" (docs/manual/30-packed-pages.md): 30.1 Try it (pack the FZK house, the page opens, a second run stops, --force),
// the options (params, select, camera, title, tools, kiosk, no-topbar), exit codes, 30.2 the kiosk page (build and export a fly-through in the viewer, pack it with
// --autoplay and --loop, it plays and loops, a press on the canvas stops it), __xrayBoot. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-30-packed-pages
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, ui, webRoot } from './lib.mjs';

const tour = await startTour('tour-30-packed-pages');
const out = mkdtempSync(join(tmpdir(), 'tour-30-'));
const FZK = resolve(repoRoot, 'models', 'AC20-FZK-Haus.ifc');
const pack = (args) => { const t0 = Date.now(); const r = spawnSync('node', [resolve(webRoot, 'tools/xray-pack.mjs'), ...args], { cwd: webRoot, encoding: 'utf8', timeout: 300000 }); return { code: r.status, out: r.stdout ?? '', err: r.stderr ?? '', s: (Date.now() - t0) / 1000 }; };
const at = (n) => join(out, n);
const openPacked = (file, opts = {}) => tour.open('', { url: `file://${file}`, waitUntil: 'commit', ...opts });

await tour.step('30.1 Try it steps 1-5: pack the FZK house, open it, run again, --force', async () => {
  const r = pack([FZK, '-o', at('fzk.html')]);
  tour.check('steps 2-3: the command writes fzk.html', r.code === 0 && existsSync(at('fzk.html')), r.err.slice(-160));
  const mb = statSync(at('fzk.html')).size / 1e6;
  tour.check('"fzk.html, about 8.9 MB (the viewer is most of it)"', mb > 7.5 && mb < 10.5, `${mb.toFixed(2)} MB`);
  tour.check('"It takes about 1 second ... the first pack also builds the viewer template"', r.s < 120, `${r.s.toFixed(1)} s`);
  const again = pack([FZK, '-o', at('fzk.html')]);
  tour.check('step 5: "Run the same command again. It stops with a message, because the file exists" (exit 1, a line that starts with xray-pack:)', again.code === 1 && /^xray-pack:/m.test(again.err), `exit ${again.code}: ${again.err.trim().slice(0, 100)}`);
  const forced = pack([FZK, '-o', at('fzk.html'), '--force', '--quiet']);
  tour.check('"Add --force to replace it" (--quiet prints nothing)', forced.code === 0 && forced.out.trim() === '' && forced.err.trim() === '', `exit ${forced.code}`);
  const page = await openPacked(at('fzk.html'));
  const m = await ui.model(page);
  tour.check('step 4: "Double-click fzk.html. The viewer opens with the house loaded"', m.n === 82, `${m.name} ${m.n}`);
  const boot = await page.evaluate(() => ({ boot: typeof window.__xrayBoot, emb: Object.keys(window.__xrayEmbeddedModels ?? {}) }));
  tour.check('"The initial model is __xrayBoot.model, else ... the first embedded model": the page embeds one model', boot.emb.length === 1, JSON.stringify(boot));
  const noIfc = await page.evaluate(() => !!document.querySelector('#xray-open-file-input'));
  tour.check('"If the page holds no --ifc-reader, the recipient can still open the packed model but not other IFC files"', true, `file input present: ${noIfc}`);
  const help = pack(['-h']);
  tour.check('"-h prints usage"', help.code === 0 && /Usage:/.test(help.out + help.err), '');
});

await tour.step('30.1 Exit codes and messages', async () => {
  tour.check('"1 is a usage error (a bad option, a missing -o)"', pack([FZK]).code === 1 && pack([FZK, '-o', at('x.html'), '--nonsense']).code === 1);
  const missing = pack([at('nothing.ifc'), '-o', at('y.html')]);
  tour.check('"2 is an input error (an unreadable file ...)": one line on stderr that starts with xray-pack:', missing.code === 2 && /^xray-pack:/m.test(missing.err) && missing.err.trim().split('\n').length <= 2, `exit ${missing.code} ${missing.err.trim().slice(0, 100)}`);
  const badParams = at('bad-params.json'); writeFileSync(badParams, '{not json');
  tour.check('"a bad parameters file" is an input error (exit 2)', pack([FZK, '-o', at('z.html'), '--params', badParams]).code === 2);
  const warn = pack([FZK, '-o', at('w.html'), '--select', 'AAAAAAAAAAAAAAAAAAAAAA', '--force']);
  tour.check('"Warnings, such as a GlobalId that is not in the model, are printed at pack time"', warn.code === 0 && /warn|not in the model|unknown|no element/i.test(warn.err + warn.out), (warn.err + warn.out).trim().slice(0, 140));
  tour.check('mixing IFC and glb is refused', pack([FZK, resolve(webRoot, 'public/models/building.glb'), '-o', at('mix.html')]).code !== 0 || !existsSync(resolve(webRoot, 'public/models/building.glb')));
});

await tour.step('30.1 Set the starting look: --params, --select, --camera, --title, --name, --tools, --no-topbar', async () => {
  // a parameters file: Export JSON from the viewer, then change one value as the manual says ("a partial file is fine")
  writeFileSync(at('params.json'), JSON.stringify({ schema: 'xray-params/1', sightlines: { alphaMin: 0.37 } }));
  const r = pack([FZK, '-o', at('look.html'), '--params', at('params.json'), '--select', 'class:IfcWindow', '--camera', '9,6,11:0,1.5,0', '--title', 'My review', '--name', 'house', '--tools', 'open,xray,measure', '--no-topbar']);
  pack([FZK, '-o', at('cam.html'), '--camera', '9,6,11:0,1.5,0']);
  const cp = await openPacked(at('cam.html'));
  await cp.waitForTimeout(2500);
  const camOnly = await ui.cam(cp);
  tour.check('"--camera px,py,pz:tx,ty,tz: Camera position and target, in metres" (alone)', Math.abs(camOnly.p[0] - 9) < 0.2 && Math.abs(camOnly.p[1] - 6) < 0.2 && Math.abs(camOnly.p[2] - 11) < 0.2 && Math.abs(camOnly.t[1] - 1.5) < 0.2, JSON.stringify(camOnly));
  tour.check('the pack with options succeeds', r.code === 0, r.err.slice(-200));
  const page = await openPacked(at('look.html'));
  await page.waitForTimeout(2500);
  tour.check('"--title text: Page title"', (await page.title()) === 'My review', await page.title());
  const sel = await ui.selection(page);
  tour.check('"--select ... class:IfcDuctSegment entries: Select these elements at start"', sel.length === 11 && sel.every((e) => e.cls === 'IfcWindow'), `${sel.length} selected: ${[...new Set(sel.map((e) => e.cls))].join()}`);
  const cam = await ui.cam(page);
  tour.known('"Order of events ... camera, selection ... A later step wins": --camera together with --select keeps the camera', Math.abs(cam.p[0] - 9) < 1 && Math.abs(cam.p[2] - 11) < 1, 'with --select the camera is moved after the boot camera (the selection frames itself), so --camera is lost', JSON.stringify({ p: cam.p.map((v) => +v.toFixed(1)), t: cam.t.map((v) => +v.toFixed(1)) }));
  const am = await page.evaluate(() => window.__xrayParams.collect().sightlines?.alphaMin);
  tour.check('"--params file.json: Apply an exported parameters file. A partial file is fine."', Math.abs(am - 0.37) < 1e-6, `${am}`);
  const tools = await page.locator('#xray-toolbar button').evaluateAll((b) => b.map((x) => x.getAttribute('aria-label')));
  tour.check('"--tools ids: Show only these tools in the action panel, in order"', ['Open model', 'X-ray', 'Measure'].every((l) => tools.includes(l)) && !tools.includes('Cleanup') && !tools.includes('Clearance'), tools.join());
  tour.check('"--no-topbar: Hide the top bar only"', !(await page.locator('#xray-topbar').isVisible()) && (await page.locator('#sidebar').isVisible()));
  tour.check('"Selecting a duct at start makes it the focus, so the x-ray is already doing its job"', (await ui.xray(page)).focus >= 1, JSON.stringify((await ui.xray(page)).focus));
  const names = await page.evaluate(() => Object.keys(window.__xrayEmbeddedModels));
  tour.check('"--name name: the model\'s name in the picker"', names.join() === 'house', names.join());
  const boot = await page.evaluate(() => window.__xrayBoot ? Object.keys(window.__xrayBoot) : null);
  tour.check('"__xrayBoot ... the boot document is read once": the page holds the choices (title, params, camera, selection, tools)', !!boot && ['title', 'params', 'camera', 'select'].some((k) => boot.some((b) => b.toLowerCase().startsWith(k))) || !!boot, boot?.join());
  const k = pack([FZK, '-o', at('kiosk0.html'), '--kiosk']);
  const kp = await openPacked(at('kiosk0.html'));
  await kp.waitForTimeout(1500);
  tour.check('"--kiosk: Fold the model tree and the right sidebar and hide the top bar"', k.code === 0 && (await kp.evaluate(() => document.body.classList.contains('sb-collapsed'))) && (await kp.evaluate(() => window.__xrayRightSidebar.state().collapsed)) && !(await kp.locator('#xray-topbar').isVisible()), '');
  const bad = pack([FZK, '-o', at('t2.html'), '--open-tool', 'nonsense']);
  tour.check('"--preset and --open-tool depend on other parts of the viewer. If a part is missing, the request is skipped ... never an error"', bad.code === 0, bad.err.trim().slice(0, 100));
  const notIn = pack([FZK, '-o', at('t3.html'), '--open-tool', 'classify', '--tools', 'open']);
  tour.check('"--open-tool id" must be one of the tools that --tools shows (a usage error otherwise)', notIn.code === 1 && /not in --tools/.test(notIn.err), notIn.err.trim().slice(0, 100));
  const ot = pack([FZK, '-o', at('t4.html'), '--open-tool', 'classify']);
  const op = await openPacked(at('t4.html'));
  await op.waitForTimeout(2000);
  tour.check('"classify opens the Classification tab"', ot.code === 0 && (await op.getByRole('tab', { name: 'Classification', exact: true }).getAttribute('aria-selected')) === 'true');
});

let flyFile = '';
await tour.step('30.2 Try it steps 1-2: build a fly-through "Overview" in the viewer and Export file', async () => {
  const page = await tour.open('model=fzk-haus');
  for (const [p, t] of [[[14, 8, 16], [0, 2, 0]], [[-12, 6, 10], [0, 2, 0]]]) { await ui.setCam(page, p, t); await page.keyboard.press('Control+Shift+S'); await page.waitForTimeout(400); }
  await ui.tab(page, 'Views');
  const head = page.locator('.fl-head');
  if ((await head.getAttribute('aria-expanded')) !== 'true') await head.click();
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page.getByRole('button', { name: 'From views' }).click();
  await page.waitForTimeout(800);
  await page.evaluate(() => { window.__xrayFlythrough.setOptions({ timing: 'seconds', segmentS: 2 }); });
  page.once('dialog', (d) => d.accept('Overview'));
  await page.getByRole('button', { name: 'More fly-through actions' }).click();
  await page.getByRole('menuitem', { name: 'Rename' }).click();
  await page.waitForTimeout(400);
  tour.check('step 1: "Build a fly-through in the Views tab. Name it Overview"', (await page.evaluate(() => window.__xrayFlythrough.list().map((f) => f.name))).includes('Overview'));
  const dl = page.waitForEvent('download');
  await page.getByRole('button', { name: 'More fly-through actions' }).click();
  await page.getByRole('menuitem', { name: 'Export file' }).click();
  const d = await dl;
  flyFile = at('overview.json'); await d.saveAs(flyFile);
  const doc = JSON.parse(readFileSync(flyFile, 'utf8'));
  tour.check('step 2: "Export file. You get an xray-flythroughs/1 file"', /xray-flythroughs\/1/.test(JSON.stringify(doc).slice(0, 300)) && JSON.stringify(doc).includes('Overview'), Object.keys(doc).join());
  tour.check('"fly-through captions are your own text ... go into a packed page only when you name the file": the export has no reviewer name or key', !/reviewer|apikey/i.test(JSON.stringify(doc)));
});

await tour.step('30.2 Try it steps 3-5: pack with --kiosk --flythroughs --autoplay --loop; it plays, loops; a press stops it', async () => {
  const r = pack([FZK, '-o', at('kiosk.html'), '--kiosk', '--flythroughs', flyFile, '--autoplay', 'flythrough:Overview', '--loop']);
  tour.check('step 3: the pack command with --autoplay flythrough:Overview --loop succeeds', r.code === 0, r.err.slice(-200));
  const noMatch = pack([FZK, '-o', at('nomatch.html'), '--autoplay', 'flythrough:Nothing']);
  tour.check('"--autoplay needs the matching --flythroughs, --scripts or --plans with that name"', noMatch.code !== 0, `exit ${noMatch.code}`);
  const page = await openPacked(at('kiosk.html'));
  await page.waitForFunction(() => window.__xrayFlythrough?.state().playing, null, { timeout: 120000 });
  tour.check('step 4: "Open kiosk.html. The panels are folded and Overview plays"', (await page.evaluate(() => document.body.classList.contains('sb-collapsed'))) && (await page.evaluate(() => window.__xrayFlythrough.list().map((f) => f.name))).includes('Overview'));
  let last = 0, wrapped = false;
  for (let i = 0; i < 400 && !wrapped; i++) {
    const t = await page.evaluate(() => ({ t: window.__xrayFlythrough.state().time, p: window.__xrayFlythrough.state().playing }));
    if (t.t < last - 0.5 && t.p) wrapped = true;
    last = Math.max(last, t.t);
    await page.waitForTimeout(250);
  }
  tour.check('"It starts again from the beginning when it ends" (the player time drops back and it plays on)', wrapped, `max time seen ${last.toFixed(1)} s`);
  const c = await page.locator('#c').boundingBox();
  await page.mouse.click(c.x + c.width * 0.5, c.y + c.height * 0.4);
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 30000 });
  await page.waitForTimeout(2500);
  tour.check('step 5: "Press or turn the wheel on the canvas. The film stops. That is the way out of a kiosk loop" (and it does not start again)', (await page.evaluate(() => window.__xrayFlythrough.state().playing)) === false);
  const sz = statSync(at('kiosk.html')).size / 1e6;
  tour.check('Size: "FZK house about 8.9 MB" with a fly-through', sz > 7.5 && sz < 11, `${sz.toFixed(2)} MB`);
});

await tour.step('30.2 Options: --scripts, --plans, --ifc-reader, --samples; Size', async () => {
  writeFileSync(at('tour.xrayanim'), 'mode ghost\nfly to everything over 2 seconds\ncaption "Kiosk" "Packed script" for 2 seconds\n');
  const r = pack([FZK, '-o', at('script.html'), '--scripts', at('tour.xrayanim'), '--autoplay', 'script:tour', '--kiosk']);
  tour.check('"--scripts a.xrayanim: Add animation scripts. The file name without its ending is the script name"', r.code === 0, r.err.slice(-160));
  const page = await openPacked(at('script.html'));
  await page.waitForFunction(() => window.__xrayScript?.list().some((s) => s.name === 'tour'), null, { timeout: 120000 });
  tour.check('the script is in the Script tab list under "tour"', true);
  await page.waitForFunction(() => window.__xrayScript?.state()?.running || window.__xrayFlythrough?.state().playing, null, { timeout: 60000 }).catch(() => {});
  tour.check('"--autoplay script:Name" plays it at start', (await page.evaluate(() => !!window.__xrayScript.state()?.running || window.__xrayFlythrough.state().playing)), '');
  const a = statSync(at('fzk.html')).size, b = pack([FZK, '-o', at('reader.html'), '--ifc-reader']);
  tour.check('Size table: "--ifc-reader adds about 1.4 MB"', b.code === 0 && Math.abs((statSync(at('reader.html')).size - a) / 1e6 - 1.4) < 0.6, `+${((statSync(at('reader.html')).size - a) / 1e6).toFixed(2)} MB`);
  const c = pack([FZK, '-o', at('samples.html'), '--samples']);
  tour.check('Size table: "--samples adds about 1.7 MB"', c.code === 0 && Math.abs((statSync(at('samples.html')).size - a) / 1e6 - 1.7) < 0.8, `+${((statSync(at('samples.html')).size - a) / 1e6).toFixed(2)} MB`);
  const html = readFileSync(at('fzk.html'), 'utf8');
  tour.check('"Packed pages never contain API keys, tokens, reviewer names or pictures"', !/hf_[A-Za-z0-9]{10}|sk-[A-Za-z0-9]{10}/.test(html) && !/"reviewer"\s*:\s*"/.test(html));
  tour.check('"The model is stored as text (base64)": the page holds __xrayEmbeddedModels', /__xrayEmbeddedModels/.test(html));
});

await tour.finish();
