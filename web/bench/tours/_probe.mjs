import { startTour, ui } from './lib.mjs';
const tour = await startTour('tour-03-screen');
const page = await tour.open('model=debris-demo');
page.setDefaultTimeout(8000);
const stat = async () => { await ui.topOfPanel(page); await ui.folder(page,'Model cleanup'); await ui.folder(page,'Simplify'); return ui.valueOf(page,'Simplify status'); };
await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
await ui.folder(page, 'Model cleanup'); await ui.folder(page, 'Simplify'); await ui.folder(page, 'Weld and clean');
await ui.press(page, 'Preview');
for (let i=0;i<4;i++){ await page.waitForTimeout(1500); console.log(JSON.stringify(await stat())); }
await ui.topOfPanel(page); await ui.folder(page,'Model cleanup'); await ui.folder(page,'Simplify'); await ui.folder(page,'Weld and clean'); await ui.press(page, 'Apply'); await page.waitForTimeout(1500);
console.log(JSON.stringify(await stat()));
await ui.topOfPanel(page); await ui.folder(page, 'Model cleanup');
await ui.press(page, 'Save cleaned model'); await page.waitForTimeout(2000);
console.log(await page.evaluate(() => [...document.querySelectorAll('dialog, [role=dialog], .modal, .xs-dialog')].map(d=>d.innerText).join('\n---\n')).then(s=>s.slice(0,1500)));
console.log(await page.evaluate(() => [...document.querySelectorAll('button')].map(b=>b.innerText).filter(t=>/glb|Open the/i.test(t)).join(' | ')));
await tour.finish();
