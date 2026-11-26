# 23. Animation scripts

A fly-through is built by clicking. That is quick for ten keyframes, and painful for "visit every pump, name it, then hide the slabs
storey by storey". You would add forty keyframes by hand, and change them all when the model changes. You want to say it in a few
lines, and let the viewer do the repeating.

## 23.1 Write a first script

### The idea

An **animation script** is a short text that tells the viewer what to do, one line at a time, in plain English: fly the camera here,
fade this out, show a caption. Press **Run** and the player (chapter 21) plays it. A script is saved as a `.xrayanim` text file.

The rule that explains everything: **each line starts when the line before it has ended.** A line that flies for 3 seconds
holds the next line for 3 seconds. Think of a recipe: you do step 2 after step 1. When you need two things at once (fly and show a
caption together), you put them in a `together` block.

### Try it

Use the **Process plant** sample.

1. Open the **Script** tab of the right sidebar.
2. Type:

   ```
   -- A walk around the pumps
   mode ghost
   fly to class IfcPump over 3 seconds
   caption "The pumps" "Seen through the rest of the plant" for 3 seconds
   ```

3. Press **Run** (or `Ctrl+Enter`). The look changes to Ghost, the camera flies to the pumps in 3 seconds, and the caption shows for 3.
4. Press **Pause** to hold it, and **Stop** to end it. The model goes back to how it was.
5. Change `IfcPump` to `IfcTank`, press **Run** again.
6. Now do two things at once. Replace the last two lines:

   ```
   together
     orbit 120 degrees about class IfcPump over 6 seconds
     caption "Four pumps" "Seen from every side" for 6 seconds
   end together
   select nothing
   ```

7. Open the **Examples** menu to see more: a walk around the pumps, peeling back slabs storey by storey (Synth 5k), highlighting
   each selection set with a caption, and changing the look over time.
8. Give the script a name and click **Save**. Click **Export** to get a `<name>.xrayanim` file for a colleague. **Import** reads such
   a file.

### How it works

The script is compiled to a timeline when you press **Run**, and the player plays it. Every line that takes time lasts as long as
you say, and instant lines (mode, preset, select, plain show or hide) take none. Lines `caption`, `label` and `hover` last 3, 3 and 2
seconds unless you add `for N seconds`, and the next line waits for them.

Words you can use for elements, wherever a line says `<elements>`:

- `class IfcPump` or `class IfcPump, IfcValve`: all elements of those classes.
- `set "Pumps"`: a stored selection set (chapter 8).
- `where class = IfcPump and storey = "Level 2"`: a query, in the same language as search and criteria sets (chapter 8).
- `the selection`, `everything`, `elements "gid1", "gid2"` (by GlobalId).
- `it`: the current element or set, inside a loop.
- `active`, `completed`, `critical`: the running 4D schedule's elements in that state (chapter 27).

Case does not matter. A comment starts with `--` or `#`. Text goes in double quotes. A number may carry a unit: `2s`, `2 seconds`.

The names of settings in `set` are the parameter paths of appendix B, for example `cinematic.glowStrength`. A name the viewer does
not know gives a warning with the nearest real names, and the line is skipped.

### Choices and settings

- **Examples**: starting points for the first script.
- **Saved scripts**: kept in this browser, per model, together with the text you were editing, so a reload brings it back.
- **Record**: compiles the script and opens the video dialog of 22.3. Errors stop it and the editor jumps to the first one.
- Where captions sit, the progress bar, compass and scale bar come from **On-screen display** in the Views tab (21.1). They are stored
  with the model's fly-throughs, not in the script.

### Limits and gotchas

- A script runs at most 1 hour, makes at most 5,000 timeline items (one is a camera move, setting change, caption, label or hover;
  the error message calls them steps), runs a loop at most 500 times and executes at most 20,000 statements. A long loop of small
  steps is the usual way to hit the 5,000.
- A script is your own text. It is never part of parameters, share links, saved views or presets. A packed page carries a script
  only if you name its exported file (chapter 30).
- The elements and set names in quotes must match the model exactly.

## 23.2 Fades, captions, loops, and reading errors

### The idea

Three more ideas cover most real scripts. A **fade** changes what is shown slowly instead of at once. A **loop** repeats lines,
once for each element or each set. A **variable** keeps a number under a name, so you change a time in one place.

