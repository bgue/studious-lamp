# 3. The screen and moving around

You have a model open and you are lost. Where is the button for this? How do I turn the model around? Why did my click
select a wall and not the pipe behind it? And how do I take back the last thing I did?

The screen has a small number of parts, and each part has one job. Learn those parts and the three ways of moving the
camera, and the rest of the manual falls into place. Everything you can do with the mouse you can also do from the
keyboard, so you never have to hunt for a button.

## 3.1 The screen map

> Picture: the viewer on FZK-Haus with each part labelled: top bar, left sidebar, tool strip, canvas, view cube and
> section strip, right sidebar, status bar.

From top to bottom and left to right:

- **Top bar.** A thin strip along the top of the canvas. On the left, five buttons: **Solid**, **Ghost**, **Radiograph**,
  **Glow**, **Cutaway** (the modes, see 4.4). To the right, the search bar (chapter 7). `Shift+T` shows or hides the bar.
- **Left sidebar.** Four tabs: **Model** (the tree of elements), **Sets**, **Views** and **Issues**. `[` folds it.
- **Tool strip.** A column of icons at the left edge of the canvas, with one button per tool: Open model, X-ray, View
  modes, Measure, Clearance, Penetrations, Cleanup and others. A tool with settings opens a *drawer* beside the strip.
  Only one drawer is open at a time. `Esc` closes it. `T` shows or hides the strip.
- **Canvas.** The model.
- **View cube** (the *gizmo*), bottom right. A cube you click to look from a side, with the pointer-mode toggle, the undo
  and redo buttons and the section strip under it. `V` shows or hides it.
- **Right sidebar.** Tabs: **Properties**, **Classification**, **Parameters**, **Script** and **4D**. A **Revision** tab
  appears only while you compare model versions (chapter 20). `]` folds it. The **Parameters** tab holds every setting
  of the viewer in folders, with a tooltip on each (hover for 350 ms).
- **Status bar.** One line along the bottom. It shows the model name and element count, whether x-ray is on, the number of
  focus, host, near and far elements, the element under the pointer or selected, and the frame time. Messages (loading,
  errors) appear here as a red segment with a dismiss button. Click the model name, or the `ⓘ` button, for details and the
  credits of the sample models.

**Try it.** Open FZK-Haus (2.3). Press `T` twice, then `[` twice, then `]` twice, and watch the strip and the sidebars fold
and come back. Hover over a tool button to read its name.

**Limits.** Your fold choices for the right sidebar, the tool strip and the top bar are remembered in the browser. The view cube is not
saved in views or share links.

## 3.2 Orbit, pan, zoom, Arrow vs Hand, the view cube

The left mouse button does one of two things, depending on the *pointer mode*. The mode is set by a toggle under the view
cube, or by two keys.

| | **Hand** (key `G`, the default) | **Arrow** (key `R`) |
| --- | --- | --- |
| Left drag | Orbit | Draw a selection box |
| Click | Select | Select |
| Right drag | Pan | Pan |
| Wheel, middle drag | Zoom | Zoom |
| Touch | One finger orbits, two fingers zoom and pan | One finger draws the box, two fingers zoom and orbit |

In Hand mode, `Shift` with a left drag pans. The camera is never out of reach in Arrow mode, because right drag, wheel and
the keyboard still work.

**The selection box (Arrow mode).** Drag from left to right: a solid blue box that picks the elements lying fully inside
it. Drag from right to left: a dashed green box that picks every element it touches. This is the convention of CAD
programs. `Shift` adds to the selection, `Ctrl` or `Cmd` toggles, and `Esc` cancels the box while the button is down. The
box looks at bounding boxes only, not at what hides what, so it picks elements behind the ones in front.

**From the keyboard.** Arrow keys orbit. `Shift` with arrow keys pans. `W`, `A`, `S`, `D` fly forward, left, back and right,
and `Q` and `E` move down and up. `=` and `-` zoom. Hold `Ctrl` to move at a quarter of the speed. `Home` frames the whole
model, `F` frames the selection (or everything when nothing is selected), and `Alt+Left` goes back to the previous view.

**The view cube.** Click a face (Top, Bottom, Front, Back, Left, Right), an edge or a corner, and the camera glides there,
framing the selection (or the whole model). Drag the cube to orbit. The curved arrows at the top corners roll the picture
by 90 degrees, and the arrows at the bottom corners turn the camera 90 degrees to the left or right. **Home** frames the
model. The projection button switches between perspective and an orthographic look (`Alt+5`).

**Try it.** In FZK-Haus, click **Top** on the cube. You look straight down. Click **Home**. Press `Alt+Left` to go back to
the view before.

**Limits and gotchas.** The orthographic look is an approximation: a camera with a 2 degree field of view moved far back.
There is no true orthographic camera. The view cube has no compass letters, because the model files carry no true north.

## 3.3 Select, hover cards and the Properties tab

Click an element to select it. `Shift`-click adds another, and `Ctrl`-click (`Cmd` on a Mac) toggles one. Press `Esc` to
clear the selection. `Alt+S` selects every element of the same class. `Ctrl+A` selects everything visible.

**Two things surprise people.**

