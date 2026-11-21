---
name: ifc-4d-schedule
description: Write schedule activities and their element links into an IFC model (IfcWorkSchedule, IfcTask with dates, task-to-element assignments, logic links, and the Xray_4D property set), from X-ray 4D linking data (a LinkML LinkDataset JSON from `xray-4d link` or the viewer's 4D tab, or rows from the generated SQL tables). Use when asked to put a P6 / XER schedule, 4D links, activity IDs, or location / trade assignments into an IFC file, through an IFC MCP server when one is connected or with IfcOpenShell locally.
---

# Write 4D schedule links into an IFC

The goal: an IFC that carries its own construction schedule, so any 4D tool (and the X-ray viewer on reload) sees which
activity builds or removes each element and when. Inputs are already-reviewed links; this skill does not decide links.

## Inputs

1. **The IFC model**: a file path, or a model already open in the IFC MCP server.
2. **Linking data** in the X-ray 4D LinkML form (`schema/linkml/xray_4d.yaml` in the xray-ref repo), from one of these:
   - `links.json`: a `LinkDataset` written by `xray-4d link`, or exported from the viewer's 4D tab.
   - SQL tables generated from the schema (`Activity`, `ActivityLink`, `ActivityLink_elements`, `Assignment`). Queries
     are in [reference/sql.md](reference/sql.md).
3. **Optional:** the `.xer` file, used only for logic links (predecessors), which the link data does not hold.

**Only rows with `status: accepted` are written.** Proposed, rejected and superseded rows are reported as skipped.
Never write `reviewed_by` (personal data) into the IFC.

## Workflow

1. **Check the inputs.**
   - Load the dataset. Confirm `model.file_name` / `model.identity_key` matches the IFC you were given; if not, stop and ask.
   - Count accepted build and remove links, the activities they use, and assignments.
2. **Check the model.**
   - Look up every linked GlobalId. Through MCP, use its query or element-by-GlobalId tool; locally,
     `scripts/apply_links.py --dry-run` does the lookup.
   - List the GlobalIds that are missing from the model. Continue only if the user agrees to skip them.
   - Note the IFC schema. IFC4 and IFC4X3 get everything. IFC2X3 has no `IfcTaskTime`, so tasks and assignments are
     written but dates are not; say so.
3. **Plan the change and say what will happen before writing:**
   - one `IfcWorkSchedule` named `Xray 4D` (an existing one with that name is replaced, nothing else is touched);
   - N `IfcTask`s with dates;
   - M build assignments and K remove assignments;
   - L logic links;
   - `Xray_4D` on E elements.

   Ask before replacing an existing `Xray 4D` schedule if the user has not already said to.
4. **Write**, always to a new file. Never overwrite the input unless the user asks.
   - **With an IFC MCP server:** follow [reference/mcp-tools.md](reference/mcp-tools.md) to find the tools that fit
     and make the calls in the order of [reference/ifc-mapping.md](reference/ifc-mapping.md).
   - **Without one, or when the MCP can only read:** run the bundled script on a copy:
     ```bash
     python scripts/apply_links.py --ifc model.ifc --links links.json [--xer schedule.xer] -o model.4d.ifc
     ```
     It needs `ifcopenshell` (0.8.x).
5. **Verify** with `python scripts/verify.py --ifc model.4d.ifc --links links.json`, or the same checks through MCP
   queries. It checks:
   - every accepted link is in the file with the right role;
   - every task has its dates (IFC4 and later);
   - every `Xray_4D.ActivityIds` value matches the links.

   A failed check means the write is not done: fix it and run the check again.
6. **Report:** counts written, items skipped and why, the output path, and the verify result. If the link data came from
   SQL, offer to record the output file's SHA-256 against the dataset so later runs can tell which file carries which
   links.

## Rules

- **Idempotent:** running twice gives the same result. The `Xray 4D` schedule and its tasks are rebuilt each time, and
  `Xray_4D` property values are overwritten, not duplicated.
- **Leave the rest alone:** never delete or change other schedules, tasks, property sets or geometry.
- **Keys:** activities are keyed by P6 Activity ID (`IfcTask.Identification`), elements by GlobalId. Do not match by name.
- **Milestones:** they become tasks with `IsMilestone = TRUE` and no elements.
- **Activities without elements:** plaster, services and drying become tasks only if `--all-activities` is given or the
  user asks. Otherwise only linked activities and milestones are written.
