// The statements of the animation script language, each with a one-line description and an example. The editor's reference,
// the docs (docs-features/animation-script.md, kept in step by tests/animscript-docs.test.ts) and the examples menu use this
// list. Pure data: no DOM.

export interface StatementHelp {
  id: string;
  group: 'Camera' | 'Look' | 'Visibility' | 'Selection and notes' | 'Timing and variables';
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
  { id: 'label', group: 'Selection and notes', syntax: 'label <elements> with <field>, <field> [for N seconds]', summary: 'Pin labels to the elements. Fields: name, class, storey, or a property as "Pset_X.Prop". Lasts 3 seconds.', example: 'label class IfcPump with name, storey, "Pset_PumpCommon.Reference" for 4 seconds' },
  { id: 'hover', group: 'Selection and notes', syntax: 'hover <elements> [for N seconds]', summary: 'Show the hover highlight on the elements. Lasts 2 seconds unless told.', example: 'hover set "Pumps" for 2 seconds' },
  { id: 'wait', group: 'Timing and variables', syntax: 'wait N [seconds]', summary: 'Do nothing for a time.', example: 'wait 1.5 seconds' },
  { id: 'together', group: 'Timing and variables', syntax: 'together ... end together', summary: 'Start the statements inside at the same moment. The block lasts as long as the longest.', example: 'together\n  fly to class IfcPump over 3 seconds\n  caption "Pumps" for 3 seconds\nend together' },
  { id: 'repeat', group: 'Timing and variables', syntax: 'repeat N times ... end repeat', summary: 'Run the statements inside again and again. `index` counts from 1. At most 500 times.', example: 'repeat 3 times\n  orbit 120 degrees over 2 seconds\nend repeat' },
  { id: 'forEachElement', group: 'Timing and variables', syntax: 'repeat for each element in <elements> ... end repeat', summary: 'Run the statements once for each element. `it` is the element. At most 500 elements.', example: 'repeat for each element in class IfcPump\n  fly to it over 2 seconds\nend repeat' },
  { id: 'forEachSet', group: 'Timing and variables', syntax: 'repeat for each set in sets ... end repeat', summary: 'Run the statements once for each stored selection set. `it` is the set.', example: 'repeat for each set in sets\n  select it\n  caption it for 2 seconds\nend repeat' },
  { id: 'put', group: 'Timing and variables', syntax: 'put <number> into <name>', summary: 'Keep a number under a name. Use the name wherever a number goes. Signs: + - * / and ( ).', example: 'put 2 * 1.5 into pause' },
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
];

/** The rules of timing, for the reference. */
export const TIMING_NOTES: readonly string[] = [
  'Statements run in order. Each starts when the one before it has ended.',
  'Fly, orbit, set, fading, caption, label, hover and wait last their time. Mode, apply, select and plain show or hide are instant.',
  'Use `together` to run statements side by side, for example a camera move with a caption.',
  'Keywords ignore case. Comments start with -- or #. One statement per line. Text goes in "double quotes".',
  'A script runs at most one hour, makes at most 5000 cues and loops at most 500 times.',
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
