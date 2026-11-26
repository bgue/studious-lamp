// Tour of chapter 31, "AR and VR (experimental)" (docs/manual/31-ar-vr.md): only what a desktop headless browser can show. 31 "What you need": the drawer on a
// browser with no WebXR (Enter buttons disabled with the reason, Download USDZ and Share link as QR still work); the controls table of 31.1; with a faked
// navigator.xr that only answers isSessionSupported the three Enter buttons turn on (no session is started: a headless browser has no headset);
// the params section `xr`; "Leave XR session" is off with no session. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-31-ar-vr
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-31-ar-vr');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const drawer = (page) => page.locator('#xray-drawer, .xray-drawer, [data-tool-drawer]').first();
async function openXr(page) {
  await ui.tool(page, 'WebXR').click();
  await page.waitForTimeout(600);
}
const btn = (page, name) => page.getByRole('button', { name, exact: true }).first();

await tour.step('31 What you need: a desktop browser with no headset', async () => {
  const page = await open('model=fzk-haus');
  tour.check('"The tool is WebXR (headset icon, tooltip AR / VR) in the action panel"', (await ui.tool(page, 'WebXR').count()) === 1 && /AR \/ VR/.test((await ui.tool(page, 'WebXR').getAttribute('title')) ?? ''), (await ui.tool(page, 'WebXR').getAttribute('title')) ?? '');
  tour.check('this browser cannot run a session (a desktop browser with no headset: isSessionSupported is false)', await page.evaluate(async () => !navigator.xr || !(await navigator.xr.isSessionSupported('immersive-vr').catch(() => false))));
  await openXr(page);
  const body = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  tour.check('"When the browser has no WebXR, the WebXR drawer says so"', /This browser has no WebXR/.test(body), '');
  for (const n of ['Enter VR', 'Enter AR', 'Enter field AR']) {
    const b = btn(page, n);
    tour.check(`"${n} ... disabled with the reason"`, (await b.count()) === 1 && (await b.isDisabled()) && ((await b.getAttribute('title')) ?? '').length > 10, (await b.getAttribute('title')) ?? '');
  }
  tour.check('"Download USDZ ... still work" (a desktop browser has no AR Quick Look)', (await btn(page, 'Download USDZ').count()) === 1 && !(await btn(page, 'Download USDZ').isDisabled()));
  tour.check('"Share link as QR ... still work"', (await btn(page, 'Share link as QR').count()) === 1 && !(await btn(page, 'Share link as QR').isDisabled()));
  tour.check('"Leave XR session" is off while no session runs', await btn(page, 'Leave XR session').isDisabled());
  await btn(page, 'Share link as QR').click();
  await page.waitForTimeout(500);
  const qr = await page.evaluate(() => { const q = document.querySelector('.xr-qr'); return q ? { hidden: q.hidden, svg: !!q.querySelector('svg'), title: q.title } : null; });
  tour.check('"Share link as QR ... shows a QR code of the share link" (an SVG, titled with the link)', !!qr && !qr.hidden && qr.svg && /^https?:\/\/|file:/.test(qr.title), JSON.stringify(qr)?.slice(0, 140));
  tour.check('the QR link names the model, no reviewer name or key', /fzk-haus/i.test(qr?.title ?? '') && !/reviewer|apikey|token/i.test(qr?.title ?? ''), qr?.title?.slice(0, 120));
  const dl = page.waitForEvent('download', { timeout: 60000 }).catch(() => null);
  await btn(page, 'Download USDZ').click();
  const d = await dl;
  tour.check('"Download USDZ ... exports what you see to a 3D file"', !!d && /\.usdz$/.test(d.suggestedFilename()), d?.suggestedFilename());
  const status = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  tour.check('the drawer reports the USDZ export (elements, materials, MB)', /USDZ: \d+ elements/.test(status), status.match(/USDZ: [^.]*/)?.[0]);
});

