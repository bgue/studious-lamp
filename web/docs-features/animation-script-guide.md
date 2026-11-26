# Animation script: a guide for coordinators

This guide shows how to make the model move: the camera flies to the parts you want to talk about, the look changes, parts
fade in and out, captions and labels appear. You do not need to program. You write short English lines, one line per step,
and press **Run**.

The formal grammar is in [animation-script-grammar.md](animation-script-grammar.md). The short reference is in
[animation-script.md](animation-script.md).

## 1. Before you start

1. Open a model.
2. Open the **Script** tab in the right sidebar.
3. Type a script in the editor, or pick one from the **Examples** menu.
4. Press **Run** (or `Ctrl+Enter`). Press **Pause** or **Stop** to change your mind.

The editor marks mistakes with a wavy line. The **Problems** list under the editor says what is wrong and where, line by line.
A click on a problem jumps to it. The line that is playing is highlighted.

Some rules that hold everywhere:

- **One statement per line.** A statement is one action: fly, hide, caption and so on.
- **Capital letters do not matter.** `Fly To` and `fly to` are the same.
- **Text goes in double quotes.** `"Level 2"`, not `'Level 2'` and not `Level 2`.
- **A comment starts with `--` or `#`.** Everything after it on the line is ignored. Use comments to explain your script to a colleague.
- **Things happen one after another.** Each line starts when the line before it has finished. Section 6 shows how to do things at the same time.

## 2. Your first script

Three lines:

```xrayanim
-- My first script
mode ghost
fly to class IfcPump over 3 seconds
caption "The pumps" "Seen through the rest of the building" for 3 seconds
```

What each line does:

- `mode ghost` switches the look to Ghost, the see-through view of the top bar. It happens at once and takes no time.
- `fly to class IfcPump over 3 seconds` moves the camera so that all the pumps fill the view. The move takes 3 seconds.
- `caption "The pumps" "Seen through ..." for 3 seconds` shows a title and a line of text for 3 seconds. The next line waits until the caption is finished.

Change `IfcPump` to the class you want. Other classes you may need: `IfcSlab` (slabs), `IfcWall` (walls), `IfcPipeSegment` (pipe runs), `IfcDuctSegment` (duct runs), `IfcColumn`, `IfcBeam`. The class names are the IFC names your model uses.

## 3. Moving the camera

Fly to the elements you name:

```xrayanim
fly to everything over 2 seconds
fly to class IfcWall, IfcSlab over 3 seconds
fly to set "Pumps" over 2 seconds
fly to where storey = "Level 2" over 4 seconds
```

- `everything` is the whole model.
- `class IfcWall, IfcSlab` is more than one class, separated by commas.
- `set "Pumps"` is a selection set stored in the model (the sets of the Sets tab). Use the exact name in quotes.
- `where ...` is a condition. Section 4.6 explains the rules.

Two small options can follow an elements name:

- `margin 3` leaves more room around the elements. `1` is tight, `6` is far away. Without `margin` the viewer picks the framing.
- `ease in out` (the default), `ease in`, `ease out` or `ease linear` changes how the move starts and stops. `linear` moves at an even speed.

```xrayanim
fly to class IfcPump over 3 seconds ease in out margin 3
```

Fly to a saved view. Save the view first in the Views tab with its name:

```xrayanim
fly to view "Plant room from the north" over 4 seconds
```

Turn the camera around a part:

```xrayanim
orbit 90 degrees about class IfcPump over 6 seconds
```

`orbit` turns by the number of degrees you give. Use a negative number (`orbit -90 degrees`) to turn the other way. Without
`about`, the camera turns around the model.

## 4. Changing the look

### 4.1 Modes

A mode is one of the five buttons of the top bar. You can switch to it by name:

| Line | What you see |
| --- | --- |
| `mode solid` | Normal, solid model |
| `mode ghost` | The rest of the model is see-through, and the parts in the way fade (the Coordination look) |
| `mode radiograph` | An X-ray picture: the thickness of the material is shown |
| `mode glow` | The parts you pick get a bright outline |
| `mode cutaway` | The parts in front are cut away to show what is behind |

A mode changes at once. It takes no time.

### 4.2 Presets

