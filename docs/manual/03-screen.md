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

## 3.2 Moving around: orbit, pan, zoom, Walk mode, the view cube

Think of holding a model house in your hands. You turn it, slide it, bring it closer. The viewer works the same way, in the
style of Revit, Navisworks and Solibri: the mouse moves the model around a point you choose, and the keyboard does the same
in small steps. A second way, **Walk mode**, puts you inside the building instead.

The left mouse button does one of two things, depending on the *pointer mode*. The mode is set by a toggle under the view
cube, or by two keys. The other buttons and the wheel do the same in both modes.

| | **Hand** (key `G`, the default) | **Arrow** (key `R`) |
| --- | --- | --- |
| Left drag | Orbit | Draw a selection box |
| Click | Select | Select |
| Double-click an element | Select it and fly to it | The same |
| `Alt` with double-click | Enter Walk mode and drop in on that spot | The same |
| Right drag, middle drag | Pan | Pan |
| `Shift` with middle drag | Orbit | Orbit |
| Wheel | Zoom toward the cursor | Zoom toward the cursor |
| Double middle click | Frame everything | Frame everything |
| Touch | One finger orbits, two fingers zoom and pan | One finger draws the box, two fingers zoom and orbit |

Two details make this feel natural. The wheel zooms toward the point under the cursor, so what you point at stays under the
pointer. And an orbit turns around the point you grab: when a drag starts, the viewer finds the element under the cursor and
makes that the centre of the turn. If the cursor is over empty space, the centre stays where it was. In Hand mode, `Shift` with
a left drag pans. A double-click on empty space does nothing. The camera is never out of reach in Arrow mode, because the
right and middle buttons, the wheel and the keyboard still work.

**The selection box (Arrow mode).** Drag from left to right: a solid blue box that picks the elements lying fully inside
it. Drag from right to left: a dashed green box that picks every element it touches. This is the convention of CAD
programs. `Shift` adds to the selection, `Ctrl` or `Cmd` toggles, and `Esc` cancels the box while the button is down. The
box looks at bounding boxes only, not at what hides what, so it picks elements behind the ones in front.

**From the keyboard.** Arrow keys orbit. `Shift` with arrow keys pans. `=` and `-` (or `+`) zoom. Hold `Ctrl` to move at a
quarter of the speed. The number pad gives the standard views: `1` front, `3` right, `7` top, `0` isometric. `F` or `.`
frames the selection (`F` frames everything when nothing is selected), and `Home` frames the whole model. `PageUp` and
`PageDown` move up and down one storey. `Alt+Left` and `Alt+Right` step back and forward through your last 50 views of the
model (mouse buttons 4 and 5 do the same).

`W`, `A`, `S`, `D`, `Q` and `E` do nothing here. They belong to Walk mode, below.

**The view cube.** Click a face (Top, Bottom, Front, Back, Left, Right), an edge or a corner, and the camera glides there,
framing the selection (or the whole model). Drag the cube to orbit. The curved arrows at the top corners roll the picture
by 90 degrees, and the arrows at the bottom corners turn the camera 90 degrees to the left or right. **Home** frames the
model. The projection button switches between perspective and an orthographic look (`Alt+5`).

### Walk mode

Orbiting looks at a building from outside. To check what you would see standing in a corridor, you need to be inside.
**Walk mode** moves the camera as a person would: you stay at one eye height and go forward, back and sideways on the level.

Enter it with `Shift+W`, or with the walk button next to the Arrow and Hand toggle under the view cube. A chip at the top of
the view reads "Walk · Esc to exit", and the cursor becomes an eye. Leave it with `Esc`, a click on the chip, or the walk
button again.

- `W` and `S`, or `Up` and `Down`, walk forward and back. `A` and `D` step left and right.
- `Left` and `Right` turn you on the spot.
- `Q` lowers the eye and `E` raises it.
- Hold `Shift` to run (3 times faster). Hold `Ctrl` to go slow (a quarter speed).
- Drag with the left button to look around. The wheel walks forward and back. A click still selects.
- Double-click a spot on the model to **drop in** there (see below). `PageUp` and `PageDown` jump one storey up or down.

While you walk, `Shift+W` does not leave: `Shift` with `W` runs forward. Use `Esc` to leave. Walk mode is also left when a
fly-through, a script or a 4D film plays (chapter 21).

**Drop in here.** Walking from far away is slow. In Walk mode, double-click a point on the model. The eye glides there
(about 0.4 s) and stands on that spot at your **eye height**, facing the way you were facing. The eye height is the
**eye height (m)** setting in the **Keyboard** folder of the **Parameters** tab. It is 1.6 m by default and can be 0.5 m to 3 m.
If you click a surface that faces up, such as a floor or a stair tread, you stand on it. If you click a wall or a ceiling, you
stand on the floor below that point, because a wall has no top to stand on.

Outside Walk mode, hold `Alt` and double-click a point. The viewer enters Walk mode and drops you in there. A plain
double-click outside Walk mode still flies to the element.