### Try it

Use **Synth 5k** for the slabs, and the **Process plant** for the loop.

1. Peel slabs with fades:

   ```
   put 1.5 into fade
   mode solid
   fly to everything over 3 seconds
   hide where class = IfcSlab and storey = "Level 5" fading over fade seconds
   wait 0.5 seconds
   hide where class = IfcSlab and storey = "Level 4" fading over fade seconds
   show everything fading over 2 seconds
   ```

   The storey names must be those of your model. Open the Model tab to read them.

2. Visit each pump:

   ```
   repeat for each element in class IfcPump
     together
       fly to it over 2 seconds margin 3
       label it with name for 2 seconds
     end together
   end repeat
   fly to everything over 3 seconds
   ```

3. Visit each selection set, naming it with its own name:

   ```
   repeat for each set in sets
     select it
     fly to it over 2 seconds
     caption it for 2 seconds
   end repeat
   select nothing
   ```

4. Make a mistake on purpose. Write `flyto everything` and look at the **Problems** list under the editor. Click the row to jump to
   the line. The tab button shows the number of errors.

### How it works

Inside `repeat`, `index` counts from 1. `it` is the element (in an element loop) or the set name (in a set loop). Join text with `&`:
`caption "Pump " & index`. Numbers can use `+ - * /` and brackets. Names of variables are your own and not case-sensitive, and cannot
be words of the language.

A `repeat for each element` loop needs the model while the script is compiled: it expands to one pass per element. With no model
loaded it is an error.

The editor colours statement words, options, text, numbers and comments, and underlines a problem in red (error) or amber (warning).
Warnings do not stop the script. Errors do.

The messages you will meet:

| Message | What to do |
| --- | --- |
| `I do not know the statement "flyto"` | Write the statement with a space: `fly to ...` |
| `A value with a space needs double quotes` | `storey = "Level 2"`, not `storey = Level 2` |
| `The "together" on line 2 has no "end together"` | Add `end together` after the last line of the block |
| `"end repeat" has no block to close` | One `end` too many, or a `repeat` is missing above |
| `I do not know the name "pause"` | Give the number a name first: `put 1.5 into pause` |
| `"it" has no meaning here` | `it` works only inside `repeat for each` |
| `There is no selection set named "Pmps"` | The message suggests the nearest names |
| `I do not know the setting "..."; the player skips it` | A warning. Fix the name or leave the line |
| `The margin 7 is outside 1 to 6` | A margin is between 1 and 6 |
| `The script makes more than 5000 steps.` | Use fewer or smaller loops, or split the script |

### Choices and settings

- Test a part: put `--` in front of lines you do not want yet. A block must keep its opening and closing line.
- Keep a script to 20 to 40 lines. Split a longer one into several saved scripts.
- Run once, then adjust the times by eye. A caption makes the next line wait, so put it in `together` to show it beside a move.

### Limits and gotchas

- A loop over elements runs at most 500 elements. Narrow it with `where`. A script of more than 20,000 statements is refused.
- `hide ... fading over N seconds` takes N seconds, and the next line waits for it.
- A `set` line for a number blends over the time. A switch or a text value changes at the end of the time.
- A setting path is checked against this build when a model loads. A path from a newer build is skipped.

## 23.3 [D] Statement reference

The full grammar is in `web/docs-features/animation-script-grammar.md`. This is the summary. `<elements>` is as in 23.1.
`ease` takes `in`, `out`, `in out` or `linear` (default `in out` for camera moves and for numbers that blend).

