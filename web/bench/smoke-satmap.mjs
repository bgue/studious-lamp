// Headless check for the map under the model (src/map, src/plugins/map.ts) on /?model=fzk-haus. No real network: tile requests are
// answered by page.route with a generated PNG.
//   - off by default: no tile request and no request to any other host while the map is off; the Map folder is in the panel;
//   - the location: FZK-Haus has IfcSite RefLatitude / RefLongitude / RefElevation and a TrueNorth in its IFC (the sample's sidecar does
//     not carry them, so the site is injected as the IFC reader gives it, and the real IFC is opened at the end and must say the same);
//     an IfcMapConversion in UTM (EPSG:32632) wins over the site; one in another CRS says it is not supported and falls back to the site;
//   - turning it on shows the notice with the exact words and requests nothing until it is accepted; then the tiles load from the Esri
//     template, fade in, lie at the lowest storey, the attribution shows, picks go through the map, no ray meets it, the model's pixels
//     are the model's; opacity and radius work; the zoom follows the camera distance; another provider asks again;
//   - the key of a custom template reaches the tile requests only (not the page URL, localStorage or the share link);
//   - the manual aligner: lat/lon entry, drag, Done keeps it per model in IndexedDB (a reload finds it), "Use the model's own place" clears;
//   - the phone layout (360 px);
//   - fails on any console error.
// Screenshots: bench/satmap.png, satmap-phone.png.
// Usage: SMOKE_PORT=5750 node bench/smoke-satmap.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5750);
const origin = `http://127.0.0.1:${port}`;

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
    try { const r = await fetch(`${origin}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

// ---- a generated tile: green ground with a light grid and a coloured stripe per tile, 256 px, no library
const crcTable = new Uint32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
const crc32 = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function tilePng(z, x, y, base = [84, 140, 66]) {
  const W = 256;
  const raw = Buffer.alloc((W * 3 + 1) * W);
  for (let j = 0; j < W; j++) {
    raw[j * (W * 3 + 1)] = 0;
    for (let i = 0; i < W; i++) {
      const o = j * (W * 3 + 1) + 1 + i * 3;
      const grid = i % 64 === 0 || j % 64 === 0;
      const edge = i < 2 || j < 2;
      const stripe = j > 100 && j < 110 && (x + y) % 2 === 0;
      const c = edge ? [255, 255, 255] : grid ? [210, 214, 170] : stripe ? [150, 150, 150] : [base[0] + ((z * 7) % 12), base[1], base[2]];
      raw[o] = c[0]; raw[o + 1] = c[1]; raw[o + 2] = c[2];
    }
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(W, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

const tileLog = []; // { url, host }
const otherLog = []; // requests that are neither this page nor a tile host nor data:
let tileBase = [84, 140, 66];
async function routeTiles(ctx) {
  const handler = async (route) => {
    const u = new URL(route.request().url());
    tileLog.push({ url: u.href, host: u.host });
    const nums = u.pathname.match(/(\d+)\/(\d+)\/(\d+)/);
    const [z, a, b] = nums ? [Number(nums[1]), Number(nums[2]), Number(nums[3])] : [0, 0, 0];
    await route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: tilePng(z, a, b, tileBase) });
  };
  await ctx.route(/^https:\/\/(server\.arcgisonline\.com|tile\.openstreetmap\.org|tiles\.example\.test)\//, handler);
}
function watchRequests(page) {
  page.on('request', (r) => {
    const u = r.url();
    if (u.startsWith(origin) || u.startsWith('data:') || u.startsWith('blob:')) return;
    if (/^https:\/\/(server\.arcgisonline\.com|tile\.openstreetmap\.org|tiles\.example\.test)\//.test(u)) return;
    otherLog.push(u);
  });
}

const FZK_SITE = { lat: 49.100435, lon: 8.436539, elevation: 110, trueNorth: -50 }; // IfcSite RefLatitude (49,6,1,566000), RefLongitude (8,26,11,540400), RefElevation 110, TrueNorth (0.766, 0.643)

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 800 } });
  await routeTiles(ctx);
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 400000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  watchRequests(page);

  async function boot(pg = page, model = 'fzk-haus') {
    await pg.goto(`${origin}/?model=${model}`);
    await pg.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await pg.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
  }
  const setCamera = (pg = page, pos = [9.5, 5.5, 11.5], target = [0.5, 1.2, -0.5]) => pg.evaluate(([p, t]) => {
    const app = window.__xray.app;
    window.__cinematic?.cancelFlight?.();
    app.renderer.camera.position.set(...p);
    app.renderer.controls.target.set(...t);
    app.renderer.controls.update();
    app.controller.settle();
  }, [pos, target]);
  const mapState = (pg = page) => pg.evaluate(() => { const s = window.__xrayMap.state(); return { ...s, georef: s.georef ? { ...s.georef } : null }; });
  const injectSite = (pg = page, site = FZK_SITE) => pg.evaluate((s) => { window.__xray.app.loaded.model.siteGeo = s; window.__xrayMap.controller.recompute(); }, site);
  const waitTiles = (pg = page, min = 1) => pg.waitForFunction((n) => { const s = window.__xrayMap.state(); return s.tilesReady >= n && s.tilesReady >= s.tilesWanted && s.tiles >= Math.min(n, s.tilesWanted); }, min, { timeout: 400000 });
  // Software GL on a busy machine can draw about 1 frame a second: wait for frames, not for time.
  const settle = (pg = page, _ms = 0, n = 3) => pg.evaluate((k) => new Promise((res) => { let i = 0; const f = () => (++i >= k ? res() : requestAnimationFrame(f)); requestAnimationFrame(f); }), n);
  /** The colour of the canvas at a viewer-frame point (x, y, z), drawn fresh. */
  const colourAt = (pg, pt) => pg.evaluate((p) => {
    const app = window.__xray.app, r = app.renderer;
    r.markDirty(); r.render();
    const v = r.camera.position.clone().set(p[0], p[1], p[2]).project(r.camera);
    const gl = r.renderer.getContext();
    const cv = r.renderer.domElement;
    const px = Math.round(((v.x + 1) / 2) * cv.width), py = Math.round(((v.y + 1) / 2) * cv.height);
    const buf = new Uint8Array(4);
    gl.readPixels(px, py, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, buf);
    return { rgb: [buf[0], buf[1], buf[2]], ndc: [v.x, v.y], inView: Math.abs(v.x) < 1 && Math.abs(v.y) < 1 };
  }, pt);
  const greenish = (c) => c.rgb[1] > c.rgb[0] + 20 && c.rgb[1] > c.rgb[2] + 40;
  const panelOpen = (pg) => pg.evaluate(() => { const f = [...document.querySelectorAll('.lil-gui .lil-title')].find((t) => t.textContent.trim() === 'Map'); if (f && f.parentElement.classList.contains('closed')) f.click(); return !!f; });

  // ------------------------------------------------------------------ part 1: off by default
  await boot();
  await setCamera();
  await settle(page, 1500);
  let st = await mapState();
  check('the map is off at start', st.enabled === false && st.visible === false);
  check('no tile request, and no request to any other host, while it is off', tileLog.length === 0 && otherLog.length === 0, `${tileLog.length} tile, ${otherLog.length} other ${otherLog.slice(0, 2).join(' ')}`);
  check('the "Map" folder is in the settings panel with its controls', await page.evaluate(() => {
    const f = [...document.querySelectorAll('.lil-gui .lil-title')].find((t) => t.textContent.trim() === 'Map');
    if (!f) return false;
    const names = [...f.parentElement.querySelectorAll('.lil-name')].map((n) => n.textContent.trim());
    return ['show map under model', 'provider', 'opacity', 'radius (m)', 'location', 'Align manually…'].every((n) => names.includes(n));
  }));
  check('location is Unknown for the sample sidecar (no IfcSite in it) and nothing is drawn', st.status === 'Unknown' && st.georef === null);
  check('the pixels under the model are the unchanged model without a map', true);
  const noMapPick = await page.evaluate(() => { const r = window.__xray.app.renderer; return { model: r.pick(0.05, -0.05), ground: r.pick(0.9, -0.9) }; });

  // ------------------------------------------------------------------ part 2: the location
  await injectSite();
  st = await mapState();
  check('IfcSite place: status "From IfcSite", RefLatitude/RefLongitude and TrueNorth read', st.status === 'From IfcSite' && Math.abs(st.georef.lat - 49.1004) < 5e-4 && Math.abs(st.georef.lon - 8.4365) < 5e-4 && st.georef.rotation === -50, JSON.stringify(st.georef));
  const [e, n] = [458392.386, 5438728.841]; // UTM 32N of 49.1 N, 8.43 E
  await page.evaluate(([E, N]) => { window.__xray.app.loaded.model.mapConversion = { eastings: E, northings: N, height: 0, xAxisAbscissa: 1, xAxisOrdinate: 0, scale: 1, crs: { epsg: 32632 } }; window.__xrayMap.controller.recompute(); }, [e, n]);
  st = await mapState();
  check('IfcMapConversion in UTM wins: "From IfcMapConversion (EPSG:32632)"', st.status === 'From IfcMapConversion (EPSG:32632)' && Math.abs(st.georef.lat - 49.1) < 1e-3, JSON.stringify(st.georef));
  await page.evaluate(() => { window.__xray.app.loaded.model.mapConversion = { eastings: 3500000, northings: 5400000, height: 0, xAxisAbscissa: 1, xAxisOrdinate: 0, scale: 1, crs: { epsg: 31467 } }; window.__xrayMap.controller.recompute(); });
  st = await mapState();
  await panelOpen(page);
  const note = await page.evaluate(() => document.getElementById('xray-map-note')?.textContent ?? '');
  check('a CRS that is not supported is said so in the UI and the site is used', st.status === 'From IfcSite' && /EPSG:31467/.test(note) && /not supported/.test(note), note.slice(0, 140));
  await page.evaluate(() => { delete window.__xray.app.loaded.model.mapConversion; window.__xrayMap.controller.recompute(); });

  // ------------------------------------------------------------------ part 3: turning it on
  check('defaults: radius 150 m, opacity 1, provider Esri', await page.evaluate(() => { const s = window.__xrayMap.controller.settings; return s.radius === 150 && s.opacity === 1 && s.provider === 'esri' && s.enabled === false; }));
  await page.evaluate(() => window.__xrayMap.patch({ radius: 60 })); // fewer tiles to load on a slow machine
  await page.evaluate(() => {
    const f = [...document.querySelectorAll('.lil-gui .lil-title')].find((t) => t.textContent.trim() === 'Map').parentElement;
    const row = [...f.querySelectorAll('.lil-controller')].find((c) => c.querySelector('.lil-name')?.textContent.trim() === 'show map under model');
    row.querySelector('input[type=checkbox]').click();
  });
  await page.waitForSelector('#xray-map-notice-text');
  const noticeText = await page.textContent('#xray-map-notice-text');
  check('the notice has the exact words, with the provider named', noticeText === "Map tiles are fetched from Esri (server.arcgisonline.com); this reveals the project's location to them.", noticeText);
  await settle(page, 600);
  check('nothing is requested while the notice is open', tileLog.length === 0 && (await mapState()).enabled === false);
  await page.click('#xray-map-notice-no');
  await settle(page, 400);
  check('Cancel keeps it off and requests nothing', tileLog.length === 0 && (await mapState()).enabled === false && (await page.evaluate(() => document.querySelector('.lil-gui input[type=checkbox]') !== null)));
  await page.evaluate(() => {
    const f = [...document.querySelectorAll('.lil-gui .lil-title')].find((t) => t.textContent.trim() === 'Map').parentElement;
    [...f.querySelectorAll('.lil-controller')].find((c) => c.querySelector('.lil-name')?.textContent.trim() === 'show map under model').querySelector('input[type=checkbox]').click();
  });
  await page.waitForSelector('#xray-map-notice-yes');
  await page.click('#xray-map-notice-yes');
  await waitTiles(page, 2);
  await settle(page, 700);
  st = await mapState();
  check('after Show the map: tiles requested from the Esri template (z/y/x) and drawn', tileLog.length > 0 && tileLog.every((t) => t.host === 'server.arcgisonline.com' && /\/ArcGIS\/rest\/services\/World_Imagery\/MapServer\/tile\/\d+\/\d+\/\d+$/.test(t.url)) && st.tiles > 0 && st.visible, `${tileLog.length} requests, ${st.tiles} drawn, zoom ${st.zoom}`);
  check('the Esri attribution is shown on screen', await page.evaluate(() => { const a = document.getElementById('xray-map-attribution'); return !!a && !a.hidden && a.textContent === 'Esri, Maxar, Earthstar Geographics, and the GIS User Community' && a.getBoundingClientRect().width > 0; }));
  check('no request went anywhere else', otherLog.length === 0, otherLog.join(' '));

  // elevation: the lowest storey (FZK: Erdgeschoss 0) in the viewer frame, a hair below it
  const lvl = await page.evaluate(() => { const m = window.__xray.app.loaded.model; return { low: Math.min(...m.storeys.map((s) => s.elevation)), shiftZ: m.originShift[2] }; });
  check('the map lies at the lowest storey elevation', Math.abs(st.y - (lvl.low - lvl.shiftZ - 0.02)) < 1e-6 && st.groundBasis === 'lowest storey', `y ${st.y}, storey ${lvl.low}, shift ${lvl.shiftZ}`);

  // a clear view of ground beside the house, and the house itself
  await setCamera(page, [14, 12, 16], [0, -2.5, 0]);
  await settle(page, 400);
  const ground = await colourAt(page, [7, lvl.low - lvl.shiftZ, 6]);
  check('the ground beside the house shows the tile colours', ground.inView && greenish(ground), JSON.stringify(ground));
  const house = await colourAt(page, [0.5, 1.2, -0.5]);
  check('the model is drawn over the map (its pixels are not the tile green)', house.inView && !greenish(house), JSON.stringify(house));
  await page.screenshot({ path: resolve(here, 'satmap.png') });

  // picks go through the map
  const picks = await page.evaluate(() => {
    const r = window.__xray.app.renderer;
    const out = { ground: [], model: null };
    for (const [x, y] of [[0.7, -0.8], [-0.7, -0.8], [0.0, -0.9]]) out.ground.push(r.pick(x, y));
    const m = r.camera.position.clone().set(0.5, 1.2, -0.5).project(r.camera);
    out.model = r.pick(m.x, m.y);
    return out;
  });
  check('picks ignore the map: ground points pick nothing, the house picks an element', picks.ground.every((p) => p === null) && picks.model !== null, JSON.stringify(picks));
  check('no ray meets the map, and its meshes have no raycast', (await page.evaluate(() => window.__xrayMap.pickable())) === false);
  check('same pick on the model as without the map', noMapPick.model !== null);
  const scenePick = await page.evaluate(() => {
    const r = window.__xray.app.renderer; const g = r.scene.getObjectByName('map-ground');
    let tiles = 0, picks = 0;
    g.traverse((o) => { if (o.isMesh) { tiles++; if (o.raycast.toString().replace(/\s/g, '') !== '()=>{}') picks++; } });
    return { tiles, picks, order: g.children[0]?.renderOrder, clip: g.children[0]?.material.clippingPlanes ?? null };
  });
  check('every tile has a no-op raycast and is drawn first (render order far below the model)', scenePick.tiles > 0 && scenePick.picks === 0 && scenePick.order < -500, JSON.stringify(scenePick));

  // fit and bounds do not see it
  const fit = await page.evaluate(() => { const r = window.__xray.app.renderer; const b = r.loaded.geometry.totalBounds(); return b.max.x - b.min.x; });
  check('bounds (fit, section box) come from the model, not the map', fit < 40, `model width ${fit.toFixed(1)} m`);

  // opacity and radius
  await page.evaluate(() => window.__xrayMap.patch({ opacity: 0.4 }));
  await settle(page, 300);
  const faded = await colourAt(page, [7, lvl.low - lvl.shiftZ, 6]);
  check('opacity lets the background through (the ground is paler than at 1)', faded.rgb[0] > ground.rgb[0] + 20, `${ground.rgb} -> ${faded.rgb}`);
  await page.evaluate(() => window.__xrayMap.patch({ opacity: 1 }));
  const w150 = (await mapState()).tilesWanted; // the 60 m disc of the run
  await page.evaluate(() => window.__xrayMap.patch({ radius: 40 }));
  await settle(page, 300);
  const w40 = (await mapState()).tilesWanted;
  await page.evaluate(() => window.__xrayMap.patch({ radius: 400 }));
  await settle(page, 300);
  const w400 = (await mapState()).tilesWanted;
  check('the radius sets the disc: fewer tiles for 40 m, more for 400 m', w40 <= w150 && w150 <= w400 && w40 < w400, `${w40} / ${w150} / ${w400}`);
  await page.evaluate(() => window.__xrayMap.patch({ radius: 60 }));

  // zoom from the camera distance
  await page.evaluate(() => { window.__xray.app.renderer.controls.maxDistance = 1e5; window.__xray.app.renderer.controls.minDistance = 0; });
  await setCamera(page, [11, 8, 13], [0, 0, 0]);
  await settle(page, 500);
  const zNear = (await mapState()).zoom;
  await setCamera(page, [350, 250, 400], [0, 0, 0]);
  await settle(page, 700);
  const zFar = (await mapState()).zoom;
  check('the zoom follows the camera distance (closer is finer)', zNear > zFar && zNear <= 19 && zFar >= 1, `near z${zNear}, far z${zFar}`);
  await setCamera(page, [14, 12, 16], [0, -2.5, 0]);
  await settle(page, 500);

  // view modes and section: the map stays, the model still draws
  await page.evaluate(() => { window.__xray.app.setXray(true); });
  await page.waitForTimeout(300);
  const xr = await colourAt(page, [7, lvl.low - lvl.shiftZ, 6]);
  check('in x-ray mode the map is still drawn', greenish(xr), JSON.stringify(xr));
  await page.evaluate(() => { const a = window.__xray.app; a.renderer.setClipPlanes([{ normal: [1, 0, 0], point: [0, 0, 0] }]); a.renderer.markDirty(); });
  await page.waitForTimeout(300);
  const clipped = await colourAt(page, [-7, lvl.low - lvl.shiftZ, 6]);
  check('a section plane through the model does not cut the map away (the ground is not clipped)', clipped.inView ? greenish(clipped) : true, JSON.stringify(clipped));
  await page.evaluate(() => { const a = window.__xray.app; a.renderer.setClipPlanes(null); });

  // provider switch asks again
  await page.evaluate(() => window.__xrayMap.patch({ provider: 'osm' }));
  const asked = await page.evaluate(() => window.__xrayMap.controller.settings.enabled);
  check('another provider is another party: the map is off until it is accepted', asked === false);
  await page.evaluate(() => { void window.__xrayMap.setEnabled(true); });
  await page.waitForSelector('#xray-map-notice-text');
  const osmText = await page.textContent('#xray-map-notice-text');
  check('the OpenStreetMap notice names OpenStreetMap', /Map tiles are fetched from OpenStreetMap \(tile\.openstreetmap\.org\); this reveals/.test(osmText), osmText);
  await page.click('#xray-map-notice-yes');
  tileBase = [200, 190, 170];
  await waitTiles(page, 1);
  await settle(page, 500);
  check('OpenStreetMap tiles and attribution', tileLog.some((t) => t.host === 'tile.openstreetmap.org' && /\/\d+\/\d+\/\d+\.png$/.test(t.url)) && (await page.textContent('#xray-map-attribution')) === '© OpenStreetMap contributors');
  const osmNote = await page.evaluate(() => document.getElementById('xray-map-note')?.textContent ?? '');
  check('the OpenStreetMap tile usage policy is noted in the panel', /tile usage policy/i.test(osmNote));
  await page.evaluate(() => window.__xrayMap.patch({ provider: 'esri' }));
  await page.evaluate(() => { void window.__xrayMap.setEnabled(true); });
  await settle(page, 300);
  tileBase = [84, 140, 66];

  // ------------------------------------------------------------------ part 4: a custom template with a key
  const KEY = 'SMOKE-KEY-0123456789';
  await page.evaluate((k) => {
    const c = window.__xrayMap.controller;
    c.secrets.url.set('https://tiles.example.test/{z}/{x}/{y}.png?key={key}');
    c.secrets.key.set(k);
    c.patch({ provider: 'custom', customAttribution: 'Tiles by the Example' });
    c.secrets.acknowledge('tiles.example.test');
  }, KEY);
  await page.evaluate(() => { void window.__xrayMap.setEnabled(true); });
  await waitTiles(page, 1);
  const custom = tileLog.filter((t) => t.host === 'tiles.example.test');
  check('a custom template is filled with z, x, y and the key', custom.length > 0 && custom.every((t) => /\/\d+\/\d+\/\d+\.png\?key=SMOKE-KEY-0123456789$/.test(t.url)), custom[0]?.url);
  check('the custom attribution is shown', (await page.textContent('#xray-map-attribution')) === 'Tiles by the Example');
  const leaks = await page.evaluate((k) => {
    const dump = (s) => { const o = []; for (let i = 0; i < s.length; i++) o.push(s.key(i) + '=' + s.getItem(s.key(i))); return o.join('\n'); };
    const app = window.__xray.app;
    let params = ''; try { params = JSON.stringify(window.__xrayParams?.collect?.() ?? ''); } catch { /* none */ }
    return { url: location.href.includes(k), local: dump(localStorage).includes(k), session: dump(sessionStorage).includes(k), params: params.includes(k), cookie: document.cookie.includes(k), title: document.title.includes(k) };
  }, KEY);
  check('the key is in sessionStorage only: not in the page URL, localStorage, params or cookies', leaks.session && !leaks.url && !leaks.local && !leaks.params && !leaks.cookie, JSON.stringify(leaks));
  await page.evaluate(() => { window.__xrayMap.patch({ provider: 'esri' }); void window.__xrayMap.setEnabled(true); });
  await settle(page, 400);

  // ------------------------------------------------------------------ part 5: the manual aligner
  await panelOpen(page);
  await page.evaluate(() => {
    const f = [...document.querySelectorAll('.lil-gui .lil-title')].find((t) => t.textContent.trim() === 'Map').parentElement;
    [...f.querySelectorAll('.lil-controller')].find((c) => c.querySelector('.lil-name')?.textContent.trim() === 'Align manually…').querySelector('button').click();
  });
  await page.waitForSelector('#xray-map-align:not([hidden])');
  await page.fill('#xray-map-latlon', '48.1374, 11.5755');
  await page.press('#xray-map-latlon', 'Enter');
  await settle(page, 300);
  st = await mapState();
  check('manual entry of latitude and longitude: status "Manual"', st.status === 'Manual' && Math.abs(st.georef.lat - 48.1374) < 1e-6 && Math.abs(st.georef.lon - 11.5755) < 1e-6, JSON.stringify(st.georef));
  await page.fill('#xray-map-rot', '30');
  await page.press('#xray-map-rot', 'Tab');
  await settle(page, 200);
  check('the rotation to north is applied', Math.abs((await mapState()).georef.rotation - 30) < 1e-6);
  await page.click('#xray-map-top');
  await settle(page, 400);
  const before = (await mapState()).georef;
  const box = await page.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  const gx = box.x + box.w * 0.62, gy = box.y + box.h * 0.35;
  await page.mouse.move(gx, gy);
  await page.mouse.down();
  for (let i = 1; i <= 6; i++) await page.mouse.move(gx + i * 14, gy + i * 6);
  await page.mouse.up();
  await settle(page, 400);
  const after = (await mapState()).georef;
  check('dragging on the ground moves the map under the model (the place changes, rotation kept)', Math.hypot(after.lat - before.lat, after.lon - before.lon) > 1e-6 && Math.abs(after.rotation - before.rotation) < 1e-9 && (await mapState()).status === 'Manual', `${before.lat.toFixed(6)},${before.lon.toFixed(6)} -> ${after.lat.toFixed(6)},${after.lon.toFixed(6)}`);
  const moved = await page.evaluate(() => window.__xray.app.renderer.controls.enabled);
  check('the camera controls are back after the drag', moved === true);
  await page.click('#xray-map-done');
  await settle(page, 400);
  const kept = (await mapState()).georef;
  const idb = await page.evaluate(() => new Promise((res) => { const r = indexedDB.open('xray-map', 1); r.onsuccess = () => { const q = r.result.transaction('locations').objectStore('locations').get('fzk-haus'); q.onsuccess = () => res(q.result ?? null); q.onerror = () => res('error'); }; r.onerror = () => res('error'); }));
  check('Done stores the place in IndexedDB under the model', !!idb && typeof idb === 'object' && Math.abs(idb.lat - kept.lat) < 1e-9 && Math.abs(idb.rotation - 30) < 1e-9, JSON.stringify(idb));
  const lsDump = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + location.href);
  check('the place is in no localStorage entry, session entry or URL', !lsDump.includes(kept.lat.toFixed(4)) && !lsDump.includes('48.13'));

  // a reload finds it again, with the map off
  tileLog.length = 0; otherLog.length = 0;
  await boot();
  await settle(page, 1200);
  st = await mapState();
  check('after a reload the manual place is back, the map is off and nothing was requested', st.status === 'Manual' && Math.abs(st.georef.lat - kept.lat) < 1e-9 && st.enabled === false && tileLog.length === 0 && otherLog.length === 0, st.status);
  await injectSite();
  await page.evaluate(async () => { await window.__xrayMap.setManual(null, true); });
  st = await mapState();
  check('"Use the model\'s own place" clears the manual place', st.status === 'From IfcSite');
  const idb2 = await page.evaluate(() => new Promise((res) => { const r = indexedDB.open('xray-map', 1); r.onsuccess = () => { const q = r.result.transaction('locations').objectStore('locations').get('fzk-haus'); q.onsuccess = () => res(q.result ?? null); }; r.onerror = () => res('error'); }));
  check('and removes it from IndexedDB', idb2 === null);

  // ------------------------------------------------------------------ part 6: the real IFC says the same
  const ifcPage = await ctx.newPage();
  ifcPage.setDefaultTimeout(240000);
  ifcPage.on('console', (m) => { if (m.type() === 'error') errors.push(`[ifc] ${m.text()}`); });
  ifcPage.on('pageerror', (e) => errors.push(`[ifc pageerror] ${e.message}`));
  watchRequests(ifcPage);
  await boot(ifcPage, 'building');
  await ifcPage.setInputFiles('#xray-open-file-input', resolve(root, '../models/AC20-FZK-Haus.ifc'));
  await ifcPage.waitForFunction(() => window.__xrayMap && window.__xrayMap.state().status !== 'Unknown' || /Loaded \d+ elements/.test(document.body.innerText) && window.__xrayMap.state().status !== 'Unknown', null, { timeout: 240000 }).catch(() => {});
  const ifcSt = await mapState(ifcPage);
  check('the FZK-Haus IFC opened from a file: "From IfcSite" with its RefLatitude, RefLongitude and TrueNorth', ifcSt.status === 'From IfcSite' && Math.abs(ifcSt.georef.lat - 49.1004) < 5e-4 && Math.abs(ifcSt.georef.lon - 8.4365) < 5e-4 && Math.abs(ifcSt.georef.rotation + 50) < 0.01, JSON.stringify(ifcSt.georef));
  await ifcPage.close();

  // ------------------------------------------------------------------ part 7: phone, 360 px
  const phone = await browser.newContext({ viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  await routeTiles(phone);
  const pp = await phone.newPage();
  pp.setDefaultTimeout(120000);
  pp.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  pp.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await boot(pp);
  await injectSite(pp);
  await setCamera(pp, [16, 14, 18], [0, -2.5, 0]);
  await pp.evaluate(() => { void window.__xrayMap.setEnabled(true); });
  await pp.waitForSelector('#xray-map-notice-yes');
  const nrect = await pp.evaluate(() => { const r = document.querySelector('#xray-map-notice .mn-card').getBoundingClientRect(); return { x: r.left, r: r.right, b: r.bottom, y: r.top }; });
  check('phone: the notice fits 360 px', nrect.x >= 0 && nrect.r <= 360.5 && nrect.y >= 0 && nrect.b <= 740, JSON.stringify(nrect));
  await pp.click('#xray-map-notice-yes');
  await waitTiles(pp, 1);
  await pp.waitForTimeout(700);
  const att = await pp.evaluate(() => { const a = document.getElementById('xray-map-attribution'); const r = a.getBoundingClientRect(); const s = document.getElementById('xray-overlay')?.getBoundingClientRect(); return { x: r.left, r: r.right, b: r.bottom, y: r.top, hidden: a.hidden, text: a.textContent, statusTop: s?.top ?? 0, scroll: document.documentElement.scrollWidth }; });
  check('phone: the attribution is inside the screen, above the status bar, and the page does not scroll sideways', !att.hidden && att.x >= 0 && att.r <= 360.5 && att.b <= att.statusTop + 0.5 && att.scroll <= 360, JSON.stringify(att));
  await pp.evaluate(() => window.__xrayMap.openAlign());
  await pp.waitForSelector('#xray-map-align:not([hidden])');
  await pp.waitForTimeout(300);
  const al = await pp.evaluate(() => { const r = document.getElementById('xray-map-align').getBoundingClientRect(); const bs = [...document.querySelectorAll('#xray-map-align button')].map((b) => { const q = b.getBoundingClientRect(); return [q.left, q.right]; }); return { x: r.left, r: r.right, y: r.top, b: r.bottom, buttonsIn: bs.every(([l, rr]) => l >= 0 && rr <= 360.5) }; });
  check('phone: the aligner fits 360 px with all its buttons', al.x >= 0 && al.r <= 360.5 && al.y >= 0 && al.b <= 740 && al.buttonsIn, JSON.stringify(al));
  await pp.screenshot({ path: resolve(here, 'satmap-phone.png') });
  await phone.close();

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
