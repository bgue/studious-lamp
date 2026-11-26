import { startTour, ui } from './lib.mjs';
const tour = await startTour('tour-03-screen');
const page = await tour.open('model=fzk-haus');
await page.keyboard.press('/'); await page.keyboard.type('fire'); await page.waitForTimeout(900);
console.log(await page.evaluate(() => document.querySelector('.ab-list').innerHTML.slice(0,1500)));
for (let i=0;i<4;i++){ await page.keyboard.press('ArrowDown'); console.log(await page.evaluate(()=>document.querySelector('.ab-active')?.innerText.replace(/\n/g,' / ')));}
await page.keyboard.press('Escape');
// eye after h
await page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^IfcDoor$/ }) }).first().locator('.lbl').click();
await page.keyboard.press('h');
for (const t of [100,500,1500]) { await page.waitForTimeout(t); console.log(t, await page.evaluate(() => [...document.querySelectorAll('.tr')].filter(r=>/IfcDoor/.test(r.innerText)).map(r=>r.className+'|'+r.querySelector('.eye').className).join('\n'))); }
await tour.finish();