A preset is a named look with many settings in one step. Use the name in double quotes:

```xrayanim
apply preset "Peelback"
apply preset "Focus glow"
apply preset "MRI scan"
```

The built-in names are: Coordination, Hide blockers, Behind only, Peelback, Peel only, Stacked floors, Radiograph, MRI scan,
Section focus, Presentation, Clearance review, Plain, Focus glow and Solid. A preset you saved yourself is found by its name too. A name that is not in the list gives a suggestion of the nearest name.

### 4.3 Settings with `set`

A setting is one switch, slider or list of the viewer. You change it with `set`, the setting's name, `to` and a value:

```xrayanim
set cinematic.glowStrength to 0.8 over 2 seconds
set sightlines.alphaMax to 0.6 over 2 seconds
set cinematic.bloom to on
set imaging.style to radiograph
```

The value depends on the setting:

- **A number** (a slider) blends over the time you give with `over`. Without `over` it changes at once.
- **on, off, yes, no, true, false** (a switch). The switch changes at the end of its time, or at once without `over`.
- **A word or text in quotes** (a choice from a list) such as `radiograph` or `"radiograph"`. It changes at the end of the time.
- **Numbers with commas** (a list of numbers, for example `set some.setting to 0.2, 0.5, 0.9`).

Where do the names come from? [docs/SETTINGS.md](../../docs/SETTINGS.md) lists every setting, grouped by the section headings of
the viewer. Each setting has a name in its first column. The name of a setting is its group in lower camel case, a dot, and
the setting's own name, for example `sightlines.alphaMax` or `cinematic.glowStrength`. The **Export JSON** button in the
Export / import section saves all settings with their exact names, so you can open the file and copy a name from it.

If you type a name the viewer does not know, the Problems list suggests the nearest real names. The script still runs; the
line with the unknown name is skipped.

## 5. Showing and hiding, with fades

```xrayanim
hide class IfcSlab fading over 2 seconds
show class IfcSlab fading over 2 seconds
hide where storey = "Level 5" fading over 1.5 seconds
show everything
isolate class IfcPump fading over 1 seconds
```

- `hide` removes the elements. `show` brings hidden elements back. `show everything` brings back everything that was hidden.
- `fading over 2 seconds` makes the change slowly. Without it the change is at once.
- `isolate` shows only the elements you name and hides the rest.

Note that `fading over 2 seconds` takes 2 seconds, and the next line waits for it.

## 6. Captions, labels and hovering

A caption has a title, an optional second line, and a time:

```xrayanim
caption "Level 2"
caption "Level 2" "Pump room and plant" for 4 seconds
```

A caption lasts 3 seconds unless you say `for`. The next line waits until the caption is finished.

A label pins a small tag to each element with the information you ask for:

```xrayanim
label class IfcPump with name, storey for 4 seconds
label class IfcPump with name, "Pset_PumpCommon.Reference"
```

The fields you can ask for are `name`, `class`, `storey`, `material`, `globalid` and `type`. Any other property is written in
quotes with its property set, for example `"Pset_PumpCommon.Reference"`. Use the property names of your model.

Hover highlights the elements as if the pointer were over them:

```xrayanim
hover class IfcPump for 2 seconds
```

### 6.1 Doing things at the same time

Each line waits for the one before it. To run lines side by side, put them in a `together` block. The block starts all the
lines at the same moment, and lasts as long as the longest of them:

```xrayanim
together
  fly to class IfcPump over 3 seconds
  caption "The pumps" "Four units in the plant room" for 3 seconds
end together
wait 1 second
together
  orbit 120 degrees about class IfcPump over 6 seconds
  caption "Seen from every side" for 6 seconds
end together
```

Every `together` must end with a line `end together`. Put nothing else on that line.

`wait 1 second` does nothing for a time. Use it to pause between steps.

## 7. Loops: doing the same thing many times

### 7.1 A number of times

```xrayanim
repeat 3 times
  orbit 120 degrees over 2 seconds
end repeat
```

Each `repeat` must end with a line `end repeat`. A loop runs at most 500 times. Inside a loop, `index` is the number of the
pass, counting from 1. You can use it in text with `&`:

```xrayanim
repeat 3 times
  caption "Pass " & index for 1 second
end repeat
```

