// Headless smoke test for the animation script editor (docs-features/animation-script.md): the Script tab of the right sidebar, typing
// a script, errors with line numbers that jump to the line, the examples, saving per model and reloading, export and import of a
// .xrayanim file, that scripts stay out of the params document, the line highlight with a fake player, "player not available" when
// no player is registered, and the phone layout (bottom sheet).
// Screenshots: bench/animation-script.png (desktop), bench/animation-script-phone.png.
// Usage: SMOKE_PORT=5810 XRAY_VITE_CACHE_DIR=/tmp/animscript-vite-cache node bench/smoke-animation-script.mjs    (SMOKE_REUSE=1 uses a server already on that port)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5810);
const base = `http://127.0.0.1:${port}`;

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

let vite = null;
let viteLog = '';
if (!process.env.SMOKE_REUSE) {
  vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  vite.stdout.on('data', (d) => (viteLog += d));
  vite.stderr.on('data', (d) => (viteLog += d));
}
async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`${base}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok: !!ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}
const errors = [];
function watch(page, label) {
  page.setDefaultTimeout(120000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`${label}: ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`${label}: pageerror ${e.message}`));
}
async function shot(page, file) {
  try { await page.screenshot({ path: resolve(here, file), timeout: 120000 }); } catch (e) { console.log(`(screenshot ${file} skipped: ${String(e.message ?? e).split('\n')[0]})`); }
}
async function ready(page) {
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000, polling: 500 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForFunction('!!window.__xrayScript && !!window.__xrayRightSidebar', null, { timeout: 60000, polling: 500 });
}
const openTab = async (page) => {
  await page.evaluate(() => window.__xrayRightSidebar.open('script'));
  await page.waitForSelector('[data-script-text]', { state: 'visible' });
};
const setScript = async (page, text) => {
  await page.fill('[data-script-text]', text);
  await page.waitForTimeout(400); // the compile is debounced
};
const errRows = (page) => page.evaluate(() => [...document.querySelectorAll('[data-script-errors] .as-err')].map((b) => ({ sev: b.classList.contains('warning') ? 'warning' : 'error', text: b.textContent, line: Number(b.dataset.line) })));
const state = (page) => page.evaluate(() => window.__xrayScript.state());

