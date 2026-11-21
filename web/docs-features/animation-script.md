# Animation script

A short text that animates the model: camera moves, settings, showing and hiding elements with fades, selection and captions.
Write it in the **Script** tab of the right sidebar (`src/plugins/animScript.ts`, `src/anim/scriptPanel.ts`). The language is plain
English in the style of HyperTalk, small and strict. It compiles to a **score** (`src/anim/score.ts`), the timeline format that the
score player plays, so a script plays, records and restores the view the same way as a fly-through of the Views tab.

```
-- A walk around the pumps
mode ghost
fly to class IfcPump over 3 seconds
together
  orbit 120 degrees about class IfcPump over 6 seconds
  caption "Four pumps" "Seen from every side" for 6 seconds
end together
select nothing
```

**See also:** the [formal grammar](animation-script-grammar.md) (EBNF, limits, timing rules) and the
[guide for coordinators](animation-script-guide.md) (first steps, recipes, reading the errors).

## How time works

- Statements run in order. **Each starts when the one before it has ended.**
- Fly, orbit, `set ... over`, `fading`, caption, label, hover and wait last their time. Mode, apply preset, select and a plain
  show or hide are instant and take no time.
- `caption`, `label` and `hover` last 3, 3 and 2 seconds unless `for N seconds` says otherwise, and the next statement waits for them.
  Put them in a `together` block to run them beside a camera move.
- `together` starts every statement inside at the same moment; the block lasts as long as its longest statement.
- Keywords ignore case. A comment starts with `--` or `#` and runs to the end of the line. One statement per line; indentation is free.
  Text goes in "double quotes". A number may carry `s`, `sec`, `second` or `seconds` (`2s`, `2 seconds`).
- Limits: a script runs at most 1 hour, makes at most 5000 cues, runs a loop at most 500 times and at most 20000 statements in all.

## Statements

<!-- statements:start -->
### Camera

- `fly to <elements> [over N seconds] [ease in|out|in out|linear] [margin N]`: Move the camera to frame the elements. Lasts 2 seconds unless told. Margin 1 to 6 is the room around them.
- `fly to view "<name>" [over N seconds] [ease ...]`: Move the camera to a saved view of the Views tab.
- `orbit N degrees [about <elements>] [over N seconds] [ease ...]`: Turn the camera around the elements, or around the model. Lasts 3 seconds unless told.

### Look

- `set <path> to <value> [over N seconds] [ease ...]`: Change one setting by its parameter path. Numbers blend over the time; on, off and text switch at its end.
- `mode ghost|solid|radiograph|glow|cutaway`: Switch to a mode of the top bar. Instant.
- `apply preset "<id or name>"`: Apply a built-in or saved preset. Instant.

### Visibility

- `show <elements> [fading over N seconds]`: Show hidden elements, with a fade or at once. `show everything` brings back all.
- `hide <elements> [fading over N seconds]`: Hide elements, with a fade or at once.
- `isolate <elements> [fading over N seconds]`: Show only these elements and hide the rest.

### Selection and notes

- `select <elements> | select nothing`: Select elements, or clear the selection. Instant.
- `caption "Title" ["More text"] [for N seconds]`: Show a caption. Lasts 3 seconds unless told, and the next statement waits for it.
- `label <elements> with <field>, <field> [for N seconds]`: Pin labels to the elements. Fields: name, class, storey, or a property as "Pset_X.Prop". Lasts 3 seconds.
- `hover <elements> [for N seconds]`: Show the hover highlight on the elements. Lasts 2 seconds unless told.

### Timing and variables

- `wait N [seconds]`: Do nothing for a time.
- `together ... end together`: Start the statements inside at the same moment. The block lasts as long as the longest.
- `repeat N times ... end repeat`: Run the statements inside again and again. `index` counts from 1. At most 500 times.
- `repeat for each element in <elements> ... end repeat`: Run the statements once for each element. `it` is the element. At most 500 elements.
- `repeat for each set in sets ... end repeat`: Run the statements once for each stored selection set. `it` is the set.
- `put <number> into <name>`: Keep a number under a name. Use the name wherever a number goes. Signs: + - * / and ( ).
<!-- statements:end -->

`ease` takes `in`, `out`, `in out` or `linear`; the default is `in out` for camera moves and for numbers that blend.

### Elements

Wherever a statement says `<elements>`:

- `where <criteria>`: the [criteria query language](sets-query.md). Text values may be bare words or in double quotes:
  `where class = IfcPump and storey = "Level 2"`, `where name like "P-1%"`, `where "Pset_WallCommon.IsExternal"`. A value with a
  space must be in double quotes. The words `over`, `ease`, `margin`, `fading`, `for`, `with` and `about` end the criteria.
