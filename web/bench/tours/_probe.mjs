import { startTour, ui } from './lib.mjs';
const tour = await startTour('tour-03-screen');
const page = await tour.open('model=process-plant');
page.setDefaultTimeout(60000);
await ui.tab(page, 'Classification');
await page.locator('#dk-pane-classification').getByRole('button', { name: 'Classify all' }).click();
for (const t of [3000, 6000, 12000, 20000]) { await page.waitForTimeout(t); console.log(t, await page.evaluate(() => window.__xrayClassify.results().length), (await page.locator('#dk-pane-classification').innerText()).replace(/\s+/g,' ').slice(0, 400)); }
await tour.finish();
