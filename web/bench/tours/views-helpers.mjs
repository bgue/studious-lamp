// Shared by the tours of chapters 13 to 17: make the "view with drawings" of 14.1 the way a person does (Views tab, Draw on this view,
// Cloud, Arrow, Callout, Done). Not a tour itself (the runner picks up only tour-*.mjs).
import { ui } from './lib.mjs';

/** Screen spots of an element class that a click lands on, found with the viewer's own picker (read only). */
export async function spotOfClass(page, cls) {
  return page.evaluate((cls) => {
    const a = window.__xray.app, cv = a.canvas.getBoundingClientRect(), cm = a.renderer.camera;
    cm.updateMatrixWorld();
    const out = [];
    for (const e of a.controller.model.elements) {
      if (e.ifcClass !== cls) continue;
      const b = e.bounds, v = cm.position.clone().set((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2).project(cm);
      const x = cv.left + (v.x * 0.5 + 0.5) * cv.width, y = cv.top + (1 - (v.y * 0.5 + 0.5)) * cv.height;
      if (v.z < 1 && x > cv.left + 40 && x < cv.right - 40 && y > cv.top + 160 && y < cv.bottom - 120 && document.elementFromPoint(x, y) === a.canvas) out.push({ x, y, id: e.id, d: Math.hypot(v.x, v.y) });
    }
    return out.sort((p, q) => p.d - q.d);
  }, cls);
}

/** The drawing toolbar tool button by its name (Cloud, Arrow, Callout, Select ...). */
export const drawTool = (page, name) => page.locator(`.markup-float button[aria-label="${name}"]`);

/**
 * 14.1 steps 1-9 on the current model (FZK-Haus): face the front, open the Views tab, Draw on this view, draw a cloud round a window,
 * an arrow to the door and a callout "Check the lintel" on the wall, then Done. Returns { windowSpot, doorSpot, wallSpot }.
 */
export async function drawThreeThings(page, { keepToolbar = false } = {}) {
  await page.keyboard.press('Home');
  await ui.waitStill(page, 10000);
  await ui.tab(page, 'Views');
  await page.getByRole('button', { name: 'Draw on this view' }).click();
  await page.locator('.markup-float').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForTimeout(500);
  const win = (await spotOfClass(page, 'IfcWindow'))[0];
  const door = (await spotOfClass(page, 'IfcDoor'))[0] ?? win;
  const wall = (await spotOfClass(page, 'IfcWallStandardCase'))[0];
  const cv = await page.locator('#c').boundingBox();
  // cloud round the window
  await drawTool(page, 'Cloud').click();
  await page.mouse.move(win.x - 35, win.y - 30); await page.mouse.down(); await page.mouse.move(win.x + 35, win.y + 30, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(500);
  // arrow from empty space to the door
  await drawTool(page, 'Arrow').click();
  const sx = Math.min(cv.x + cv.width - 120, door.x + 140), sy = Math.max(cv.y + 190, door.y - 120);
  await page.mouse.move(sx, sy); await page.mouse.down(); await page.mouse.move(door.x, door.y, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(500);
  // callout on the wall
  await drawTool(page, 'Callout').click();
  await page.getByLabel('Text for the next drawing').fill('Check the lintel');
  await page.mouse.click(wall.x, wall.y);
  await page.waitForTimeout(600);
  if (!keepToolbar) {
    await page.locator('.markup-float button[data-act=done]').click();
    await page.waitForTimeout(500);
  }
  return { windowSpot: win, doorSpot: door, wallSpot: wall };
}