### 7.2 Each element

`repeat for each element in ...` runs the lines once for every element that matches. Inside the loop, `it` stands for the
current element:

```xrayanim
repeat for each element in class IfcPump
  together
    fly to it over 2 seconds margin 3
    label it with name for 2 seconds
  end together
end repeat
```

A loop over elements needs the model to be loaded. It runs at most 500 elements. Narrow the elements with `where` if there are
more: `repeat for each element in where class = IfcPump and storey = "Level 2"`.

### 7.3 Each selection set

The selection sets of the model can be visited one by one. Inside the loop, `it` is the name of the set:

```xrayanim
repeat for each set in sets
  select it
  fly to it over 2 seconds
  caption it for 2 seconds
end repeat
select nothing
```

`select nothing` clears the selection at the end.

## 8. Variables

A variable keeps a number under a name (it can also keep text or a yes/no, see chapter 13). Use `put` to set it, and the name wherever a number goes:

```xrayanim
put 2 * 1.5 into pause
put 1.2 into fade
hide class IfcSlab fading over fade seconds
wait pause seconds
show class IfcSlab fading over fade seconds
```

- The names are your own. Choose names like `pause` or `gap`. The words of the language (such as `over`, `set`, `index`, `class`)
  cannot be names.
- Signs: `+`, `-`, `*`, `/` and brackets `( )`. Multiplication is `*`, not `x`.
- Names are case-insensitive: `Pause` and `pause` are the same.
- In text, join pieces with `&`: `caption "Pump " & index`.

## 9. Reading the error messages

Every message gives the line number, the column, what is wrong and often a suggestion. This table shows the messages you will
meet most, and what to do.

```text
Line 2, column 7: Unexpected `secs` right after the number 2.
  -> Write a space between the number and the unit: wait 2 secs, or use 2s.

Line 3, column 1: I do not know the statement `flyto`.
  -> Did you mean `fly`? Write the statement word with a space: fly to ...

Line 1, column 29: In the criteria: Unexpected "2": expected AND, OR or the end of the query.
  -> A value with a space needs double quotes: storey = "Level 2".

Line 4, column 18: I did not expect `2` here.
  -> A word or number is in the wrong place. Check the order of the words in the statement.

Line 5, column 1: The `together` on line 2 has no `end together`.
  -> Add a line end together after the last line of the block.

Line 9, column 1: `end repeat` has no block to close.
  -> You have one more end line than blocks. Remove it, or add the missing repeat above it.

Line 3, column 8: I do not know the name `pause`.
  -> Give the number a name first: put 1.5 into pause.

Line 4, column 6: `it` has no meaning here.
  -> it works only inside repeat for each.

Line 2, column 8: There is no selection set named "Pmps".
  -> Did you mean "Pumps"? The message suggests the nearest names.

Line 2, column 1: I do not know the setting `sightlines.alphaMax2`; the player skips it.
  -> The message suggests the nearest real settings. Fix the name, or leave the line: it is skipped.

Line 3, column 6: The margin 7 is outside 1 to 6.
  -> A margin is between 1 and 6.

Line 2, column 1: repeat for each element needs the model to find the elements, and none is loaded.
  -> Open a model, then run the script again.
```

Warnings (in amber) do not stop the script. Errors (in red) do: the script does not run until they are fixed.

## 10. Tips

- **Test a part.** Put `--` in front of the lines you do not want to run yet, or copy a few lines into a new script and run that.
  A block (`together`, `repeat`) must keep its opening and closing line, or the script has an error.
- **Keep it short.** A script of 20 to 40 lines is easy to read and to fix. Split a long tour into several scripts.
- **Time it by eye.** Run the script once from the start, then change the times. A caption makes the next line wait; put it in
  `together` to show it beside a camera move.
- **Keep the names readable.** Write `hide class IfcSlab fading over fade seconds`, not `hide class IfcSlab fading over f seconds`.
- **Save the script.** Give it a name and press **Save**. Scripts are kept in this browser for this model. **Export** saves the
  text to a `.xrayanim` file that you can send to a colleague, and **Import** opens it.