let failed = false;
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  watch(page, 'desktop');
  await page.goto(`${base}/?model=process-plant`);
  await ready(page);
  await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('xray.anim.')) localStorage.removeItem(k); });

  // ---- the tab
  const tabs = await page.locator('#dock .dk-tab').allTextContents();
  check('the right sidebar has a Script tab after the built-in tabs', tabs.includes('Script') && tabs.indexOf('Script') > tabs.indexOf('Parameters'), tabs.join(', '));
  await openTab(page);
  const w = await page.evaluate(() => document.getElementById('dock').getBoundingClientRect().width);
  check('the Script tab asks for 420 px', Math.abs(w - 420) < 8, `${Math.round(w)} px`);
  check('the tab button is the active one and has a help key', await page.evaluate(() => { const b = document.querySelector('#dock .dk-tab.active'); return b?.textContent === 'Script' && !!b.getAttribute('data-help-key'); }));
  const keys = await page.evaluate(() => [...document.querySelectorAll('[data-script-panel] [data-help-key]')].map((e) => e.getAttribute('data-help-key')));
  const missing = await page.evaluate((ks) => ks.filter((k) => !window.__xrayHelp.lookup(k)), keys);
  check('every control of the tab has a help key with a text', keys.length >= 12 && missing.length === 0, `${keys.length} keys, missing: ${missing.join(', ') || 'none'}`);

  // ---- typing, errors, jumping
  const bad = 'mode ghost\nfly to everything over 3 seconds\nshow everything fade over 2 seconds\nflyy to class IfcPump';
  await setScript(page, bad);
  let rows = await errRows(page);
  check('errors are listed with their line numbers', rows.filter((r) => r.sev === 'error').map((r) => r.line).join() === '3,4', JSON.stringify(rows.map((r) => `${r.sev} ${r.line}`)));
  check('an error row names line and column and gives a hint', /Line 3, column 17/.test(rows[0]?.text ?? '') && /Did you mean `fading`/.test(rows[0]?.text ?? ''), rows[0]?.text);
  check('the gutter marks the bad lines and the tab shows the error count', await page.evaluate(() => document.querySelectorAll('.as-gn.error').length === 2 && document.querySelector('#dock .dk-tab.active .dk-badge, #dock .dk-tab.active [class*=badge]')?.textContent === '2'));
  check('the bad words are underlined in the code', await page.evaluate(() => document.querySelectorAll('.as-hl .as-mark-error').length >= 2));
  await page.locator('[data-script-errors] .as-err').first().click();
  const sel = await page.evaluate(() => { const t = document.querySelector('[data-script-text]'); return { s: t.selectionStart, e: t.selectionEnd, text: t.value.slice(t.selectionStart, t.selectionEnd), focus: document.activeElement === t }; });
  check('a click on an error selects the wrong text in the editor', sel.focus && sel.text === 'fade', JSON.stringify(sel));
  check('Run with errors says where and does not play', await (async () => {
    await page.click('[data-act=run]');
    const s = await state(page);
    return /Line 3, column 17/.test(s.status) && !s.running;
  })());

  // auto-indent
  await setScript(page, '');
  await page.focus('[data-script-text]');
  await page.keyboard.type('together\nwait 1\n');
  const typed = await page.evaluate(() => document.querySelector('[data-script-text]').value);
  check('Enter keeps the indentation and adds a level after together', typed === 'together\n  wait 1\n  ', JSON.stringify(typed));

  // ---- a good script
  const good = 'mode ghost\nfly to everything over 3 seconds\nshow everything fading over 2 seconds\ncaption "Hello" for 2 seconds\nset cinematic.glowStrength to 1 over 1 seconds\nrepeat for each element in class IfcPump\n  select it\nend repeat';
  await setScript(page, good);
  rows = await errRows(page);
  let st = await state(page);
  check('a good script has no errors, a status with cues and the duration', st.errors === 0 && st.cues >= 8 && Math.abs(st.duration - 8) < 0.01 && /No errors/.test(st.status), `${JSON.stringify(rows.map((r) => r.text))} ${st.status}`);
  check('repeat for each element expanded against the model (4 pumps)', await page.evaluate(() => window.__xrayScript.compile('repeat for each element in class IfcPump\n select it\nend repeat').score?.cues.length === 4));
  const c = await page.evaluate(() => window.__xrayScript.compile('fly to class IfcPump over 3 seconds\nset xray.alphaMx to 3'));
  check('window.__xrayScript.compile returns the score and the warnings (setting names are checked against the model)', c.score?.cues[0]?.line === 1 && c.errors.some((e) => e.severity === 'warning' && /alphaMx/.test(e.message)), JSON.stringify(c.errors.map((e) => e.message)));
  const paths = await page.evaluate(() => window.__xrayScript.paramPaths());
  check('the settings paths of the params document are listed', paths.length > 20 && paths.some((p) => p.startsWith('cinematic.')), `${paths.length} paths`);

  // ---- Run without a player
  const hasPlayer = await page.evaluate(async () => !!(await import('/src/anim/score.ts')).getScorePlayer());
  await page.click('[data-act=run]');
  st = await state(page);
  if (!hasPlayer) check('Run says the player is not available, cleanly', /not available/.test(st.status) && !st.running, st.status);
  else check('Run plays through the real player', st.running || /Finished|Playing/.test(st.status), st.status);

  // ---- a script on the real player (after the merge with the fly-through work). Times are score time: a software renderer draws
  // slowly and the player then plays slower than real time, so the checks wait on the player's clock, not on the wall clock.
  if (hasPlayer) {
    await page.evaluate(() => window.__xrayScript.stop());
    await page.waitForTimeout(400);
    const snap = () => page.evaluate(() => {
      const a = window.__xray.app;
      const r = a.renderer;
      const cap = document.querySelector('.fl-caption');
      const fs = window.__xrayFlythrough?.state?.() ?? {};
      return { t: fs.time ?? 0, playing: !!fs.playing, cam: [r.camera.position.x, r.camera.position.y, r.camera.position.z], hidden: a.settings.overrides.userHides.size, cap: !!cap && !cap.hidden, glow: window.__cinematic.cfg.glowStrength };
    });
    const until = async (pred, ms = 180000) => { const t0 = Date.now(); let s = await snap(); while (!pred(s) && Date.now() - t0 < ms) { await page.waitForTimeout(150); s = await snap(); } return s; };
    const keepText = await page.evaluate(() => window.__xrayScript.text());
    const before = await snap();
    const script = 'fly to class IfcPump over 1 second\ntogether\n  caption "Pumps" for 1 second\n  set cinematic.glowStrength to 1.2 over 1 second\n  hide where class = IfcSlab fading over 1 second\nend together\nwait 1';
    const run = await page.evaluate((t) => window.__xrayScript.run(t), script);
    const mid = await until((s) => s.t >= 0.7);
    const moved = Math.hypot(mid.cam[0] - before.cam[0], mid.cam[1] - before.cam[1], mid.cam[2] - before.cam[2]);
    check('real player: the script plays and the camera flies to the pumps', run.ok && moved > 1, `${moved.toFixed(1)} m at t=${mid.t.toFixed(2)}`);
    const capS = await until((s) => s.t >= 1.3);
    check('real player: the caption shows during its time and the setting blends', capS.cap && capS.glow > before.glow && capS.glow < 1.2, JSON.stringify({ cap: capS.cap, glow: capS.glow, t: capS.t }));
    const hid = await until((s) => s.t >= 2.2 || !s.playing);
    check('real player: the slabs are hidden once their fade is over', hid.hidden > 100, `${hid.hidden} hidden at t=${hid.t.toFixed(2)}`);
    const end = await until((s) => !s.playing);
    await page.waitForTimeout(500);
    const back = await snap();
    const home = Math.hypot(back.cam[0] - before.cam[0], back.cam[1] - before.cam[1], back.cam[2] - before.cam[2]);
    check('real player: at the end the camera, the hidden elements, the setting and the caption are put back', !end.playing && home < 0.05 && back.hidden === before.hidden && back.glow === before.glow && !back.cap, JSON.stringify({ home, hidden: back.hidden, glow: back.glow, cap: back.cap }));
    await page.evaluate((t) => window.__xrayScript.setText(t), keepText); // run(text) put its script in the editor
  }

  // ---- the line highlight with a fake player
  await page.evaluate(async () => {
    const m = await import('/src/anim/score.ts');
    window.__fakeCue = null;
    const fake = {
      playing: false, paused: false, time: 0,
      play(score, opts) { this.playing = true; this.opts = opts; this.score = score; return true; },
      stop() { this.playing = false; this.opts?.onEnd?.(); }, pause() { this.paused = true; }, resume() { this.paused = false; }, seek() {},
    };
    window.__fake = fake;
    m.setScorePlayer(fake);
  });
  await page.click('[data-act=run]');
  await page.evaluate(() => window.__fake.opts.onCue(window.__fake.score.cues[1], 1));
  await page.waitForTimeout(100);
  const play = await page.evaluate(() => ({ hl: [...document.querySelectorAll('.as-hl .as-l')].findIndex((d) => d.classList.contains('play')) + 1, gn: document.querySelector('.as-gn.play')?.dataset.line, st: window.__xrayScript.state() }));
  check('the line of the playing cue is highlighted in the code and the gutter', play.hl === 2 && play.gn === '2' && play.st.playingLine === 2 && play.st.running, JSON.stringify(play.st));
  check('Pause and Stop are enabled while playing', await page.evaluate(() => !document.querySelector('[data-act=pause]').disabled && !document.querySelector('[data-act=stop]').disabled));
  await page.click('[data-act=pause]');
  check('Pause asks the player to pause and the button turns into Resume', await page.evaluate(() => window.__fake.paused && document.querySelector('[data-act=pause]').textContent === 'Resume'));
  await page.click('[data-act=pause]');
  await page.click('[data-act=stop]');
  st = await state(page);
  check('Stop stops the player and clears the highlight', st.playingLine === null && !st.running && await page.evaluate(() => !window.__fake.playing && !document.querySelector('.as-l.play')));
  await page.click('[data-act=run]');
  await page.evaluate(() => { window.__fake.playing = false; window.__fake.opts.onEnd(); });
  st = await state(page);
  check('the end of the score clears the highlight and says Finished', st.playingLine === null && /Finished/.test(st.status), st.status);
  await page.evaluate(async () => (await import('/src/anim/score.ts')).setScorePlayer(null));

  // ---- examples
  const ex = await page.evaluate(() => window.__xrayScript.examples());
  check('there are 3 or 4 examples', ex.length >= 3 && ex.length <= 4, ex.map((e) => e.title).join(' | '));
  for (let i = 0; i < ex.length; i++) {
    await page.click('[data-act=examples]');
    await page.waitForSelector('.xm-menu');
    const items = await page.locator('.xm-menu button').allTextContents();
    if (i === 0) check('the Examples menu lists the examples with help keys', items.join('|') === ex.map((e) => e.title).join('|') && (await page.locator('.xm-menu button[data-help-key]').count()) === ex.length, items.join(' | '));
    await page.locator('.xm-menu button').nth(i).click();
    await page.waitForTimeout(400);
    const s = await state(page);
    const text = await page.evaluate(() => window.__xrayScript.text());
    check(`example "${ex[i].title}" loads and compiles without errors`, text.length > 100 && s.errors === 0 && s.cues > 3 && s.name === ex[i].title, `${s.cues} cues, ${s.duration}s, ${s.errors} errors, ${s.warnings} warnings`);
  }
  await shot(page, 'animation-script.png');

  // ---- save, reload, per model
  const marker = `-- smoke marker ${Date.now()}\nmode glow\nwait 1`;
  await setScript(page, marker);
  await page.fill('.as-name', 'Smoke script');
  await page.click('[data-act=save]');
  check('Save stores the script and the list shows it', await page.evaluate(() => window.__xrayScript.list().some((s) => s.name === 'Smoke script') && [...document.querySelectorAll('.as-saved option')].some((o) => o.textContent === 'Smoke script')));
  const keyUsed = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('xray.anim.')));
  check('the scripts are stored under one key per model', keyUsed.length === 1 && /\|\d+\|/.test(keyUsed[0]), keyUsed.join());
  await page.waitForTimeout(800); // the draft is stored after a short pause
  await page.reload();
  await ready(page);
  await openTab(page);
  const after = await page.evaluate(() => ({ text: window.__xrayScript.text(), name: document.querySelector('.as-name').value, list: window.__xrayScript.list().map((s) => s.name) }));
  check('after a reload the draft and the saved script are back', after.text === marker && after.name === 'Smoke script' && after.list.includes('Smoke script'), JSON.stringify(after.list));
  await setScript(page, 'wait 9');
  await page.selectOption('.as-saved', 'Smoke script');
  await page.waitForTimeout(300);
  check('choosing a saved script loads its text', (await page.evaluate(() => window.__xrayScript.text())) === marker);
  // the script text is in no params document, share link or view
  const leak = await page.evaluate(() => {
    const p = JSON.stringify(window.__xrayParams.collect());
    const share = window.__xrayParams.shareUrl ? String(window.__xrayParams.shareUrl()) : '';
    const views = JSON.stringify(window.__xrayViews?.exportJson?.() ?? '');
    const preset = JSON.stringify(window.__xrayPresets?.exportJson?.(true) ?? '');
    return { p: p.includes('smoke marker'), share: share.includes('smoke'), views: views.includes('smoke marker'), preset: preset.includes('smoke marker'), anim: p.includes('xray.anim') };
  });
  check('the script is not in the params document, the share link, the saved views or the presets', !leak.p && !leak.share && !leak.views && !leak.preset && !leak.anim, JSON.stringify(leak));

  // ---- export and import
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('[data-act=export]')]);
  const exportPath = join(mkdtempSync(join(tmpdir(), 'xray-anim-')), dl.suggestedFilename());
  await dl.saveAs(exportPath);
  check('Export downloads Smoke script.xrayanim with the script text', dl.suggestedFilename() === 'Smoke script.xrayanim' && readFileSync(exportPath, 'utf8') === `${marker}\n`, dl.suggestedFilename());
  const importPath = join(mkdtempSync(join(tmpdir(), 'xray-anim-in-')), 'Pump tour.xrayanim');
  writeFileSync(importPath, 'mode radiograph\r\nfly to class IfcPump over 2 seconds\r\n');
  await page.setInputFiles('[data-script-file]', importPath);
  await page.waitForTimeout(500);
  const imp = await page.evaluate(() => ({ text: window.__xrayScript.text(), name: document.querySelector('.as-name').value, st: window.__xrayScript.state() }));
  check('Import reads a .xrayanim file into the editor with its name', imp.text === 'mode radiograph\nfly to class IfcPump over 2 seconds\n' && imp.name === 'Pump tour' && imp.st.errors === 0, JSON.stringify(imp.name));
  await page.click('[data-act=examples]'); await page.keyboard.press('Escape');

  // ---- delete (two clicks)
  await page.selectOption('.as-saved', 'Smoke script');
  await page.waitForTimeout(200);
  await page.click('[data-act=delete]');
  check('Delete asks again before it removes', await page.evaluate(() => window.__xrayScript.list().some((s) => s.name === 'Smoke script') && /again/.test(document.querySelector('[data-act=delete]').textContent)));
  await page.click('[data-act=delete]');
  check('a second click removes the saved script', await page.evaluate(() => !window.__xrayScript.list().some((s) => s.name === 'Smoke script')));

  // ---- the reference
  await page.locator('[data-script-reference] summary').click();
  const ref = await page.evaluate(() => ({ items: document.querySelectorAll('[data-script-reference] [data-statement]').length, hasFading: /fading over N seconds/.test(document.querySelector('[data-script-reference]').textContent) }));
  check('the statement reference lists every statement', ref.items === 19 && ref.hasFading, `${ref.items} statements`);
  await setScript(page, '');
  await page.click('[data-insert=wait]');
  check('Insert example adds the example to the editor', (await page.evaluate(() => window.__xrayScript.text())) === 'wait 1.5 seconds\n');

  // ---- phone
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(600);
  await page.evaluate(() => {
    // this page was resized from a desktop width: only one sidebar stays open on a phone
    if (!document.body.classList.contains('sb-collapsed')) document.querySelector('.sb-toggle')?.click();
    window.__xrayRightSidebar.open('script');
  });
  await page.waitForTimeout(500);
  await setScript(page, good);
  await page.evaluate(() => { const p = document.querySelector('#dock .dk-pane[data-pane=script]'); if (p) p.scrollTop = 0; });
  const phone = await page.evaluate(() => {
    const dock = document.getElementById('dock').getBoundingClientRect();
    const root = document.querySelector('[data-script-panel]');
    const rr = root.getBoundingClientRect();
    const over = [...root.querySelectorAll('button, input, select, .as-editor')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > dock.right + 1 || r.left < dock.left - 1); }).length;
    const btn = document.querySelector('[data-act=run]').getBoundingClientRect();
    return { state: window.__xrayRightSidebar.state(), dockW: Math.round(dock.width), dockTop: Math.round(dock.top), rootW: Math.round(rr.width), over, scroll: document.documentElement.scrollWidth <= window.innerWidth, runH: Math.round(btn.height), fs: getComputedStyle(document.querySelector('[data-script-text]')).fontSize };
  });
  check('phone: the Script tab is in the bottom sheet and fills the width without overflow', phone.state.phone && phone.state.tab === 'script' && phone.dockW >= 340 && phone.over === 0 && phone.scroll, JSON.stringify(phone));
  check('phone: large buttons and 16 px text', phone.runH >= 36 && phone.fs === '16px', `${phone.runH}px, ${phone.fs}`);
  const align = await page.evaluate(() => { const ta = document.querySelector('[data-script-text]'); const l = document.querySelectorAll('.as-hl .as-l'); return { n: l.length, lines: ta.value.split('\n').length, h: l[0]?.getBoundingClientRect().height }; });
  check('phone: the coloured copy has one 20 px row per line', align.n === align.lines && Math.abs(align.h - 20) < 0.5, JSON.stringify(align));
  await shot(page, 'animation-script-phone.png');
  await ctx.close();
} catch (e) {
  failed = true;
  console.error(e);
} finally {
  try { await browser?.close(); } catch { /* ignore */ }
  if (vite) vite.kill();
}
check('no console errors', errors.length === 0, errors.slice(0, 5).join(' || '));
const bad = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - bad.length}/${checks.length} checks passed`);
process.exit(failed || bad.length ? 1 : 0);
