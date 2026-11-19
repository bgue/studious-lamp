// Headless smoke for Save IFC and the revision walkthrough (design docs/design/ifc-save-and-revision.md, section 6).
// This file holds steps 1 and 2 (ticket T2) and step 8 (ticket T5); the revision steps 3 to 7 are added by ticket T4.
//   1. Open AC20-FZK-Haus.ifc through the file input; classify all with rules only; confirm 3 elements and commit.
//   2. Save IFC (API, then the dialog button), capture the download, check the bytes (original untouched, no reviewer name),
//      re-open the saved file as a new model (same element count, <psetName>.Discipline readable with properties: all) and
//      screenshot bench/ifc-save-dialog.png.
//   8. Cleaned copy: open Building-Architecture.ifc, run cleanup and hide the matches, Save cleaned copy (API, then the dialog), re-open
//      the .cleaned.ifc: the elements cleanup hid are gone (except the ones kept and marked), every other element is still there.
// Usage: SMOKE_PORT=5770 node bench/smoke-ifc-save-revision.mjs        (SMOKE_STEPS=8 runs only step 8)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5770);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-ifc-save-'));
const FZK = resolve(root, '..', 'models', 'AC20-FZK-Haus.ifc');
const REVIEWER = 'Smoke Reviewer-Quentin';
const ARCH = resolve(root, '..', 'models', 'Building-Architecture.ifc');
const only8 = process.env.SMOKE_STEPS === '8';

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
const check = (name, ok, detail = '') => { if (!ok) failed = true; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`); };
const errors = [];
let browser;
try {
  let up = false;
  for (let i = 0; i < 100 && !up; i++) {
    try { up = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  if (!up) throw new Error('vite did not start:\n' + viteLog);
  browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  // the native save dialog cannot be driven headless: the dialog falls back to a download
  await page.addInitScript(() => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; });
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error(`startup failed: ${startErr}`);

  const openFile = async (file, label) => {
    await page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').setValue(''));
    await page.setInputFiles('#xray-open-file-input', file);
    await page.waitForFunction(() => {
      const s = window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue();
      return /^Loaded \d+ elements/.test(s) || /fail|error|cannot|not a valid/i.test(s);
    }, null, { timeout: 180000 });
    const st = await page.evaluate(() => ({ status: window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue(), model: window.__xray.app.modelName, n: window.__xray.app.controller.model.elements.length }));
    check(`${label} opens`, /^Loaded/.test(st.status), JSON.stringify(st));
    return st;
  };

  if (!only8) {
  // ---------------------------------------------------------------- step 1
  const opened = await openFile(FZK, 'AC20-FZK-Haus.ifc');
  const srcs = await page.evaluate(() => window.__xrayIfcSave.sources());
  check('the source file is retained with its facts', srcs.length === 1 && srcs[0].fileName === 'AC20-FZK-Haus.ifc' && srcs[0].schema.startsWith('IFC4') && srcs[0].maxExpressId > 1000 && srcs[0].size > 1e6, JSON.stringify(srcs));
  await page.waitForFunction('window.__xrayClassify', null, { timeout: 60000 });
  await page.evaluate(() => window.__xrayClassify.review.ready());
  await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
  await page.evaluate(() => window.__xrayClassify.classify('all'));
  const stats = await page.evaluate(() => window.__xrayClassify.stats());
  check('rules-only classification gave results for most elements', stats.total > opened.n * 0.8 && stats.calls === 0, JSON.stringify(stats.bySource));
  await page.evaluate((who) => window.__xrayClassify.review.setReviewer(who), REVIEWER);
  const confirmed = await page.evaluate(() => {
    const c = window.__xrayClassify;
    const gids = c.results().slice(0, 3).map((r) => r.id);
    c.review.propose(gids, { action: 'confirm', item: 'smoke', comment: 'smoke comment ZQX' });
    const commit = c.review.commit('smoke commit');
    return { gids, changes: commit.changes.length, author: commit.author };
  });
  check('3 elements confirmed and committed under the reviewer name', confirmed.changes === 3 && confirmed.author === REVIEWER, JSON.stringify(confirmed));

  // ---------------------------------------------------------------- step 2: API save
  const plan = await page.evaluate(() => window.__xrayIfcSave.plan());
  check('the plan has one file with data for the classified elements', plan.files.length === 1 && plan.files[0].elements === plan.elements && plan.elements > opened.n * 0.8, JSON.stringify(plan));
  const downloaded = page.waitForEvent('download');
  const summary = await page.evaluate(() => window.__xrayIfcSave.save({ includeReviewers: false }));
  const dl = await downloaded;
  const outPath = join(tmp, dl.suggestedFilename());
  await dl.saveAs(outPath);
  const out = readFileSync(outPath);
  const orig = readFileSync(FZK);
  check('the download is named <stem>.xray.ifc', dl.suggestedFilename() === 'AC20-FZK-Haus.xray.ifc', dl.suggestedFilename());
  check('the summary matches the file', summary.files.length === 1 && summary.files[0].bytes === out.length && summary.files[0].lines > 100 && ['worker', 'main'].includes(summary.mode), JSON.stringify(summary));
  const cut = orig.lastIndexOf('ENDSEC;\r\nEND-ISO') >= 0 ? orig.lastIndexOf('ENDSEC;') : orig.lastIndexOf('ENDSEC;');
  check('the original bytes are untouched up to the insert point', out.subarray(0, cut).equals(orig.subarray(0, cut)));
  check('the original tail follows the block', out.subarray(out.length - (orig.length - cut)).equals(orig.subarray(cut)));
  const text = out.toString('latin1');
  check('the file holds our block and the property sets', /\/\* XRAY-BEGIN xray-ifc-additions\/1 base=\d+/.test(text) && text.includes("'Xray_Review'") && text.includes('IFCRELASSOCIATESCLASSIFICATION'));
  check('no reviewer name and no comment in the bytes', !text.includes('Quentin') && !text.includes('Smoke Reviewer') && !text.includes('ZQX'));
  check('the review set records the confirmations without a name', text.includes("IFCLABEL('confirmed')") && text.includes("IFCLABEL('unreviewed')"));

  // ---------------------------------------------------------------- step 2: the dialog
  await page.evaluate(() => window.__xrayIfcSave.open());
  const dlg = page.locator('.xis-box');
  await dlg.waitFor();
  const ticked = await dlg.locator('input[type=checkbox]').first().isChecked();
  check('the reviewer box is off when the dialog opens', ticked === false);
  check('the dialog names the file and its output', (await dlg.textContent()).includes('AC20-FZK-Haus.xray.ifc'));
  await page.screenshot({ path: resolve(here, 'ifc-save-dialog.png') });
  const dl2p = page.waitForEvent('download');
  await dlg.locator('button.primary').click();
  const dl2 = await dl2p;
  const p2 = join(tmp, `dialog-${dl2.suggestedFilename()}`);
  await dl2.saveAs(p2);
  const out2 = readFileSync(p2);
  check('the dialog button saves the same bytes as the API', out2.equals(out));
  await page.waitForFunction(() => /Saved AC20/.test(document.querySelector('.xis-box')?.textContent ?? ''));
  check('the dialog reports the result', /Saved AC20-FZK-Haus\.xray\.ifc/.test(await dlg.textContent()));
  // reopening the dialog resets the reviewer box
  await dlg.locator('input[type=checkbox]').first().check();
  await dlg.locator('button', { hasText: 'Close' }).click();
  await page.evaluate(() => window.__xrayIfcSave.open());
  check('the reviewer box is off again after closing and reopening', (await dlg.locator('input[type=checkbox]').first().isChecked()) === false);
  await dlg.locator('button', { hasText: 'Close' }).click();

  // ---------------------------------------------------------------- step 2: re-open the saved file
  // re-open the saved file as a new model
  const reopened = await openFile(outPath, 'the saved file');
  check('the saved file opens with the same element count', reopened.n === opened.n && reopened.model !== opened.model, `${opened.n} vs ${reopened.n}`);
  // The viewer's reader keeps at most 24 properties per element and only the common sets, so the new sets are read back
  // from the block text with readAdditions (the same function the node tests use), in the page.
  const readBack = await page.evaluate(async (b64) => {
    const { readAdditions } = await import('/src/ifcsave/readBack.ts');
    const bin = atob(b64);
    const a = bin.indexOf('/* XRAY-BEGIN');
    const e = bin.indexOf('/* XRAY-END');
    const r = readAdditions(bin.slice(a, e + 40));
    let withDiscipline = 0;
    for (const v of r.byExpressId.values()) if (Object.keys(v.review).some((k) => k.endsWith('.Discipline'))) withDiscipline++;
    return { elements: r.byExpressId.size, withDiscipline, header: r.header };
  }, out.toString('base64'));
  check('<psetName>.Discipline is readable back from the block for every classified element', readBack.elements === opened.n && readBack.withDiscipline === opened.n, JSON.stringify(readBack));
  }

  // ---------------------------------------------------------------- step 8: cleaned copy
  const arch = await openFile(ARCH, 'Building-Architecture.ifc');
  await page.waitForFunction('window.__xrayCleanup', null, { timeout: 60000 });
  // Building-Architecture has only 9 elements and nothing tiny: widen the tiny rule until cleanup hides some but not all of them
  const hidden = await page.evaluate(() => {
    const c = window.__xrayCleanup;
    const m = window.__xray.app.controller.model;
    for (const maxSize of [0.5, 1, 2, 3, 4, 6, 10]) {
      c.restore();
      c.setRules({ tiny: { enabled: true, maxSize } });
      c.analyse();
      c.hide();
      const n = c.hiddenByCleanup().length;
      if (n > 0 && n < m.elements.length / 2) break;
    }
    return { ids: c.hiddenByCleanup(), globalIds: c.hiddenByCleanup().map((i) => m.elements[i].globalId), all: m.elements.map((e) => e.globalId), rules: c.rules.tiny };
  });
  check('cleanup hid some elements', hidden.ids.length > 0, `${hidden.ids.length} of ${arch.n}, tiny ${JSON.stringify(hidden.rules)}`);
  const cands = await page.evaluate(() => window.__xrayIfcSave.cleanCandidates());
  check('the cleaned copy sees the hidden elements', cands.cleanup === hidden.ids.length, JSON.stringify(cands));
  const cplan = await page.evaluate(() => window.__xrayIfcSave.cleanPlan());
  check('the dry run reports removed and kept', cplan.files.length === 1 && cplan.files[0].removed + cplan.files[0].kept.length === hidden.ids.length, JSON.stringify({ removed: cplan.files[0]?.removed, kept: cplan.files[0]?.kept.length, cascaded: cplan.files[0]?.cascaded }));
  // the dialog and its report
  await page.evaluate(() => window.__xrayIfcSave.openClean());
  const cdlg = page.locator('.xis-box').last();
  await cdlg.locator('button.primary').waitFor();
  await page.waitForFunction(() => { const b = [...document.querySelectorAll('.xis-box button.primary')].pop(); return b && !b.disabled; });
  const ctext = await cdlg.textContent();
  check('the dialog states what is removed and the risks', /Removed: \d/.test(ctext) && /Kept and marked instead/.test(ctext) && ctext.includes('Building-Architecture.cleaned.ifc'), ctext.slice(0, 200));
  await page.screenshot({ path: resolve(here, 'ifc-clean-dialog.png') });
  await cdlg.locator('button', { hasText: 'Close' }).click();
  const t0 = Date.now();
  const cdl = page.waitForEvent('download');
  const csum = await page.evaluate(() => window.__xrayIfcSave.saveCleaned({ withClassification: false }));
  const cfile = await cdl;
  const cpath = join(tmp, cfile.suggestedFilename());
  await cfile.saveAs(cpath);
  const cbytes = readFileSync(cpath);
  console.log(`cleaned copy: ${csum.files[0].removed} removed, ${csum.files[0].kept} kept, ${csum.files[0].sourceBytes} -> ${cbytes.length} bytes, ${csum.ms.toFixed(0)} ms in the ${csum.mode}, ${Date.now() - t0} ms with the download`);
  check('the download is named <stem>.cleaned.ifc and smaller than the source', cfile.suggestedFilename() === 'Building-Architecture.cleaned.ifc' && cbytes.length < readFileSync(ARCH).length, `${cbytes.length}`);
  check('the summary matches the file', csum.files[0].bytes === cbytes.length && csum.files[0].removed + csum.files[0].kept === hidden.ids.length, JSON.stringify(csum.files[0]));
  const ctxt = cbytes.toString('latin1');
  check('the block records removed and kept', ctxt.includes(`removed=${csum.files[0].removed} kept=${csum.files[0].kept}`));
  const keptGuids = new Set(csum.kept.map((k) => k.globalId));
  const goneGuids = hidden.globalIds.filter((g) => !keptGuids.has(g));
  const reopened8 = await openFile(cpath, 'the cleaned copy');
  const after = await page.evaluate(() => window.__xray.app.controller.model.elements.map((e) => e.globalId));
  const afterSet = new Set(after);
  const expected = hidden.all.filter((g) => !goneGuids.includes(g));
  check('the elements cleanup hid are gone from the re-opened copy', goneGuids.every((g) => !afterSet.has(g)), `${goneGuids.length} removed`);
  check('every other element is still there', expected.length === after.length && expected.every((g) => afterSet.has(g)), `${expected.length} expected, ${reopened8.n} found`);
  if (keptGuids.size > 0) check('kept elements carry Xray_Cleanup.KeptBecause', ctxt.includes("'Xray_Cleanup'") && ctxt.includes("'KeptBecause'"));

  check('no console or page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('FAIL smoke crashed:', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill('SIGTERM');
}
console.log(failed ? 'SMOKE FAILED' : 'SMOKE OK');
process.exit(failed ? 1 : 0);
