# 23A. Scripts that decide: logic, text and reuse

A script from chapter 23 plays every line, in order. Real work needs more. "Show the pumps if there are any." "Visit floors 1 to 5,
but skip a floor with no walls." "Label each wall with its fire rating." "The same film for any floor." Copying lines and editing them
by hand does not scale, and it breaks when the model changes.

## 23A.1 Decide, count and repeat

### The idea

The script looks at the model while you press **Run**, then plays a fixed list of steps. Nothing is decided during playback. So an
`if` is like a person writing a to-do list after looking at the model: the lines that do not apply are never written.

### Try it

Use the **Process plant** sample. In the **Script** tab type:

```
if there are class IfcPump then
  fly to class IfcPump over 3 seconds
  caption "Pumps" "There are " & the count of class IfcPump for 3 seconds
else
  caption "No pumps" for 2 seconds
end if
```

Press **Run**. The caption names the number of pumps. Change `IfcPump` to `IfcDuctSegment` (the plant has none) and Run again: the `else` line plays.

Now count and wait:

```
put 1 into gap
repeat while gap < 10
  caption "Pause of " & gap & " seconds" for 1 seconds
  wait gap
  put gap * 2 into gap
end repeat
```

### How it works

- **Conditions** compare numbers and text with `=`, `<>`, `<`, `>`, `<=`, `>=` (text ignores capitals) and join with `and`, `or`,
  `not` and brackets. `there are <elements>` is yes or no. `the count of <elements>` is a number.
- **One-line form:** `if the count of class IfcPump > 3 then caption "A big pump room" for 2 seconds`.
- **Loops that count:** `repeat with i from 1 to 5` (add `by 2`, or `down to`). `repeat while` and `repeat until` go on until
  the condition changes, so something inside the loop must change it. A loop stops after 500 passes, with a message that names its line.
- **Leaving early:** `exit repeat` leaves a loop. `next repeat` skips to the next pass. `exit <handler>` leaves your own command.
- When a `where` is followed by more words, put it in brackets: `if there are (where class = IfcDoor and storey = "Level 1") and n > 2 then`.

### Limits and gotchas

- `the count of` and `there are` need a model. They cannot count `active`, `completed` or `critical`, which are known only while
  a schedule plays.
- Blocks nest at most 8 deep.

## 23A.2 Your own commands and functions

### The idea

When you write the same four lines for the third time, give them a name. A **handler** is a command you define. A **function** is a
calculation you define.

### Try it

```
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

Run it on **Synth 5k**. The film visits each floor that has walls and skips the rest. A function returns a value instead:

```
function plural n
  if n = 1 then return n & " pump"
  return n & " pumps"
end plural
caption "The plant" "It has " & plural(the count of class IfcPump) for 3 seconds
```

### How it works

A handler's lines go on the timeline where it is called, one after another, so it can fly, caption and wait. A function only
computes. Each has its own names: a `put` inside never changes a name outside. They can call each other, up to 16 calls deep.
A handler may stand below the lines that call it. Their names cannot be words of the language.

## 23A.3 Issues, drawings and fades

While a script plays, issue pins and drawings are hidden, so the film is clean. They come back as they were when it ends. Say
`show issues` or `show drawings` to keep them (and `hide issues`, `hide drawings` to take them away again). The same default holds for
fly-throughs and 4D films (chapters 22 and 27), which have their own tick boxes.

`fade new elements over 1.5 seconds` sets how long elements fade in or out from that line on. In a 4D line,
`schedule "Plan" over 60 seconds fade 0.8 seconds` sets the fade-in of that schedule.

## 23A.4 Facts, text, lists and maths

### Try it

On a model whose walls carry `Pset_WallCommon.FireRating`:

Try it on **Synth 5k** (240 of its walls carry `FireRating`) or the **Process plant** (5 walls).

```
repeat for each element in class IfcWall
  put property "Pset_WallCommon.FireRating" of it into rating
  if rating contains "60" then
    caption the name of it && "has" && rating for 1 seconds
  end if
end repeat
```

Then a list:

```
put "Level 3, Level 1, Level 2" into floors
put sort items of floors into ordered
repeat for each item floor in ordered
  caption floor && "of" && the number of items in floors for 1 seconds
end repeat
```

### How it works

- **Facts of an element**, inside `repeat for each element`: `the name of it`, `the class of it`, `the storey of it`, `the type of it`,
  `the globalid of it`, and `property "Pset.Name" of it`. A missing fact is empty text. `the names of class IfcPump` gives all the
  names, separated by commas.
- **Text:** `&` joins; `&&` joins with one space. The tests `contains`, `begins with`, `ends with`, `is in` and `is not in` ignore capitals.
- **Lists are text.** Items are separated by commas, words by spaces, lines by line breaks. `item 2 of x`, `word 3 of x`, `line 1 of x`,
  `char 1 to 3 of x`, `the number of items in x`, `sort items of x` (add `descending` or `numeric`).
- **Maths:** `round(x)`, `round(x, 1)`, `trunc`, `floor`, `ceil`, `abs`, `min`, `max`, `sqrt`, `x mod y`, `x div y`, `x ^ y`, `pi`.
  Division by zero, or the root of a negative number, is an error.
- **Random:** `random(6)` gives 1 to 6, `random()` 0 to 1. The numbers are seeded from the script text, so the same script always makes the
  same film. `set the random seed to 7` picks another.

### Limits and gotchas

- A list or `names of` is cut at 500 pieces. A `repeat for each item` over more is an error.
- The seed means a "random" pause is the same every run. That is on purpose: a film you recorded can be recorded again.

## 23A.5 One script, any floor: param and use

### The idea

A script that mentions "Level 1" in six places is a script for one floor. Declare that value once at the top, and change it without
editing the script.

### Try it

```
param floor default "Level 1"
param pause default 3
fly to where storey = floor over 3 seconds
caption "Now showing" && floor for pause seconds
```

Run it. A **Parameters** form appears above **Run** in the Script tab with `floor` and `pause`. Change `floor` and run again. The
**Examples** menu has "One script, any floor" and "Label the fire-rated walls", which show both ideas on a real model.

### How it works

`param name default value` takes a text, a number or yes or no. The form is yours, in this browser; it is not in a share link. The same value
can be given from `xray-4d render --param floor="Level 2"` (chapter 32) and `xray-pack --script-param` (chapter 30). A value for a name the
script does not declare is a warning.

`use "Floor helpers"` pulls in the handlers and functions of another saved script, and nothing else. A missing library, or two libraries
that use each other, is an error. If your script has a handler of the same name, yours wins, with a warning. On the command line,
`--use-dir folder` finds libraries as `.xrayanim` files in that folder.

### Limits and gotchas

- Names of handlers and functions are checked at Run. A call with the wrong number of values names its line in the Problems list.
- The full grammar and every limit are in the grammar document (`web/docs-features/animation-script-grammar.md`) and in 23.3.

## See also

Chapter 23 (first scripts, errors, statement reference), chapter 8 (the query language used in `where`), chapter 27 (4D statements and films).
