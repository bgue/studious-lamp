// Tour of chapter 2, "Opening the viewer and a model" (docs/manual/02-opening.md): the Try it of 2.1 (single file and from source), 2.2 (open files, errors),
// 2.3 (Sample Projects) and 2.4 (large models). No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-02-opening
import { resolve } from 'node:path';
import { repoRoot, startTour, ui } from './lib.mjs';

const tour = await startTour('tour-02-opening');
const model = (name) => resolve(repoRoot, 'models', name);

/** Click "Open IFC or glb file" and answer the file chooser with `files` (paths or { name, mimeType, buffer }). */
async function openFiles(page, files) {
  const chooser = page.waitForEvent('filechooser');
  await ui.press(page, 'Open IFC or glb file');
  await (await chooser).setFiles(files);
}
const statusLine = async (page) => String(await ui.valueOf(page, 'Load status'));
async function waitStatus(page, re, timeout = 120000) {
  const t0 = Date.now();
  let s = '';
  while (Date.now() - t0 < timeout) {
    s = await statusLine(page);
    if (re.test(s)) return s;
    await page.waitForTimeout(200);
  }
  return s;
}
const toParameters = async (page) => { await ui.topOfPanel(page); await ui.tab(page, 'Parameters'); };

await tour.step('2.1 Try it (single file) steps 1-4: open xray-viewer.html, click an element, X, ?', async () => {
  const file = resolve(repoRoot, 'xray-viewer.html');
  const page = await tour.open('', { url: `file://${file}` });
  const m = await ui.model(page);
  tour.check('"The page opens with a sample model on screen"', m.n > 0, `${m.name}, ${m.n} elements`);
  tour.check('you see "the top bar above it"', await page.locator('#xray-topbar').isVisible());
  tour.check('"a tree on the left"', await page.getByRole('tab', { name: 'Model', exact: true }).isVisible());
  tour.check('"a tabbed column on the right"', await page.getByRole('tab', { name: 'Properties', exact: true }).isVisible());
  const picked = await ui.clickElement(page, { cls: /Duct|Pipe|Wall|Slab/ });
  tour.check('step 3: clicking an element selects it', !!picked, JSON.stringify(picked));
  const x1 = await ui.xray(page);
  await page.keyboard.press('x');
  await ui.settle(page, 800);
  const x2 = await ui.xray(page);
  tour.check('step 4: X switches x-ray off, all ghosts go solid', x1.on === true && x2.on === false && x2.faint === 0, `on ${x1.on}->${x2.on}, faint ${x1.faint}->${x2.faint}`);
  await page.keyboard.press('x');
  await ui.settle(page, 500);
  tour.check('X again switches it on', (await ui.xray(page)).on === true);
  await page.keyboard.press('Shift+?');
  const dlg = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
  await dlg.waitFor({ timeout: 10000 }).catch(() => {});
  tour.check('step 4: ? shows the list of keys', await dlg.isVisible().catch(() => false));
  await page.keyboard.press('Escape');
});

await tour.step('2.1 Try it (from source) steps 2-3: open ?model=building, click a duct, X', async () => {
  const page = await tour.open('model=building');
  tour.check('"?model=building" shows the building', (await ui.model(page)).name === 'building');
  const picked = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  tour.check('a duct can be clicked', !!picked);
  const x = await ui.xray(page);
  tour.check('"The parts that block your view of it turn faint"', x.faint > 0, `${x.faint} faint`);
});

await tour.step('2.1 the ?model= values: an unknown value shows the procedural model and a message', async () => {
  const page = await tour.open('model=no-such-model');
  const m = await ui.model(page);
  tour.check('"the viewer shows the in-memory procedural model"', m.name === 'procedural', m.name);
  const msg = page.locator('#xray-message');
  const t = await msg.innerText().catch(() => '');
  tour.check('"and a red message"', /procedural/i.test(t), t.slice(0, 120));
  const box = await msg.boundingBox().catch(() => null);
  const vh = page.viewportSize().height;
  tour.check('the red message sits in the status bar at the bottom (the manual now says so)', !!box && box.y > vh / 2, box ? `y=${Math.round(box.y)}` : 'no box');
  for (const name of ['building', 'fzk-haus', 'plumbing', 'process-plant', 'debris-demo', 'procedural']) {
    const p = await tour.open(`model=${name}`, { width: 900, height: 600 });
    const mm = await ui.model(p);
    tour.check(`?model=${name} opens`, mm.name === name && mm.n > 0, `${mm.name} ${mm.n}`);
    await p.context().close();
  }
});

