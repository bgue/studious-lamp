// Headless browser check for "open your own files" (src/plugins/fileLoader.ts, src/model/ifcImport.ts).
//   node bench/smoke-open-file.mjs                  dev server (bench/vite.smoke.config.mjs), all scenarios
//   node bench/smoke-open-file.mjs --single         dist-single/xray-viewer.html from file:// (run `npm run bundle` first)
//   node bench/smoke-open-file.mjs --single --no-ifc   the `--no-ifc` bundle: glb opens, IFC says the reader is missing
//   options: --bridge /tmp/bridge.ifc   extra timing run (Infra-Bridge.ifc, IFC4, 1.7 MB)
//            --shots                    write bench/open-file-fzk.png and bench/open-file-federated.png (dev mode)
//            --dist                     serve the production build (`npm run build`, then `vite preview`) instead of the dev server
//            --stress file.ifc          time an extra IFC file (repeatable)
//            --no-worker                hide Worker so the reader falls back to the main thread
// Drives the hidden file input with page.setInputFiles, reads the "Load status" readout and the model picker, and fails
// on console errors, page errors, or (single mode) any request that is not file:, data: or blob:.
import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const repo = resolve(root, '..');
const args = process.argv.slice(2);
const flag = (k) => args.includes(k);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const single = flag('--single');
const noIfc = flag('--no-ifc');
const port = Number(process.env.SMOKE_PORT ?? 5197);
const bridge = arg('--bridge', existsSync('/tmp/bridge.ifc') ? '/tmp/bridge.ifc' : '');
const stress = args.flatMap((a, i) => (a === '--stress' ? [args[i + 1]] : [])); // extra IFC files to time, repeatable
const shots = flag('--shots') || !single;
const noWorker = flag('--no-worker'); // hide the Worker constructor: the reader falls back to the main thread

const m = (f) => resolve(repo, 'models', f);
const pub = (f) => resolve(root, 'public/models', f);
const tmp = '/tmp/xray-open-file-smoke';