- **Check the size.** The whole script can run at most one hour and make at most 5 000 cues. Every camera move, setting change,
  caption, label and hover is one cue, and a loop makes its cues again on every pass. A long loop of many small steps is the usual
  reason for the message "The script makes more than 5000 steps".

## 11. Cookbook

Each recipe is a complete script. Change the class, storey, set and view names to the ones in your model. The names in quotes
must match the model exactly.

### 11.1 A walk-around of the pumps

The camera goes to the pumps, circles them, then visits each one with its name.

```xrayanim
-- Walk-around of the pumps
mode ghost
caption "The pumps" "Where the water is moved" for 3 seconds
fly to class IfcPump over 3 seconds margin 2.5
together
  orbit 120 degrees about class IfcPump over 6 seconds
  caption "Seen from every side" for 6 seconds
end together
select nothing
repeat for each element in class IfcPump
  together
    fly to it over 2 seconds margin 3
    label it with name for 2 seconds
  end together
end repeat
fly to everything over 3 seconds
```

### 11.2 Storey by storey: peel back the slabs

The slabs of the top floors fade away, one storey at a time, so that the floors below and the services show.

```xrayanim
-- Peel the slabs off, top floor first
put 1.5 into fade
mode solid
fly to everything over 3 seconds
caption "Peel back" "One storey at a time" for 2 seconds
hide where class = IfcSlab and storey = "Level 5" fading over fade seconds
wait 0.5 seconds
hide where class = IfcSlab and storey = "Level 4" fading over fade seconds
wait 0.5 seconds
hide where class = IfcSlab and storey = "Level 3" fading over fade seconds
caption "Inside" "The services show through the open floors" for 3 seconds
show everything fading over 2 seconds
```

### 11.3 Highlight each system

Each stored selection set (for example the set of the supply air duct, the set of the drainage pipes) is selected, flown to and
named in turn. Make the sets first in the **Sets** tab of the left sidebar ([sets-query.md](sets-query.md)).

```xrayanim
-- Visit every stored selection set
mode ghost
repeat for each set in sets
  together
    select it
    fly to it over 2 seconds margin 2.5
    caption it for 3 seconds
  end together
end repeat
select nothing
fly to everything over 2 seconds
```

### 11.4 Compare two options with captions

Two saved views, Option A and Option B, are shown one after the other, with a caption that says what changes. Save the two views
in the Views tab first, with these names.

```xrayanim
-- Option A against option B
mode solid
fly to view "Option A" over 3 seconds
caption "Option A" "Duct route through the corridor" for 4 seconds
wait 1 second
fly to view "Option B" over 3 seconds
caption "Option B" "Duct route above the ceiling" for 4 seconds
wait 1 second
caption "Compare" "Look at the clearance to the beams" for 4 seconds
```

### 11.5 A slow orbit for a kiosk

A kiosk shows the model turning slowly. The script runs 20 turns of 30 seconds (10 minutes). When it ends, press **Run** again,
or raise the count. The whole script can run at most one hour.

```xrayanim
-- Slow turn for a screen in the lobby
mode solid
set cinematic.glowStrength to 0.4 over 2 seconds
repeat 20 times
  orbit 360 degrees over 30 seconds ease linear
end repeat
```

### 11.6 Show one system, then bring the building back

One system is isolated and named; the rest of the model returns afterwards.

```xrayanim
-- Isolate the pumps, then show the rest
mode ghost
isolate class IfcPump fading over 1.5 seconds
caption "Pumps only" "The rest of the model is hidden" for 4 seconds
show everything fading over 2 seconds
caption "The whole building" for 3 seconds
```

### 11.7 A walk through one floor

The camera goes around the floor, stops at each room group, and says what it is. Replace the storey and the sets with yours.

```xrayanim
-- Walk through level 2
mode solid
fly to where storey = "Level 2" over 3 seconds margin 2
caption "Level 2" "The floor plan" for 3 seconds
together
  orbit 90 degrees about where storey = "Level 2" over 4 seconds
  caption "Services" "Ducts and pipes on this floor" for 4 seconds
end together
hover class IfcDuctSegment for 2 seconds
hover class IfcPipeSegment for 2 seconds
select nothing
fly to everything over 2 seconds
```

### 11.8 Label the walls of one storey

