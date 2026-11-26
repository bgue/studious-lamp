// Tour of chapter 29, "Sharing without a server" (docs/manual/29-sharing.md): 29.1 the settings link, the view link (the Try it of sending a view as a link),
// what no link carries, the QR button; 29.2 the single file and the table of exports. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-29-sharing
import { resolve } from 'node:path';
import { repoRoot, startTour, ui } from './lib.mjs';

const tour = await startTour('tour-29-sharing');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const clipInit = () => { window.__clip = []; try { navigator.clipboard.writeText = async (t) => { window.__clip.push(String(t)); }; } catch { /* no clipboard */ } };
const b64 = (s) => JSON.parse(Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'));

let viewLink = '';
await tour.step('29.1 Try it: send a view as a link (steps 1-4)', async () => {
  const page = await open('model=fzk-haus', { init: clipInit });
  const roof = await ui.clickElement(page, { name: /Dach|Roof/i }) ?? await ui.clickElement(page, { cls: 'IfcSlab' });
  tour.check('step 2: "Click the roof"', !!roof, JSON.stringify(roof));
  await page.keyboard.press('f');
  await ui.waitStill(page);
  const x = await ui.xray(page);
  if (!x.on) await page.keyboard.press('x');
  await page.keyboard.press('Control+Shift+S');
  await page.waitForTimeout(600);
  await ui.tab(page, 'Views');
  const rowBtn = page.getByRole('button', { name: /^More actions for/ }).first();
  await rowBtn.click();
  await page.getByRole('menuitem', { name: 'Rename' }).click().catch(async () => { await page.getByText('Rename', { exact: true }).first().click(); });
  const inp = page.getByRole('textbox', { name: 'Rename view' });
  await inp.fill('Roof'); await inp.press('Enter');
  await page.waitForTimeout(400);
  tour.check('step 3: "Ctrl+Shift+S to save a view. Give it the name Roof": the Views tab lists "Roof"', (await page.locator('#views-panel').innerText()).includes('Roof'));
  await page.getByRole('button', { name: 'More actions for Roof' }).click();
  await page.getByText('Copy link', { exact: true }).first().click();
  await page.waitForTimeout(500);
  const clip = await page.evaluate(() => window.__clip);
  viewLink = clip[clip.length - 1] ?? '';
  tour.check('step 4: "Click ⋯ on the row Roof, then Copy link. The address is now on your clipboard"', /#view=/.test(viewLink), viewLink.slice(0, 100));
  tour.check('"A view link is typically 300 to 900 characters"', viewLink.length > 100 && viewLink.length < 1500, `${viewLink.length} characters`);
  const payload = viewLink.split('#view=')[1] ?? '';
  let doc = null; try { doc = b64(payload); } catch { /* binary payload */ }
  tour.check('"It never carries a thumbnail, drawings or other views": no image data in the link', !/data:image|jpeg|png/i.test(payload) && !/data:image/.test(JSON.stringify(doc ?? {})));
  tour.check('"Reviewer names ... in no link", "API keys ... cannot contain them"', !/reviewer|apikey|api_key|hf_/i.test(JSON.stringify(doc ?? {})) && !/reviewer/i.test(viewLink));
});

await tour.step('29.1 Try it steps 5-6: paste the address in a new tab', async () => {
  if (!viewLink) throw new Error('no view link from the previous step');
  const page = await open('', { url: viewLink, init: () => { const rec = () => { const m = (document.body?.innerText ?? '').match(/Shared view[^\n]*/); if (m && !window.__sharedNote) window.__sharedNote = m[0]; }; new MutationObserver(rec).observe(document, { subtree: true, childList: true, characterData: true }); } });
  const st = (await page.evaluate(() => window.__sharedNote ?? '')) || (await ui.statusText(page)).replace(/\s+/g, ' ');
  tour.check('step 5: "The status bar says Shared view "Roof" applied. Press Save view to keep it."', /Shared view "Roof" applied\. Press Save view to keep it\./.test(st), st.slice(0, 200));
  tour.check('step 5: "The viewer loads FZK-Haus"', /fzk/i.test(st) || (await ui.model(page)).name.toLowerCase().includes('fzk'), (await ui.model(page)).name);
  tour.check('step 6: "The # part is gone ... a reload does not undo"', !(await page.evaluate(() => location.hash)).includes('view='));
  const n = await page.evaluate(() => window.__xrayViews.list().length);
  tour.check('"Press Save view to keep it": the shared view is applied, not saved', n === 0, `${n} saved views`);
});

await tour.step('29.1 The settings link (#p=) from Copy share URL, and what it carries', async () => {
  const page = await open('model=fzk-haus', { init: clipInit });
  await page.keyboard.press('Control+Shift+S'); // a view exists but a settings link must not carry it
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Export / import');
  await ui.press(page, 'Copy share URL');
  await page.waitForTimeout(400);
  const url = (await page.evaluate(() => window.__clip)).pop() ?? '';
  tour.check('"Settings link (#p=)": Copy share URL', /#p=/.test(url), url.slice(0, 100));
  let doc = null; try { doc = b64(url.split('#p=')[1]); } catch { /* checked next */ }
  tour.check('the link decodes as JSON (base64url) - "the settings, written as JSON, turned into text with base64url"', !!doc && typeof doc === 'object', url.slice(0, 80));
  const keys = Object.keys(doc ?? {});
  tour.check('"Carries: model name, x-ray ... sightlines, display, camera position and target"', keys.some((k) => /model/.test(k)) && keys.includes('camera'), keys.join());
  tour.check('"Does not carry: selection, hides, sets, class styles, views, drawings, issues, key bindings"', !keys.some((k) => /^(selection|selectionSets|classStyles|views|drawings|issues|keymap|keys)$/.test(k)), keys.join());
  tour.check('"Camera numbers are rounded to 1 mm to keep the link short"', (() => { const p = doc?.camera?.position ?? []; return p.length === 3 && p.every((v) => Math.abs(v * 1000 - Math.round(v * 1000)) < 1e-6); })(), JSON.stringify(doc?.camera?.position));
  tour.check('"What no link ever carries": no key, token or reviewer name', !/apikey|token|reviewer/i.test(JSON.stringify(doc)));
  tour.check('"The map is off at every start, and it is in no link"', !keys.includes('map'));
  tour.check('"Copy share URL, Export JSON, Import JSON and Reset to defaults" are in the Export / import folder', await (async () => { const t = await page.locator('#dock').innerText(); return ['Copy share URL', 'Export JSON', 'Import JSON', 'Reset to defaults'].every((n) => t.includes(n)); })());
  const p2 = await open('', { url });
  const st = (await ui.statusText(p2)).replace(/\s+/g, ' ');
  tour.check('"When a link opens, the viewer ... applies the settings once, then removes the # part"', !(await p2.evaluate(() => location.hash)).includes('p='), st.slice(0, 100));
});

await tour.step('29.1 The QR code (WebXR drawer) and 29.2 What you can export', async () => {
  const page = await open('model=fzk-haus');
  await ui.tool(page, 'WebXR').click();
  await page.getByRole('button', { name: 'Share link as QR' }).click();
  await page.waitForTimeout(400);
  tour.check('"The WebXR drawer has Share link as QR. It shows a QR code of the share link"', await page.evaluate(() => !!document.querySelector('.xr-qr svg') && !document.querySelector('.xr-qr').hidden));
  await ui.tool(page, 'WebXR').click().catch(() => {});
  await ui.tab(page, 'Views');
  const views = (await page.locator('#sidebar').innerText());
  tour.check('table: Views tab, Export', /Export/.test(views), '');
  await ui.tab(page, 'Sets');
  tour.check('table: Sets tab, Export', /Export/.test(await page.locator('#sidebar').innerText()));
  await ui.tab(page, 'Script');
  tour.check('table: Script tab, Export', /Export/.test(await page.locator('#dock').innerText()));
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  const dock = await page.locator('#dock').evaluate((n) => n.textContent);
  tour.check('table: Presets folder, Export presets; All settings: Export JSON; Shortcuts: Edit shortcuts', ['Export presets', 'Export JSON', 'Edit shortcuts'].every((n) => dock.includes(n)), '');
  await ui.tab(page, 'Views');
  const flyMore = await page.getByRole('button', { name: 'More fly-through actions' }).count();
  tour.check('table: fly-throughs, fly-through section menu (⋯) exports', flyMore === 1);
});

await tour.step('29.2 The viewer alone: xray-viewer.html makes no network requests', async () => {
  const reqs = [];
  const page = await open('', { url: `file://${resolve(repoRoot, 'xray-viewer.html')}`, waitUntil: 'commit', onRequest: (r) => { if (!/^(file|data|blob|about):/.test(r.url())) reqs.push(r.url()); } });
  const m = await ui.model(page);
  tour.check('"xray-viewer.html is one file that holds the application, the sample models and the IFC reader": it opens with a model', m.n > 0, `${m.name} ${m.n}`);
  tour.check('"It makes no network requests"', reqs.length === 0, reqs.slice(0, 3).join(' '));
  tour.check('"then open your own IFC file with Open IFC or glb file": the button is there', (await page.locator('.lil-controller', { hasText: 'Open IFC or glb file' }).count()) > 0 || (await ui.tab(page, 'Parameters').then(() => page.locator('.lil-controller', { hasText: 'Open IFC or glb file' }).count())) > 0);
});

await tour.finish();