const req = createRequire(import.meta.url);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = req(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

let vite = null;
if (!single) {
  const viteArgs = flag('--dist')
    ? ['preview', '--host', '127.0.0.1', '--port', String(port), '--strictPort']
    : ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'];
  vite = spawn(resolve(root, 'node_modules/.bin/vite'), viteArgs, { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  vite.stdout.on('data', (d) => (log += d));
  vite.stderr.on('data', (d) => (log += d));
  let ok = false;
  for (let i = 0; i < 100 && !ok; i++) {
    try { ok = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  if (!ok) { console.error('vite did not start (is port ' + port + ' still held by an earlier run?):\n' + log); vite.kill('SIGTERM'); process.exit(1); }
}

const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
let failures = 0;
const results = [];
const check = (cond, what) => { if (!cond) { failures++; console.log('  FAIL:', what); } return cond; };

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  const requests = [];
  const infos = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') errors.push(`[${msg.type()}] ${msg.text()}`);
    else if (msg.text().startsWith('[ifc-import]')) infos.push(msg.text());
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  page.on('requestfailed', (r) => errors.push(`[requestfailed] ${r.url()}`));
  page.on('request', (r) => {
    const u = r.url();
    if (single && !u.startsWith('file://') && !u.startsWith('data:') && !u.startsWith('blob:')) requests.push(u);
  });
  page.on('worker', (w) => infos.push(`[worker started] ${w.url().slice(0, 60)}`));

  if (noWorker) await page.addInitScript(() => { delete window.Worker; });
  const url = single ? pathToFileURL(resolve(root, noIfc ? 'dist-single/xray-viewer-no-ifc.html' : 'dist-single/xray-viewer.html')).href : `http://127.0.0.1:${port}/?model=building`;
  await page.goto(url);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error('app failed to start: ' + startErr);

  const state = () => page.evaluate(() => {
    const app = window.__xray.app;
    const ctl = (p) => app.panel.controllersRecursive().find((c) => c.property === p);
    const sel = ctl('model').$select;
    return {
      status: ctl('status').getValue(),
      statusShown: ctl('status').$input.value,
      cancelDisabled: ctl('cancel')._disabled,
      model: app.modelName,
      elements: app.controller.model.elements.length,
      options: Array.from(sel.options).map((o) => o.value),
      message: document.getElementById('xray-message')?.style.display === 'none' ? '' : (document.getElementById('xray-message')?.textContent ?? ''),
    };
  });
  const resetStatus = () => page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').setValue(''));
  const waitDone = async (timeout = 180000) => {
    const t0 = Date.now();
    for (;;) {
      const s = await state();
      if (s.cancelDisabled && s.status !== '') return s;
      if (Date.now() - t0 > timeout) throw new Error('timed out; status: ' + s.status);
      await new Promise((r) => setTimeout(r, 40));
    }
  };
  /** Open files through the hidden input; resolves with the final state and the wall time in seconds. */
  const open = async (files) => {
    await resetStatus();
    const t0 = Date.now();
    await page.setInputFiles('#xray-open-file-input', files);
    const s = await waitDone();
    check(s.statusShown === s.status, `the readout shows the status text ("${s.statusShown}" vs "${s.status}")`);
    return { ...s, secs: (Date.now() - t0) / 1000 };
  };
  const record = (label, s) => {
    results.push({ label, status: s.status, model: s.model, elements: s.elements, secs: s.secs });
    console.log(`${label}: ${s.secs.toFixed(2)} s wall | model "${s.model}" ${s.elements} elements | status: ${s.status}`);
  };

  // ---- panel structure
  const layout = await page.evaluate(() => {
    const app = window.__xray.app;
    const folder = app.panel.folders.find((f) => f._title === 'Open model');
    const first = app.panel.$children.firstElementChild;
    return {
      hasFolder: !!folder,
      isFirst: !!folder && first === folder.domElement,
      names: folder ? folder.controllers.map((c) => c._name) : [],
      cancelDisabled: folder ? folder.controllers[1]._disabled : null,
      statusDisabled: folder ? folder.controllers[2]._disabled : null,
      statusIsText: folder ? folder.controllers[2].domElement.querySelector('input[type=text]') !== null : null,
      accept: document.getElementById('xray-open-file-input')?.accept,
      multiple: document.getElementById('xray-open-file-input')?.multiple,
    };
  });
  console.log('panel:', JSON.stringify(layout));
  check(layout.hasFolder && layout.isFirst, "folder 'Open model' is the first thing in the panel");
  check(JSON.stringify(layout.names) === JSON.stringify(['Open IFC or glb file', 'Cancel load', 'Load status']), 'control names');
  check(layout.cancelDisabled && layout.statusDisabled && layout.statusIsText, 'Cancel disabled at rest, status is a disabled text field');
  check(layout.accept === '.ifc,.ifczip,.glb,.json' && layout.multiple === true, 'input accept/multiple');

  const before = await state();
  console.log(`start model "${before.model}" ${before.elements} elements`);
  const refCount = (file) => JSON.parse(readFileSync(pub('building.json'), 'utf8')).elements.filter((e) => e.file === file).length;

  if (single && noIfc) {
    // ---- --no-ifc bundle
    const d = await open([pub('building.glb'), pub('building.json')]);
    record('no-ifc: glb + json', d);
    check(/^Loaded 26 elements in /.test(d.status) && d.elements === 26 && d.options.includes('file:building.glb'), 'glb opens in the no-ifc bundle');
    const e = await open([m('Building-Structural.ifc')]);
    record('no-ifc: ifc', e);
    check(e.status === 'This build does not include the IFC reader', 'IFC says the reader is missing');
    check(e.model === d.model && e.elements === d.elements, 'model untouched after the IFC message');
    const hasWasm = await page.evaluate('typeof window.__xrayIfcWasm');
    check(hasWasm === 'undefined', 'no embedded wasm in the no-ifc bundle');
  } else {
    // (a) Building-Structural alone
    const a = await open([m('Building-Structural.ifc')]);
    record('(a) Building-Structural.ifc', a);
    check(a.status.startsWith(`Loaded ${refCount('Building-Structural.ifc')} elements in `), `(a) loaded ${refCount('Building-Structural.ifc')} elements`);
    check(a.model === 'file:Building-Structural.ifc' && a.options.includes(a.model), '(a) model picker lists file:Building-Structural.ifc');
    check(a.elements === refCount('Building-Structural.ifc'), '(a) element count in the viewer');

    // (c) FZK
    const c = await open([m('AC20-FZK-Haus.ifc')]);
    record('(c) AC20-FZK-Haus.ifc', c);
    check(/^Loaded 82 elements in /.test(c.status) && c.elements === 82 && c.options.includes('file:AC20-FZK-Haus.ifc'), '(c) 82 elements, listed in the picker');
    if (shots) {
      // a window: the frame of a feature with host relations
      await page.evaluate(() => {
        const app = window.__xray.app;
        const els = app.controller.model.elements;
        const win = els.find((e) => e.ifcClass === 'IfcWindow') ?? els[0];
        app.selectIds([win.id]);
      });
      await page.waitForTimeout(1200);
      await page.screenshot({ path: resolve(here, single ? 'open-file-fzk-single.png' : 'open-file-fzk.png') });
    }

    // the same file through the real button: the worker and wasm start while the (simulated) file dialog is open
    {
      await resetStatus();
      const t0 = Date.now();
      const [chooser] = await Promise.all([
        page.waitForEvent('filechooser'),
        page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'open').$button.click()),
      ]);
      await page.waitForTimeout(1500); // the user picks a file
      const t1 = Date.now();
      await chooser.setFiles([m('Building-Structural.ifc')]);
      const w = await waitDone();
      const secs = (Date.now() - t1) / 1000;
      record('(a2) Building-Structural.ifc via the button, after a 1.5 s dialog (worker pre-warmed)', { ...w, secs });
      check(/^Loaded 14 elements in /.test(w.status), '(a2) loads');
      void t0;
    }

    if (!single) {
      // (b) three federated
      const b = await open([m('Building-Structural.ifc'), m('Building-Architecture.ifc'), m('Building-Hvac.ifc')]);
      record('(b) three Building-*.ifc federated', b);
      check(/^Loaded 26 elements in /.test(b.status) && b.elements === 26, '(b) 26 elements');
      check(b.model === 'file:Building-Structural.ifc +2 more' && b.options.includes(b.model), '(b) picker name');
      const fed = await page.evaluate(() => {
        const app = window.__xray.app;
        const model = app.controller.model;
        const duct = model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
        app.selectIds([duct.id]);
        return { duct: duct.id, storeys: model.storeys.length, systems: model.relations.systems.map((s) => [s.name, s.elements.length]) };
      });
      console.log('  federated model:', JSON.stringify(fed));
      await page.waitForTimeout(1500);
      if (shots) await page.screenshot({ path: resolve(here, 'open-file-federated.png') });

      // (d) glb + sidecar
      const d = await open([pub('building.glb'), pub('building.json')]);
      record('(d) building.glb + building.json', d);
      check(/^Loaded 26 elements in /.test(d.status) && d.elements === 26 && d.options.includes('file:building.glb'), '(d) 26 elements, listed');
      const d2 = await open([pub('plumbing.glb')]);
      record('(d2) plumbing.glb without sidecar', d2);
      check(/^Loaded 26 elements in /.test(d2.status), '(d2) glb alone loads');

      // (e) corrupt IFC, (f) unsupported file, plus mixed and empty
      const keep = await state();
      const { writeFileSync, mkdirSync } = await import('node:fs');
      mkdirSync(tmp, { recursive: true });
      const rnd = Buffer.alloc(4096);
      for (let i = 0; i < rnd.length; i++) rnd[i] = (i * 2654435761) >>> 24;
      writeFileSync(resolve(tmp, 'x.ifc'), rnd);
      writeFileSync(resolve(tmp, 'notes.txt'), 'hello');
      writeFileSync(resolve(tmp, 'empty.ifc'), '');
      writeFileSync(resolve(tmp, 'trunc.ifc'), readFileSync(m('Building-Hvac.ifc')).subarray(0, 3000));
      for (const [label, files, re] of [
        ['(e) corrupt x.ifc', [resolve(tmp, 'x.ifc')], /^x\.ifc is not a valid IFC file/],
        ['(f) unsupported notes.txt', [resolve(tmp, 'notes.txt')], /^Unsupported file type: notes\.txt/],
        ['(g) empty.ifc', [resolve(tmp, 'empty.ifc')], /^empty\.ifc is empty/],
        ['(h) truncated IFC', [resolve(tmp, 'trunc.ifc')], /trunc\.ifc/],
        ['(i) IFC + glb mixed', [m('Building-Hvac.ifc'), pub('building.glb')], /^Cannot open IFC and glb files together/],
      ]) {
        const s = await open(files);
        record(label, s);
        check(re.test(s.status), `${label}: status matches ${re}`);
        check(s.model === keep.model && s.elements === keep.elements, `${label}: current model untouched (${keep.model})`);
      }
      const msg = await state();
      check(msg.message.length > 0, 'a banner message is shown for errors');

      // zipped IFC (.ifczip), made with python's zipfile
      {
        const { execFileSync } = await import('node:child_process');
        const zipPath = resolve(tmp, 'Zipped-Hvac.ifczip');
        execFileSync('python3', ['-I', '-c', 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1],"w",zipfile.ZIP_DEFLATED); z.write(sys.argv[2],"inner/Zipped-Hvac.ifc"); z.close()', zipPath, m('Building-Hvac.ifc')]);
        const z = await open([zipPath]);
        record('(n) Zipped-Hvac.ifczip', z);
        check(/^Loaded 3 elements in /.test(z.status) && z.model === 'file:Zipped-Hvac.ifczip', '(n) ifczip loads');
        writeFileSync(resolve(tmp, 'bad.ifczip'), Buffer.from('PK\x03\x04 this is not a real zip archive at all, only the magic'));
        const bz = await open([resolve(tmp, 'bad.ifczip')]);
        record('(o) corrupt bad.ifczip', bz);
        check(/^bad\.ifczip could not be unzipped/.test(bz.status) && bz.model === z.model, '(o) corrupt zip fails cleanly');
      }

      // 100 MB warning: a 101 MB file that is not a glb; the banner must warn, then the load fails cleanly
      {
        const { writeFileSync, mkdirSync } = await import('node:fs');
        mkdirSync(tmp, { recursive: true });
        const big = resolve(tmp, 'big.glb');
        writeFileSync(big, Buffer.alloc(101 * 1024 * 1024));
        const keepBig = await state();
        await resetStatus();
        const warned = page.waitForFunction(() => /Large input/.test(document.getElementById('xray-message')?.textContent ?? '') || /Large input/.test(window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue()), null, { timeout: 60000 });
        await page.setInputFiles('#xray-open-file-input', [big]);
        await warned.then(() => console.log('  large input warning shown'), () => check(false, 'the 100 MB warning was not shown'));
        const s = await waitDone();
        record('(m) 101 MB big.glb', { ...s, secs: 0 });
        check(/is not a valid glb file/.test(s.status), '(m) big non-glb fails cleanly');
        check(s.model === keepBig.model && s.elements === keepBig.elements, '(m) model untouched');
      }

      // drag and drop (a synthetic drop with a real File built in the page)
      const bytes = readFileSync(m('Building-Hvac.ifc')).toString('base64');
      await resetStatus();
      const overlay = await page.evaluate((b64) => {
        const bin = atob(b64);
        const u8 = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        const dt = new DataTransfer();
        dt.items.add(new File([u8], 'Dropped-Hvac.ifc'));
        document.body.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true, cancelable: true }));
        const ov = document.getElementById('xray-drop-overlay');
        const shown = { display: ov.style.display, text: ov.textContent };
        window.__dropDt = dt;
        return shown;
      }, bytes);
      console.log('  drop overlay:', JSON.stringify(overlay));
      check(overlay.display === 'flex' && overlay.text === 'Drop IFC or glb files to open', 'drop overlay appears on dragenter');
      if (shots) await page.screenshot({ path: resolve(here, 'open-file-dropzone.png') });
      await page.evaluate(() => document.body.dispatchEvent(new DragEvent('drop', { dataTransfer: window.__dropDt, bubbles: true, cancelable: true })));
      const dropped = await waitDone();
      record('(j) drag and drop Dropped-Hvac.ifc', { ...dropped, secs: 0 });
      const ovAfter = await page.evaluate(() => document.getElementById('xray-drop-overlay').style.display);
      check(ovAfter === 'none', 'overlay hides after drop');
      check(/^Loaded 5 elements/.test(dropped.status) || /^Loaded 3 elements/.test(dropped.status), '(j) drop loads the file');

      // cancel mid-load (FZK takes a second or more in the worker)
      const keep2 = await state();
      await resetStatus();
      await page.setInputFiles('#xray-open-file-input', [m('AC20-FZK-Haus.ifc')]);
      await page.waitForFunction(() => {
        const s = window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue();
        return /^(Opening|Meshing|Reading relations)/.test(s);
      }, null, { timeout: 60000 });
      await page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'cancel').$button.click());
      const cancelled = await waitDone();
      record('(k) cancel during FZK load', { ...cancelled, secs: 0 });
      check(cancelled.status === 'Load cancelled' && cancelled.model === keep2.model && cancelled.elements === keep2.elements, '(k) cancelled, model untouched');
      // and a load right after the cancel still works (a fresh worker)
      const again = await open([m('Building-Hvac.ifc')]);
      record('(l) load after cancel', again);
      check(/^Loaded \d+ elements/.test(again.status), '(l) loads after a cancel');
    }

    for (const f of stress) {
      const sz = readFileSync(f).length;
      const r = await open([f]);
      record(`stress ${f} (${(sz / 1048576).toFixed(1)} MB)`, r);
      check(/^Loaded \d+ elements/.test(r.status), `${f} loads`);
    }
    if (bridge) {
      const br = await open([bridge]);
      record('Infra-Bridge.ifc (1.7 MB)', br);
      check(/^Loaded \d+ elements/.test(br.status), 'bridge loads');
    }
  }

  const want = noWorker ? 'main' : 'worker';
  const modes = infos.filter((i) => i.startsWith('[ifc-import] {')).map((i) => JSON.parse(i.slice(12)).mode);
  check(modes.length === 0 || modes.every((x) => x === want), `every IFC import ran in the ${want} (modes: ${[...new Set(modes)]})`);
  console.log('import info:', infos.length ? '\n  ' + infos.join('\n  ') : 'none');
  if (single) console.log('non-file requests:', requests.length ? requests.join(', ') : 'none');
  console.log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.length) failures += errors.length;
  if (requests.length) failures += requests.length;
} catch (e) {
  console.error(e);
  failures++;
} finally {
  await browser.close();
  vite?.kill('SIGTERM');
}
console.log(failures ? `\n${failures} problem(s)` : '\nall checks passed');
console.log(JSON.stringify(results));
process.exit(failures ? 1 : 0);