Each wall of one storey is hovered and labelled in turn. Change the storey name to yours.

```xrayanim
-- Labels on the first floor walls
mode solid
fly to where class = IfcWall and storey = "Level 1" over 2 seconds margin 2.5
repeat for each element in where class = IfcWall and storey = "Level 1"
  together
    label it with name, material for 1.5 seconds
    hover it for 1.5 seconds
  end together
end repeat
```

## 12. 4D films: following a construction schedule

A 4D plan (`xray-4d plan`, or the 4D tools of the viewer) says when every element is built. The `schedule` statement plays it; the
statements that come with it direct the film: where the camera goes, when the building explodes, which floor is cut open. You can
write this by hand, or let the director write it (`xray-4d script build.4d.json -o film.xrayanim`) and edit the result.

Three things work differently from the rest of the language:

- `schedule "Plan name" over 120 seconds` starts the plan and **does not wait**: the statements after it start with it.
- `at date "2027-03-01"` and `at milestone "Frame complete"` put the statements after them **at that moment of the schedule**. They
  do not wait for the lines above, so the blocks of a film may overlap. The compiler turns the date into seconds with the plan's
  time map, so the plan must be known by name when the script is compiled. An unknown plan or milestone, or a text that is not a
  date, is an error with its line and column.
- `active`, `completed` and `critical` are element words: the elements of the running schedule that are being built, are done, or
  are on the critical path *at that moment* (`fly to active`, `focus active`, `tint critical red`).

