// Example scripts for the editor's Examples menu. Each compiles without errors on a model that has what it names (the
// process-plant sample for the pumps, synth5k for the storeys); the tests compile them with a fake model.

export interface ScriptExample {
  id: string;
  title: string;
  /** One line for the menu. */
  about: string;
  text: string;
}

export const EXAMPLES: readonly ScriptExample[] = [
  {
    id: 'pumps',
    title: 'A walk around the pumps',
    about: 'Ghost the model, fly to the pumps, circle them, then visit each one.',
    text: `-- A walk around the pumps (try it on the process-plant sample)
mode ghost
caption "The pumps" "Where the water is moved" for 3 seconds
fly to class IfcPump over 3 seconds margin 2.5
select class IfcPump
together
  orbit 120 degrees about class IfcPump over 6 seconds
  caption "Four pumps" "Seen from every side" for 6 seconds
end together
select nothing
repeat for each element in class IfcPump
  together
    fly to it over 2 seconds margin 3
    hover it for 2 seconds
  end together
end repeat
fly to everything over 3 seconds
`,
  },
  {
    id: 'slabs',
    title: 'Peel back the slabs storey by storey',
    about: 'Fade out the slabs from the top level down to look inside (synth5k).',
    text: `-- Peel back the slabs, top level first (try it on the synth5k sample)
put 1.5 into fade
mode solid
fly to everything over 3 seconds
caption "Peel back" "One storey at a time" for 2 seconds
hide where class = IfcSlab and storey = "Level 5" fading over fade seconds
wait 0.5
hide where class = IfcSlab and storey = "Level 4" fading over fade seconds
wait 0.5
hide where class = IfcSlab and storey = "Level 3" fading over fade seconds
caption "Inside" "The services show through the open storeys" for 3 seconds
show everything fading over 2 seconds
`,
  },
  {
    id: 'sets',
    title: 'Highlight each set with a caption',
    about: 'Go through the stored selection sets: select, fly, name.',
    text: `-- Visit every stored selection set
mode ghost
repeat for each set in sets
  together
    select it
    fly to it over 2 seconds
    caption it "Selection set" for 3 seconds
  end together
end repeat
select nothing
fly to everything over 2 seconds
`,
  },
  {
    id: 'look',
    title: 'Change the look over time',
    about: 'Blend settings, switch modes and orbit.',
    text: `-- Settings blend over time; modes switch at once
mode radiograph
caption "Radiograph" "Dense things show up bright" for 3 seconds
mode glow
set cinematic.glowStrength to 0.3
together
  set cinematic.glowStrength to 1.4 over 4 seconds ease in out
  orbit 180 degrees over 4 seconds
end together
mode solid
`,
  },
];
