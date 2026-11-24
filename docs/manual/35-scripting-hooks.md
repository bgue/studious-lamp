# 35. Scripting hooks and plugins [D]

## 35.1 Reaching the viewer from outside, and adding to it from inside

You want a smoke test that loads a model, selects a duct and checks that a wall ghosts. Or a button that runs your
company's check. Or a macro that assigns trades by a rule only you know. Clicking is not enough, and a fork of the whole
viewer is too much. The viewer offers two doors: objects on `window` for scripts, and a plugin interface for code that
becomes part of the build.

### The idea

Everything beyond the core (loader, renderer, the x-ray controller) is a **plugin**: one module, one feature, one
document. A plugin plugs into the viewer in four ways:

- **Hooks**: functions the viewer calls at fixed moments (once at start, after each model, after the selection changes,
  every frame).
- **Actions**: named commands. An action gets a keyboard shortcut, an entry in the cheat sheet (chapter 3) and an entry in
  the command palette and the shortcut editor for free.
- **Tools**: a button in the tool strip, with a drawer if it needs a panel.
- **Parameter sections**: a named block in the exported `xray-params/1` document, so presets, `xray-pack --params` and
  (if you allow it) share links carry your settings.

Each feature also exposes a `window.__xray…` object. Scripts, smoke tests and packed pages use it. These objects are the
supported way to drive the viewer from the outside.

## 35.2 Try it: drive the viewer from the console

Open the viewer, choose the **FZK-Haus 4D** sample, then open the browser's developer console.

1. Check the tab is there: `window.__xray4dSchedule.summary()` returns the project, data date and counts.
2. Read the links: `window.__xray4dSchedule.links().length` gives the number of links; `window.__xray4dSchedule.report()`
   gives the coverage.
3. Find out which tools are in the strip: `window.__xrayToolbar.tools()`.
4. Open the 4D tab on the Play section: `window.__xray4dSchedule.open('play')`, then `window.__xray4dSchedule.play()`.
5. Stop it: `window.__xray4dSchedule.stop()`.

The same objects work in a packed page (chapter 30) once it has started. Wait for the object's `ready()` where there is
one, because saved data is restored asynchronously.

## 35.3 The scripting objects

| Object | Feature |
| --- | --- |
| `__xray` | the core: `app`, `renderer`, `classification`, `stats` |
| `__xrayViewModes`, `__xrayImaging`, `__xraySection` | peel and behind-only, imaging looks, section box and plane |
| `__xrayCleanup`, `__xrayPresets` | cleanup rules, presets |
| `__xrayPenetrations`, `__xrayMeasure`, `__xrayClearance` | checks (chapters 10 and 11) |
| `__xrayViews`, `__xrayFlythrough`, `__xrayScript`, `__xrayRecord` | views, fly-throughs, animation scripts, video export |
| `__xrayIssues`, `__xrayMarkup`, `__xraySheets`, `__xrayBcf`, `__xrayWork`, `__xrayIssueReport`, `__xrayClash` | issues, drawings, PDF sheets, BCF files, their store, the issue report, check results as issues |
| `__xrayClassify`, `__xrayRevision`, `__xrayIfcSave` | classification, revision walk, Save IFC |
| `__xraySearch`, `__xrayUndo`, `__xrayPointer`, `__xrayTopBar`, `__xrayRightSidebar`, `__xrayGizmo` | search bar, undo, pointer modes, top bar, right sidebar tabs, view cube |
| `__xrayMap` | the map under the model (not the 4D mapping) |
| `__xrayPointCloud`, `__xrayXr` | scans, AR and VR |
| `__xrayToolbar` | `open(id)`, `close()`, `toggle()`, `tools()` |
| `__xrayParams`, `__xrayHelp` | the params document, help |
| `__xray4dMap` | 4D mapping: `values`, `assign`, `clear`, `suggest`, `proposals`, `accept`, `reject`, `coverage`, `colourBy`, `selectUnassigned`, `exportJson`, `importJson`, `open` |
| `__xray4dSchedule` | 4D workflow: `load`, `summary`, `config`, `link`, `links`, `report`, `decide`, `exportLinks`, `importLinks`, `plan`, `play`, `stop`, `seekDate`, `record`, `open`, `loadSample` |
| `__xray4d`, `__xray4dFilm` | 4D playback: `registerPlan`, `demoPlan`, `play`, `state`, `live`, `bench`; the film builder that `xray-4d render` calls |
| `__xrayBoot` | read once at start by a packed page: model, preset, params, camera, selection, tools, autoplay |
| `__xrayReady`, `__xrayError`, `__xrayInfo` | flags a test waits on: `__xrayReady` is true after the first frame, `__xrayError` holds a start-up error |

The table follows the source (`window.__xray…` assignments in `web/src/plugins` and `web/src/anim`). Each plugin file lists the
methods of its object in the comment at its top. In a running viewer, `Object.keys(window).filter(k => k.startsWith('__xray'))`
shows what is there. Some objects (embedded models, the IFC reader, credits) are for the build and are not listed.

A few calls you will use most, from the 4D documents:

- `__xray4dMap.assign(attr, value, target)`: `attr` is `location`, `trade` or `zone`. `target` is `{ selection: true }`,
  `{ query }`, `{ storey }`, `{ set }`, `{ ids }` or `{ globalIds }`. It returns the counts of assigned, unchanged and matched
  elements. This is an accepted assignment, so use it as a person would.
