# Tours: the manual's "Try it" walk-throughs as browser tests

A tour is a browser test that follows one chapter of the user manual (`docs/manual/NN-*.md`) step by step, as a person would: it clicks by the
visible labels the manual uses, checks what the manual says you will see, and (when asked) captures the manual's pictures. If a tour and the
manual disagree, one of them is wrong: fix the manual text when the manual is wrong, and mark the check `known` (below) when the product looks wrong.

One file per chapter: `web/bench/tours/tour-NN-<name>.mjs`, `NN` the two-digit chapter number and `<name>` the chapter file name without the number
(`tour-03-screen.mjs` for `03-screen.md`). Appendices, if toured, are `tour-A-keys.mjs`. `lib.mjs` is the shared machinery.

## Run

From `web/`:

```sh
node bench/run-smokes.mjs --only tour-03-screen --port 5830 --cache /tmp/vc-tours     # one tour
node bench/run-smokes.mjs --tier tours --port 5830 --cache /tmp/vc-tours              # every tour (npm run tours)
TOUR_PICTURES=1 node bench/run-smokes.mjs --only tour-03-screen --port 5830 --cache /tmp/vc-tours   # also write the pictures
```

`--tier full` includes the tours. The summary line counts them like the smokes (`tour-03-screen rc=0 pass=40 fail=0 known=1 210s`).
A tour on its own: `SMOKE_PORT=5830 node bench/tours/tour-03-screen.mjs`. The runner needs the port to itself (it kills what listens there when a tour ends);
use `--cache` so the dependency cache is not shared with another dev server. Serial only: the tours use a software renderer and are slow.
Output lines: `STEP <label>` (a Try it step, not counted), `PASS`, `FAIL`, `KNOWN` (a suspected product bug, not a failure), `PICTURE`, `INFO`.

## Write a tour

```js
import { startTour, ui } from './lib.mjs';
const tour = await startTour('tour-07-tree-and-search');            // starts vite on SMOKE_PORT and a headless Chromium

await tour.step('7.1 Try it step 2: click a storey in the tree', async () => {   // label: section number, Try it step, what the person does
  const page = await tour.open('model=building');                    // a new browser context at 1400x900 (options: width, height, url, init, onRequest, route)
  await ui.tab(page, 'Model');                                       // click a tab by its visible label
  tour.check('"The tree lists the storeys"', await page.getByText('Level 1').isVisible());   // the manual's own words in the check name
});

await tour.finish();                                                  // always last: closes everything, prints the totals, exit code 1 on a FAIL
```

Rules of thumb:

- Follow the **Try it** steps in order, one `tour.step` per step or small group. Name each check with the sentence the manual uses, in quotes.
- Click by the labels the manual puts in bold: `page.getByRole('button', { name: 'Solid' })`, `ui.tab(page, 'Parameters')`, `ui.press(page, 'Pin selected')`.
  Fall back to a selector only when the label is an icon (the tool strip and the cube buttons carry their label as `aria-label`: `ui.tool(page, 'Measure')`).
- Press keys as the manual says (`page.keyboard.press('Shift+4')`). Click the model with `ui.clickElement` (it finds a spot where the element shows, and orbits if it is hidden).
- Do not call app internals to do what a person does with the mouse or keyboard. Internals (`window.__xray...`) are for **reading** what happened.
- A step that throws is a FAIL and the tour goes on with the next step.

### When the manual and the product disagree

Run the steps by hand logic first. If the **manual is wrong** (a label, an order, a number): fix the manual text and say so in your report.
If the **product looks wrong** (a bug): do not change product code. Use `tour.known(name, ok, issue, detail)`: it prints `PASS` when fine and `KNOWN <name> - <issue>`
when not, and the tour still passes. List every KNOWN with its evidence in your report.

## Helper API (`lib.mjs`)

`startTour(name)` returns `tour`:

| Member | What it does |
| --- | --- |
| `tour.open(query, opts)` | New page on the served viewer (`?query`), waits for `__xrayReady`. `opts`: `width`, `height`, `url` (e.g. `file:///...`), `init`, `onRequest`, `route` (answer outside requests offline). |
| `tour.step(label, fn)` | Records a manual step; a throw is a FAIL. |
| `tour.check(name, ok, detail)` | PASS/FAIL line. |
| `tour.known(name, ok, issue, detail)` | PASS, or KNOWN (not a failure) with the suspected bug. |
| `tour.expectText(locator, text/regex, manualSays)` | Waits for text, then checks it, quoting the manual. |
| `tour.picture(id, { page, clip, element, pad, scale, png })` | Saves `docs/manual/img/<id>.jpg` (JPEG q80, deviceScaleFactor 2, light theme) when `TOUR_PICTURES=1`; `clip` = `{x,y,width,height}` in CSS px, `element` = selector to clip to (with `pad`). Whole viewport otherwise. `#stage` is the canvas area without the sidebars. |
| `tour.shot(page, opts)` / `tour.pictureRow(id, [{ buf, label }])` | Several states in one picture (x-ray on and off, three looks), side by side with captions. |
| `tour.annotate(page, [{ selector \| rect, text, side }])` / `tour.unannotate(page)` | Labelled boxes over the page for a picture (the screen map). |
| `tour.finish()` | Closes the browser, stops vite, prints totals, exits. |

`ui` (page helpers, first argument the page): `settle`, `tab`, `button`, `tool`, `mode` / `litMode` (top bar), `statusText`, `cam` / `setCam`, `selection`, `clearSelection`,
`clickElement(page, { cls, name, id })`, `xray` (bucket sizes and the faint elements), `model`, `pixel(page, x, y)` (colour of a screen pixel), and the Parameters tab (lil-gui):
`folder(page, 'Cinematic', 'Exploded view')` (opens by title prefix), `topOfPanel` (forget the folder), `control(page, 'name')`, `press`, `set` (tick, choose by label, type), `valueOf`.

## Add a picture

1. The manual note must carry an id: `> Picture (some-id): what it shows` (`docs/manual/STYLE.md`). `lib.mjs` fails a picture whose id no note declares.
2. In the tour, bring the viewer to the state the caption describes, then `await tour.picture('some-id', { page, element: '#stage' })`. For a picture of several states take
   `tour.shot` of each and call `tour.pictureRow`. Wait for `ui.settle(page, 1500)` first: ghosts ease in over about a second.
3. `TOUR_PICTURES=1 node bench/run-smokes.mjs --only tour-NN-name ...` writes it. Look at the image (open the jpg) and check it shows what the caption says.
4. `python tools/build_manual.py` shows the figure instead of the placeholder (`--embed-images` inlines the images for a single-file publish; the page should stay under 12 MB).

## Refresh the pictures

Run the tours with `TOUR_PICTURES=1` (all of them: `node bench/run-smokes.mjs --tier tours --port 5830 --cache ...`). Routine runs without the variable never touch `docs/manual/img/`.
The run-smokes runner restores tracked `bench/*.png` at its end; the manual images are not touched by that.
