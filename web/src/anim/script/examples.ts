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
  {
    id: 'floors',
    title: 'Floor by floor',
    about: 'A handler for each storey, called in a counting loop; a storey without walls is skipped (synth5k).',
    text: `-- Floor by floor: one handler, called for each storey. A storey with no walls is skipped.
-- (try it on the synth5k sample: its storeys are "Level 1" ... "Level 5")
on showFloor name
  if there are (where class = IfcWall and storey = name) then
    show where storey = name fading over 0.5 seconds
    fly to where storey = name over 2 seconds margin 2
    caption name "Walls: " & the count of (where class = IfcWall and storey = name) for 2 seconds
  end if
end showFloor

mode ghost
hide everything
fly to everything over 2 seconds
repeat with i from 1 to 6
  showFloor "Level " & i
end repeat
show everything fading over 1 seconds
`,
  },
  {
    id: 'pumpcount',
    title: 'Count the pumps',
    about: 'Decide by what the model holds: a function for the wording, an if for the story (process-plant).',
    text: `-- Tell the story of the pumps. The script looks at the model when it compiles and picks what to show.
function plural n
  if n = 1 then return n & " pump"
  return n & " pumps"
end plural

put the count of class IfcPump into pumps
if pumps = 0 then
  caption "No pumps" "This model has none" for 3 seconds
else
  mode ghost
  caption "Pumps" "This model has " & plural(pumps) for 3 seconds
  fly to class IfcPump over 3 seconds margin 2.5
  select class IfcPump
  if pumps > 1 then
    orbit 90 degrees about class IfcPump over 4 seconds
  end if
  select nothing
end if
`,
  },
  {
    id: 'film4d',
    title: 'A 4D film: follow the work',
    about: 'Play a 4D plan, follow the active work, explode the storeys when it spreads, clip to one storey (needs a plan named "Demo").',
    text: `-- A 4D film. It needs the 4D plan "Demo" (the demo plan of the 4D tools); change the name and the dates to yours.
schedule "Demo" over 40 seconds
together
  fly to everything over 3 seconds
  caption "Construction sequence" "Follow the work as it is built" for 3 seconds
end together
at date "2027-01-20"
  fly to active over 2 seconds margin 2
  label active with activity, percent for 4 seconds
at date "2027-02-01"
  explode storeys by 1.5 over 2 seconds
at date "2027-02-12"
  collapse over 2 seconds
at date "2027-02-18"
  section box around storey "Level 2" over 1.5 seconds
  focus active
at date "2027-03-01"
  section box off over 1 seconds
  tint critical red fading over 1 seconds
`,
  },
];