- A click picks the nearest thing you can see. A ghost that is fainter than 0.3 opacity can no longer be clicked: your
  click goes through it to what is behind. This is on purpose, so you can select the duct through the faint wall. It also
  means you cannot select a very faint wall by clicking it. Use the Model tree or the search bar (chapter 7).
- Selecting any element makes it a focus, whatever its class. Select a slab and the other slabs and walls become context.

**Hover cards.** Rest the pointer on an element for 350 ms and a small card appears. It shows the element name, its
`class · storey · material`, a few properties (type, whether it is external, load-bearing, fire rating, length, width,
height, volume), and while x-ray is on a line such as `x-ray: near · alpha 0.40`. The card goes away when the pointer
leaves, when you press a key or when you click. Hold `Alt` to freeze the card, select its text, or press **Copy** to copy
every row. `I` switches the cards on and off. The element under the pointer is also outlined.

**The Properties tab.** The first tab of the right sidebar follows the selection. It shows the GlobalId (with **Copy
GlobalId**), class, name, storey, material, the x-ray state, and a list **Properties (n)** with the property sets and
quantities. By default the list shows the same filtered properties as the card, and the title reads `Properties (k of n)`.
Click a row to copy its value. To see every property, switch on `all properties in sidebar` in the **Hover info** folder
of the **Parameters** tab. With several elements selected, the tab shows the first and says `+ N more selected`.

**Try it.** In FZK-Haus, hover over a wall, and wait. Then click it. Open the **Properties** tab. Find `IsExternal` and
`FireRating` if the file has them.

**Limits.** Only the element's own property sets are read, at most 24 per element. Properties of the element's type (the
catalogue entry) are not shown. For a file opened with `properties: none` (see 2.4), the card shows nothing but the name,
class, storey and material.

## 3.4 Undo and redo

`Ctrl+Z` undoes and `Ctrl+Shift+Z` (or `Ctrl+Y`) redoes. The two buttons under the view cube do the same, and their tooltips
name the step, such as "Undo zoom" or "Undo selection".

Four kinds of change are on one stack:

- **Camera.** A whole wheel gesture, an orbit, a click on the cube or a jump to a saved view is one step. The camera is
  recorded when it has been still for 0.4 s.
- **Section.** Moving a cut plane (a drag of a handle is one step), or switching a cut on or off.
- **Selection.** Each change of the selected set.
- **Settings.** Each change of a control in the Parameters tab. A slider drag is one step. A preset or a mode button
  changes many settings and is also one step, shown as "N settings".

**What is not undoable.** The stack lasts for the session. It is not saved, not in share links, views or presets, and it
is cleared when a model loads. It holds 100 steps. A new change throws away the redo list. Drawings on views have their
own history. Settings that live outside the Parameters tab (some tool-strip toggles) are not recorded. The keys are not
taken while you type in a text box.

**Try it.** Orbit, select a wall, change a slider. Press `Ctrl+Z` three times and watch each go back.

## 3.5 On a phone

On a screen 700 px wide or less, the layout changes.

- The model tree on the left becomes an overlay, and the right sidebar becomes a **bottom sheet** that rises from the
  bottom edge, at most 58 % of the height. The right sidebar starts folded, as a thin rail.
- The left sidebar, the Issues sheet and the bottom sheet are never open together. Opening one folds the others.
- The five top-bar modes become small icon buttons. Their labels stay as the accessible names.
- The view cube starts collapsed as a small cube button. Tap it to open it. The Arrow and Hand toggle and the undo and
  redo buttons sit beside it.
- In Arrow mode, two fingers zoom and orbit but do not pan. Switch to Hand to pan.

Apart from that, everything in this manual works on a phone. The views grid (chapter 13) and the revision walk (chapter 20)
have phone-friendly layouts.

## 3.6 Keyboard, command palette, cheat sheet

You can do nearly every action from the keyboard.

- `?` or `F1` opens the **cheat sheet**: every action with its key, grouped.
- `Ctrl+Shift+K` opens the **command palette**. It lists every action and every button and checkbox of the Parameters tab,
  with the folder path and the key. Type a few letters (the ranking favours the start of words), use the arrow keys, and
  press `Enter`. Entries you used recently come first.
- `/` or `Ctrl+K` opens the **search bar** (chapter 7).
- **Edit shortcuts** (in the **Keyboard** folder of the Parameters tab) lets you change any key. Click a key cell, press the
  new keys, and press `Backspace` to remove one. Cells with a clash turn red. Your changes are stored in the browser, and
  you can export and import them as a file.

Keys are ignored while you type in a text box. A few that you will use all the time:

| Key | Action |
| --- | --- |
| `X` | x-ray on or off |
| `Shift+0` to `Shift+4` | the five top-bar modes |
| `1` to `9` | presets |
| `H`, `Alt+H`, `Shift+H` | hide selected, unhide all, hide everything not selected |
| `B`, `P` | behind-only, peelback |
| `C`, `Shift+C`, `Alt+C` | section box, fit box to selection, section plane |

Appendix A lists every key.

## See also

- Chapter 4: x-ray, the main feature.
- Chapter 7: the model tree and search.
- Appendix A: keyboard reference.
