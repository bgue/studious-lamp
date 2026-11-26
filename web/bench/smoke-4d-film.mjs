// Headless smoke for the film bar of the 4D tab (src/map4d/schedulePanel.ts) and "Open as script": ?model=fzk-haus-4d and the Sample Projects menu
// open the 4D tab with the bar in view at the top, Play starts the film, the bar stays while the tab scrolls, Open as script fills the Script tab with a
// script that compiles and that Run plays, the bar says what is missing without a schedule, a plain ?model= is unaffected, and the bar fits a phone.
// Usage: SMOKE_PORT=5850 XRAY_VITE_CACHE_DIR=/tmp/xray-vite-film node bench/smoke-4d-film.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5850);

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

const newPage = async (viewport, tag, query) => {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  page.setDefaultTimeout(90000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${tag}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[${tag} pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/${query}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForFunction('window.__xray4dSchedule && window.__xrayScript && window.__xrayFlythrough', null, { timeout: 60000 });
  return { ctx, page };
};
const linked = (page) => page.waitForFunction(() => window.__xray4dSchedule.links()?.links?.some((l) => l.status === 'accepted') && window.__xray4dSchedule.plan?.window !== null, null, { timeout: 180000 });
/** The bar's box against the viewport and the sidebar pane. */
const barBox = (page) => page.evaluate(() => {
  const b = document.querySelector('#dk-pane-4d [data-x4=film-bar]');
  const pane = document.getElementById('dk-pane-4d');
  if (!b) return null;
  const r = b.getBoundingClientRect();
  const p = pane.getBoundingClientRect();
  return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight, paneTop: p.top, paneBottom: p.bottom, scrollTop: pane.scrollTop, scrollH: pane.scrollHeight, paneH: pane.clientHeight, paneVisible: p.height > 0 };
});
const inView = (b) => !!b && b.h > 0 && b.top >= b.paneTop - 1 && b.bottom <= b.paneBottom + 1 && b.top >= 0 && b.bottom <= b.vh && b.left >= 0 && b.right <= b.vw + 1;


/** Issue pins and drawings: one of each on the model (the issues drawer is open, so the pins show), and what the overlay layers show now. */
const addIssueAndDrawing = (page) => page.evaluate(() => {
  const w = window.__xray.app.controller.model.elements.find((e) => e.globalId && /Wall/.test(e.ifcClass));
  window.__xrayBcf.createTopic({ title: 'Smoke pin', globalIds: [w.globalId], snapshot: false });
  window.__xrayIssues.open('issues');
  window.__xrayMarkup.create('Smoke drawing');
  window.__xrayMarkup.add({ kind: 'rect', fractions: { points: [[0.3, 0.3], [0.6, 0.55]], depth: 8 } });
});
const overlayState = (page) => page.evaluate(() => {
  const q = (l) => { const g = document.querySelector(`svg.xray-svg-overlay g[data-layer="${l}"]`); return g ? { n: g.childElementCount, shown: getComputedStyle(g).display !== 'none' } : { n: 0, shown: false }; };
  const pins = q('bcf-markup');
  const drawings = q('markup');
  return { pins: pins.n > 0 && pins.shown, pinsDrawn: pins.n, drawings: drawings.n > 0 && drawings.shown, drawingsDrawn: drawings.n, cls: document.documentElement.className };
});

try {
  let up = false;
  for (let i = 0; i < 100 && !up; i++) {
    try { up = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  if (!up) throw new Error('vite did not start:\n' + viteLog);
  browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ---------------------------------------------------------------- ?model=fzk-haus-4d
  const { ctx, page } = await newPage({ width: 1400, height: 900 }, 'desktop', '?model=fzk-haus-4d');
  await linked(page);
  const st = await page.evaluate(() => ({ model: window.__xray.app.modelName, tab: window.__xrayRightSidebar.state(), summary: window.__xray4dSchedule.summary()?.project }));
  check('?model=fzk-haus-4d loads FZK-Haus and the sample schedule', st.model === 'fzk-haus' && st.summary === 'FZK-HAUS', JSON.stringify(st));
  check('the right sidebar is open on the 4D tab', st.tab.tab === '4d' && !st.tab.collapsed, JSON.stringify(st.tab));
  await page.waitForSelector('#dk-pane-4d [data-x4=film-ready]', { state: 'visible' });
  const b0 = await barBox(page);
  check('the film bar is in view without scrolling', inView(b0) && b0.scrollTop === 0, JSON.stringify(b0));
  const labels = await page.locator('#dk-pane-4d [data-x4=film-bar] button:visible').allInnerTexts();
  check('the bar has Play, Pause, Stop, Record, Storyboard PDF and Open as script', ['Play', 'Pause', 'Stop', 'Record', 'Storyboard PDF', 'Open as script'].every((l) => labels.includes(l)), labels.join());
  check('the date slider is in the bar', await page.locator('#dk-pane-4d [data-x4=film-bar] input[data-x4=scrub]').isVisible());

  // sticky: the Film step fits the pane now (the 4D tab is in steps); the Link step, with the decided links, is the long one.
  // Scroll it to the bottom and the bar stays.
  await page.evaluate(() => window.__xray4dSchedule.step('link'));
  await page.waitForTimeout(300);
  await page.evaluate(() => { const p = document.getElementById('dk-pane-4d'); p.scrollTop = p.scrollHeight; });
  await page.waitForTimeout(300);
  const b1 = await barBox(page);
  const scrolls = b1.scrollH > b1.paneH + 50;
  check('the bar stays in view while the tab scrolls (Link step)', !scrolls || (b1.scrollTop > 50 && inView(b1) && Math.abs(b1.top - b1.paneTop) < 12), JSON.stringify({ scrolls, scrollTop: b1.scrollTop, top: b1.top, paneTop: b1.paneTop, scrollH: b1.scrollH, paneH: b1.paneH }));
  await page.evaluate(() => window.__xray4dSchedule.step('film'));
  // open('link') opens and scrolls to the section; open('play') returns to the top
  await page.evaluate(() => { window.__xray4dSchedule.open('link'); });
  await page.waitForTimeout(300);
  const link = await page.evaluate(() => { const d = document.querySelector('#dk-pane-4d details[data-sec=link]'); const r = d.getBoundingClientRect(); const p = document.getElementById('dk-pane-4d').getBoundingClientRect(); return { open: d.open, top: r.top - p.top }; });
  check('open(section) opens the section and scrolls it into view', link.open && link.top >= 0 && link.top < 800, JSON.stringify(link));
  await page.evaluate(() => { window.__xray4dSchedule.open('play'); });
  await page.waitForTimeout(300);
  check('open(play) scrolls back to the film bar', (await barBox(page)).scrollTop === 0);

  // Play
  await page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Play$/ }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.playing === true, null, { timeout: 120000 });
  check('Play in the bar starts the film', true);
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 0.5 || !window.__xray4dSchedule.playing, null, { timeout: 240000 });
  await page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Stop$/ }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.playing === false);
  check('Stop in the bar stops it', true);

  // issue pins and drawings: hidden while the film plays, back after Stop; the style setting keeps them
  await addIssueAndDrawing(page);
  await page.waitForFunction(() => document.querySelector('svg.xray-svg-overlay g[data-layer="bcf-markup"]')?.childElementCount > 0 && document.querySelector('svg.xray-svg-overlay g[data-layer="markup"]')?.childElementCount > 0, null, { timeout: 60000 });
  const ov0 = await overlayState(page);
  check('before the film: the issue pin and the drawing are on screen', ov0.pins && ov0.drawings && !/xray-hide/.test(ov0.cls), JSON.stringify(ov0));
  await page.evaluate(() => window.__xray4dSchedule.step('film'));
  await page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Play$/ }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.playing === true && window.__xrayFlythrough.state().time > 0.5, null, { timeout: 240000 });
  const ov1 = await overlayState(page);
  check('during the film the pins and the drawings are hidden', !ov1.pins && !ov1.drawings && ov1.pinsDrawn > 0, JSON.stringify(ov1));
  await page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Stop$/ }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.playing === false);
  await page.waitForTimeout(400);
  const ov2 = await overlayState(page);
  check('after Stop they are back, exactly as before', ov2.pins && ov2.drawings && ov2.cls === ov0.cls && ov2.pinsDrawn === ov0.pinsDrawn && ov2.drawingsDrawn === ov0.drawingsDrawn, JSON.stringify(ov2));

  // the Style section: each floor apart, fade in, issues and drawings
  await page.evaluate(() => window.__xray4dSchedule.open('style'));
  await page.waitForTimeout(300);
  const ui = await page.evaluate(() => {
    const q = (k) => document.querySelector(`#dk-pane-4d [data-style="${k}"]`);
    return { explode: q('explode')?.value, options: [...(q('explode')?.options ?? [])].map((o) => o.textContent), fadeAuto: q('fade auto')?.checked, fadeDisabled: q('fade in')?.disabled, issues: q('issues in film')?.checked, labels: [...document.querySelectorAll('#dk-pane-4d .x4-grid > label')].map((l) => l.textContent) };
  });
  check('Style: the sample asks for "Each floor apart"', ui.explode === 'floor' && ui.options.includes('Each floor apart'), JSON.stringify(ui));
  check('Style: "Fade in (s)" is on auto and "Issues and drawings in the film" is off', ui.fadeAuto === true && ui.fadeDisabled === true && ui.issues === false && ui.labels.includes('Fade in (s)') && ui.labels.includes('Issues and drawings in the film'), JSON.stringify(ui));
  await page.locator('#dk-pane-4d [data-style="fade auto"]').uncheck();
  await page.locator('#dk-pane-4d [data-style="fade in"]').fill('1.5');
  await page.locator('#dk-pane-4d [data-style="fade in"]').dispatchEvent('change');
  await page.locator('#dk-pane-4d [data-style="issues in film"]').check();
  const cfg = await page.evaluate(() => { const c = window.__xray4dSchedule.config(); return c?.style ? { fadeIn: c.style.fadeIn, issuesInFilm: c.style.issuesInFilm, explode: c.style.explode } : null; });
  check('Style: the fade time and the issues setting go into the configuration (the .4d.json)', cfg && cfg.fadeIn === 1.5 && cfg.issuesInFilm === true && cfg.explode === 'floor', JSON.stringify(cfg));
  await page.evaluate(() => window.__xray4dSchedule.open('play'));
  await page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Play$/ }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.playing === true && window.__xrayFlythrough.state().time > 0.5, null, { timeout: 240000 });
  const ov3 = await overlayState(page);
  check('with "Issues and drawings in the film" on, the pins and the drawings stay during the film', ov3.pins && ov3.drawings, JSON.stringify(ov3));
  await page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Stop$/ }).click();
  await page.waitForFunction(() => window.__xray4dSchedule.playing === false);
  await page.evaluate(() => window.__xray4dSchedule.open('style'));
  await page.locator('#dk-pane-4d [data-style="issues in film"]').uncheck();
  await page.locator('#dk-pane-4d [data-style="fade auto"]').check();
  await page.evaluate(() => window.__xray4dSchedule.open('play'));

  // legend and strip: the switches in Style, the picture of the film with both, the Storyboard PDF
  await page.evaluate(() => window.__xray4dSchedule.open('style'));
  await page.waitForTimeout(300);
  const sw = await page.evaluate(() => ({ legend: document.querySelector('#dk-pane-4d [data-style="legend"]')?.checked, strip: document.querySelector('#dk-pane-4d [data-style="strip"]')?.checked }));
  check('Style has the Colour legend and Schedule strip switches, on by default', sw.legend === true && sw.strip === true, JSON.stringify(sw));
  await page.locator('#dk-pane-4d [data-style="strip"]').uncheck();
  await page.locator('#dk-pane-4d [data-style="legend"]').uncheck();
  const off = await page.evaluate(() => ({ strip: window.__xray4dSchedule.config().style.strip, legend: window.__xray4dSchedule.config().style.legend }));
  check('switching them off writes style.strip and style.legend "off" into the configuration', off.strip === 'off' && off.legend === 'off', JSON.stringify(off));
  await page.evaluate(async () => { await window.__xray4dSchedule.seekDate(window.__xray4dSchedule.plan().window.from + 40 * 86400000); });
  await page.waitForFunction(() => !!window.__xrayFlythrough.hudState().last?.fourd?.date, null, { timeout: 240000, polling: 300 });
  await page.waitForTimeout(800);
  const hudOff = await page.evaluate(() => { const f = window.__xrayFlythrough.hudState().last?.fourd; return { legend: !!f?.legend, strip: !!f?.strip, date: f?.date ?? null }; });
  check('with both off the film draws neither (but still the date)', hudOff.date && !hudOff.legend && !hudOff.strip, JSON.stringify(hudOff));
  await page.locator('#dk-pane-4d [data-style="strip"]').check();
  await page.locator('#dk-pane-4d [data-style="legend"]').check();
  await page.evaluate(() => window.__xray4dSchedule.open('play'));
  await page.evaluate(async () => { window.__xray4dSchedule.stop(); await window.__xray4dSchedule.seekDate(window.__xray4dSchedule.plan().window.from + 55 * 86400000); });
  await page.waitForTimeout(2500);
  const hudOn = await page.evaluate(() => { const f = window.__xrayFlythrough.hudState().last?.fourd; return { legend: f?.legend?.entries ?? null, strip: f?.strip ?? null }; });
  check('back on: the film draws the legend and the strip', !!hudOn.legend && hudOn.legend.length >= 4 && !!hudOn.strip && hudOn.strip.rows >= 2, JSON.stringify(hudOn));
  await page.screenshot({ path: resolve(root, 'bench/4d-legend-strip.png') });
  await page.evaluate(() => window.__xray4dSchedule.stop());
  await page.waitForFunction(() => window.__xray4dSchedule.playing === false);

  const boardBtn = page.locator('#dk-pane-4d [data-x4=film-bar] button', { hasText: /^Storyboard PDF$/ });
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 900000 }), boardBtn.click()]);
  const pdfPath = resolve(root, 'bench', '.storyboard-smoke.pdf');
  await dl.saveAs(pdfPath);
  const pdfLib = createRequire(import.meta.url)(resolve(root, 'node_modules/pdf-lib'));
  const { readFileSync, rmSync } = await import('node:fs');
  const bytes = readFileSync(pdfPath);
  const doc = await pdfLib.PDFDocument.load(bytes);
  const sb = await page.evaluate(() => { const p = window.__xray4dSchedule.plan(); return { last: window.__xray4dSchedule.lastStoryboard, from: p.window.from, to: p.window.to }; });
  const weeks = Math.floor((sb.to - sb.from) / (7 * 86400000)) + 1 + ((sb.to - sb.from) % (7 * 86400000) > 0 ? 1 : 0);
  console.log(`INFO storyboard ${JSON.stringify(sb.last)} expected weekly frames ${weeks}`);
  check('Storyboard PDF downloads a PDF of one weekly frame per page slot (A4, 3 columns, 6 per page)', String.fromCharCode(...bytes.slice(0, 4)) === '%PDF' && sb.last?.frames === weeks && doc.getPageCount() === Math.ceil(weeks / 6) && sb.last.pages === doc.getPageCount(), JSON.stringify({ pages: doc.getPageCount(), weeks, last: sb.last }));
  check('the storyboard pages are landscape and the file is small (JPEG frames)', doc.getPage(0).getWidth() > doc.getPage(0).getHeight() && bytes.length < weeks * 250000, `${bytes.length} bytes`);
  const png = await page.evaluate(async (b64) => {
    const pdfjs = await import('/node_modules/pdfjs-dist/build/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = '/node_modules/pdfjs-dist/build/pdf.worker.min.mjs';
    const data = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const d = await pdfjs.getDocument({ data }).promise;
    const pg = await d.getPage(1);
    const vp = pg.getViewport({ scale: 1.6 });
    const c = document.createElement('canvas');
    c.width = Math.round(vp.width); c.height = Math.round(vp.height);
    await pg.render({ canvasContext: c.getContext('2d'), viewport: vp }).promise;
    const text = (await pg.getTextContent()).items.map((i) => i.str).join(' ');
    return { url: c.toDataURL('image/png'), text };
  }, bytes.toString('base64')).catch((e) => ({ error: String(e) }));
  if (png.url) writeFileSync(resolve(root, 'bench/4d-storyboard-p1.png'), Buffer.from(png.url.split(',')[1], 'base64'));
  check('page 1 reads back with the title block, "Page 1 of N", a date caption and the legend', !!png.text && /4D storyboard/.test(png.text) && new RegExp(`Page 1 of ${doc.getPageCount()}`).test(png.text) && /\d{4}-\d\d-\d\d\s+Week \d+/.test(png.text) && /Trades/.test(png.text) && /Active/.test(png.text), png.error ?? png.text?.slice(0, 200));
  rmSync(pdfPath, { force: true });

  // Open as script
  await page.locator('#dk-pane-4d [data-x4=film-script]').click();
  await page.waitForFunction(() => window.__xrayRightSidebar.state().tab === 'script' && /Script made from the 4D film/.test(window.__xrayScript.state()?.status ?? ''), null, { timeout: 120000 });
  const sc = await page.evaluate(() => { const s = window.__xrayScript; const t = s.text(); const c = s.compile(t); return { state: s.state(), len: t.length, lines: t.split('\n').length, schedule: /schedule "[^"]+"/.exec(t)?.[0], errors: c.errors.filter((e) => e.severity === 'error').length, fly: (t.match(/^\s*(fly to|orbit)/gm) ?? []).length, still: /camera stays put/.test(t), plans: window.__xray4d.plans(), saved: s.list().length }; });
  check('the Script tab opens with the film as a script that compiles', sc.errors === 0 && sc.state.errors === 0 && sc.schedule && sc.fly > 3 && !sc.still && sc.len > 500, JSON.stringify({ ...sc, state: undefined }));
  const floors = await page.evaluate(() => { const t = window.__xrayScript.text(); return { explode: (t.match(/^\s*explode storeys/gm) ?? []).length, collapse: (t.match(/^\s*collapse over/gm) ?? []).length, floorNotes: (t.match(/^-- .*floor "[^"]+": the work moves onto it/gm) ?? []).map((l) => /floor "([^"]+)"/.exec(l)[1]), caps: (t.match(/caption "(Erdgeschoss|Dachgeschoss)"/g) ?? []).length }; });
  check('the film script has an explode and a collapse per floor (ground floor and roof storey), with the notes and a caption naming the floor', floors.explode >= 2 && floors.collapse === floors.explode && floors.floorNotes.includes('Erdgeschoss') && floors.floorNotes.includes('Dachgeschoss') && floors.caps >= 2, JSON.stringify(floors));
  check('the status says how many lines were made', new RegExp(`Script made from the 4D film: ${sc.lines} lines\\. Press Run\\.`).test(sc.state.status) || /Script made from the 4D film: \d+ lines\. Press Run\./.test(sc.state.status), sc.state.status);
  check('the script is named after the schedule, registered as a plan, and not saved yet', sc.state.name !== '' && sc.plans.some((n) => sc.schedule.includes(`"${n}"`)) && sc.state.dirty !== undefined && sc.saved === 0, `${sc.state.name} ${sc.plans.join()}`);
  await page.locator('#dk-pane-script button', { hasText: /^Run$/ }).click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing === true, null, { timeout: 120000 });
  const live = await page.evaluate(() => ({ script: window.__xrayScript.state().running, flow: window.__xrayFlythrough.state().playing }));
  check('Run plays the film from the script', live.flow === true, JSON.stringify(live));
  await page.evaluate(() => window.__xrayScript.stop());
  await ctx.close();

  // ---------------------------------------------------------------- the Sample Projects menu, from another model
  const menu = await newPage({ width: 1400, height: 900 }, 'menu', '?model=building');
  const none = await menu.page.evaluate(() => ({ model: window.__xray.app.modelName, summary: window.__xray4dSchedule.summary() }));
  check('a plain ?model=building is unaffected: no schedule', none.model === 'building' && none.summary === null, JSON.stringify(none));
  await menu.page.evaluate(() => window.__xray4dSchedule.open());
  await menu.page.waitForSelector('#dk-pane-4d [data-x4=film-missing]', { state: 'visible' });
  const miss = await menu.page.evaluate(() => ({ text: document.querySelector('#dk-pane-4d [data-x4=film-need]').textContent, ready: getComputedStyle(document.querySelector('#dk-pane-4d [data-x4=film-ready]')).display, btn: [...document.querySelectorAll('#dk-pane-4d [data-x4=film-missing] button')].filter((b) => b.offsetParent).map((b) => b.textContent) }));
  check('without a schedule the bar says Open a schedule, with its button', /Open a schedule/.test(miss.text) && miss.ready === 'none' && miss.btn.join() === 'Open schedule', JSON.stringify(miss));
  await menu.page.evaluate(() => { const p = document.getElementById('dk-pane-4d'); p.scrollTop = p.scrollHeight; });
  await menu.page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'model').setValue('fzk-haus-4d'));
  await menu.page.waitForFunction(() => window.__xray.app.modelName === 'fzk-haus' && window.__xray4dSchedule.links()?.links?.some((l) => l.status === 'accepted'), null, { timeout: 180000 });
  await menu.page.waitForSelector('#dk-pane-4d [data-x4=film-ready]', { state: 'visible' });
  await menu.page.waitForTimeout(500);
  const bm = await barBox(menu.page);
  check('Sample Projects -> FZK-Haus 4D opens the 4D tab with the bar in view at the top', inView(bm) && bm.scrollTop === 0, JSON.stringify(bm));
  const plural = await menu.page.evaluate(() => window.__xray4dSchedule.open('link') ?? document.querySelector('#dk-pane-4d').textContent.match(/\d+ activit\w* without elements/)?.[0]);
  check('the unlinked-activities line has no "activitys"', !/activitys/.test(await menu.page.locator('#dk-pane-4d').innerText()), String(plural));
  await menu.ctx.close();

  // ---------------------------------------------------------------- phone
  const ph = await newPage({ width: 390, height: 800 }, 'phone', '?model=fzk-haus-4d');
  await linked(ph.page);
  await ph.page.waitForSelector('#dk-pane-4d [data-x4=film-ready]', { state: 'visible' });
  await ph.page.waitForTimeout(500);
  const bp = await barBox(ph.page);
  const over = await ph.page.evaluate(() => [...document.querySelectorAll('#dk-pane-4d [data-x4=film-bar] button, #dk-pane-4d [data-x4=film-bar] input')].filter((e) => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > innerWidth + 1).length);
  check('on a 390 px phone the bar is in view and fits', inView(bp) && bp.w <= 390 && over === 0 && (await ph.page.evaluate(() => document.documentElement.scrollWidth)) <= 391, JSON.stringify({ ...bp, over }));
  await ph.ctx.close();

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
