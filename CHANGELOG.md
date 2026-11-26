# Changelog

What changed in the X-ray viewer, newest first. One section per release; the number is the viewer download number
(`tools/viewer-release.txt`). The viewer shows the newest section once, the first time you open a new version.

## Unreleased

- Issue pins and drawings are hidden while a fly-through, script or 4D film plays or is recorded, and come back exactly as they were
  when it stops.
- The 4D tab has "Issues and drawings in the film" (Style) and fly-throughs have "Issues and drawings": tick them to keep the pins
  and drawings on screen during playback.
- The 4D film has a "Fade in (s)" setting: how long a new part takes to appear (auto, 0 for at once), also in the director script
  and on the xray-4d command line.
- The 4D director has "Each floor apart": the storeys move apart around the floor being built, that floor is in x-ray focus and
  named, and they close again before the work moves on.
- The FZK-Haus 4D sample shows its ground floor and roof storey built apart.
- Animation script: element properties in expressions (`the name of it`, `the storey of it`, `property "Pset_WallCommon.FireRating" of it`, `the names of class IfcWall`); text tests (`contains`, `is in`, `begins with`, `ends with`) and `&&`; lists and chunks (`item 2 of x`, `the number of words in x`, `sort items of x`, `repeat for each item v in x`); `exit repeat`, `next repeat`, `exit <handler>`; maths (`round`, `trunc`, `abs`, `min`, `max`, `sqrt`, `mod`, `div`, `^`, `pi`) and a seeded `random(n)` so the same script gives the same film.
- Animation script: `param name default value` declares a value shown in a Parameters form above Run in the Script tab (also `xray-4d render --param`, `xray-pack --script-param`, `window.__xrayScript.compile(text, { params })`), and `use "Name"` pulls in the handlers and functions of another saved script (`--use-dir` on the command line). Two new examples: "Label the fire-rated walls" and "One script, any floor". The ifc-4d-schedule skill checker takes `--param` and resolves `use` next to the script; `anim_write.py --as-param`.
- The 4D film builds temporary works: scaffold along the outer walls, falsework under slabs and formwork on concrete, from rules in
  the 4D configuration (`temporaryWorks`, edited in the Film step under "Temporary works"). They go up before the work they serve and
  come down after it, have their own layer and toggle, and are not part of the IFC model. `xray-4d plan` reads the rules
  (`--no-temporary-works` leaves them out). The FZK-Haus 4D sample has scaffold, props and formwork.

## v31 - 2026-11-26

- Walk collision holds in corners: sliding along one wall no longer carries you through the next, and a slanting approach stops
  at the same 0.3 m as a straight one.
- Point cloud alignment: Stop ICP answers much sooner (the work hands control back at least every 30 ms), and the button no
  longer jumps while the status text changes.
- The lit mode in the top bar comes back when the settings return to it, for example after switching x-ray off and on again.

## v30 - 2026-11-25

- The 4D tab is in three steps under the film bar: Map, Link and Film. Each step shows whether it is done or needs you, and
  the tab opens on the step you need next.
- The film bar shows how much of the schedule is linked. Activities that have nothing in the model can be marked "not
  modelled": they stop counting as gaps, and while one is under way the film says so on screen.
- The FZK-Haus 4D sample marks its 25 activities that have nothing in the model (earthworks, drainage, finishes and so on).
- Walk mode: double-click a spot to stand there at eye height (1.6 m by default); Alt and double-click enters Walk mode from
  anywhere. Page Up and Page Down go up or down a storey while you walk.
- Walk collision (off by default, in the Keyboard settings) stops you at walls; doors and ghosted parts let you through.
- This note: the first time you open a new version, the viewer shows what changed. "What's new" in the command palette
  shows it again.
- The manual covers the 4D steps, the new Walk mode features and this note.

## v29 - 2026-11-25

- The 4D tab has a film bar: Play, a date slider you can drag, Record, and Open as script.
- Open as script turns the 4D film into a script you can edit.
- Sample 4D models open at the top of the 4D tab, and the model link accepts the 4D workflow values.
- The manual covers the 4D film bar (chapters 24 and 27).