**Storey jump.** In Walk mode, `PageUp` and `PageDown` move you to the storey above or below. You keep your spot on the plan
and your height above the floor. A short message names the storey, for example "Level 2", or says that you are already at the
top or bottom storey. Outside Walk mode the same keys move the camera target one storey (see above).

**Walls that stop you (optional).** By default you walk through everything. Switch on **Walk collision** in the same
**Keyboard** folder and the movement keys and the wheel stop you about 0.3 m short of a wall. If you push at a slant, you slide
along it. Doors do not block you, and neither do ghosted or hidden parts, so you can still walk through a faint wall or a
hidden one. Floors and ceilings are not walls. `Q` and `E` ignore collision.

**Try it.** In FZK-Haus, walk into the house from outside.

1. Press `Home`. The whole house fills the view, seen from above and outside.
2. Press `Shift+W`. The chip appears. Nothing moves yet.
3. Hold `Q` until the ground outside the house is just below the middle of the view: your eye is now low, at about the height
   of the ground floor. Drag with the left button to look level, toward the house.
4. Hold `W`. You walk toward the house at the same height. Keep it down and you pass through the outer wall and stand inside
   the ground floor. Hold `Shift` as well to run, or `Ctrl` to creep.
5. Press `Left` to turn and look around the room. Press `PageUp`. You move to the storey above, at the same spot, and a message
   names it. Press `PageDown` to come back.
6. Press `Esc` to leave, then `Home`. Hold `Alt` and double-click a wall of the house. The chip appears and you stand inside, on
   the floor below the point you clicked, at 1.6 m.
7. Open the **Keyboard** folder of the **Parameters** tab and switch on **Walk collision**. Hold `W` toward a wall. You stop
   short of it. Switch it off again if you like.
8. Press `Esc`. The chip goes away and the mouse orbits again, around a point a short way in front of you.

**How it works.** Walk mode moves the camera and a point a fixed distance in front of it, so leaving it leaves a sensible
orbit. It is a state of your viewer only. It is not in share links, saved views, presets or packed pages, and opening another
model ends it. A walk is one camera step on the undo stack (3.4).

**Limits.** There is no gravity. Collision is off unless you switch on **Walk collision**, so by default you pass through walls
and floors. It checks three points in the direction you move, and only while you move, so a thin railing can slip past. You stay
at the eye height you set until you change it with `Q` and `E`. Speeds scale with the size of the model, and the **move speed** and **orbit speed** settings change them.

### The old keys: Navigation style

If you liked the older way, where `W`, `A`, `S`, `D`, `Q` and `E` always fly the camera and the middle button zooms, open the
**Keyboard** folder of the **Parameters** tab and set **navigation style** to **Game**. **BIM** is the default. The choice is
remembered in your browser. It is not in share links or views. Game style has no pivot pick and no double-click action.

**Try it.** Click **Top** on the cube. You look straight down. Click **Home**. Press `Alt+Left` to go back to the view before.
Turn the wheel with the pointer over a corner of the house, and see that corner stay under the pointer.

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

- **Camera.** A whole wheel gesture, an orbit, a click on the cube or a jump to a view is one step. The camera is
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

## 3.6 What's new

The first time you open a new version of the viewer, a small **What's new** card appears in the corner of the 3D view. It names
the version and lists the changes of the newest release. It takes the keyboard focus. Press `Esc` or **Dismiss** to close it.
It shows once for each version, in each browser.

- **Show all changes** on the card opens a list of every release, newest first, each with its date.
- The command palette action **What's new** (`Ctrl+Shift+K`, see 3.7) opens the same list at any time. It has no key until you
  give it one in the shortcut editor.

The card stays away on the very first start in a browser, and in packed pages, kiosk pages, embedded pages and pages in a
frame. It also stays away when the browser blocks local storage. The text comes from `CHANGELOG.md`, the file at the root of
the repository that lists every release.

## 3.7 Keyboard, command palette, cheat sheet

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

**Where the keys go (focus).** A list such as the model tree, the Views list or the Sets list keeps its own arrow keys,
`Home`, `End`, `PageUp`, `PageDown`, `Enter` and `Space` while it has focus. So `PageUp` in the tree moves up the tree, not up
a storey. Keys that the list does not use, such as `F`, `H` and `X`, still act on the selection. Chapter 7 gives the tree keys.

`Esc` is the way out. With focus in a list, the first `Esc` hands focus back to the 3D view and does nothing else. A second
`Esc` does what it always does: it closes an open panel or card, then clears the selection. In a text box, `Esc` also leaves the
box.

`F6` moves focus around the screen: the 3D view, the left sidebar, the right sidebar, the top bar, and back to the 3D view.
`Shift+F6` goes the other way. A folded sidebar or a hidden top bar is skipped (open it with `[`, `]` or `Shift+T` first). The
region that has focus shows a ring. `F6` is the one key that also works while you type in a text box. Together with `Tab`, it
lets you reach every part of the screen without the mouse.

## See also

- Chapter 4: x-ray, the main feature.
- Chapter 7: the model tree, its keys and search.
- Chapter 21: what happens to the camera while something plays.
- Appendix A: keyboard reference.
