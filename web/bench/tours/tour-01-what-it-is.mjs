// Tour of chapter 1, "What the viewer is and the x-ray idea in one page" (docs/manual/01-what-it-is.md).
// The chapter has no numbered Try it; this tour does what 1.1 and 1.2 describe on the Building model and on the single file, and writes the picture
// `focus-context-occluder`. Run: node bench/run-smokes.mjs --only tour-01-what-it-is   (TOUR_PICTURES=1 writes the picture)
import { resolve } from 'node:path';
import { repoRoot, startTour, ui } from './lib.mjs';

const tour = await startTour('tour-01-what-it-is');

await tour.step('1.1 select one duct segment: the focus is the connected run, the context ghosts', async () => {
  const page = await tour.open('model=building');
  const m = await ui.model(page);
  tour.check('the Building model has ducts, slabs and walls', ['IfcDuctSegment', 'IfcSlab', 'IfcWall'].every((c) => (m.classes[c] ?? m.classes[`${c}StandardCase`] ?? 0) > 0), JSON.stringify(m.classes));
  const picked = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  tour.check('a duct segment can be selected by clicking it', !!picked, JSON.stringify(picked));
  const x = await ui.xray(page);
  tour.known('"the focus is the whole connected duct run": more than the one segment is in focus', x.focus > 1, 'the sample duct belongs to a system with 3 elements ([23,24,25]) but the focus is only the selected segment', `focus ${x.focus}`);
  tour.check('the viewer sorts the context into host, near and far', x.host + x.near + x.far > 0, `host ${x.host}, near ${x.near}, far ${x.far}`);
  const ghosted = Object.keys(x.faintByClass);
  tour.check('"the slab above it and one wall are faint": slabs or walls ghost', ghosted.some((c) => /Slab|Wall/.test(c)), JSON.stringify(x.faintByClass));
  const focusAlpha = await ui.xray(page, x.focusIds);
  tour.check('"the duct is solid": every focus element is fully opaque', Object.values(focusAlpha.alpha).every((a) => a > 0.99));
  const s = await page.evaluate(() => { const a = window.__xray.app.settings; return { n: a.sightlines.samplesPerObject, max: a.sightlines.maxSamples, lo: a.classification.bufferLo, hi: a.classification.bufferHi }; });
  tour.check('"64 points per focus part, and at most 500 in total"', s.n === 64 && s.max === 500, JSON.stringify(s));
  tour.check('"the buffer starts at 0.30 m ... up to 1.50 m"', s.lo === 0.3 && s.hi === 1.5, JSON.stringify(s));
  const total = (await ui.model(page)).n;
  tour.check('"the rest of the building is solid": some context keeps its normal look', x.faint < total - x.focus, `${x.faint} faint of ${total}, ${x.focus} in focus`);
  await ui.setCam(page, [8, 5.5, 9], [0.5, 1.2, -0.5]).catch(() => {});
  await tour.picture('focus-context-occluder', { page, element: '#stage' });
});

await tour.step('1.2 the single file opens without a network request', async () => {
  const net = [];
  const file = resolve(repoRoot, 'xray-viewer.html');
  const page = await tour.open('', { url: `file://${file}`, onRequest: (r) => { if (/^https?:/.test(r.url())) net.push(r.url()); } });
  const m = await ui.model(page);
  tour.check('"xray-viewer.html: one file with the program, the sample models and the IFC reader": it opens and shows a model', m.n > 0, `${m.name}, ${m.n} elements`);
  await page.waitForTimeout(1500);
  tour.check('"The single file makes no network request"', net.length === 0, net.slice(0, 3).join(' '));
});

await tour.finish();
