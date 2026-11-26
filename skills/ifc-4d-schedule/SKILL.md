---
name: ifc-4d-schedule
description: Link a Primavera P6 schedule (.xer) to an IFC model and write the result back into both, then write an animation script (.xrayanim) that plays any part of the build in schedule order. Reads the XER and the IFC itself, links activities to elements (rules from a 4D configuration plus the agent's own proposals for review), writes IfcWorkSchedule / IfcTask / dates / task-to-element assignments / logic and the Xray_4D property set into a copy of the IFC, writes 4D link status into a copy of the XER as activity user fields, and generates and checks X-ray animation scripts. Uses an IFC MCP server when one is connected, else the bundled Python and Node tools. Use for 4D linking, putting a schedule into an IFC, activity IDs or location/trade assignments in a model, or animating construction sequences tied to a schedule.
---

# 4D: schedule ↔ IFC, and animations tied to the schedule

The skill does every step with its own tools. Nothing needs to have been run before.

| Step | Tool (in `scripts/`) | Needs |
| --- | --- | --- |
| Read the schedule | `python xer_read.py schedule.xer [--project P] -o schedule.json` | nothing |
| Read the model | `python ifc_read.py model.ifc [--props Pset.Prop,...] -o model.json`, or IFC MCP queries | ifcopenshell 0.8.x (`requirements.txt`) |
| Link | `python link.py --xer schedule.json --ifc model.json --config map.4d.json [--prior links.json] [--proposals mine.json] -o links.json` | the two JSONs, a 4D configuration |
| Write the IFC | `python apply_links.py --ifc model.ifc --links links.json --xer schedule.xer -o model.4d.ifc`, or IFC MCP calls | ifcopenshell, or an MCP that can write |
| Check the IFC | `python verify.py --ifc model.4d.ifc --links links.json` | ifcopenshell |
| Write the XER | `python xer_write.py --xer schedule.xer --links links.json -o schedule.4d.xer` | nothing |
| Write an animation | `python anim_write.py --links links.json --ifc model.json [selection] [style] -o build.xrayanim` | nothing |
| Check an animation | `node xrayanim_check.mjs build.xrayanim [--param name=value]` (the viewer's own compiler; `use "Name"` reads `Name.xrayanim` next to the script) | node 18+ |

The JSON formats are described in [reference/data-formats.md](reference/data-formats.md). Every tool prints a JSON
summary on stdout and never overwrites its input.

## Workflow

1. **Read both files.** Run `xer_read.py` and `ifc_read.py` (or the MCP equivalents). Report:
   - the project, data date and activity count;
   - the activity code types and their values;
   - the model's storeys and the element count by class;
   - any 4D links already in the IFC (elements carrying tasks).
2. **Get a 4D configuration.** This says which schedule fields mean location, trade and zone, how schedule values map to
   model values, and which elements each trade builds (queries in the criteria language). Use one the user gives, or
   draft one from step 1 and show it to them:
   - Level or Area codes against storey names and zones;
   - Trade codes against IFC classes, names or properties.

   The format is the viewer's `.4d.json`; an example is `fzk-haus.4d.json` in the xray-ref samples, and the query
   language is summarised in `scripts/criteria.py`.
3. **Link.** Run `link.py`.
   - Rules give accepted links. The order of strength is links already in the IFC, then per-activity overrides, then
     matching location, trade and zone.
   - An element two activities claim equally is a tie and goes to neither.
4. **Propose where the rules fall short.** For activities with no elements, unlinked elements and ties, read the activity
   names and WBS and the element names, classes and storeys, and propose links yourself.
   - Write the proposals as `[{activity, role, elements, reasons, confidence}]` and pass them with `--proposals`.
   - They become `proposed` links, never `accepted`.
   - Show the user what you proposed and why, and record their decision: set the link's `status` to `accepted` or
     `rejected` in links.json, or in the SQL tables ([reference/sql.md](reference/sql.md)).
   - Re-run `link.py --prior links.json` to fold decisions in.
5. **Write the IFC** to a new file.
   - Through an IFC MCP server: [reference/mcp-tools.md](reference/mcp-tools.md), in the order of
     [reference/ifc-mapping.md](reference/ifc-mapping.md).
   - Otherwise with `apply_links.py`.

   Then run `verify.py`, or the same checks through MCP; it must pass. Only accepted links are written. An existing
   `Xray 4D` schedule is replaced; ask first if the user has not said to.
6. **Write the XER** with `xer_write.py`. This adds three activity user fields to a copy:
   - `4D Elements`: how many elements each activity builds;
   - `4D Status`: linked, proposed, tie, no elements or no geometry;
   - `4D Model`: the model file.

   Tell the user to import it into P6 with "update existing project", so only those fields change.
7. **Write an animation** when asked, or offer one. `anim_write.py` turns a selection of the schedule into a script:
   - **Selection**, combined: `--activities`, `--trade`, `--location`, `--wbs`, `--from`/`--to`, `--critical`,
     `--status`. For example "the roof", "everything on the critical path in June", or "the ground-floor masonry".
   - **What it does:** elements appear at their schedule time, swept along the building in `--chunks` steps. The camera
     follows the work (`--camera follow`), captions give the date and activity, and `--labels N` names the elements.
     Work finished before the window is shown at the start (`--context built`).
   - **Timing:** `--length` (seconds) or `--days-per-second`.
   - **4D statements:** `--plan NAME` uses the schedule clock statements (`schedule … over N`, `at date`,
     `at milestone`, `focus active`). These need the plan built in the viewer or by `xray-4d plan` from the same
     schedule.

   For a whole film with automatic camera work (shots, explode on multi-storey work, section boxes at interior work,
   milestone beats, each decision explained), use the X-ray CLI's director when the xray-ref repo is at hand:
   `xray-4d plan …` then `xray-4d script build.4d.json --model model.ifc --name NAME -o film.xrayanim --notes notes.txt`.
   `anim_write.py` is for parts of the build you select.

   You may edit the script afterwards, for example to add `explode storeys` at a milestone, `orbit`, or `mode cutaway`
   for interior work. The language also has `if` / `else if` / `else` / `end if`, `repeat while|until|with i from a to b`,
   your own commands (`on name params ... end name`, called as `name value`) and functions (`function name params ... return
   value ... end name`, called as `name(value)`), and `show issues` / `show drawings` (hidden while a script plays),
   `fade new elements over N seconds` and `schedule ... fade N seconds`. Decisions are made when the script compiles; the
   language also reads element facts (`the name of it`, `property "Pset_X.Prop" of it`, `the names of class IfcWall`), text
   (`contains`, `begins with`, `&&`, `item 2 of list`, `sort items of list`, `repeat for each item v in list`), maths (`round`,
   `min`, `max`, `sqrt`, `mod`, `div`, `^`, `pi`, a seeded `random(n)`), `exit repeat` / `next repeat` / `exit <handler>`,
   `param name default value` (a value changed from the Script tab's Parameters form, `xray-4d render --param name=value`,
   `xray-pack --script-param name=value`, or `xrayanim_check.mjs --param name=value`) and `use "Name"` (the handlers and
   functions of another script; the checker finds `Name.xrayanim` next to the script, `xray-4d render --use-dir folder` too).
   `anim_write.py --as-param` declares the film title as a `param`. The
   checker has no model, so a script that asks the model (`the count of ...`, `there are ...`) reports "needs the model" there:
   check those in the viewer. **Always** run `node xrayanim_check.mjs` on the result and fix every error before handing it
   over. The user plays it in the viewer's Script tab or renders it with `xray-4d render`.
8. **Report:**
   - counts: links accepted, proposed, rejected and ties, coverage, tasks written;
   - what was skipped and why;
   - the output files, the check results, and the sha256 of the outputs.

## Rules

- **Keys:** activities by P6 Activity ID, elements by GlobalId; never by name alone.
- **What reaches the files:** only accepted links are written into the IFC, the XER fields count only accepted
  links, and animations use only accepted links. Never write `reviewed_by` (personal data).
- **Outputs:** every output is a new file. Re-running gives the same file: the `Xray 4D` schedule and the `4D` user fields
  are replaced, never duplicated, and nothing else is changed.
- **IFC2X3:** has no `IfcTaskTime`. Tasks and assignments are written but dates are not; say so.
- **Duplicate logic links:** P6 can link one pair of activities twice (SS and FF); IFC keeps one sequence per pair.
  The first is kept and the other reported.
