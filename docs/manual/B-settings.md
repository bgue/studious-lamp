# Appendix B. Settings reference

The viewer has hundreds of settings. A manual page for each would be out of date by the next release, so this appendix does not
copy them. It explains how to find any setting, how to read what you find, and where each panel's settings live. The full list
is the file `docs/SETTINGS.md` in the repository.

## Three ways to get the same text

Every setting has a help text with four lines. The viewer shows it, and the file holds it.

1. **In the viewer.** Hover a control for 350 ms, or focus a slider with the keyboard. A tooltip shows the four lines.
2. **In the search bar.** Press `/` and type part of a setting name. Settings are in the results, next to elements, commands, presets, views and sets (chapter 7).
3. **In the file `docs/SETTINGS.md`.** One table per folder of the settings panel. Use your editor's search to find a name.

The file is generated from the same source as the tooltips. Do not edit it by hand; a change is made in `web/src/ui/helpText.ts`,
then `npm run docs` writes the file again. Tooltips can be switched off for a session with `window.__xrayHelp.disable()`.

## How to read a row

Each row has five columns.

| Column | What it tells you | Read it when |
| --- | --- | --- |
| **Setting** | The label on the control, exactly as on screen. A row that starts with *Folder:* describes the whole folder. | You look up a name |
| **Intent** | What the setting does, in technical wording. | You want the precise meaning |
| **Impact** | What you see change on screen, in everyday words, with no jargon. At the ends of a slider, or in the on and off states of a switch. | You want to know what it will do to the picture. Read this first. |
| **Use** | What to do with it, in the imperative. | You want advice |
| **Ref** | The section of the technical report that defines it. | You want the theory |

Intent and Use are written in a controlled, short-sentence English. They are exact but dry. Impact is the one for people.

Controls that do not apply right now are dimmed. For example the imaging controls are dimmed while the render style is
**standard**.

## Names to know when you read the file

- The file still has folders with old names: `BCF`, `Markup`, `BCF drawer`, `Markup drawer`, `Classify drawer`, and rows that say "sketch". Their controls now live in the **Views**, **Issues** and **Classification** tabs. Appendix E lists the old names. Where the two differ, the viewer is right.
- The file has a glossary of its own (terms such as occluder, buffer, tier). Appendix E gives short versions.
- Some folder names in the contents list appear cut short (for example the simplify folders). That is how the generator wrote them; the text of the rows is complete.
- Names with a slash, such as `Sheet view/Fit`, are a control inside a folder.

## Where each panel's settings are

The settings panel is the **Parameters** tab of the right sidebar. Each folder is one feature. The action panel (the tool strip at
the left edge) has one button per tool and each opens a drawer. Drawers and folders hold the same settings in two places.

| Part of the viewer | Where | Folder in `docs/SETTINGS.md` | Chapter |
| --- | --- | --- | --- |
| The x-ray itself: switch, pin, hide, frame | Top of the Parameters tab; **X-ray** tool | X-ray | 4 |
| Which elements count as host, near, far | Parameters tab | Classification (Alg 1) | 4 |
| How strongly things ghost | Parameters tab | Sightlines (Alg 2) | 4 |
| Colours, edges, ghost look | Parameters tab | Display, Rendering | 4, 6 |
| Pins and hides | Parameters tab | Overrides (Alg 7) | 4 |
| Opening files, sample models | **Open model**, **Sample Projects** | Open model, Sample Projects | 2 |
| Class styles per IFC class | Parameters tab | Class styles, Classes | 4 |
| Camera moves, bloom, glow, sweep, grade, explode, turntable, dolly | **Cinematic** folder | Cinematic and its sub-folders | 6, 21 |
| Imaging looks | **Imaging** tool | Imaging, MRI slice, Imaging drawer | 6 |
| Behind-only and peelback | **View modes** tool | View modes, Behind only, Peelback | 5 |
| Section box and plane | **Section** tool | Section, Section drawer | 5 |
| View cube and section strip | Overlay on the canvas | Gizmo | 3, 5 |
| Cleanup of debris | **Cleanup** tool | Model cleanup and sub-folders | 9 |
| Hover cards | Parameters tab | Hover info | 3 |
| Presets and the top bar | **Presets** tool; top of the screen | Presets, Presets drawer, Top bar | 4 |
| Distance and clearance | **Measure**, **Clearance** tools | Measure, Clearance, and their drawers | 10 |
| Penetrations | **Penetrations** tool | Penetrations, Penetrations drawer | 11 |
| Point clouds | **Scan** tool | Point cloud, Scan drawer | 12 |
| Views, drawings, issues, PDF sheets | **Views** and **Issues** tabs of the left sidebar | Sidebar/Views tab, Views panel, Sidebar/Issues tab, Issues panel, Drawing toolbar, Sheet view | 13 to 17 |
| Classification (discipline) | **Classification** tab of the right sidebar | Right sidebar, Classify drawer | 18 |
| 4D mapping and schedule | **4D** tab | 4D tab | 24 to 28 |
| Animation scripts | **Script** tab | Script tab | 23 |
| Revisions | Revision banner and walk | Revision banner, Revision walk | 20 |
| Map under the model | Parameters tab | Map | 6 |
| Keys and navigation style | **Keyboard** folder | Keyboard, Shortcut sheet, Shortcut editor, Command palette | 3.2, Appendix A |
| AR and VR | **WebXR** tool | WebXR, WebXR drawer | 31 |
| Search | Top bar | Search bar | 7 |
| Large files | **Large model** tool | Large model drawer | 2 |
| All settings as a file | **Export / import** folder | Export / import | 29 |

