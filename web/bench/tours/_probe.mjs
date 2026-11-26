import { startTour, ui } from './lib.mjs';
const tour = await startTour('tour-03-screen');
const page = await tour.open('model=building');
page.setDefaultTimeout(8000);
console.log(JSON.stringify(await page.evaluate(() => window.__xray.app.controller.model.elements.map(e => [e.id, e.ifcClass, e.name, e.bounds.map(v=>+v.toFixed(1)).join(',')]))));
await ui.tool(page, 'Measure').click();
console.log('snap default', await page.locator('label.xt-check', { hasText: 'Snap' }).locator('input').isChecked());
console.log(await ui.cam(page).then(c=>JSON.stringify(c)));
await tour.finish();
