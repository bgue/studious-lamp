# Appendix D. Presets

A preset is a saved look: a set of settings, never the camera. Applying one never changes the model or the selection. Keys `1`
to `9` apply the first nine. Four of them are also behind the buttons of the top bar (chapter 4). You can add your own presets
(chapter 4.5).

The viewer ships with 14 built-in presets. They all start from the factory values of the sections they touch, so applying one
switches the previous one off instead of piling on top of it.

> Check: the TOC and README say 13 presets. `web/src/presets/builtin.ts` and `web/public/xray.presets.json` both hold 14 (`focus-glow` was added for the top bar). This table lists 14.

## The table

"Frames the selection" means the camera moves so that the selection fills the view. Without a selection, nothing moves. Presets
without that note never move the camera.

| Key | Name | Group | What you see | Frames the selection |
| --- | --- | --- | --- | --- |
| `1` | Coordination | Review | The standard x-ray view. The selection is in front, and the structure that blocks the view is ghosted. The factory look. The **Ghost** mode of the top bar. | no |
| `2` | Hide blockers | Review | What blocks the view of the selection disappears completely. Everything else stays solid. | no |
| `3` | Behind only | Cutaway | Cuts away everything in front of the selection, with a flat cap on the cut. Shows only what lies behind. | yes |
| `4` | Peelback | Cutaway | Cuts a window through what is in front of the selection and keeps the x-ray ghosting around it. | yes |
| `5` | Peel only | Cutaway | Cuts a window through what is in front of the selection. Everything else is solid. The **Cutaway** mode of the top bar. | yes |
| `6` | Stacked floors | Review | For buildings with many floors. The nearest layers fade first and the deeper ones are graded back in depth. | no |
| `7` | Radiograph | Imaging | A medical x-ray picture. Dense parts glow, thin parts fade. The **Radiograph** mode of the top bar. | no |
| `8` | MRI scan | Imaging | A thin slice of the model, moving slowly through it. | no |
| `9` | Section focus | Cutaway | Cuts a box around the selection and caps the cut faces, so you see the selection inside its surroundings. | yes |
| none | Presentation | Presentation | Soft scene lighting, glow on the selection and animated reveals. | no |
| none | Clearance review | Review | Colours the surroundings of the selection by distance: red for clashes, amber for tight gaps, blue for clear space. | no |
| none | Plain | Basic | The x-ray off. The whole model is drawn as it is. Cuts and clearance are also reset. | no |
| none | Focus glow | Presentation | The selection glows with a soft halo and a bright outline. The structure around it stays ghosted. The **Glow** mode of the top bar. | no |
| none | Solid | Basic | Every element is opaque. X-ray, view modes, imaging, glow and auto orbit are off. Section cuts and clearance stay as they are. The **Solid** mode of the top bar. | no |

## What each preset sets

For people who tune presets or pack pages. The names are the settings of the parameters file.

| Name | Settings |
| --- | --- |
| Coordination | `xray` on; sightlines, display, view modes, imaging, section and clearance at factory values; bloom, edge glow and auto orbit off |
| Hide blockers | `sightlines`: alphaMin 0, alphaMax 1, gamma 0.3, occluder scope all, far weight 1, layer weighting budget, layer budget 6 |
| Behind only | `viewModes.behind`: on, front treatment `cut + cap` |
| Peelback | `viewModes.peel`: on, outside `x-ray` |
| Peel only | `viewModes.peel`: on, outside `solid`; alphaMax 1; bloom and edge glow off |
| Stacked floors | layer weighting `front`, layer falloff 0.3; depth grade on, strength 0.85 |
| Radiograph | imaging style `radiograph`, palette `classic`; bloom and edge glow off |
| MRI scan | imaging style `mri`, scan on |
| Section focus | section box on, fit `selection`, caps on; runs "fit the section box to the selection" |
| Presentation | scene dressing, bloom, fly-to and reveal on; sweep on, mode `both` |
| Clearance review | clearance on, tight 0.05 m, max 0.5 m |
| Plain | `xray` off; bloom and edge glow off |
| Focus glow | bloom on, edge glow on, glow scope `focus` |
| Solid | `xray` off; view modes and imaging reset; bloom, edge glow and auto orbit off |

## The top bar modes

The top bar has five modes. Each applies one preset.

| Mode | Key | Preset |
| --- | --- | --- |
| Solid | `Shift+0` | Solid |
| Ghost | `Shift+1` | Coordination |
| Radiograph | `Shift+2` | Radiograph |
| Glow | `Shift+3` | Focus glow |
| Cutaway | `Shift+4` | Peel only |

Pressing a lit mode again switches to Solid. A mode is lit only while the settings still match the preset. A setting that changes by
itself (a running animation that writes into the section) can clear the light. Applying a mode is one step of undo.

## Your own presets

- **Save**: **Presets** drawer, save the current settings under a name.
- **Edit, duplicate, delete**: built-ins cannot be edited or deleted. Duplicate one to change it.
- **Export and import**: an `xray-presets/1` file.
- **Share**: one preset as a link (`#preset=`). The preset is applied once and is not saved. Its actions run too, so open such links only from people you trust.
- Your presets are kept in this browser. They are settings only: no API keys, tokens or names.
- An installation can replace or add presets with `web/public/xray.presets.json`. A replacement with a built-in id (for example `radiograph`) also changes the top bar mode that uses it.

## Where presets sit in the ladder

Mode = one click on a preset. Preset = look only. View = camera, look, selection and hides. Fly-through keyframe = a view with
timing. Share link = a view as an address. Chapter 13 has the table of what each stores.