await tour.step('2.2 Try it steps 1-4: Parameters tab, Open model folder, Open IFC or glb file, Load status', async () => {
  const page = await tour.open('model=building');
  await toParameters(page);
  await ui.folder(page, 'Open model');
  tour.check('step 1: the Parameters tab has the folder "Open model" with "Open IFC or glb file"', await page.locator('.lil-controller', { hasText: 'Open IFC or glb file' }).first().isVisible());
  const first = await page.evaluate(() => document.querySelector('.lil-gui.lil-root > .lil-children > .lil-gui > .lil-title')?.textContent?.trim());
  tour.check('"The first folder is Open model"', first === 'Open model', first);
  tour.check('"The first button of the tool strip ... Open model" is there', await ui.tool(page, 'Open model').isVisible());
  await openFiles(page, model('Building-Hvac.ifc'));
  const s = await waitStatus(page, /^Loaded \d+ elements in [\d.]+ s/);
  tour.check('step 3: Load status ends with "Loaded <N> elements in <S> s"', /^Loaded \d+ elements in [\d.]+ s/.test(s), s);
  const m = await ui.model(page);
  tour.check('step 4: "Its name is file: and the first file name"', m.name === 'file:Building-Hvac.ifc', m.name);
  // several files: federated, the name says +N more
  await openFiles(page, [model('Building-Architecture.ifc'), model('Building-Structural.ifc'), model('Building-Hvac.ifc')]);
  await waitStatus(page, /^Loaded \d+ elements/);
  const m2 = await ui.model(page);
  tour.check('"or ` +N more` when you opened several files"', m2.name === 'file:Building-Architecture.ifc +2 more', m2.name);
  tour.check('several IFC files are joined into one model', m2.n > m.n, `${m.n} -> ${m2.n}`);
});

await tour.step('2.2 Read a load error: each wrong input gives one line, the model stays', async () => {
  const page = await tour.open('model=building');
  await toParameters(page);
  await ui.folder(page, 'Open model');
  const before = (await ui.model(page)).n;
  const empty = Buffer.alloc(0), junk = Buffer.from('this is not an ifc file at all');
  const cases = [
    ['IFC mixed with glb', [{ name: 'a.ifc', mimeType: 'text/plain', buffer: junk }, { name: 'b.glb', mimeType: 'model/gltf-binary', buffer: junk }], /Cannot open IFC and glb files together/],
    ['several glb files', [{ name: 'a.glb', mimeType: 'model/gltf-binary', buffer: junk }, { name: 'b.glb', mimeType: 'model/gltf-binary', buffer: junk }], /Open one glb file at a time/],
    ['a lone .json', [{ name: 'a.json', mimeType: 'application/json', buffer: Buffer.from('{}') }], /sidecar goes with its \.glb/],
    ['an unsupported file type', [{ name: 'a.txt', mimeType: 'text/plain', buffer: junk }], /Unsupported file type/],
    ['an empty file', [{ name: 'empty.ifc', mimeType: 'text/plain', buffer: empty }], /is empty/],
    ['a corrupt file', [{ name: 'broken.ifc', mimeType: 'text/plain', buffer: Buffer.from('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=GARBAGE(;\nENDSEC;\nEND-ISO-10303-21;\n') }], /This IFC file could not be read: it may be damaged or not an IFC file \(broken\.ifc\)/],
  ];
  for (const [label, files, re] of cases) {
    await openFiles(page, files);
    const s = await waitStatus(page, re, 60000);
    tour.check(`${label}: one line in Load status`, re.test(s), s.slice(0, 160));
    const msg = await page.locator('#xray-message').innerText().catch(() => '');
    tour.check(`${label}: and in the red segment of the status bar`, re.test(msg) || msg.length > 0, msg.slice(0, 120));
  }
  tour.check('"The model you had stays on screen"', (await ui.model(page)).n === before && (await ui.model(page)).name === 'building');
});