- `__xray4dSchedule.decide(linkId, status)`: accept, reject or reopen a link.
- `__xray4dSchedule.load(text or bytes, name?, project?)`: read an XER. It returns `{ ok, message }`. A file with several
  projects waits for `chooseProject(name)`.
- `__xray4d.registerPlan(name, plan)`: register a plan, so a `schedule4d` cue or a script can use it by name.

## 35.4 Add an action and a tool

Plugins are compiled into the viewer. They are not loaded at run time. You add one to the source and rebuild. The steps:

1. Create `web/src/plugins/myThing.ts` that exports a plugin with a `name` and the hooks you need. Keep logic that needs no
   screen in its own module under `web/src/myThing/`, so tests can reach it.
2. In `install(app)`, register an action and a tool.
3. Add the plugin to the `PLUGINS` list in `web/src/plugins/index.ts`, at the place its hooks need. The order matters: hooks
   run in list order, `help` runs after every plugin that builds a panel, `panelDock` is last, and `boot` is at the very end.
4. Expose `window.__xrayMyThing` for scripts and smoke tests.
5. Write `web/tests/myThing-*.test.ts` for the pure part, and a document in `web/docs-features/myThing.md`. Add help text in
   `web/src/ui/helpText.ts` and run `npm run docs`.

An outline of step 2:

```ts
import type { AppPlugin } from '../app';
import { registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';

export const myThingPlugin: AppPlugin = {
  name: 'myThing',
  install(app) {
    registerAction({
      id: 'myThing.run', label: 'Run my check', group: 'Panels', keys: ['Alt+m'],
      run: () => { /* do the work */ },
    });
    registerTool({
      id: 'myThing', label: 'My check', title: 'Run my check on the model', icon: '<svg viewBox="0 0 20 20">…</svg>', order: 120,
      panel(container) { container.textContent = 'Hello'; },
    });
  },
};
```

The hooks, all optional:

| Hook | Called |
| --- | --- |
| `install(app)` | once, after the interface exists and before the first model |
| `onModel(app)` | after every model is installed |
| `onStatic(app)` | after the selection, classification or settings changed and the x-ray classification has run |
| `beforeFrame`, `onFrame`, `afterFrame` | every frame; `onFrame` may return true to force a render-state upload |

Action ids are dotted (`select.clear`, `mode.peel`). Key chords are `Ctrl+`, `Alt+`, `Shift+` or `Meta+` plus a key, or
`code:` plus a key code for layout-independent keys. An action can be held (`hold`), repeat (`repeat`) or disable itself
(`enabled`). Reserved tool ids include `open`, `presets`, `xray`, `viewModes`, `imaging`, `section`, `measure`, `clearance`,
`penetrations`, `bcf`, `pointcloud`, `xr`, `cleanup`, `largeModel` and `classify`; pick another. The `order` number sorts
the strip: Open model is 10, X-ray 30, View modes 40, Measure 70, Clearance 80, Penetrations 90, Cleanup 110.

### Parameter sections

`registerParamSection(name, { collect(), apply(value, bad, path), share? })` adds a section to the params document. In
`apply`, push a path onto `bad` for a key you cannot use, and the importer reports it. Set `share: true` only for small
sections, because share links carry them in the address. The name must not clash with a core key (`xray`, `classification`,
`sightlines`, `overrides`, `display`, `farMode`, `tiersMode`, `tiers`, `rendering`, `cinematic`, `camera`, `selectionSets`,
`classStyles`, `materialAliases`).

### The shared overlay

A tool that draws labels over the canvas (a measure label, a callout) uses the shared overlay (`getOverlay(app)`), an SVG
layer above the canvas. It gives you a group per layer, a callback when the camera or canvas changes, and a `project(point)`
call that gives pixel coordinates. `ov.place` keeps your label clear of the toolbar, the gizmo and the legends and draws a
leader line back to its anchor.

## 35.5 Booting a packed page

A page made by `xray-pack` (chapter 30) reads `window.__xrayBoot` once, after the first model installs. It handles, in this
order: page title, preset, params, camera, selection, open tool, kiosk, saved view, packed fly-throughs and scripts,
autoplay. `__xrayBoot.tools` is an ordered list of tool ids to show: anything else is hidden and gets no `tool.<id>`
action. 4D plans are in `__xrayBoot.plans`, registered by file name.

## 35.6 Limits and gotchas

- Plugins are not loaded at run time, and there is no sandbox. A plugin has the same reach as the viewer.
- The `window.__xray…` objects are the stable way in. Internal modules are not. A smoke test that imports a module path
  breaks on a refactor; one that calls the object does not.
- A section name that clashes with a core key is a bug. Test with an exported params document.
- Hooks run in list order, and `onFrame` runs every frame. Keep it short, or it costs the frame rate.
- Most objects are installed after the first model loads. Wait for it.
- Share links carry only parameter sections marked `share`. Do not put private data in one.

## See also

- Chapter 3: the cheat sheet, palette and shortcut editor that your actions appear in.
- Chapter 30: packed pages and `__xrayBoot`. Chapter 34: the data side of 4D.
- Appendix A: keyboard reference.
