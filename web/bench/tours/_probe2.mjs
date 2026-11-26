import { startTour, ui } from './lib.mjs';
const tour = await startTour('tour-03-screen');
const page = await tour.open('model=fzk-haus');
page.setDefaultTimeout(10000);
await page.keyboard.press('Home');
await ui.waitStill(page, 10000);
await ui.tab(page, 'Views');
console.log(await page.locator('#sidebar').innerText().then(t => t.replace(/\s+/g,' ').slice(0, 400)));
console.log(await page.getByRole('button', { name: 'Draw on this view' }).count(), await page.locator('[data-act=draw-current]').count());
try { await page.getByRole('button', { name: 'Draw on this view' }).click(); } catch (e) { console.log(String(e).slice(0, 1200)); }
await page.waitForTimeout(1500);
console.log(await page.locator('.markup-float').isVisible());
await tour.finish();