await tour.step('2.3 Try it: Sample Projects, choose FZK-Haus, then Building (Simple-Scene)', async () => {
  const page = await tour.open('model=building');
  await toParameters(page);
  await ui.folder(page, 'Sample Projects');
  const opts = await (await ui.control(page, 'Model')).locator('select option').allInnerTexts();
  const want = ['Building (Simple-Scene)', 'FZK-Haus', 'Plumbing', 'Process plant', 'Synthetic 5k', 'Debris demo', 'Procedural', 'FZK-Haus 4D'];
  tour.check('the Model list holds the samples with readable names', want.every((w) => opts.some((o) => o.startsWith(w))), opts.join(' | '));
  await ui.set(page, 'Model', 'FZK-Haus');
  await page.waitForFunction(() => window.__xray.app.modelName === 'fzk-haus', null, { timeout: 120000 });
  await ui.settle(page, 800);
  const m = await ui.model(page);
  tour.check('step 3: the model on screen is replaced by a small house (FZK-Haus)', m.name === 'fzk-haus' && (m.classes.IfcWindow ?? 0) > 0, `${m.n} elements`);
  await ui.set(page, 'Model', 'Building (Simple-Scene)');
  await page.waitForFunction(() => window.__xray.app.modelName === 'building', null, { timeout: 120000 });
  const b = await ui.model(page);
  tour.check('"Building (Simple-Scene) ... a building with HVAC ducts"', (b.classes.IfcDuctSegment ?? 0) > 0, `${b.n} elements`);
  tour.check('the status bar names the model', /building/.test(await ui.statusText(page)), (await ui.statusText(page)).replace(/\s+/g, ' ').slice(0, 100));
});

await tour.step('2.3 Limits: Synthetic 5k in the served app', async () => {
  const page = await tour.open('model=synth5k');
  const m = await ui.model(page);
  tour.check('"Synthetic 5k: a generated building with 5,000 elements and 7 storeys"', m.name === 'synth5k' && m.n >= 4900 && m.n <= 5300, `${m.n} elements`);
});

await tour.step('2.4 Try it: properties none, edges none, open a larger file, read Load status and Model stats', async () => {
  const page = await tour.open('model=building');
  await toParameters(page);
  await ui.folder(page, 'Open model');
  await ui.set(page, 'properties', 'none');
  await ui.set(page, 'edges', 'none');
  tour.check('the two options are set before the file is opened', (await ui.valueOf(page, 'properties')) === 'none' && (await ui.valueOf(page, 'edges')) === 'none');
  await page.evaluate(() => {
    window.__seen = new Set();
    const inp = [...document.querySelectorAll('.lil-controller')].find((c) => c.querySelector('.lil-name')?.textContent.trim() === 'Load status')?.querySelector('input');
    window.__seenTimer = setInterval(() => { if (inp) window.__seen.add(inp.value.replace(/\d+(\.\d+)?/g, '#')); }, 30);
  });
  await openFiles(page, model('AC20-FZK-Haus.ifc'));
  const s = await waitStatus(page, /^Loaded \d+ elements/, 240000);
  const seen = await page.evaluate(() => { clearInterval(window.__seenTimer); return [...window.__seen]; });
  tour.check('"Load status ... ends with Loaded N elements in S s"', /^Loaded \d+ elements in/.test(s), s);
  const steps = ['Reading', 'Opening', 'Meshing', 'Merging', 'Edges', 'BVH', 'Transferring', 'Uploading'];
  const hit = steps.filter((w) => seen.some((t) => t.startsWith(w)));
  tour.check('"It walks through the steps": Reading, Opening, Meshing, Merging, Edges, BVH, Transferring geometry, Uploading', hit.length >= 4, `seen ${hit.join(', ')} of ${seen.length} texts: ${seen.slice(0, 12).join(' / ')}`);
  const stats = String(await ui.valueOf(page, 'Model stats'));
  tour.check('"Model stats then shows elements, triangles, memory in megabytes and load seconds"', /\d/.test(stats) && /(MB|tri)/i.test(stats), stats.slice(0, 160));
  await ui.tool(page, 'Large model').click();
  const drawer = page.locator('#xray-toolbar-drawer');
  await tour.expectText(drawer, /Meshing|Reading|BVH/i, 'The Large model tool shows the same numbers with the time of each step');
  await page.keyboard.press('Escape');
  // no property sets without properties:none
  await ui.clickElement(page, { cls: /Wall|Slab/ });
  await ui.tab(page, 'Properties');
  const props = await page.locator('#dk-pane-properties').innerText().catch(() => '');
  tour.check('"Hover cards and the Properties tab then show no property sets"', !/IsExternal|FireRating/.test(props), props.replace(/\s+/g, ' ').slice(0, 140));
});

await tour.finish();
