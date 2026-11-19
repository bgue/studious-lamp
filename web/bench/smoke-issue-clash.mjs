// Headless check for "Raise issues from results" of the penetrations and clearance tools (docs-features/issues.md, "Issues from checks"):
//   synth5k, penetrations (hundreds of rows):
//   - above the batch limit (lowered to 5 here) the drawer asks first and offers "Raise top N by severity"; the worst results are
//     raised, with progress, and the page keeps drawing frames between the issues;
//   - each issue is "Penetration: A through B", has both GlobalIds, the labels clash and penetration, the camera on the pair, a pin and a
//     sketch tied to the pair (penetration attachment); the worst rows come first (no opening before the rest);
//   - re-running the analysis and raising again makes no doubles: the counts say new / already raised / not found;
//   - a result the re-run no longer reports gets one note "Not found in latest run", is not deleted, and "Close n not found" closes it;
//   - the BCF export and a re-open keep the dedup keys, so raising after loading the file makes no doubles either;
//   building, clearance with a duct as the focus:
//   - the tight pairs are raised as "Clearance n mm < m mm: A / B" with a measurement attachment, and a second raise adds nothing;
//   - fails on any console error.
// Usage: SMOKE_PORT=5732 node bench/smoke-issue-clash.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5732);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 150; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

/** The batch limit used here (a render takes seconds in a software GL, so the smoke raises a few issues at a time). */
const K = 5;
const errors = [];
async function open(browser, model) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 240000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${model}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[${model}] [pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForTimeout(500);
  return { page, ctx };
}