## Navigation style

One setting in the **Keyboard** folder decides how the mouse and the keys move the camera: **navigation style**.

| Value | What it does |
| --- | --- |
| **BIM** (default) | The style of Revit, Navisworks and Solibri. The wheel zooms toward the cursor, middle drag pans, `Shift` with middle drag orbits, an orbit turns around the point you grab, and a double-click flies to an element. `w a s d q e` do nothing, except in Walk mode (3.2). |
| **Game** | The older style. `w a s d q e` always fly the camera, middle drag zooms, the wheel zooms to the orbit target, and there is no pivot pick and no double-click action. |

Two more settings in the same folder belong to Walk mode (3.2). Like the navigation style, they are kept in your browser, not in exported settings, share links or views.

| Setting | Default | What it does |
| --- | --- | --- |
| **eye height (m)** | 1.6 | Your eye height above the floor when you drop in with a double-click, and the fallback for the storey jump. From 0.5 to 3. |
| **Walk collision** | off | When on, the movement keys and the wheel stop you about 0.3 m short of a wall and slide you along it. Doors, hidden parts and ghosted parts do not block. |

Choose **Game** to get the old keys back. The choice is kept in your browser, not in exported settings, share links or views.

## Saving settings

Settings are not saved between visits unless a section says so. To keep a look, save it as a preset (chapter 4) or a view
(chapter 13). To move all settings, use the **Export / import** folder:

| Button | What it does |
| --- | --- |
| **Export JSON** | Downloads all settings as an `xray-params/1` file. |
| **Copy JSON** | Puts the same text on the clipboard. |
| **Import JSON** | Reads a file. The viewer applies what it can and lists keys it cannot use. |
| **Copy share URL** | Copies a link with the main settings and camera (chapter 29). |
| **Export Python dict** | Writes the settings as a Python dictionary for a script in Bonsai or Blender. |
| **Reset to defaults** | Sets all settings back, and clears your pins, hides and class edits. |

An exported file does not hold API keys, tokens or reviewer names (appendix G). A file that contains a key field is refused on import.

A few settings are remembered in the browser by themselves: the keyboard speeds, the navigation style, shortcuts, panel sizes and folded state, which
side panels are open, and the view list style. Appendix G lists them.

## Settings for a packed page

`xray-pack --params` takes an exported file. A partial file is fine: name only the keys you want. For example:

```json
{ "schema": "xray-params/1", "sightlines": { "alphaMin": 0.05, "layerWeighting": "budget" } }
```

Keys the viewer does not know are reported once in the browser console (chapter 30).

## Where the defaults come from

Factory values are the report's defaults (for example `alphaMin 0.15`, `alphaMax 0.85`, `gamma 0.5`, `smoothingRate 0.20`,
`bufferBase 0.30 m`). Some defaults differ on purpose from the report. `occluderScope` is `all`, so a Far part that blocks the view ghosts, with `farWeight` 0.7. `layerWeighting` is `front`. Chapter 4 explains both.
An installation can change the factory look with `web/public/xray.config.json` (class styles) and `web/public/xray.presets.json`
(presets). Those files are for administrators and appear in chapter 35.
