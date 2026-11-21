# 4D schedule workflow in the viewer

The **4D tab** also runs the whole schedule workflow: open a Primavera P6 export (`.xer`), say what its codes mean, link activities to elements, review the links, set the film style, play and record the 4D film, and write the links back into the IFC. Design: [4d-xer-animation.md](../../docs/design/4d-xer-animation.md). The pure pipeline behind it is described in [4d-linking.md](4d-linking.md); playback in [4d-playback.md](4d-playback.md); the location, trade and zone mapping in [4d-mapping.md](4d-mapping.md).

The sections of the tab, top to bottom: **Values, Assign, Suggest, Coverage** (the mapping tool), then **Schedule, Configure, Link, Style, Play**, then **Import / Export** (the mapping dataset). Open the tab with `4D`, or with `window.__xray4dSchedule.open('schedule' | 'configure' | 'link' | 'style' | 'play')`. A phone shows the tab as a bottom sheet; the controls keep a 32 px touch height.

## The steps

1. **Map the model** (optional, recommended): give elements a location, trade and zone in the mapping sections. The accepted assignments take part in linking. The sample needs none: it reads the storey and uses queries for the trades.
2. **Schedule.** `Open .xer` (a file input), or **drop an `.xer` on the viewer** (a `.4d.json` dropped there loads as a configuration). A file with several projects shows a list: pick one and press `Use project` (the configuration remembers the project). The summary shows the project, file, data date, activity counts by type, WBS and relation counts, the code types with their value counts, the user fields and the number of parser warnings.
3. **Configure.** `Location from`, `Trade from` and `Zone from` are lists filled from the schedule: its activity code types (`Activity code: Level`), user fields (`User field: Area`) and WBS levels (`WBS level 1` ...); `Not used` turns one off. A first guess picks a code type whose name looks like level / floor / storey for the location, trade / discipline for the trade and zone / area for the zone. The **value table** lists, for one attribute at a time, the schedule's values with the number of activities that carry each and a box for the **model value** it maps to (`EG` -> `Erdgeschoss`); the box offers the model's own values (storeys, zones, the mapping tool's lists). An empty box uses the schedule value as it is. **Trade queries**: one row per trade value with an element query in the criteria language (see [sets-query.md](sets-query.md)), a live count of matches, and the matches tinted orange while the box has focus. `Existing parts` is a query for elements that stand before the job starts. `Save` keeps the setup in the browser for this model (it is also kept after every change), `Export .4d.json` and `Import .4d.json` write and read the file (`FourDConfig`, schema `xray-4d-config/1`).
4. **Link.** `Link schedule` runs `linkSchedule` with the config, the accepted assignments of the mapping tool and the earlier decisions. The coverage table shows elements and activities (linked, of, share); then ties, the unlinked elements grouped by class and storey (each group has `Select`, and `Select unlinked` selects all of them), the activities without elements (a list), and the **suggestions** with `Accept` and `Reject` (best confidence first, reasons under each row, a click selects the elements). `Open report` opens the link report (`renderReportHtml`) in a new window. `Export links` and `Import links` write and read the **LinkML dataset** (the file format of the mapping export, now with `schedule`, `activities` and `links`; reviewer names stay out). Importing a dataset replaces the links on screen and merges its assignments into the mapping tool.
5. **Style.** The options of `FourDStyle`; they are part of the configuration. See the table below.
6. **Play.** `Play` builds the plan from the accepted links, registers it under the name `4d:<model name>` and plays a `schedule4d` cue over the film length with the score player (the HUD, keyboard, fly-through transport and `Space` come from the player). The slider **scrubs by schedule date**: it seeks while the film plays, and from a stop it starts the film paused at that date. `Record` opens the video export dialog for the same score. `Save IFC with 4D links` opens Save IFC (see below).

## Review state of the links

Status is kept per link (`proposed`, `accepted`, `rejected`). A decision is kept when the linker runs again:

- an **accepted** suggestion (or a manual or agent link) goes back in as a prior link, wins over the rules and stays accepted;
- a **rejected** link goes back in too, so the activity gets no new suggestion;
- links that the configuration makes again (`attributes`, `override`, and `property` or `native` from the model) are **not** kept: they follow the configuration and the model;
- an open suggestion is made again on every run (it is not a decision). `Reopen` (under `Decided links`) sets a link back to `proposed`.

Only **accepted** links drive the plan and are written into the IFC.

## Style options

| Option | Values | Notes |
| --- | --- | --- |
| View | planned, actual to date then forecast, variance | default planned |
| Unbuilt parts | hidden, faint ghost | |
| Window | the whole job, look ahead N weeks (from the data date), date range | |
| Film length by | length in seconds, or days per second | one of the two; default 120 s (the sample 90 s) |
| Pace | warp (busy weeks get more screen time), fixed | |
| Camera | director, fixed (the current camera), none | see below |
| Explode, Section box | auto, off | made by the director |
| X-ray active work | on, off | the active elements are the x-ray focus; works without the director |
| Labels | 0 to 12 | at most this many activity labels at once |
| Critical float | hours, or driving path only | |
| Captions, milestone hold | on/off, seconds | |
| Default split | by trade, all at once, sweep x / y / up, storey by storey, by name | the `*` entry of `split` |
| Trade colours | colour per trade value | from the file's style, else the mapping tool's trade colours |

### The camera director

The director is written apart (`src/schedule/director.ts`, `directFourD(plan, model) -> Cue[]`). The workflow does not import it by name: `src/map4d/directorHook.ts` finds it with a glob import (an empty result when the file does not exist, so the build compiles and the bundle holds nothing) and also accepts `registerDirector(fn)` from a plugin or a test. With `Camera: director` and a director present, its cues are added to the score after the `schedule4d` cue. **Without one, the film keeps the current camera** (as `fixed`), and the Style and Play sections say so (`window.__xray4dSchedule.note`). A director that throws gets the same fallback with its error in the note. The plan's style (explode, section box, labels, captions) travels in `plan.style`, where the director reads it.

## Save IFC with 4D links, and reading them back

`Save IFC with 4D links` opens the existing Save IFC dialog with the 4D box on. The property set `Xray_4D` (see [4d-mapping.md](4d-mapping.md)) gains **`ActivityIds`** (`IfcText`): the task codes of the **accepted build links** of the element, sorted, comma separated (`A1010,A1040`). Elements with only links get the set too. Remove links are not written; a task code with a comma or semicolon is skipped; the property reader keeps the first 80 characters of a text, so an element with very many codes is cut when read back. (`IfcTask` and `IfcRelAssignsToProcess` come with the `xray-4d` command line.)

**Reading back.** `Xray_4D.ActivityIds` is among the hover properties of the opened model. `Link schedule` passes it to the linker as `idProperty`, so the links come back as **accepted, confidence 1, `source: property`**, with the schedule loaded and the codes found in it, and no configuration needed.

## Persistence

IndexedDB database `xray-4d-schedule` (next to `xray-4d-map`), one record per model (the model identity key): the configuration, the links with their review state, and the `.xer` file as it was read (files above 24 MB are not stored; the configuration and links are). The same work comes back when the model is opened again, in the same browser; without IndexedDB nothing is kept and `Export` is the way. Nothing goes into the page address, share links, saved views or packed pages.

## The sample: FZK-Haus 4D

The Sample Projects menu has **FZK-Haus 4D** after FZK-Haus. It loads the model, then `fzk-haus.xer` and `fzk-haus.4d.json`, links (every element), builds the plan and leaves the 4D tab open on **Play**. The two files (26 KB and 2 KB) are imported as strings (`?raw`, `src/map4d/sampleFiles.ts`, loaded by a dynamic import), so the single-file build has them in its one chunk and makes no request. The entry exists wherever FZK-Haus does.

## Script API

`window.__xray4dSchedule`:

| Call | Does |
| --- | --- |
| `load(text or bytes, name?, project?)` | read an XER; `{ ok, message }`; several projects wait for `chooseProject(name)` (listed in `summary().pendingProjects`) |
| `summary()` | project, data date, counts, code types, user fields |
| `config()`, `setConfig(c)`, `loadConfig(text)`, `exportConfig()` | the `FourDConfig` |
| `link()` | run the linker; coverage summary or `{ error }` |
| `links()`, `report()`, `reportHtml()` | the LinkML links, the `LinkReport`, the report page |
| `decide(linkId, status)` | accept, reject or reopen a link |
| `exportLinks()`, `importLinks(text)` | the LinkML dataset |
| `plan()` | build and register the plan (`4d:<model>`) |
| `play(fromSeconds?)`, `stop()`, `seekDate(planMs)`, `record()` | the film |
| `activityIds()` | GlobalId -> task codes that Save IFC writes |
| `loadSample()` | the FZK-Haus 4D sample |
| `open(section?)`, `ready()`, `flush()`, `reset()` | the tab, the restore, write now, forget this model |
| `playing`, `note` | state, and the director note |

## Files

`src/map4d/` (pure: `scheduleConfig.ts`, `linkReview.ts`, `scheduleStore.ts`, `directorHook.ts`, `ifcio.ts` for `ActivityIds`; app: `scheduleController.ts`, `schedulePanel.ts`, `sampleFiles.ts`), `src/plugins/map4d.ts` (the API), `src/plugins/fileLoader.ts` (the drop), `src/samples.ts` (the menu entry), the `ActivityIds` writer in `src/ifcsave/additions.ts`, tests `tests/map4d-schedule-config.test.ts`, `map4d-link-review.test.ts`, `map4d-schedule-store.test.ts`, `ifcsave-4d-links.test.ts`, `samples.test.ts`, smoke `bench/smoke-4d-schedule.mjs`.

## Limits

- One schedule per model at a time; a baseline (`.xer`) is not loaded in the viewer yet (the plan builder supports it).
- The configuration UI picks one source per attribute; a file with several sources, a pattern source or `activities` overrides keeps them and shows them, and only the first source is edited.
- The model side of the configuration (`config.model`) is read from the file and not edited in the tab.
- The review list shows the first 60 suggestions; the unlinked list the first 40 groups.
