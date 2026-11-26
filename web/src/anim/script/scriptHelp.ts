// The statements of the animation script language, each with a one-line description and an example. The editor's reference,
// the docs (docs-features/animation-script.md, kept in step by tests/animscript-docs.test.ts) and the examples menu use this
// list. Pure data: no DOM.

export interface StatementHelp {
  id: string;
  group: 'Camera' | 'Look' | 'Visibility' | 'Selection and notes' | 'Timing and variables' | 'Decisions, loops and your own commands' | 'Playback' | '4D schedule';
  /** The statement as written; `[ ]` marks what may be left out. */
  syntax: string;
  /** One line: what it does and how long it lasts. */
  summary: string;
  example: string;
}

export const STATEMENT_HELP: readonly StatementHelp[] = [
  { id: 'fly', group: 'Camera', syntax: 'fly to <elements> [over N seconds] [ease in|out|in out|linear] [margin N]', summary: 'Move the camera to frame the elements. Lasts 2 seconds unless told. Margin 1 to 6 is the room around them.', example: 'fly to class IfcPump over 3 seconds ease in out margin 2.5' },
  { id: 'flyView', group: 'Camera', syntax: 'fly to view "<name>" [over N seconds] [ease ...]', summary: 'Move the camera to a saved view of the Views tab.', example: 'fly to view "Plant room" over 4 seconds' },
  { id: 'orbit', group: 'Camera', syntax: 'orbit N degrees [about <elements>] [over N seconds] [ease ...]', summary: 'Turn the camera around the elements, or around the model. Lasts 3 seconds unless told.', example: 'orbit 90 degrees about where class = IfcPump over 6 seconds' },
  { id: 'set', group: 'Look', syntax: 'set <path> to <value> [over N seconds] [ease ...]', summary: 'Change one setting by its parameter path. Numbers blend over the time; on, off and text switch at its end.', example: 'set cinematic.glowStrength to 1.2 over 2 seconds' },
  { id: 'mode', group: 'Look', syntax: 'mode ghost|solid|radiograph|glow|cutaway', summary: 'Switch to a mode of the top bar. Instant.', example: 'mode radiograph' },
  { id: 'preset', group: 'Look', syntax: 'apply preset "<id or name>"', summary: 'Apply a built-in or saved preset. Instant.', example: 'apply preset "Peelback"' },
  { id: 'show', group: 'Visibility', syntax: 'show <elements> [fading over N seconds]', summary: 'Show hidden elements, with a fade or at once. `show everything` brings back all.', example: 'show everything fading over 1.5 seconds' },
  { id: 'hide', group: 'Visibility', syntax: 'hide <elements> [fading over N seconds]', summary: 'Hide elements, with a fade or at once.', example: 'hide class IfcSlab fading over 2 seconds' },
  { id: 'isolate', group: 'Visibility', syntax: 'isolate <elements> [fading over N seconds]', summary: 'Show only these elements and hide the rest.', example: 'isolate set "Pumps" fading over 1 seconds' },
  { id: 'select', group: 'Selection and notes', syntax: 'select <elements>   |   select nothing', summary: 'Select elements, or clear the selection. Instant.', example: 'select where storey = "Level 2"' },
  { id: 'caption', group: 'Selection and notes', syntax: 'caption "Title" ["More text"] [for N seconds]', summary: 'Show a caption. Lasts 3 seconds unless told, and the next statement waits for it.', example: 'caption "The pump room" "Four pumps feed the loop" for 4 seconds' },
  { id: 'label', group: 'Selection and notes', syntax: 'label <elements> with <field>, <field> [for N seconds]', summary: 'Pin a tag to each element (at most 12 show, with "+N more"). Fields: name, class, storey, material, globalid, type, or a property as "Pset_X.Prop". Lasts 3 seconds.', example: 'label class IfcPump with name, storey, "Pset_PumpCommon.Reference" for 4 seconds' },
  { id: 'hover', group: 'Selection and notes', syntax: 'hover <elements> [for N seconds]', summary: 'Show the hover card of the first element, near it with a leader line. Lasts 2 seconds unless told.', example: 'hover set "Pumps" for 2 seconds' },
  { id: 'wait', group: 'Timing and variables', syntax: 'wait N [seconds]', summary: 'Do nothing for a time.', example: 'wait 1.5 seconds' },
  { id: 'together', group: 'Timing and variables', syntax: 'together ... end together', summary: 'Start the statements inside at the same moment. The block lasts as long as the longest.', example: 'together\n  fly to class IfcPump over 3 seconds\n  caption "Pumps" for 3 seconds\nend together' },
  { id: 'repeat', group: 'Timing and variables', syntax: 'repeat N times ... end repeat', summary: 'Run the statements inside again and again. `index` counts from 1. At most 500 times.', example: 'repeat 3 times\n  orbit 120 degrees over 2 seconds\nend repeat' },
  { id: 'forEachElement', group: 'Timing and variables', syntax: 'repeat for each element in <elements> ... end repeat', summary: 'Run the statements once for each element. `it` is the element. At most 500 elements.', example: 'repeat for each element in class IfcPump\n  fly to it over 2 seconds\nend repeat' },
  { id: 'forEachSet', group: 'Timing and variables', syntax: 'repeat for each set in sets ... end repeat', summary: 'Run the statements once for each stored selection set. `it` is the set.', example: 'repeat for each set in sets\n  select it\n  caption it for 2 seconds\nend repeat' },
  { id: 'put', group: 'Timing and variables', syntax: 'put <value> into <name>', summary: 'Keep a number, text ("a" & b joins text) or a yes/no under a name. Use the name wherever a number goes. Signs: + - * / and ( ).', example: 'put 2 * 1.5 into pause' },
  {
    id: 'if',
    group: 'Decisions, loops and your own commands',
    syntax: 'if <condition> then ... [else if <condition> then ...] [else ...] end if',
    summary: 'Run the statements of the first branch whose condition is true. Decided when the script compiles, so the timeline has no branches. Conditions: = <> < > <= >= on numbers and text (text ignores case), and, or, not, ( ), the count of <elements>, there are <elements>.',
    example: 'if there are class IfcPump then\n  fly to class IfcPump over 2 seconds\nelse if there are class IfcValve then\n  fly to class IfcValve over 2 seconds\nelse\n  caption "No pumps or valves"\nend if',
  },
  { id: 'ifOne', group: 'Decisions, loops and your own commands', syntax: 'if <condition> then <statement>', summary: 'The one-line form: one plain statement, no `end if`.', example: 'if the count of class IfcPump > 3 then caption "Many pumps"' },
  { id: 'while', group: 'Decisions, loops and your own commands', syntax: 'repeat while <condition> ... end repeat', summary: 'Run the statements again and again while the condition is true. Something inside must change what it tests. At most 500 times, then an error names the line.', example: 'put 1 into n\nrepeat while n < 4\n  caption "Step " & n for 1 seconds\n  put n + 1 into n\nend repeat' },
  { id: 'until', group: 'Decisions, loops and your own commands', syntax: 'repeat until <condition> ... end repeat', summary: 'Run the statements again and again until the condition becomes true.', example: 'put 1 into n\nrepeat until n > 3\n  wait 1\n  put n + 1 into n\nend repeat' },
  { id: 'repeatWith', group: 'Decisions, loops and your own commands', syntax: 'repeat with <name> from <a> to|down to <b> [by <step>] ... end repeat', summary: 'Count from a to b (or down). The name holds the count and is given back after the loop. At most 500 times.', example: 'repeat with i from 1 to 5\n  caption "Level " & i for 1 seconds\nend repeat' },
  {
    id: 'on',
    group: 'Decisions, loops and your own commands',
    syntax: 'on <name> [param, param] ... end <name>',
    summary: 'Define your own command (a handler). Call it as a statement: name value, value. Its statements go on the timeline where it is called. Parameters and names it `put`s are its own; it can read the script\'s names. It may stand anywhere at the top level.',
    example: 'on showFloor name\n  show where storey = name fading over 1 seconds\n  caption name for 2 seconds\nend showFloor\nshowFloor "Level 1"',
  },
  { id: 'call', group: 'Decisions, loops and your own commands', syntax: '<name> [value, value]', summary: 'Call a handler: its statements run here, one after the other, with the values as its parameters. Calls may nest up to 16 deep (recursion).', example: 'on pause n\n  wait n\nend pause\npause 2' },
  {
    id: 'function',
    group: 'Decisions, loops and your own commands',
    syntax: 'function <name> [param, param] ... return <value> ... end <name>',
    summary: 'Define a function: it works out a value and gives it back with `return`. Use it in an expression: name(value, value). A function computes only; it does not move the camera or wait.',
    example: 'function double x\n  return x * 2\nend double\nwait double(1.5) seconds',
  },
  { id: 'return', group: 'Decisions, loops and your own commands', syntax: 'return [<value>]', summary: 'Inside a function: give the value back and stop. Inside a handler: stop early (no value).', example: 'on early n\n  if n > 1 then return\n  caption "small"\nend early\nearly 1' },
  { id: 'overlays', group: 'Playback', syntax: 'show|hide issues|drawings   (or: issues and drawings)', summary: 'Show or hide the issue pins and the drawings during playback. Both are hidden while a script plays unless it shows them, and come back as they were afterwards. Instant.', example: 'show issues and drawings' },
  { id: 'fadeNew', group: 'Playback', syntax: 'fade new elements over N seconds   |   fade new elements instantly', summary: 'Set how long elements that appear or disappear from here on fade (show, hide, schedule activities). Instantly is 0.', example: 'fade new elements over 1.5 seconds' },
  { id: 'schedule', group: '4D schedule', syntax: 'schedule "<plan>" [view planned|actual|variance] [from "<date>"] [to "<date>"] [over N seconds] [fade N seconds]', summary: 'Play a 4D plan by name over a time (default: the plan\'s film length). It runs in the background: the statements after it start with it. View, from and to go to the step for the host to rebuild the plan with. Fade is how long a new element fades in.', example: 'schedule "Tower A" view actual from "2026-09-01" to "2028-05-30" over 120 seconds fade 0.8 seconds' },
  { id: 'atDate', group: '4D schedule', syntax: 'at date "<YYYY-MM-DD[THH:MM]>"', summary: 'The statements after it start when the running schedule reaches that date, whether or not the ones before have ended.', example: 'at date "2027-01-18"' },
  { id: 'atMilestone', group: '4D schedule', syntax: 'at milestone "<name>"', summary: 'The statements after it start when the running schedule reaches that milestone.', example: 'at milestone "Envelope closed"' },
  { id: 'tint', group: '4D schedule', syntax: 'tint <elements> <#rrggbb|colour name|off> [fading over N seconds]', summary: 'Colour elements, with a fade or at once; `off` takes the tint away. Names: red, orange, yellow, green, teal, cyan, blue, indigo, purple, magenta, pink, brown, grey, white, black.', example: 'tint critical #e53935 fading over 1 seconds' },
  { id: 'explode', group: '4D schedule', syntax: 'explode storeys|radial [by N] [over N seconds]', summary: 'Move the storeys apart (or push every element out from the centre). By is the factor (default 1). Lasts 2 seconds unless told.', example: 'explode storeys by 1.5 over 2 seconds' },
  { id: 'collapse', group: '4D schedule', syntax: 'collapse [over N seconds]', summary: 'Bring an exploded building back together. Lasts 2 seconds unless told.', example: 'collapse over 2 seconds' },
  { id: 'focus', group: '4D schedule', syntax: 'focus <elements>   |   focus nothing', summary: 'Set the x-ray focus: what stands in front of these elements ghosts. `focus active` follows the active work of the schedule; `focus nothing` gives the focus back to the selection. Instant.', example: 'focus active' },
  { id: 'section', group: '4D schedule', syntax: 'section box around <elements>|storey "<name>" [over N seconds]', summary: 'Clip the model to a box around the elements or a storey. Lasts 1.5 seconds unless told.', example: 'section box around storey "Level 3" over 1.5 seconds' },
  { id: 'sectionOff', group: '4D schedule', syntax: 'section box off [over N seconds]', summary: 'Take the section box away, opening it out over the time.', example: 'section box off over 1 seconds' },
];

