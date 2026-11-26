# Animation script

A short text that animates the model: camera moves, settings, showing and hiding elements with fades, selection and captions, and,
for a 4D plan, the schedule with its explode, section box and tint.
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
- 4D: `schedule` does not wait, and `at date` / `at milestone` put the statements after them at that moment of the plan's clock, even
  before the end of earlier ones (see the [grammar](animation-script-grammar.md#31-the-4d-statements) and chapter 12 of the guide).
- `if`, `repeat while|until|with` and your own commands (`on` handlers, `function`s) are decided when the script compiles, over numbers,
  text, names, the model (`the count of <elements>`, `there are <elements>`) and the plan; the score stays a fixed timeline. A handler's
  statements start where it is called and take time like inline statements.
- Issues and drawings are hidden while a script plays (the player does that). A script shows them only when it says so (`show issues`,
  `show drawings`); they come back as they were when playback ends.
- Limits: a script runs at most 1 hour, makes at most 5000 steps, runs a loop at most 500 times and at most 20000 statements in all.
  Calls of handlers and functions nest at most 16 deep.

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
- `label <elements> with <field>, <field> [for N seconds]`: Pin a tag to each element (at most 12 show, with "+N more"). Fields: name, class, storey, material, globalid, type, or a property as "Pset_X.Prop". Lasts 3 seconds.
- `hover <elements> [for N seconds]`: Show the hover card of the first element, near it with a leader line. Lasts 2 seconds unless told.

### Timing and variables

- `wait N [seconds]`: Do nothing for a time.
- `together ... end together`: Start the statements inside at the same moment. The block lasts as long as the longest.
- `repeat N times ... end repeat`: Run the statements inside again and again. `index` counts from 1. At most 500 times.
- `repeat for each element in <elements> ... end repeat`: Run the statements once for each element. `it` is the element. At most 500 elements.
- `repeat for each set in sets ... end repeat`: Run the statements once for each stored selection set. `it` is the set.
- `repeat for each item|word|line|char <name> in <text> ... end repeat`: Run the statements once for each piece of a text: items are between commas, words between spaces, lines between line breaks. The name holds the piece. At most 500 times.
- `set the random seed to N`: Start the random numbers of random() and random(n) from seed N. Without it the seed comes from the script text, so the same script always gives the same film.
- `put <value> into <name>`: Keep a number, text ("a" & b joins text) or a yes/no under a name. Use the name wherever a number goes. Signs: + - * / and ( ).

### Decisions, loops and your own commands

- `if <condition> then ... [else if <condition> then ...] [else ...] end if`: Run the statements of the first branch whose condition is true. Decided when the script compiles, so the timeline has no branches. Conditions: = <> < > <= >= on numbers and text (text ignores case), and, or, not, ( ), the count of <elements>, there are <elements>.
- `if <condition> then <statement>`: The one-line form: one plain statement, no `end if`.
- `repeat while <condition> ... end repeat`: Run the statements again and again while the condition is true. Something inside must change what it tests. At most 500 times, then an error names the line.
- `repeat until <condition> ... end repeat`: Run the statements again and again until the condition becomes true.
- `repeat with <name> from <a> to|down to <b> [by <step>] ... end repeat`: Count from a to b (or down). The name holds the count and is given back after the loop. At most 500 times.
- `on <name> [param, param] ... end <name>`: Define your own command (a handler). Call it as a statement: name value, value. Its statements go on the timeline where it is called. Parameters and names it `put`s are its own; it can read the script's names. It may stand anywhere at the top level.
- `<name> [value, value]`: Call a handler: its statements run here, one after the other, with the values as its parameters. Calls may nest up to 16 deep (recursion).
- `function <name> [param, param] ... return <value> ... end <name>`: Define a function: it works out a value and gives it back with `return`. Use it in an expression: name(value, value). A function computes only; it does not move the camera or wait.
- `return [<value>]`: Inside a function: give the value back and stop. Inside a handler: stop early (no value).
- `exit repeat`: Leave the loop that holds it, at once. An error outside a loop.
- `next repeat`: Skip the rest of this round of the loop and go on with the next one.
- `exit <handler name>`: Leave the handler it stands in (the name must be that handler's own). Like `return` in a handler.

### Reusable scripts

- `param <name> default <"text"|number|yes|no>`: Declare a value the person can change without editing the script: the Parameters form of the Script tab, xray-4d render --param, xray-pack --script-param. Top level only. The name works like a name you `put`.
- `use "<saved script>"`: Pull in the handlers and functions (only those) of another saved script of the Script tab, by name. A script that uses itself in a circle, or a missing script, is an error. A handler of this script wins over one of the library, with a warning. Top level only.

### Playback

- `show|hide issues|drawings   (or: issues and drawings)`: Show or hide the issue pins and the drawings during playback. Both are hidden while a script plays unless it shows them, and come back as they were afterwards. Instant.
- `fade new elements over N seconds | fade new elements instantly`: Set how long elements that appear or disappear from here on fade (show, hide, schedule activities). Instantly is 0.

### 4D schedule

- `schedule "<plan>" [view planned|actual|variance] [from "<date>"] [to "<date>"] [over N seconds] [fade N seconds]`: Play a 4D plan by name over a time (default: the plan's film length). It runs in the background: the statements after it start with it. View, from and to go to the step for the host to rebuild the plan with. Fade is how long a new element fades in.
- `at date "<YYYY-MM-DD[THH:MM]>"`: The statements after it start when the running schedule reaches that date, whether or not the ones before have ended.
- `at milestone "<name>"`: The statements after it start when the running schedule reaches that milestone.
- `tint <elements> <#rrggbb|colour name|off> [fading over N seconds]`: Colour elements, with a fade or at once; `off` takes the tint away. Names: red, orange, yellow, green, teal, cyan, blue, indigo, purple, magenta, pink, brown, grey, white, black.
- `explode storeys|radial [by N] [over N seconds]`: Move the storeys apart (or push every element out from the centre). By is the factor (default 1). Lasts 2 seconds unless told.
- `collapse [over N seconds]`: Bring an exploded building back together. Lasts 2 seconds unless told.
- `focus <elements> | focus nothing`: Set the x-ray focus: what stands in front of these elements ghosts. `focus active` follows the active work of the schedule; `focus nothing` gives the focus back to the selection. Instant.
- `section box around <elements>|storey "<name>" [over N seconds]`: Clip the model to a box around the elements or a storey. Lasts 1.5 seconds unless told.
- `section box off [over N seconds]`: Take the section box away, opening it out over the time.
<!-- statements:end -->

`ease` takes `in`, `out`, `in out` or `linear`; the default is `in out` for camera moves and for numbers that blend.

### Values and text

Expressions (`put`, `if`, captions, arguments) can read the model and work on text and numbers. All of it is worked out when the script compiles; see the [guide](animation-script-guide.md), chapters 14 and 15, and the [grammar](animation-script-grammar.md).

<!-- expressions:start -->
- `the name|class|storey|type|globalid|material of <element>`: A fact of an element, as text; empty when the element has none. The element is `it` inside `repeat for each element`, or a GlobalId in text.
- `property "<Pset.Prop>" of <element>`: A property of an element: text, a number or yes/no; empty text when the element has none.
- `the names|globalids|classes|storeys|types of <elements>`: The values of many elements as comma-separated text (empty ones left out), at most 500. Use it with `repeat for each item`.
- `<a> contains|begins with|ends with <b> | <a> is [not] in <b>`: Text tests for conditions, without regard to case. `a is in b` is true when b contains a.
- `<a> & <b> | <a> && <b>`: `&` joins text; `&&` joins with one space between.
- `item|word|line|char <n> [to <m>] of <text>`: A piece of a text. Items are between commas (spaces around them dropped), words between spaces, lines between line breaks. Counting starts at 1; past the end gives empty text. Ranges join the pieces again.
- `the number of items|words|lines|chars in <text>`: How many pieces a text has.
- `sort items|words|lines of <text> [descending] [numeric]`: The pieces in order, as text. Alphabetical without regard to case ("Level 2" before "Level 10"); `numeric` sorts as numbers.
- `round(x[, digits]) trunc(x) floor(x) ceil(x) abs(x) min(a, b, ...) max(a, b, ...) sqrt(x) number(text)`: Maths on numbers. round goes away from zero at .5. sqrt of a negative is an error.
- `<a> mod <b>   <a> div <b>   <a> ^ <b>   pi`: mod and div (whole division, rounded down) with a zero on the right are errors. ^ is the power, tighter than * and /. pi is 3.14159.
- `random(n) | random()`: A whole number from 1 to n, or a number from 0 up to 1. Seeded: the same script text gives the same numbers every time (set the random seed to change them).
<!-- expressions:end -->

### Elements

Wherever a statement says `<elements>`:

- `where <criteria>`: the [criteria query language](sets-query.md). Text values may be bare words or in double quotes:
  `where class = IfcPump and storey = "Level 2"`, `where name like "P-1%"`, `where "Pset_WallCommon.IsExternal"`. A value with a
  space must be in double quotes. The words `over`, `ease`, `margin`, `fading`, `for`, `with` and `about` end the criteria.
- `class IfcPump` or `class IfcPump, IfcValve`: shorthand for the elements of those classes.
- `set "Name"`: the members of a stored selection set ([sets-query.md](sets-query.md)).
- `the selection`, `everything`, `it`, `elements "gid1", "gid2"` (by GlobalId).
- `active`, `completed`, `critical`: 4D, the elements of the running schedule in that state at that moment.
- `the count of` and `there are` take the short forms too: `the count of class IfcDoor`, `there are set "Pumps"`. After a `where`, put the elements in parentheses when more follows: `the count of (where class = IfcDoor and storey = "Level 1") > 3`.

### Decisions, loops and your own commands

- **Conditions**: `=`, `<>` (also `!=`, `≠`), `<`, `>`, `<=`, `>=` on numbers and text (text ignores case), joined with `and`, `or`, `not` and
  parentheses. `the count of <elements>` is a number; `there are <elements>` / `there is <elements>` is true when it is more than 0
  (`there are no <elements>` the opposite). They need the model. Put a `where` in parentheses when more follows it:
  `if the count of (where class = IfcDoor) > 3 and n > 1 then`.
- **`if`** `<condition>` **`then`** ... **`else if`** ... **`else`** ... **`end if`**, or the one-line `if <condition> then <statement>`.
- **`repeat while|until <condition>`** and **`repeat with i from a to|down to b [by step]`**, closed by `end repeat`. A loop stops with an
  error that names its line after 500 passes. The counter of `repeat with` has its earlier value again after the loop.
- **`on name params ... end name`** defines a handler, called as `name value, value`; **`function name params ... return value ... end name`**
  defines a function, called in an expression as `name(value)`. Definitions may stand anywhere at the top level. Parameters and names a
  handler `put`s are its own; it reads the script's names and `it`, and a `put` inside never changes an outer name. Recursion is allowed up to
  16 calls deep. A function only computes (no camera, wait or caption). A name clash with a statement or reserved word is an error.
- A bare word in a `where` value position that is the name of a variable stands for its value: `where storey = name`.

### Variables and numbers

`put 2 * 1.5 into pause` keeps a number (or text, or a yes/no) under a name; use the name wherever a number goes (`wait pause seconds`). Signs: `+ - * /` and
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
| `schedule "plan" ...` | `schedule4d` with `plan: { name }`, the `over` time, and `view`, `from`, `to` when given (for the host to rebuild the plan with), and `fadeIn` for `fade N seconds` |
| `at date` / `at milestone` | no cue: sets the time of the statements after it, through the plan's time map |
| `show` or `hide` `issues` or `drawings` | `overlays` with `issues` and/or `drawings` (booleans); instant |
| `fade new elements over N seconds` / `instantly` | `fadeDefault` with `seconds`; instant |
| `if`, `repeat while`, `until`, `with`, `on` calls | no cue of their own: the compiler works them out and emits the cues of the statements that run |
| `tint <elements> <colour>` | `tint` with `elements`, `colour` (`#rrggbb`, null for `off`), `dur` the fading time |
| `explode` / `collapse` | `explode` with `mode` and `factor`, `collapse`; 2 seconds, `inOut` |
| `focus` | `focus` with `elements` (or null) |
| `section box ...` | `sectionBox` with `around` (elements, `{ storey }` or null); 1.5 seconds, `inOut` |

Every cue has `line`, the line of the script, which the editor highlights while the cue plays. Elements stay references (a query, a set
name, GlobalIds, the selection) for the player to resolve when playback starts. Only `repeat for each element` needs the model while
compiling: it expands to one pass per element, with `it` as `{ globalIds: [id] }`. Without a model it is an error.

## The HUD

Captions, labels and the hover card are drawn by the HUD layer over the view, not by the player: see [Fly-through, The HUD](flythrough.md#the-hud) for how they look (fade in and out over 0.3 s, word wrap, safe margins, no overlapping tags). The progress bar (chapter marks at the start of each caption and label), the compass and the scale bar come from the HUD settings in the **Fly-through** section of the Views tab (**On-screen display**); they apply to scripts too and are stored with the model's fly-throughs, not in the script.

## The Script tab

- **Editor** with line numbers and light colours: statement words blue, options purple, text green, numbers orange, comments grey.
  A wavy underline marks the place of an error (red) or a warning (amber). `Ctrl+Enter` runs; Enter keeps the indentation.
- **Problems** list under the editor, live as you type. Each row has line, column, a message and a hint ("Did you mean `fading`?", the
  nearest setting paths, the nearest preset names). A click jumps to the place. The tab button shows the number of errors.
- **Run, Pause, Stop** use the score player. The line being played is highlighted. If the player is not part of the build, Run says so.
- **Examples** menu: a walk around the pumps (process-plant sample), peeling back the slabs storey by storey (synth5k), highlighting each
  selection set with a caption, and changing the look over time.
- **Parameters**: when the script has `param` lines, a small form above Run holds one field for each. The values stay in this browser only (not in share links). **Reset to defaults** clears them. The example "One script, any floor" uses a parameter and the saved library "Floor helpers" (`use`).
- **Saved scripts**: give the script a name and **Save**. Scripts are kept per model (the model identity of
  `src/markup/scope.ts`) in `localStorage["xray.anim.<model>"]`, together with the text you were editing, so a reload brings it back.
- **Record** compiles the script and opens the video export dialog (size, frame rate, quality, format, captions and labels, file name; the
  name of the script is the file name). The export plays the script frame by frame at a fixed step, so the video holds duration x fps frames
  on any machine; the viewer is busy until it ends or you cancel. Fix errors first: Record jumps to the first error instead. See
  [flythrough.md](flythrough.md), Export.
- **Export** downloads the text as `<name>.xrayanim` (plain text, the script itself); **Import** reads such a file (or a `.txt`).
- **Statement reference** with an **Insert example** button for each statement.
- On a phone the right sidebar is a bottom sheet; the tab has one column, 16 px text and large buttons.

Scripts are the person's own text. They are **never** part of the parameters document, share links, saved views or presets, and no
tool copies them anywhere on its own; only the browser's storage and exported files hold them. A packed page carries a script only
when you name its exported file yourself (`xray-pack --scripts a.xrayanim --autoplay script:a`, see [xray-pack.md](xray-pack.md)).

A script of a 4D film can come from the 4D tab: **Open as script** in its film bar loads the film, camera moves included, into the editor under the schedule's name, unsaved.

## For scripts and smoke tests

```js
const r = window.__xrayScript.compile('fly to everything over 3 seconds');  // { score, errors }
window.__xrayScript.run(text);       // compile and play; { ok, message, errors, score }
window.__xrayRecord.run(score, { size: '1280x720', fps: 30, format: 'auto', name: 'tour' });  // export a score as a video (a promise)
window.__xrayScript.list();          // the saved scripts of this model
window.__xrayScript.save('Tour', text);
window.__xrayScript.load('Tour');
window.__xrayScript.compile(text, { params: { floor: 'Level 2' } });  // values for `param` lines; { score, errors, params }
window.__xrayScript.state();         // { errors, playingLine, status, running, ... } once the tab was shown
```

The pure modules are in `src/anim/script/`: `lexer.ts`, `parser.ts` (syntax tree with line and column), `compiler.ts` (tree to score),
`scriptHelp.ts` (this reference), `examples.ts`, `highlight.ts`, `runner.ts`. They use no DOM, no storage and no network, and no `eval`.
`compileScript(text, options)` takes optional `params` (values for `param` lines), `library` (the text of a saved script by name, for `use`), `elementField` (a fact of an element),  `resolve` (query to GlobalIds), `setNames`, `paramPaths`, `presets`, `views` and `plans` (4D plan by name; default: the registry of `src/anim/fourd/plans.ts`) from the app.

Command line: `xray-4d render|pack ... --script film.xrayanim --param name=value` (repeatable) and `--use-dir folder` (libraries for `use`); `xray-pack --scripts ... --script-param name=value`; the skill checker `xrayanim_check.mjs film.xrayanim --param name=value` resolves `use` against files next to the script.