The other 4D statements: `tint <elements> <colour> [fading over N]`, `explode storeys|radial [by N] [over N]`,
`collapse [over N]`, `focus <elements>`, `section box around <elements>|storey "Name" [over N]` and `section box off [over N]`.
See the [grammar](animation-script-grammar.md#31-the-4d-statements).

### 12.1 A calm film: title, a look inside, the frame complete

The plan is called "Tower A". The film opens wide with a title, shows the structure going up with the active work in focus, and
opens the building out when the frame is complete.

```xrayanim
-- A calm 4D film of Tower A
schedule "Tower A" view planned from "2026-09-01" to "2028-05-30" over 120 seconds
together
  fly to everything over 3 seconds
  caption "Tower A" "Planned 2026-09-01 to 2028-05-30" for 3 seconds
end together
at date "2027-01-18"
  fly to active over 3 seconds margin 2
  label active with activity, percent for 5 seconds
at milestone "Frame complete"
  together
    focus everything
    explode storeys by 1.5 over 2 seconds
    caption "Frame complete" "The structure is up" for 3 seconds
  end together
at date "2027-06-20"
  orbit 60 degrees over 6 seconds ease linear
  collapse over 2 seconds
  focus active
```

### 12.2 One floor at a time: section box and the critical path

During the fit-out the film goes into one floor with a section box, tints the critical work and opens the box again when the
work leaves the floor.

```xrayanim
-- Fit-out of level 3, then the whole building again
schedule "Tower A" over 120 seconds
at date "2027-11-02"
  section box around storey "Level 3" over 1.5 seconds
  fly to active over 2 seconds
at date "2027-11-20"
  tint critical #e53935 fading over 1 seconds
  label critical with activity, finish for 4 seconds
at milestone "Envelope closed"
  caption "Envelope closed" "Fit-out starts inside" for 3 seconds
at date "2028-02-10"
  tint critical off fading over 1 seconds
  section box off over 1 seconds
  fly to everything over 3 seconds
```

If the plan is missing, the first line is the error: `There is no 4D plan named "Tower A"`, with the names of the plans that are
loaded. A date outside the plan is a warning and counts as the nearest end of it.

## 13. Decisions, loops and your own commands

So far every line runs, in order. You can also let the script **decide** what to show, **count**, and **name a group of lines**
you use more than once. All of this is worked out when you press Run, before anything plays: the script looks at the model,
your numbers and your text, and the result is the fixed list of steps that then plays. Nothing is decided while it plays.

**Decisions with `if`.** Conditions compare numbers and text (`=`, `<>`, `<`, `>`, `<=`, `>=`; text ignores capital letters),
and join with `and`, `or`, `not` and brackets. Two questions about the model: `the count of <elements>` is a number, and
`there are <elements>` is yes or no.

```xrayanim
-- Show the pumps if there are any, else the valves
if there are class IfcPump then
  fly to class IfcPump over 3 seconds
  caption "Pumps" "There are " & the count of class IfcPump for 3 seconds
else if there are class IfcValve then
  fly to class IfcValve over 3 seconds
else
  caption "Nothing to show" for 2 seconds
end if
if the count of class IfcPump > 3 then caption "A big pump room" for 2 seconds
```

Notes: `else if` and `else` are optional; the one-line form `if <condition> then <statement>` takes one plain statement and no
`end if`. When a `where` is followed by more, put it in brackets: `if there are (where class = IfcDoor and storey = "Level 1") and n > 2 then`.

**Loops that count or wait for something.** `repeat with i from 1 to 5` counts (add `by 2`, or write `down to` to count
backwards). `repeat while <condition>` and `repeat until <condition>` go on until the condition changes, so something inside
must change it. A loop runs at most 500 times; a loop that never ends is stopped with a message that names its line.

```xrayanim
-- Grow a gap: 1, 2, 4, 8 seconds
put 1 into gap
repeat while gap < 10
  caption "Pause of " & gap & " seconds" for 1 seconds
  wait gap
  put gap * 2 into gap
end repeat
repeat with i from 3 down to 1
  caption "" & i for 1 seconds
end repeat
```

**Your own commands.** `on <name> <parameters>` ... `end <name>` teaches the script a new statement; call it by name with its
values. Its lines go on the timeline where it is called, one after the other, so it can fly, caption and wait like any lines.
The parameters can be used in text, in numbers, and in a `where` (`where storey = name`). A handler may stand anywhere at the
top level, even below the lines that call it.

```xrayanim
-- Floor by floor, skipping a floor that has no walls
on showFloor name
  if there are (where class = IfcWall and storey = name) then
    show where storey = name fading over 0.5 seconds
    fly to where storey = name over 2 seconds
    caption name for 2 seconds
  end if
end showFloor

hide everything
repeat with i from 1 to 5
  showFloor "Level " & i
end repeat
show everything fading over 1 seconds
```

**Your own functions.** `function <name> <parameters>` ... `return <value>` ... `end <name>` works out a value; use it in an
expression as `name(value)`. A function only computes: it cannot fly, wait or caption (use a handler for that).

```xrayanim
function plural n
  if n = 1 then return n & " pump"
  return n & " pumps"
end plural
caption "The plant" "It has " & plural(the count of class IfcPump) for 3 seconds
```

Rules for names: a handler or function has **its own names**: its parameters and what it `put`s. It can read the names of the
script, but a `put` inside it never changes a name outside. Handlers and functions can call each other and themselves (recursion) up to 16
calls deep. Their names may not be words of the language (`show`, `if`, ...).

**Issues and drawings.** While a script plays, the issue pins and the drawings are hidden, so the film is clean. A script shows
them only when it says so, with `show issues` and `show drawings` (and `hide` to take them away again); they come back as they
were when the script ends. `fade new elements over 1.5 seconds` sets how long elements that appear or disappear fade from then
on, and `schedule "Plan" over 60 seconds fade 0.8 seconds` sets the fade-in of that schedule.

When something goes wrong the Problems list says where: an `if` with no `end if`, an `end repeat` that closes an `if`, an `else`
with no `if`, a call with the wrong number of values, a `return` outside a function.

## 14. Summary

- A line is one step. Lines run one after another unless they are in a `together` block.
- Name the elements with `class`, `where`, `set` or `everything`.
- Change the look with `mode`, `apply preset`, or `set` with a setting name from [docs/SETTINGS.md](../../docs/SETTINGS.md).
- Show and hide with fades. Caption and label to explain.
- Loops (`repeat`) do the same thing many times. Variables (`put`) keep numbers under names.
- When it does not run, read the first message in the Problems list. Its line number is where to look.
- `if`, `repeat while`, `repeat with` and your own commands (`on`, `function`) let the script decide and count; it is all worked out when you press Run (chapter 13).
- A 4D plan plays with `schedule`; `at date` and `at milestone` place the statements on the schedule's clock (chapter 12).