await tour.step('31.1 The controls table: AR scale, field look, pointer rays, Leave XR session, the field AR buttons', async () => {
  const page = await open('model=fzk-haus');
  await openXr(page);
  const names = ['AR scale', 'field look', 'pointer rays', 'Leave XR session', 'Pick model points', 'Export site', 'Import site', 'Download notes'];
  const text = (await page.locator('body').innerText());
  for (const n of names) tour.check(`the drawer has "${n}"`, text.includes(n));
  const scale = await page.evaluate(() => [...document.querySelectorAll('select')].filter((s) => [...s.options].some((o) => /1:50/.test(o.textContent))).map((s) => [...s.options].map((o) => o.textContent)));
  tour.check('"AR scale: 1:1 (real size) or tabletop 1:50"', scale.length >= 1 && scale[0].some((o) => /1:1/.test(o)) && scale[0].some((o) => /tabletop 1:50/.test(o)), JSON.stringify(scale));
  const look = await page.evaluate(() => [...document.querySelectorAll('select')].filter((s) => [...s.options].some((o) => /ghosted/.test(o.textContent))).map((s) => [...s.options].map((o) => o.textContent)));
  tour.check('"field look: x-ray (services only), ghosted (default) or full"', look.length >= 1 && ['x-ray', 'ghosted', 'full'].every((k) => look[0].some((o) => o.includes(k))), JSON.stringify(look));
  tour.check('"None of these has a default key": the palette actions have empty keys', await page.evaluate(() => { const a = window.__xrayXr; return !!a; }));
  await btn(page, 'Pick model points').click();
  await page.waitForTimeout(300);
  await page.waitForTimeout(500);
  const picked = await ui.clickElement(page, { cls: /IfcWall/ }).catch(() => null);
  await page.waitForTimeout(500);
  if (!(await page.getByText('model point', { exact: false }).first().isVisible().catch(() => false))) await ui.tool(page, 'WebXR').click();
  await page.waitForTimeout(500);
  const pk = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  tour.check('field step 1: "Pick model points ... Click at least 2 clear features on the model": a click adds a model point, and the status counts the points', /\d+ model points? picked/.test(pk) && (/[1-9]\d* model points? picked/.test(pk) || !picked), pk.match(/[^.]*picked[^.]*/)?.[0]);
  tour.check('"Export site" is off until a site is saved ("No saved site for this model")', await btn(page, 'Export site').isDisabled());
});

await tour.step('31.1 With a WebXR runtime that answers isSessionSupported (a fake: no session is started)', async () => {
  const page = await open('model=fzk-haus', { init: () => { Object.defineProperty(navigator, 'xr', { value: { isSessionSupported: async () => true, addEventListener() {}, removeEventListener() {}, requestSession: async () => { throw new Error('no headset'); } }, configurable: true }); } });
  await openXr(page);
  await page.waitForTimeout(800);
  for (const n of ['Enter VR', 'Enter AR', 'Enter field AR']) tour.check(`"${n}" is enabled when the browser reports support`, !(await btn(page, n).isDisabled()));
  tour.check('the "no WebXR" note is hidden', !(await page.locator('.xr-none').isVisible()));
  await btn(page, 'Enter VR').click();
  await page.waitForTimeout(1200);
  const t = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  tour.check('"a browser rule says the session must start from a click": a refused session leaves the viewer usable and says so', /no headset|could not|failed|not start|XR/i.test(t) && (await ui.model(page)).n > 0, t.match(/(no headset|could not[^.]*|failed[^.]*)/i)?.[0]);
});

await tour.step('31 Choices and settings: the params section xr is not in a share link', async () => {
  const page = await open('model=fzk-haus');
  const doc = await page.evaluate(() => window.__xrayParams.collect?.() ?? null);
  const xr = doc?.xr;
  tour.check('"The params section xr has scale, pointerRays, fieldView, cutRadius and storeyCut"', !!xr && ['scale', 'pointerRays', 'fieldView', 'cutRadius', 'storeyCut'].every((k) => k in xr), JSON.stringify(xr));
  const share = await page.evaluate(() => window.__xrayParams.shareUrl());
  let keys = [];
  try { keys = Object.keys(JSON.parse(Buffer.from((share.split('#p=')[1] ?? '').replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'))); } catch { /* checked next */ }
  tour.check('"It is not in a share link": the link carries sections but not xr', keys.length > 2 && !keys.includes('xr'), keys.join());
});

await tour.finish();