- `class IfcPump` or `class IfcPump, IfcValve`: shorthand for the elements of those classes.
- `set "Name"`: the members of a stored selection set ([sets-query.md](sets-query.md)).
- `the selection`, `everything`, `it`, `elements "gid1", "gid2"` (by GlobalId).

### Variables and numbers

`put 2 * 1.5 into pause` keeps a number under a name; use the name wherever a number goes (`wait pause seconds`). Signs: `+ - * /` and
parentheses. Inside `repeat`, `index` counts from 1. In text, join pieces with `&`: `caption "Pump " & index`. `it` in text is the
set name (in a set loop) or the GlobalId (in an element loop). Names are case-insensitive and cannot be words of the language.

### Settings paths

`set` takes the paths of the parameters document ([docs/SETTINGS.md](../../docs/SETTINGS.md)), for example `cinematic.glowStrength`. The
compiler checks them against the paths of this build when a model is loaded; a path it does not know gives a warning with the
nearest known paths and the player skips it. A setting that is a number blends over the time; on, off and text switch at the end of
the cue.

## What each statement becomes

| Statement | Cue of the score |
| --- | --- |
| `fly to <elements>` | `camera` with `to: { frame: <ref>, margin }`, 2 seconds, `inOut` |
| `fly to view "name"` | `camera` with `to: { view }` |
| `orbit N degrees [about ...]` | `camera` with `to: { orbitDeg, about }`, 3 seconds |
| `set path to value` | `param` with `path` and `to` (number, boolean, text or a list of numbers) |
| `mode m` | `preset` with the id of the built-in preset of the mode (`solid`, `coordination`, `radiograph`, `focus-glow`, `peel-only`) |
| `apply preset "x"` | `preset` with the id (a name is looked up) |
| `show` / `hide` / `isolate` | `visibility` with `show`, `hide`, `isolate` or `showAll`; `dur` is the fading time |
| `select` / `select nothing` | `select` with `elements` or `null` |
| `caption` | `caption` with `title` and `text` |
| `label` | `label` with `elements` and `fields` |
| `hover` | `hover` with `elements` |

Every cue has `line`, the line of the script, which the editor highlights while the cue plays. Elements stay references (a query, a set
name, GlobalIds, the selection) for the player to resolve when playback starts. Only `repeat for each element` needs the model while
compiling: it expands to one pass per element, with `it` as `{ globalIds: [id] }`. Without a model it is an error.

## The Script tab

- **Editor** with line numbers and light colours: statement words blue, options purple, text green, numbers orange, comments grey.
  A wavy underline marks the place of an error (red) or a warning (amber). `Ctrl+Enter` runs; Enter keeps the indentation.
- **Problems** list under the editor, live as you type. Each row has line, column, a message and a hint ("Did you mean `fading`?", the
  nearest setting paths, the nearest preset names). A click jumps to the place. The tab button shows the number of errors.
- **Run, Pause, Stop** use the score player. The line being played is highlighted. If the player is not part of the build, Run says so.
- **Examples** menu: a walk around the pumps (process-plant sample), peeling back the slabs storey by storey (synth5k), highlighting each
  selection set with a caption, and changing the look over time.
- **Saved scripts**: give the script a name and **Save**. Scripts are kept per model (the model identity of
  `src/markup/scope.ts`) in `localStorage["xray.anim.<model>"]`, together with the text you were editing, so a reload brings it back.
- **Export** downloads the text as `<name>.xrayanim` (plain text, the script itself); **Import** reads such a file (or a `.txt`).
- **Statement reference** with an **Insert example** button for each statement.
- On a phone the right sidebar is a bottom sheet; the tab has one column, 16 px text and large buttons.

Scripts are the person's own text. They are **never** part of the parameters document, share links, saved views, presets or packed
pages; only the browser's storage and exported files hold them (`tests/animscript-leak.test.ts`).

## For scripts and smoke tests

```js
const r = window.__xrayScript.compile('fly to everything over 3 seconds');  // { score, errors }
window.__xrayScript.run(text);       // compile and play; { ok, message, errors, score }
window.__xrayScript.list();          // the saved scripts of this model
window.__xrayScript.save('Tour', text);
window.__xrayScript.load('Tour');
window.__xrayScript.state();         // { errors, playingLine, status, running, ... } once the tab was shown
```

The pure modules are in `src/anim/script/`: `lexer.ts`, `parser.ts` (syntax tree with line and column), `compiler.ts` (tree to score),
`scriptHelp.ts` (this reference), `examples.ts`, `highlight.ts`, `runner.ts`. They use no DOM, no storage and no network, and no `eval`.
`compileScript(text, options)` takes optional `resolve` (query to GlobalIds), `setNames`, `paramPaths`, `presets` and `views` from the app.