/** The issues raised from a check, with what the checks below look at. */
const raisedFn = (check) => {
  const c = window.__xrayIssues.controller;
  return c.bcf.topics.filter((t) => t.clash?.check === check).map((t) => {
    const sk = c.sketchesOf(t)[0];
    const m = sk?.markups[0];
    const sh = m?.shape?.points ?? [];
    return {
      guid: t.guid, title: t.title, key: t.clash.key, a: t.clash.a, b: t.clash.b, missing: !!t.clash.missing, status: t.topicStatus, labels: t.labels, type: t.topicType, desc: t.description ?? '',
      comments: t.comments.map((x) => x.text), pin: !!t.pin, snapshot: !!t.viewpoints[0]?.snapshot, sel: (t.viewpoints[0]?.data?.selection ?? []).length,
      attach: m?.attach?.kind ?? null, pen: m?.attach?.penetration ? [m.attach.penetration.mep, m.attach.penetration.host].sort().join('|') : null, meas: m?.attach?.measurement?.elementGuids ?? null,
      inside: sh.length === 2 && sh.flat().every((v) => v > 0 && v < 1), linked: !!sk && c.issueOf(sk.id)?.topic.guid === t.guid,
    };
  });
};
const raisedOf = (kind) => (pg) => pg.evaluate(raisedFn, kind);

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ================================================================ penetrations on synth5k
  {
    const { page, ctx } = await open(browser, 'synth5k');
    const N = await page.evaluate(() => window.__xrayPenetrations.analyse({ scope: 'focus classes' }).rows.length);
    const nNone = await page.evaluate(() => window.__xrayPenetrations.rows.filter((r) => r.status === 'none').length);
    check('synth5k has penetrations to raise', N >= 100, `${N} rows, ${nNone} without opening`);
    await page.evaluate(() => window.__xrayToolbar.open('penetrations'));
    await page.waitForSelector('[data-clash-section=penetration] [data-act=clash-raise]');
    check('the drawer shows the counts before raising', (await page.textContent('[data-clash-section=penetration] [data-clash-counts]')) === `${N} new, 0 already raised, 0 not found in the latest run`);

    // above the batch limit the drawer asks first
    await page.evaluate((k) => { window.__xrayClash.config.maxBatch = k; }, K);
    await page.click('[data-clash-section=penetration] [data-act=clash-raise]');
    await page.waitForSelector('[data-clash-ask] [data-act=clash-raise-top]');
    const ask = await page.evaluate(() => ({ text: document.querySelector('[data-clash-ask]').textContent, top: document.querySelector('[data-act=clash-raise-top]').textContent, all: document.querySelector('[data-act=clash-raise-all]').textContent }));
    check('it asks first and offers "top N by severity"', ask.text.includes(`${N} new results`) && ask.top === `Raise top ${K} by severity` && ask.all === `Raise all ${N}`, JSON.stringify(ask));
    check('asking raised nothing', (await raisedOf('penetration')(page)).length === 0);
    await page.click('[data-act=clash-ask-cancel]');
    check('Cancel closes the question', await page.evaluate(() => !document.querySelector('[data-act=clash-raise-top]')));

    // raise the top K, watching the progress text and the frames
    await page.click('[data-clash-section=penetration] [data-act=clash-raise]');
    await page.evaluate(() => {
      window.__frames = { n: 0, max: 0, last: performance.now(), progress: [] };
      const loop = () => { const t = performance.now(); window.__frames.max = Math.max(window.__frames.max, t - window.__frames.last); window.__frames.last = t; window.__frames.n++; if (!window.__frames.stop) requestAnimationFrame(loop); };
      requestAnimationFrame(loop);
      window.__poll = setInterval(() => { const p = document.querySelector('[data-clash-progress]')?.textContent ?? ''; if (/Raising issues/.test(p)) window.__frames.progress.push(p); }, 15);
    });
    await page.click('[data-act=clash-raise-top]');
    await page.waitForFunction(() => /raised/.test(document.querySelector('[data-clash-progress]')?.textContent ?? ''), null, { timeout: 600000 });
    const fr = await page.evaluate(() => { clearInterval(window.__poll); window.__frames.stop = true; return { n: window.__frames.n, max: Math.round(window.__frames.max), progress: [...new Set(window.__frames.progress)] }; });
    check('progress is shown while raising', fr.progress.length >= 2 && fr.progress.some((p) => /Raising issues \d+ \/ 5/.test(p)), fr.progress.join(' | '));
    check('the page keeps drawing frames between issues', fr.n >= K, `${fr.n} frames, longest gap ${fr.max} ms`);
    const first = await raisedOf('penetration')(page);
    const report = await page.textContent('[data-clash-progress]');
    check('5 issues were raised and the report says so', first.length === K && /^5 raised, 0 already raised, /.test(report) && /left out \(top 5 by severity\)/.test(report), `${first.length}: ${report}`);
    check('titles read "Penetration: A through B"', first.every((x) => /^Penetration: .+ through .+$/.test(x.title)), first[0]?.title);
    check('each has both GlobalIds, the labels clash + penetration, a pin, a snapshot and the check type', first.every((x) => x.a && x.b && x.a !== x.b && x.labels.includes('clash') && x.labels.includes('penetration') && x.pin && x.snapshot && x.type === 'Clash'), JSON.stringify(first[0]?.labels));
    check('the viewpoint selects the pair and the camera frames it (sketch rectangle inside the picture)', first.every((x) => x.sel >= 2 && x.inside), first.map((x) => `${x.sel}/${x.inside}`).join(' '));
    check('each issue has a sketch tied to the pair with the penetration attachment, linked both ways', first.every((x) => x.attach === 'penetration' && x.pen === [x.a, x.b].sort().join('|') && x.linked), first.map((x) => x.attach).join(','));
    check('the worst results come first: the raised ones have no opening when there are enough such rows', nNone < K || first.every((x) => x.desc.startsWith('no opening')), first.map((x) => x.desc.split(';')[0]).join(' / '));
    const openIssues = await page.evaluate(() => window.__xrayIssues.controller.bcf.topics.length);
    check('the Issues panel did not jump into the detail of each new issue', await page.evaluate(() => window.__xrayIssues.detail === null), `${openIssues} topics`);

    // re-run and raise again: no doubles
    await page.evaluate(() => window.__xrayPenetrations.analyse({ scope: 'focus classes' }));
    const c2 = await page.evaluate(() => window.__xrayClash.preview('penetration'));
    check('after a re-run: counts are N-5 new, 5 already raised, 0 not found', c2.fresh === N - K && c2.already === K && c2.resolved === 0, JSON.stringify(c2));
    check('the drawer shows the same counts', (await page.textContent('[data-clash-section=penetration] [data-clash-counts]')) === `${N - K} new, ${K} already raised, 0 not found in the latest run`);
    const r2 = await page.evaluate((k) => window.__xrayClash.raise('penetration', { limit: k }), K);
    const second = await raisedOf('penetration')(page);
    check('raising again adds 5 more, never an old one', r2.raised.length === K && second.length === 2 * K && new Set(second.map((x) => x.key)).size === 2 * K, `${second.length} issues, ${new Set(second.map((x) => x.key)).size} keys`);
    const r3 = await page.evaluate(() => window.__xrayClash.raise('penetration', { limit: 0 }));
    check('raising with nothing new adds nothing', r3.raised.length === 0 && (await raisedOf('penetration')(page)).length === 2 * K && r3.counts.already === 2 * K, JSON.stringify(r3.counts));

    // a result that no longer occurs: a raised issue whose pair is in scope but not a penetration of the run
    const stale = await page.evaluate(() => {
      const c = window.__xrayIssues.controller;
      const m = window.__xray.app.controller.model;
      const rows = window.__xrayPenetrations.rows;
      const pairs = new Set(rows.map((r) => `${r.mep}|${r.host}`));
      const t = c.bcf.topics.find((x) => x.clash?.check === 'penetration');
      const mepId = m.byGlobalId.get(t.clash.a) !== undefined && rows.some((r) => r.mep === m.byGlobalId.get(t.clash.a)) ? m.byGlobalId.get(t.clash.a) : m.byGlobalId.get(t.clash.b);
      const host = rows.find((r) => !pairs.has(`${mepId}|${r.host}`))?.host;
      const a = m.elements[mepId].globalId, b = m.elements[host].globalId;
      const [x, y] = a <= b ? [a, b] : [b, a];
      t.clash = { check: 'penetration', key: `penetration|${x}|${y}`, a: x, b: y };
      return { guid: t.guid, title: t.title };
    });
    const c3 = await page.evaluate(() => window.__xrayClash.preview('penetration'));
    check('a raised pair the run does not report is counted as not found', c3.resolved === 1 && c3.already === 2 * K - 1, JSON.stringify(c3));
    const r4 = await page.evaluate(() => window.__xrayClash.raise('penetration', { limit: 0 }));
    let t = (await raisedOf('penetration')(page)).find((x) => x.guid === stale.guid);
    check('it is marked once with "Not found in latest run", and not deleted', r4.flagged === 1 && t.missing && t.comments.filter((x) => x.startsWith('Not found in latest run')).length === 1, JSON.stringify({ flagged: r4.flagged, comments: t.comments }));
    await page.evaluate(() => window.__xrayClash.raise('penetration', { limit: 0 }));
    t = (await raisedOf('penetration')(page)).find((x) => x.guid === stale.guid);
    check('a second raise does not add the note again', t.comments.filter((x) => x.startsWith('Not found in latest run')).length === 1);
    check('the drawer offers "Close 1 not found"', (await page.textContent('[data-clash-section=penetration] [data-act=clash-close]')) === 'Close 1 not found');
    await page.click('[data-clash-section=penetration] [data-act=clash-close]');
    t = (await raisedOf('penetration')(page)).find((x) => x.guid === stale.guid);
    check('closing sets its status to Closed; the issue stays', t.status === 'Closed' && (await raisedOf('penetration')(page)).length === 2 * K, t.status);

    // BCF round trip: the keys survive the file
    const rt = await page.evaluate(async () => {
      const bytes = await window.__xrayBcf.exportZip('2.1');
      await window.__xrayBcf.load(bytes);
      const c = window.__xrayIssues.controller;
      return { n: c.bcf.topics.filter((x) => x.clash).length, missing: c.bcf.topics.filter((x) => x.clash?.missing).length, preview: window.__xrayClash.preview('penetration') };
    });
    check('the keys and the "not found" mark survive a BCF export and open', rt.n === 2 * K && rt.missing === 1, JSON.stringify(rt));
    check('raising after opening the file makes no doubles', rt.preview.already === 2 * K - 1 && rt.preview.fresh === N - (2 * K - 1), JSON.stringify(rt.preview));
    await ctx.close();
  }

  // ================================================================ clearance on building
  {
    const { page, ctx } = await open(browser, 'building');
    const duct = await page.evaluate(() => window.__xray.app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment')?.id ?? window.__xray.app.loaded.model.elements.find((e) => /Duct|Pipe|Flow/.test(e.ifcClass))?.id);
    await page.evaluate((id) => window.__xray.app.selectIds([id]), duct);
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.__xrayToolbar.open('clearance'));
    await page.evaluate(() => { window.__xrayClearance.settings.tight = 0.6; window.__xrayClearance.settings.max = 1.2; window.__xrayClearance.setEnabled(true); });
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.__xrayClearance.recompute());
    const c0 = await page.evaluate(() => window.__xrayClash.preview('clearance'));
    check('clearance has pairs closer than the tight limit to raise', !!c0 && c0.fresh > 0, JSON.stringify(c0));
    await page.waitForSelector('[data-clash-section=clearance] [data-act=clash-raise]');
    await page.evaluate(() => { window.__xrayClash.config.maxBatch = 200; });
    await page.click('[data-clash-section=clearance] [data-act=clash-raise]');
    await page.waitForFunction(() => /raised/.test(document.querySelector('[data-clash-section=clearance] [data-clash-progress]')?.textContent ?? ''), null, { timeout: 600000 });
    const cl = await raisedOf('clearance')(page);
    check('the issues are raised, one per pair', cl.length === c0.fresh && new Set(cl.map((x) => x.key)).size === cl.length, `${cl.length} of ${c0.fresh}`);
    check('titles read "Clearance n mm < m mm: A / B"', cl.every((x) => /^Clearance \d+ mm < 600 mm: .+ \/ .+$/.test(x.title)), cl[0]?.title);
    check('labels clash + clearance; sketch tied with a measurement of both elements', cl.every((x) => x.labels.includes('clash') && x.labels.includes('clearance') && x.attach === 'measurement' && x.meas?.length === 2 && x.linked && x.inside), JSON.stringify([cl[0]?.labels, cl[0]?.attach, cl[0]?.meas]));
    const c1 = await page.evaluate(() => window.__xrayClash.preview('clearance'));
    check('the counts say 0 new, all already raised', c1.fresh === 0 && c1.already === cl.length && c1.resolved === 0, JSON.stringify(c1));
    await page.evaluate(() => window.__xrayClearance.recompute());
    const r2 = await page.evaluate(() => window.__xrayClash.raise('clearance'));
    check('a re-run and a second raise make no doubles', r2.raised.length === 0 && (await raisedOf('clearance')(page)).length === cl.length, JSON.stringify(r2.counts));
    await ctx.close();
  }

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