## v28 - 2026-11-24

- Camera navigation works like other BIM viewers by default: the wheel zooms to the cursor, the middle button pans, Shift and the
  middle button orbits, and orbiting turns around the point under the cursor.
- Double click flies to an element; middle double click shows the whole model.
- Walk mode: press Shift+W (or the gizmo button) to walk through the building with the keys, look around with the mouse, and change
  your eye height. Esc leaves Walk mode.
- A Game style is available in the Keyboard settings for people who prefer W, A, S, D movement.
- The model tree works from the keyboard: arrows, Home and End, type to find a row, Space or Enter to select.
- F6 and Shift+F6 move between the main regions of the page; Escape returns to the 3D view.
- The manual covers navigation, Walk mode and the keyboard (chapters 3 and 7, appendices A and B).

## v27 - 2026-11-24

- Views and Issues are two clear lists. The Views tab holds saved views and drawings together, with the filters All, With drawings,
  On sheets and In an issue. The Issues tab holds issues only, and each issue points at a view.
- A Draw on this view button and a sheets pane sit in the Views tab; on a phone the drawing toolbar moves the sidebar aside.
- Names of views, drawings and issues are the same everywhere in the interface.
- Sample PDF sheets are included with the sample models.
- The user manual is available as one page.

## v26 - 2026-11-21

- 4D tab: open a Primavera P6 schedule (.xer), link activities to model elements, review and accept the links, and see the result.
- Link elements to activities by level, trade or any query; the viewer suggests links and keeps your decisions between runs.
- Play the building being built by schedule date, scrub the date, and record the film as a video.
- Links can be saved into the IFC file (as an IfcWorkSchedule with tasks) and are read back when the model is opened again.
- A sample 4D schedule for the FZK-Haus house is in the sample projects menu.
- A camera director writes a ready-made film from a schedule: camera moves, captions, labels and focus on the active work.
- The animation script has statements for 4D: schedule dates, milestones, tint, explode, collapse, focus and section box.
- Label fields can show the running schedule: activity, percent and finish.
- The xray-4d command line tool does the same steps without the viewer, and an agent skill writes 4D links into an IFC.

## v25 - 2026-11-21

- Video export records a film frame by frame, so the result does not depend on how fast your computer draws (MP4, WebM or a zip
  of PNG pictures), with an options dialog.
- Packed pages can start a film by themselves.
- Captions, labels and the progress bar stay clear of the side panels, the tool strip and the status bar, and appear in recorded video.

## v24 - 2026-11-21

- Fly-through is rebuilt: keyframes are saved views with timing (constant speed or seconds per move, hold, ease, fade, caption),
  a timeline in the Views tab, a 3D path line, and several fly-throughs per model.
- Animation scripts: write a camera and visibility film in plain, HyperTalk-style sentences in a new Script tab, with live error
  messages, examples, saved scripts per model and .xrayanim files.
- A HUD layer draws captions, labels, a hover card, a progress bar, a compass and a scale bar over the view, with settings.
- A formal grammar and a step-by-step guide with recipes for animation scripts.

## v23 - 2026-11-20

- Fly-to has framing controls: how much room around the element, and the closest distance.
- The focus glow is calmer by default, and the glow and edge glow can pulse gently.

## v22 - 2026-11-19

- Save IFC from the viewer: your classification, review and cleanup results are written into a copy of the IFC file.
- Save a cleaned copy of the model without the elements you hid in cleanup; simplification tools and Save cleaned model (.glb).
- Revision walkthrough: compare a new revision with the old one, step through the changes, carry over your decisions, and make a report.
- The revision walk is a tab of the right sidebar.
- The right sidebar has Properties, Classification and Parameters tabs, and becomes a bottom sheet on a phone.
- Issue report as PDF or CSV, and raise issues straight from clash and clearance results.
- A map can be shown under the model.
- The AR / VR tool is always in the icon bar.
- 3D sketches and issues stay after a reload; clip planes can be undone and redone.
- A view mode that turns the section on is one undo step.
- Ending a review or revision walk keeps the camera where it was restored.
