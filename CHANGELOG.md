# Changelog

What changed in the X-ray viewer, newest first. One section per release; the number is the viewer download number
(`tools/viewer-release.txt`). The viewer shows the newest section once, the first time you open a new version.

## Unreleased

- Changes for the next release are collected here.

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
