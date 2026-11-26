// Shared machinery of the tours: browser tests that follow the "Try it" walk-throughs of the user manual (docs/manual) and capture its
// pictures. How to write a tour: bench/tours/README.md.
//
//   import { startTour } from './lib.mjs';
//   const tour = await startTour('tour-03-screen');
//   const page = await tour.open('model=fzk-haus');
//   await tour.step('3.1 Try it, step 1: press T twice', async () => { ... tour.check('the strip comes back', ok); });
//   await tour.finish();
//
// Output is PASS / FAIL / KNOWN lines like the smokes, so run-smokes.mjs counts them. A FAIL names the step and quotes the manual.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
export const webRoot = resolve(here, '..', '..');
export const repoRoot = resolve(webRoot, '..');
export const manualDir = resolve(repoRoot, 'docs', 'manual');
export const imgDir = resolve(manualDir, 'img');
/** Pictures are written only when TOUR_PICTURES=1, so a routine run does not rewrite the images. */
export const PICTURES = process.env.TOUR_PICTURES === '1';

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(webRoot, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}

/** The picture ids the manual declares (`> Picture (some-id): text`), id -> caption. */
export function manualPictures() {
  const out = new Map();
  for (const f of readdirSync(manualDir).filter((n) => n.endsWith('.md'))) {
    for (const m of readFileSync(resolve(manualDir, f), 'utf8').matchAll(/^> Picture \(([a-z0-9-]+)\):\s*(.*)$/gm)) out.set(m[1], m[2]);
  }
  return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Start vite on SMOKE_PORT (default 5830) and a headless Chromium. Returns the tour object (see the README for each member).
 * @param {string} name file-less name of the tour, for the output lines
 */
export async function startTour(name) {
  const pw = loadPlaywright();
  const port = Number(process.env.SMOKE_PORT ?? 5830);
  const vite = spawn(resolve(webRoot, 'node_modules/.bin/vite'), ['--config', resolve(webRoot, 'bench/vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: webRoot, stdio: ['ignore', 'pipe', 'pipe'] });
  let viteLog = '';
  vite.stdout.on('data', (d) => (viteLog += d));
  vite.stderr.on('data', (d) => (viteLog += d));
  let up = false;
  for (let i = 0; i < 150 && !up; i++) {
    try { up = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await sleep(200); }
  }
  if (!up) { vite.kill('SIGKILL'); throw new Error(`vite did not start:\n${viteLog}`); }
  const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  const counts = { pass: 0, fail: 0, known: 0 };
  const pictures = [];
  const consoleErrors = [];
  let stepLabel = '';
  const declared = manualPictures();
  const tag = () => (stepLabel ? `${stepLabel}: ` : '');

  const tour = {
    name, port, browser, counts, pw,

    /** A recorded step of the manual. The label starts with the section number and says which Try it step it is. A throw is a FAIL and the tour goes on. */
    async step(label, fn) {
      stepLabel = label;
      console.log(`STEP ${label}`);
      try { await fn(); } catch (e) { tour.check('the step could be carried out', false, String(e?.message ?? e).split('\n')[0]); }
    },

    /** A check of what the manual says you will see. `name` is the manual's own wording. */
    check(checkName, ok, detail = '') {
      if (ok) counts.pass++; else counts.fail++;
      console.log(`${ok ? 'PASS' : 'FAIL'} ${tag()}${checkName}${detail ? ` (${detail})` : ''}`);
      return !!ok;
    },

    /** A check that fails because the product looks wrong, not the manual: printed as KNOWN, not counted as a failure. `issue` says what is wrong. */
    known(checkName, ok, issue, detail = '') {
      if (ok) { counts.pass++; console.log(`PASS ${tag()}${checkName}${detail ? ` (${detail})` : ''}`); return true; }
      counts.known++;
      console.log(`KNOWN ${tag()}${checkName} - ${issue}${detail ? ` (${detail})` : ''}`);
      return false;
    },

    /** Wait until the text of `scope` (a page or a locator) matches `pattern` (string = contains, RegExp), then check it, quoting what the manual says. */
    async expectText(scope, pattern, manualSays, timeout = 20000) {
      const loc = typeof scope.innerText === 'function' ? scope : scope.locator('body');
      const test = (t) => (pattern instanceof RegExp ? pattern.test(t) : t.includes(pattern));
      let text = '';
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) {
        text = await loc.first().innerText({ timeout: 2000 }).catch(() => '');
        if (test(text)) break;
        await sleep(250);
      }
      return tour.check(`the manual says: ${manualSays}`, test(text), test(text) ? '' : `saw "${text.replace(/\s+/g, ' ').slice(0, 160)}"`);
    },

    /**
     * Open a page on the served viewer and wait until it is ready. `query` is the part after `?` (default `model=building`).
     * Options: width, height (default 1400x900), init (a function run before the page scripts), url (a full URL instead, e.g. file:///...),
     * onRequest (called with every request), route (a page.route handler for every URL, e.g. to answer map tile requests offline).
     */
    async open(query = 'model=building', { width = 1400, height = 900, init, url, onRequest, route } = {}) {
      const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: PICTURES ? 2 : 1, colorScheme: 'light', acceptDownloads: true });
      const page = await ctx.newPage();
      page.setDefaultTimeout(90000);
      page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
      page.on('pageerror', (e) => { consoleErrors.push(`pageerror: ${e.message}`); });
      if (init) await page.addInitScript(init);
      if (onRequest) page.on('request', (r) => onRequest(r));
      if (route) await page.route('**/*', route);
      await page.goto(url ?? `http://127.0.0.1:${port}/?${query}`, { timeout: 240000 });
      await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
      const err = await page.evaluate('window.__xrayError');
      if (err) throw new Error(`startup failed: ${String(err).split('\n')[0]}`);
      await ui.settle(page);
      return page;
    },

    /**
     * Save docs/manual/<img>/<id>.jpg (only when TOUR_PICTURES=1; the id must be declared by a `> Picture (id):` note in the manual).
     * Options: clip {x,y,width,height} in CSS pixels | element (a selector, with pad px around it, default 0). Whole viewport otherwise.
     * scale: 'device' (default, the context is at deviceScaleFactor 2 when pictures are on) or 'css' (1x).
     * Pass `png: true` for a sharp-edged picture (written as <id>.png); everything else is a JPEG at quality 80.
     * Returns the Buffer (also when pictures are off, so `pictureRow` can still be exercised) or null when off.
     */
    async picture(id, { page, clip, element, pad = 0, scale = 'device', png = false } = {}) {
      if (!PICTURES) return null;
      const buf = await tour.shot(page, { clip, element, pad, scale, png });
      tour.savePicture(id, buf, png);
      return buf;
    },

    /** Take a screenshot without saving it (the pieces of a composite picture). */
    async shot(page, { clip, element, pad = 0, scale = 'device', png = false } = {}) {
      if (element) {
        const b = await page.locator(element).first().boundingBox();
        if (!b) throw new Error(`picture: no box for ${element}`);
        const vp = page.viewportSize();
        const x = Math.max(0, b.x - pad), y = Math.max(0, b.y - pad);
        clip = { x, y, width: Math.min(vp.width - x, b.width + 2 * pad), height: Math.min(vp.height - y, b.height + 2 * pad) };
      }
      return page.screenshot({ type: png ? 'png' : 'jpeg', ...(png ? {} : { quality: 80 }), scale, ...(clip ? { clip } : {}), timeout: 180000 });
    },

    savePicture(id, buf, png = false) {
      if (!declared.has(id)) { tour.check(`picture "${id}" is declared in the manual`, false, 'no `> Picture (id):` note has this id'); return; }
      mkdirSync(imgDir, { recursive: true });
      const file = resolve(imgDir, `${id}.${png ? 'png' : 'jpg'}`);
      writeFileSync(file, buf);
      pictures.push({ id, bytes: buf.length });
      console.log(`PICTURE ${id} ${(buf.length / 1024).toFixed(0)} KB -> docs/manual/img/${id}.${png ? 'png' : 'jpg'}`);
    },

    /**
     * Several shots side by side in one picture, each under a caption: `panels` is [{ buf, label }] from `tour.shot`.
     * Written only when TOUR_PICTURES=1. Uses a scratch page, so the panels keep their size.
     */
    async pictureRow(id, panels) {
      if (!PICTURES) return null;
      const ctx = await browser.newContext({ viewport: { width: 1600, height: 600 }, deviceScaleFactor: 1, colorScheme: 'light' });
      const p = await ctx.newPage();
      const cells = panels.map((q) => `<figure><img src="data:image/jpeg;base64,${q.buf.toString('base64')}"><figcaption>${q.label}</figcaption></figure>`).join('');
      await p.setContent(`<style>body{margin:0;background:#fff;font:600 22px system-ui,sans-serif;color:#172026}.r{display:flex;gap:12px;padding:12px;align-items:flex-start;width:max-content}figure{margin:0;display:block}img{display:block;height:auto;width:${Math.floor(1560 / panels.length)}px;border:1px solid #c8d2d7}figcaption{padding:8px 2px 2px;text-align:center}</style><div class="r">${cells}</div>`);
      await p.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
      const box = await p.locator('.r').boundingBox();
      await p.setViewportSize({ width: Math.ceil(box.width), height: Math.ceil(box.height) });
      const buf = await p.screenshot({ type: 'jpeg', quality: 80, timeout: 180000 });
      await ctx.close();
      tour.savePicture(id, buf);
      return buf;
    },

    /**
     * Draw labelled boxes over parts of the page for a picture (the screen map). items: [{ selector | rect, text, side?: 'top'|'bottom'|'left'|'right'|'inside' }].
     * `tour.unannotate(page)` removes them.
     */
    async annotate(page, items) {
      await page.evaluate((items) => {
        document.getElementById('tour-annotations')?.remove();
        const layer = document.createElement('div');
        layer.id = 'tour-annotations';
        layer.style.cssText = 'position:fixed;inset:0;z-index:2147483000;pointer-events:none;font:600 14px system-ui,sans-serif';
        for (const it of items) {
          let r = it.rect;
          if (it.selector) {
            const el = [...document.querySelectorAll(it.selector)].find((e) => e.getBoundingClientRect().width > 0);
            if (!el) continue;
            const b = el.getBoundingClientRect();
            r = { x: b.left, y: b.top, width: b.width, height: b.height };
          }
          const box = document.createElement('div');
          box.style.cssText = `position:absolute;left:${r.x}px;top:${r.y}px;width:${r.width}px;height:${r.height}px;border:3px solid #d1480f;border-radius:6px;box-sizing:border-box`;
          const tag = document.createElement('div');
          tag.textContent = it.text;
          const side = it.side ?? 'inside';
          const pos = side === 'bottom' ? `left:${r.x}px;top:${r.y + r.height + 4}px` : side === 'top' ? `left:${r.x}px;top:${Math.max(0, r.y - 28)}px` : side === 'left' ? `right:${innerWidth - r.x + 4}px;top:${r.y}px` : side === 'right' ? `left:${r.x + r.width + 4}px;top:${r.y}px` : `left:${r.x + 6}px;top:${r.y + 6}px`;
          tag.style.cssText = `position:absolute;${pos};background:#d1480f;color:#fff;padding:2px 8px;border-radius:4px;white-space:nowrap`;
          layer.append(box, tag);
        }
        document.body.appendChild(layer);
      }, items);
    },
    async unannotate(page) { await page.evaluate(() => document.getElementById('tour-annotations')?.remove()); },

    /** Close the browser, stop vite, print the totals and exit (code 1 on a FAIL). Always call it last. */
    async finish() {
      if (consoleErrors.length) {
        const own = consoleErrors.filter((e) => e.startsWith('pageerror'));
        console.log(`INFO ${consoleErrors.length} console errors, ${own.length} uncaught`);
        for (const e of consoleErrors.slice(0, 6)) console.log(`INFO   ${e.slice(0, 200)}`);
        tour.check('no uncaught exception in the page', own.length === 0, own[0]?.slice(0, 160));
      }
      await browser.close().catch(() => {});
      vite.kill('SIGKILL');
      const total = PICTURES ? `, ${pictures.length} pictures, ${(pictures.reduce((a, p) => a + p.bytes, 0) / 1024).toFixed(0)} KB` : '';
      console.log(`${name}: ${counts.pass} passed, ${counts.fail} failed, ${counts.known} known issues${total}`);
      process.exit(counts.fail ? 1 : 0);
    },
  };

  // A crash outside a step still ends the tour with a FAIL, a clean browser and no vite left behind.
  const bail = (e) => {
    console.log(`FAIL ${tag()}the tour stopped: ${String(e?.stack ?? e).split('\n').slice(0, 3).join(' | ')}`);
    counts.fail++;
    tour.finish();
  };
  process.on('uncaughtException', bail);
  process.on('unhandledRejection', bail);
  return tour;
}

// ---------------------------------------------------------------------------------------------------------------------------------
// Page helpers: what a person does with the screen. Each takes the page first.

const MARK = 'data-tour-ref';

export const ui = {
  /** Let the x-ray classification and the camera animation finish. */
  async settle(page, ms = 400) {
    await page.evaluate(() => { try { window.__xray?.app.controller.settle(); } catch { /* not ready */ } });
    await page.waitForTimeout(ms);
  },

  /** The tabs of both sidebars are role=tab with the label as name: ui.tab(page, 'Parameters'). */
  async tab(page, name) {
    const t = page.getByRole('tab', { name, exact: true });
    await t.first().click();
    return t.first();
  },

  /** A button by its visible label or accessible name (the tool strip and the cube buttons carry theirs as aria-label). */
  button(page, name, opts = {}) { return page.getByRole('button', { name, exact: opts.exact ?? true, ...opts }).first(); },

  /** The tool strip button of a tool, by its label ("Open model", "X-ray", ...). */
  tool(page, label) { return page.locator(`#xray-toolbar button[aria-label="${label}"]`); },

  /** The status bar text. */
  statusText(page) { return page.locator('#xray-overlay').innerText(); },

  /** A screen spot where the element shows (the nearest to the middle of the canvas that is not covered by a panel), by trying it with a pick. */
  async spotOf(page, id) { return (await ui.spotsOf(page, id))[0]; },
  async spotsOf(page, id) {
    return page.evaluate((id) => {
      const app = window.__xray.app, cm = app.renderer.camera, cv = app.canvas.getBoundingClientRect();
      cm.updateMatrixWorld();
      const e = app.controller.model.elements.find((x) => x.id === id), b = e.bounds, out = [];
      for (const fx of [0.5, 0.25, 0.75]) for (const fy of [0.5, 0.25, 0.75]) for (const fz of [0.5, 0.25, 0.75]) {
        const v = cm.position.clone().set(b[0] + (b[3] - b[0]) * fx, b[1] + (b[4] - b[1]) * fy, b[2] + (b[5] - b[2]) * fz).project(cm);
        const x = cv.left + (v.x * 0.5 + 0.5) * cv.width, y = cv.top + (1 - (v.y * 0.5 + 0.5)) * cv.height;
        if (x > cv.left + 8 && x < cv.right - 8 && y > cv.top + 8 && y < cv.bottom - 8 && document.elementFromPoint(x, y) === app.canvas) out.push({ x, y, d: Math.hypot(v.x, v.y) });
      }
      return out.sort((a, b) => a.d - b.d);
    }, id);
  },

  /** Park the pointer over empty sky near the top right of the canvas (no tooltip, no hover card), for pictures. */
  async park(page) { const c = await page.locator('#c').boundingBox(); await page.mouse.move(c.x + c.width * 0.9, c.y + 90); await page.waitForTimeout(300); },

  /** Wait until the camera has stopped (a glide or a fly-to is over). */
  async waitStill(page, maxMs = 15000) {
    await page.waitForTimeout(1200); // a glide may start a moment after the click on a slow machine
    let last = null, same = 0;
    for (let t = 0; t < maxMs && same < 2; t += 400) {
      const c = JSON.stringify((await ui.cam(page)).p.map((v) => +v.toFixed(3)));
      same = c === last ? same + 1 : 0;
      last = c;
      await page.waitForTimeout(400);
    }
    await ui.settle(page, 300);
  },

  /** After a key that starts a glide (PageUp, a cube click): wait until the camera has left `from` (a cam() result), then until it is still. */
  async waitMoved(page, from, maxMs = 20000) {
    for (let t = 0; t < maxMs; t += 400) {
      const c = await ui.cam(page);
      if (Math.hypot(...c.p.map((v, i) => v - from.p[i])) > 0.3) break;
      await page.waitForTimeout(400);
    }
    await ui.waitStill(page, maxMs);
  },

  /** The camera: position, target and the distance, for "the view changed" checks. */
  cam(page) {
    return page.evaluate(() => {
      const r = window.__xray.app.renderer, c = r.camera.position, t = r.controls.target;
      return { p: [c.x, c.y, c.z], t: [t.x, t.y, t.z], d: c.distanceTo(t) };
    });
  },
  /** Put the camera somewhere (for a picture); `settle` follows. */
  async setCam(page, pos, target) {
    await page.evaluate(([p, t]) => {
      const r = window.__xray.app.renderer;
      window.__cinematic?.cancelFlight?.();
      r.camera.position.set(...p); r.controls.target.set(...t); r.controls.update();
    }, [pos, target]);
    await ui.settle(page);
  },

  /** The ids and classes of the selection. */
  selection(page) {
    return page.evaluate(() => {
      const a = window.__xray.app, sel = a.selection, els = a.controller.model.elements;
      return sel.map((id) => { const e = els.find((x) => x.id === id); return { id, cls: e?.ifcClass, name: e?.name }; });
    });
  },

  /** Clear the selection the way a person does: Esc until it is empty. */
  async clearSelection(page) {
    for (let i = 0; i < 3 && (await ui.selection(page)).length; i++) { await page.keyboard.press('Escape'); await page.waitForTimeout(150); }
  },

  /**
   * Click an element on the canvas like a person: find a spot where it shows, click it, and orbit with the mouse when it is hidden
   * (the manual says "orbit until you find one"). `want` is plain data, because it is evaluated in the page:
   * { cls: 'IfcDuctSegment' | ['IfcWall', ...] | /IfcDuct/ (a RegExp is matched as its source), name?: RegExp, id?: number }.
   * Returns { id, cls, name } of the element that ended up selected, or null.
   */
  async clickElement(page, want, { orbits = 6, tree = true } = {}) {
    const w = { cls: want.cls instanceof RegExp ? { re: want.cls.source } : want.cls, name: want.name?.source, id: want.id };
    const PRED = `(w) => (e) => {
      if (w.id !== undefined && e.id !== w.id) return false;
      if (w.cls !== undefined) {
        const c = e.ifcClass;
        const ok = typeof w.cls === 'string' ? c === w.cls : Array.isArray(w.cls) ? w.cls.includes(c) : new RegExp(w.cls.re).test(c);
        if (!ok) return false;
      }
      return !w.name || new RegExp(w.name).test(e.name ?? '');
    }`;
    for (let round = 0; round <= orbits; round++) {
      const cands = await page.evaluate(([PRED, w]) => {
        const pred = (0, eval)(PRED)(w);
        const app = window.__xray.app, cm = app.renderer.camera, cv = app.canvas.getBoundingClientRect();
        cm.updateMatrixWorld();
        const out = [];
        for (const e of app.controller.model.elements) {
          if (!pred(e)) continue;
          const b = e.bounds;
          for (const fx of [0.5, 0.25, 0.75, 0.1, 0.9]) for (const fy of [0.5, 0.25, 0.75]) for (const fz of [0.5, 0.25, 0.75]) {
            const v = cm.position.clone().set(b[0] + (b[3] - b[0]) * fx, b[1] + (b[4] - b[1]) * fy, b[2] + (b[5] - b[2]) * fz).project(cm);
            if (v.z > 1 || v.z < -1) continue;
            const x = cv.left + (v.x * 0.5 + 0.5) * cv.width, y = cv.top + (1 - (v.y * 0.5 + 0.5)) * cv.height;
            if (x < cv.left + 8 || x > cv.right - 8 || y < cv.top + 8 || y > cv.bottom - 8) continue;
            if (document.elementFromPoint(x, y) !== app.canvas) continue; // a panel or a button is on top of that spot
            out.push({ x, y, id: e.id, dist: Math.hypot(v.x, v.y) });
          }
        }
        // at most 6 spots per element, so one big element does not use up the list
        const per = new Map(), pick = [];
        for (const o of out.sort((a, b) => a.dist - b.dist)) { const n = per.get(o.id) ?? 0; if (n < 6) { per.set(o.id, n + 1); pick.push(o); } }
        return pick.slice(0, 120);
      }, [PRED, w]);
      for (const c of cands) {
        await page.mouse.click(c.x, c.y);
        await page.waitForTimeout(120);
        const sel = await page.evaluate(([PRED, w]) => {
          const pred = (0, eval)(PRED)(w);
          const a = window.__xray.app;
          const e = a.controller.model.elements.find((x) => x.id === a.selection[0]);
          return e && pred(e) ? { id: e.id, cls: e.ifcClass, name: e.name } : null;
        }, [PRED, w]);
        if (sel) { await ui.settle(page, 200); return { ...sel, x: c.x, y: c.y }; }
      }
      // Hidden from here: orbit a little with the left mouse button (Hand mode) and look again.
      const cv = await page.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { x: r.left + r.width * 0.6, y: r.top + r.height * 0.6 }; });
      await page.mouse.move(cv.x, cv.y);
      await page.mouse.down();
      await page.mouse.move(cv.x + (round % 2 ? -90 : 90), cv.y + (round % 3 === 0 ? 30 : -20), { steps: 5 });
      await page.mouse.up();
      await ui.settle(page, 300);
    }
    // Still hidden behind other parts (a duct inside a wall): a person would pick it in the Model tree, by its class row.
    if (tree && want.cls) {
      const cls = typeof want.cls === 'string' ? want.cls : await page.evaluate((re) => { const r = new RegExp(re); return window.__xray.app.controller.model.elements.map((e) => e.ifcClass).find((c) => r.test(c)) ?? null; }, want.cls.source);
      if (cls) {
        await ui.tab(page, 'Model');
        await page.locator('#sidebar').getByText(cls, { exact: true }).first().click().catch(() => {});
        await ui.settle(page, 500);
        const s = await ui.selection(page);
        if (s.length && s.every((e) => e.cls === cls)) return { ...s[0], viaTree: true };
      }
    }
    return null;
  },

  // ---- the Parameters tab (lil-gui): folders and controls by their visible names
  /** Find a folder by its title (starts with; nested titles in order) and open it by clicking the title when it is closed. */
  async folder(page, ...titles) {
    for (const title of titles) {
      const ok = await page.evaluate(([title, MARK]) => {
        document.querySelectorAll(`[${MARK}]`).forEach((n) => n.removeAttribute(MARK));
        const scope = window.__tourFolder ?? document;
        const all = [...scope.querySelectorAll('.lil-gui:not(.lil-root)')];
        const f = all.find((n) => n.querySelector(':scope > .lil-title')?.textContent.trim().toLowerCase().startsWith(title.toLowerCase()));
        if (!f) return false;
        f.setAttribute(MARK, '1');
        return true;
      }, [title, MARK]);
      if (!ok) throw new Error(`no folder "${title}" in the Parameters tab`);
      const f = page.locator(`[${MARK}]`);
      if (await f.evaluate((n) => n.classList.contains('lil-closed') || n.querySelector(':scope > .lil-title')?.getAttribute('aria-expanded') === 'false')) await f.locator('> .lil-title').click();
      await page.evaluate(([MARK]) => { window.__tourFolder = document.querySelector(`[${MARK}]`); }, [MARK]);
    }
    return page.locator(`[${MARK}]`);
  },
  /** Forget the folder scope (the next `folder` starts from the top of the panel). */
  async topOfPanel(page) { await page.evaluate(() => { window.__tourFolder = null; }); },

  /** A control (`.lil-controller`) by its visible name; in the folder opened last, else anywhere in the panel. */
  async control(page, name, { exact = true } = {}) {
    const found = await page.evaluate(([name, exact, MARK]) => {
      document.querySelectorAll(`[${MARK}-c]`).forEach((n) => n.removeAttribute(`${MARK}-c`));
      const scope = window.__tourFolder ?? document;
      const list = [...scope.querySelectorAll('.lil-controller')].filter((c) => {
        const t = c.querySelector('.lil-name')?.textContent.trim() ?? '';
        return exact ? t === name : t.toLowerCase().includes(name.toLowerCase());
      });
      const vis = list.find((c) => c.getBoundingClientRect().height > 0) ?? list[0];
      if (!vis) return false;
      vis.setAttribute(`${MARK}-c`, '1');
      return true;
    }, [name, exact, MARK]);
    if (!found) throw new Error(`no control "${name}" in the Parameters tab`);
    const c = page.locator(`[${MARK}-c]`);
    await c.scrollIntoViewIfNeeded();
    return c;
  },
  /** Click a button control (lil-gui button) by its visible name. */
  async press(page, name, opts) { await (await ui.control(page, name, opts)).locator('button').first().click(); },
  /** Set a control the way a person does: tick a box, choose from a list by its label, or type a number. Returns the control. */
  async set(page, name, value, opts) {
    const c = await ui.control(page, name, opts);
    const sel = c.locator('select');
    if (await sel.count()) { await sel.selectOption({ label: String(value) }); return c; }
    const box = c.locator('input[type=checkbox]');
    if (await box.count()) { if ((await box.isChecked()) !== !!value) await box.click(); return c; }
    const inp = c.locator('input[type=text], input:not([type])').first();
    await inp.fill(String(value)); await inp.press('Enter');
    return c;
  },
  /** Drag a slider control (lil-gui) sideways by dx px: one gesture, one undo step. */
  async dragSlider(page, name, dx = 60) {
    const c = await ui.control(page, name);
    const b = await c.locator('.lil-slider').boundingBox();
    const y = b.y + b.height / 2, x = b.x + b.width * 0.5;
    await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + dx, y, { steps: 5 }); await page.mouse.up();
  },
  /** The value shown by a control: a checkbox's state, a list's chosen label, or the text of the field. */
  async valueOf(page, name, opts) {
    const c = await ui.control(page, name, opts);
    return c.evaluate((n) => {
      const s = n.querySelector('select'); if (s) return s.selectedOptions[0]?.textContent ?? '';
      const b = n.querySelector('input[type=checkbox]'); if (b) return b.checked;
      const i = n.querySelector('input'); return i ? (i.value || i.title || '') : n.querySelector('.lil-widget')?.textContent.trim() ?? '';
    });
  },

  /** The text of the hover card, when one shows. */
  hoverCardText(page) { return page.locator('#xray-hover-card').innerText({ timeout: 1000 }).catch(() => ''); },

  /** Model summary: name, element count, classes. */
  model(page) {
    return page.evaluate(() => {
      const a = window.__xray.app, els = a.controller.model.elements;
      const classes = {};
      for (const e of els) classes[e.ifcClass] = (classes[e.ifcClass] ?? 0) + 1;
      return { name: a.modelName, n: els.length, classes };
    });
  },

  /** The five top-bar modes: click one by its label. */
  async mode(page, label) { await page.locator('#xray-topbar').getByRole('button', { name: new RegExp(`^${label}`) }).click(); await ui.settle(page, 500); },
  /** The label of the lit top-bar mode, or null. */
  litMode(page) { return page.evaluate(() => document.querySelector('#xray-topbar .tb-mode[aria-pressed=true]')?.textContent?.trim() ?? null); },

  /** What the x-ray did: bucket sizes, how many elements are faint (alpha < 0.95), the faintest alpha, and the alpha of chosen elements ({ ids }). */
  xray(page, ids = []) {
    return page.evaluate((ids) => {
      const a = window.__xray.app, c = a.controller, al = c.state.alpha, cl = c.classification;
      let faint = 0, min = 1;
      for (let i = 0; i < al.length; i++) { if (al[i] < 0.95) faint++; if (al[i] < min) min = al[i]; }
      const els = c.model.elements;
      const faintByClass = {}, faintIds = [];
      for (const e of els) if (al[e.id] < 0.95) { faintByClass[e.ifcClass] = (faintByClass[e.ifcClass] ?? 0) + 1; faintIds.push(e.id); }
      return { on: a.settings.xray, focus: cl.focus.size, host: cl.host.size, near: cl.near.size, far: cl.far.size, faint, min, faintByClass, faintIds, alpha: Object.fromEntries(ids.map((i) => [i, al[i]])), focusIds: [...cl.focus] };
    }, ids);
  },

  /** The colour of one screen pixel (CSS px), as [r, g, b], from a 1x1 screenshot. */
  async pixel(page, x, y) {
    const { inflateSync } = await import('node:zlib');
    const png = await page.screenshot({ type: 'png', clip: { x, y, width: 1, height: 1 }, scale: 'css' });
    let o = 8, idat = [], ct = 2, bd = 8;
    while (o < png.length) {
      const len = png.readUInt32BE(o), type = png.toString('ascii', o + 4, o + 8);
      if (type === 'IHDR') { bd = png[o + 16]; ct = png[o + 17]; }
      if (type === 'IDAT') idat.push(png.subarray(o + 8, o + 8 + len));
      o += 12 + len;
    }
    const raw = inflateSync(Buffer.concat(idat));
    const ch = ct === 6 ? 4 : ct === 2 ? 3 : ct === 0 ? 1 : 3;
    void bd;
    return ch === 1 ? [raw[1], raw[1], raw[1]] : [raw[1], raw[2], raw[3]];
  },

  /** Press keys with a short pause after, so the viewer has taken the key before the next check. */
  async press_keys(page, ...keys) { for (const k of keys) { await page.keyboard.press(k); await page.waitForTimeout(200); } },
};