/** What `<elements>` can be. */
export const ELEMENT_HELP: readonly { syntax: string; summary: string; example: string }[] = [
  { syntax: 'where <criteria>', summary: 'Elements that match a criteria query. Text values need no quotes unless they hold spaces.', example: 'where class = IfcPump and storey = "Level 2"' },
  { syntax: 'class A[, B]', summary: 'Shorthand for the elements of one or more classes.', example: 'class IfcPump, IfcValve' },
  { syntax: 'set "Name"', summary: 'The members of a stored selection set.', example: 'set "Pumps"' },
  { syntax: 'the selection', summary: 'What is selected at that moment.', example: 'the selection' },
  { syntax: 'everything', summary: 'All elements.', example: 'everything' },
  { syntax: 'it', summary: 'The current element or set inside `repeat for each`.', example: 'it' },
  { syntax: 'elements "id", "id"', summary: 'Elements by GlobalId.', example: 'elements "2O2Fr$t4X7Zf8NOew3FLOH"' },
  { syntax: 'active | completed | critical', summary: '4D: the elements of the running schedule that are being built, are done, or are being built on the critical path, at that moment.', example: 'active' },
];

/** The rules of timing, for the reference. */
export const TIMING_NOTES: readonly string[] = [
  'Statements run in order. Each starts when the one before it has ended.',
  'Fly, orbit, set, fading, caption, label, hover and wait last their time. Mode, apply, select and plain show or hide are instant.',
  'Use `together` to run statements side by side, for example a camera move with a caption.',
  'Keywords ignore case. Comments start with -- or #. One statement per line. Text goes in "double quotes".',
  '`schedule` does not wait: the statements after it start with it. `at date` and `at milestone` put the statements after them at that moment of the schedule (through the plan\'s time map), whether or not the ones before have ended. Explode, collapse and section box last their `over` time; tint lasts its `fading` time.',
  '`if`, `repeat while`, `repeat until`, `repeat with` and your own commands are worked out when the script compiles, from numbers, text, the model (`the count of`, `there are`) and the 4D plan; the result is a fixed timeline. Nothing is decided while it plays.',
  'Names: a handler or function has its own names (its parameters, and what it `put`s); it can read the script\'s names and `it`, but a `put` inside never changes one outside.',
  'Issues and drawings are hidden while a script plays; `show issues` and `show drawings` bring them in, `hide` takes them away.',
  'A script runs at most one hour, makes at most 5000 steps and loops at most 500 times. Calls of your own commands nest at most 16 deep.',
];

/** A markdown reference, the same text as the docs page uses for its statement list. */
export function referenceMarkdown(): string {
  const lines: string[] = [];
  let group = '';
  for (const s of STATEMENT_HELP) {
    if (s.group !== group) {
      group = s.group;
      if (lines.length > 0) lines.push('');
      lines.push(`### ${group}`, '');
    }
    lines.push(`- \`${s.syntax.replace(/\s+\|\s+/g, ' | ')}\`: ${s.summary}`);
  }
  return lines.join('\n');
}
