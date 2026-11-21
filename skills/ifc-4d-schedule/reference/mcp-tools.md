# Using an IFC MCP server

IFC MCP servers differ in their tool names. Discover what the connected one offers, then map the steps of
[ifc-mapping.md](ifc-mapping.md) onto it. Most are built on IfcOpenShell.

## What to look for, best first

1. **A general "run IfcOpenShell API" or "execute code on the model" tool.** It takes an API name and arguments, or a
   Python snippet. Use it for every step with the API names in the mapping table. This is the most reliable way, because
   the API keeps the relationships consistent.
2. **Specific tools:** create or edit an entity, assign a product or process, add or edit a property set, list entities
   by class, get an element by GlobalId, save or export. Build the entities of the mapping table with them, keeping the
   order.
3. **Read-only tools only:** use them for the checks (steps 1, 2 and 5 of the workflow), and write with
   `scripts/apply_links.py` on a local copy of the file. If the server works on a file the agent cannot reach, say so and
   stop.

## Checklist per step

| Step | Need | Typical tool shape |
| --- | --- | --- |
| Open | the model handle or path | `open_model(path)` / `load_ifc(path)` |
| Look up elements | GlobalId to element | `get_element(global_id)` / `query(class, filter)` |
| Remove the old schedule | find `IfcWorkSchedule` by Name, remove it with its tasks | `list_entities("IfcWorkSchedule")` + `run_api("sequence.remove_work_schedule", ...)` |
| Create entities | add schedule, task, task time, relationships | `run_api(...)` / `create_entity(class, attributes)` |
| Property sets | add or edit `Xray_4D` | `run_api("pset.add_pset"/"pset.edit_pset", ...)` / `set_property(element, pset, name, value)` |
| Save | write to a NEW path | `save_model(path)` / `export(path)` |

## Habits that avoid trouble

- **Batch the calls.** Make one call per task with its elements, not one call per element, when the server allows it;
  thousands of round trips are slow and easy to interrupt.
- **Know whether a failed run left half its changes.** If the server does not undo a failed call, re-run the whole
  apply from the original file rather than patching.
- **Re-read after writing.** Check that one task's assignments come back as expected before doing the rest. Servers
  differ in how they name RelatingProduct and RelatedObjects.
- **Keep the SQL as it is.** The link data is the record; the IFC is a product of it. Never "fix" link rows to match
  what a server could write; report the difference instead.
