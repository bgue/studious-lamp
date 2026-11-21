# IFC mapping: link data to IFC entities

The same mapping is used by the X-ray viewer and the `xray-4d` CLI, so a file written by any of the three reads the same.
IfcOpenShell API names are given for each step; an IFC MCP server built on IfcOpenShell usually exposes these calls, or the
entities can be created directly.

## Entities

| Data | IFC4 / IFC4X3 | IfcOpenShell API |
| --- | --- | --- |
| The schedule | `IfcWorkSchedule` Name `Xray 4D`, PredefinedType `PLANNED` (or `ACTUAL` for an actual-dates dataset), CreationDate now | `sequence.add_work_schedule(name=..., predefined_type=...)` |
| An activity | `IfcTask`: Identification = Activity ID (task_code), Name = activity name, Description = WBS path, IsMilestone, PredefinedType `CONSTRUCTION` (build links), `DEMOLITION` (remove links), `NOTDEFINED` (no elements) | `sequence.add_task(work_schedule=ws, identification=..., name=..., predefined_type=...)`, `sequence.edit_task(task, attributes={"IsMilestone": True})` |
| Its dates | `IfcTaskTime` on the task: ScheduleStart, ScheduleFinish (the dataset's activity start / finish), plus ActualStart / ActualFinish when the activity is complete and the dataset is an actual view; DurationType `WORKTIME` | `sequence.add_task_time(task)`, `sequence.edit_task_time(task_time, attributes={...})` |
| Elements an activity **builds** (its outputs) | `IfcRelAssignsToProduct`: RelatingProduct = the element, RelatedObjects = [the task] | `sequence.assign_product(relating_product=element, related_object=task)` |
| Elements an activity **removes** (its inputs) | `IfcRelAssignsToProcess`: RelatingProcess = the task, RelatedObjects = [the elements] | `sequence.assign_process(relating_process=task, related_object=element)` |
| Logic link (from the XER) | `IfcRelSequence`: RelatingProcess = predecessor task, RelatedProcess = successor, SequenceType `FINISH_START` / `START_START` / `FINISH_FINISH` / `START_FINISH`, TimeLag = `IfcLagTime` (P*n*D, WORKTIME) | `sequence.assign_sequence(relating_process=pred, related_process=succ)`, `sequence.edit_sequence(rel, attributes={"SequenceType": ...})`, `sequence.assign_lag_time(rel, lag_value="P3D", duration_type="WORKTIME")` |
| Location / trade / zone and activity IDs | Property set `Xray_4D` on the element: `Location`, `Trade`, `Zone` (IfcLabel, from accepted assignments) and `ActivityIds` (IfcText, comma-separated Activity IDs of the accepted build links) | `pset.add_pset(product=element, name="Xray_4D")`, `pset.edit_pset(pset, properties={...})` |

Reading back (the viewer and `xray-4d link` do this):
- `IfcRelAssignsToProduct` from an element to a task means a build link.
- `IfcRelAssignsToProcess` from a CONSTRUCTION task means a build link, because some tools export it that way; from a
  DEMOLITION or DISMANTLE task it means a remove link.
- Both come back as `native` links with confidence 1.

## Order

1. Remove an existing `IfcWorkSchedule` named `Xray 4D` with its tasks (`sequence.remove_work_schedule`). Nothing else.
2. Add the schedule.
3. Add the tasks, then their task times.
4. Add the element assignments.
5. Add the sequences, only between tasks written in step 3.
6. Write `Xray_4D` on the elements: edit the existing set if there is one, else add it.

## IFC2X3

There is no `IfcTaskTime`. Write the work schedule, the tasks and the assignments; skip dates (IFC2X3's
`IfcScheduleTimeControl` + `IfcRelAssignsTasks` is a different model and is not written), and say so in the report.

## Dates

Dataset dates are P6 local times without a zone (`2027-03-15T08:00`). IFC `IfcDateTime` takes the same form;
`2027-03-15T08:00:00` is fine. Do not add a zone.