| Statement | What it does | Default time |
| --- | --- | --- |
| `fly to <elements> [over N seconds] [ease ...] [margin N]` | Frame the elements. Margin 1 to 6 is the room around them | 2 s |
| `fly to view "<name>" [over N seconds] [ease ...]` | Go to a saved view | 2 s |
| `orbit N degrees [about <elements>] [over N seconds] [ease ...]` | Turn about the elements, or about the model. Negative turns the other way | 3 s |
| `set <path> to <value> [over N seconds] [ease ...]` | Change one setting by parameter path | instant |
| `mode ghost\|solid\|radiograph\|glow\|cutaway` | Switch to a top-bar mode | instant |
| `apply preset "<id or name>"` | Apply a built-in or saved preset | instant |
| `show <elements> [fading over N seconds]` | Show hidden elements. `show everything` brings back all | instant |
| `hide <elements> [fading over N seconds]` | Hide elements | instant |
| `isolate <elements> [fading over N seconds]` | Show only these | instant |
| `select <elements>` / `select nothing` | Select, or clear the selection | instant |
| `caption "Title" ["More text"] [for N seconds]` | Lower-third caption | 3 s |
| `label <elements> with <field>, ... [for N seconds]` | Tag each element (at most 12 shown). Fields: `name`, `class`, `storey`, `material`, `globalid`, `type`, or `"Pset.Prop"` | 3 s |
| `hover <elements> [for N seconds]` | Hover card of the first element | 2 s |
| `wait N [seconds]` | Do nothing | as given |
| `together` ... `end together` | Start the lines inside at once. Lasts as long as the longest | longest |
| `repeat N times` ... `end repeat` | Repeat. `index` from 1. At most 500 | n/a |
| `repeat for each element in <elements>` ... `end repeat` | Once per element; `it` is the element | n/a |
| `repeat for each set in sets` ... `end repeat` | Once per stored set; `it` is its name | n/a |
| `put <number> into <name>` | Keep a number; `+ - * /` and brackets | instant |

More statements, with short examples, are in chapter 23A: `if ... else`, `repeat while`, `repeat until`, `repeat with`, `repeat for each item`,
`exit repeat`, `next repeat`, `on name ... end name` (handler), `function name ... return ... end name`, `show issues`, `hide issues`,
`show drawings`, `hide drawings`, `fade new elements over N seconds`, `param name default value` and `use "Name"`. Expressions also read
`there are`, `the count of`, facts such as `the name of it`, `property "Pset.Prop" of it`, text tests, lists and chunks, maths and
`random(n)`.

The 4D statements are used with a plan (chapter 27). A plan name is one the viewer knows: the 4D tab registers the plan it builds
as `4d:<model name>`, and a packed page registers each plan by its file name (chapter 30).

| Statement | What it does | Default time |
| --- | --- | --- |
| `schedule "<plan>" [view planned\|actual\|variance] [from "<date>"] [to "<date>"] [over N seconds]` | Play a 4D plan. It runs in the background: the lines after it start with it | plan's film length |
| `at date "<YYYY-MM-DD[THH:MM]>"` | The lines after it start when the schedule reaches that date | n/a |
| `at milestone "<name>"` | The same, for a milestone | n/a |
| `tint <elements> <#rrggbb\|colour name\|off> [fading over N seconds]` | Colour elements. Names: red, orange, yellow, green, teal, cyan, blue, indigo, purple, magenta, pink, brown, grey, white, black | instant |
| `explode storeys\|radial [by N] [over N seconds]` | Move storeys apart, or push every element out from the centre. `by` is the factor, default 1 | 2 s |
| `collapse [over N seconds]` | Bring an exploded building back | 2 s |
| `focus <elements>` / `focus nothing` / `focus active` | Set the x-ray focus; `active` follows the active work; `nothing` gives it back to the selection | instant |
| `section box around <elements>\|storey "<name>" [over N seconds]` | Clip to a box around the elements or a storey | 1.5 s |
| `section box off [over N seconds]` | Take the section box away | 1.5 s |

**Internals.** The compiler turns each statement into a cue of a score (`src/anim/score.ts`). `fly to` becomes a `camera` cue with a
`frame`; `set` a `param` cue; `mode` and `apply preset` a `preset` cue; `show`, `hide`, `isolate` a `visibility` cue whose duration
is the fade; `schedule` a `schedule4d` cue. `at date` and `at milestone` produce no cue: they set the time of the lines after them,
through the plan's time map. Every cue carries its script line, which the editor highlights. Elements stay references that the player
resolves when playback starts. The modules in `src/anim/script/` use no DOM, no storage, no network and no `eval`.
`window.__xrayScript` offers `compile(text)`, `run(text)`, `list()`, `save(name, text)`, `load(name)` and `state()`.

### See also

Chapter 23A (decisions, handlers, text and lists, parameters), chapter 8 (queries, sets), chapter 21 (the player), chapter 22 (exporting a
video), chapter 27 (4D films).
