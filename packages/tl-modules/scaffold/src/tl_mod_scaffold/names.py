"""Names the scaffold module shares: record types, events, tables, workflow, states, words.

Plain constants, so a projector, a command, a job and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

SCAFFOLD: Final = "scaffold.Scaffold"
INSPECTION: Final = "scaffold.ScaffoldInspection"
RECORD_TYPES: Final = frozenset({SCAFFOLD, INSPECTION})

SCAFFOLD_TABLE: Final = "cur_scaffold_scaffold"
SCAFFOLD_VIEW: Final = "v_scaffold_scaffold"
INSPECTION_TABLE: Final = "cur_scaffold_scaffold_inspection"
INSPECTION_VIEW: Final = "v_scaffold_scaffold_inspection"

#: The requisitions record type a scaffold is registered from, and its state names.
REQUEST_TYPE: Final = "requisitions.ScaffoldRequest"
REQUEST_TABLE: Final = "cur_requisitions_scaffold_request"
REQUEST_STATES: Final = ("Requested", "Approved", "Scheduled", "In progress", "Done", "Closed")
#: Request states that allow a scaffold (approved or later; not Requested, Rejected, Cancelled).
REQUEST_REGISTERABLE: Final = frozenset({"Approved", "Scheduled", "In progress", "Done", "Closed"})
IWP_TYPE: Final = "awp.IWP"
IWP_INITIAL: Final = "Draft"
REQUIRES: Final = "requires"

REGISTERED: Final = "Scaffold.Registered"
DESIGNED: Final = "Scaffold.Designed"
ERECTING: Final = "Scaffold.Erecting"
INSPECTED: Final = "Scaffold.Inspected"
RELEASED: Final = "Scaffold.Released"
MODIFIED: Final = "Scaffold.Modified"
DISMANTLE_STARTED: Final = "Scaffold.DismantleStarted"
REMOVED_EVENT: Final = "Scaffold.Removed"
INSPECTION_DUE: Final = "Scaffold.InspectionDue"
SCAFFOLD_EVENTS: Final = frozenset(
    {
        REGISTERED,
        DESIGNED,
        ERECTING,
        INSPECTED,
        RELEASED,
        MODIFIED,
        DISMANTLE_STARTED,
        REMOVED_EVENT,
        INSPECTION_DUE,
    }
)

#: Workflow states (``schema/fixtures/workflows/scaffold-scaffold.yaml``).
REQUESTED: Final = "Requested"
DESIGNED_STATE: Final = "Designed"
ERECTING_STATE: Final = "Erecting"
INSPECTED_STATE: Final = "Inspected"
IN_USE: Final = "In Use"
MODIFY: Final = "Modify"
DISMANTLE: Final = "Dismantle"
REMOVED: Final = "Removed"

#: Workflow transitions.
T_DESIGN: Final = "design"
T_ERECT: Final = "erect"
T_PASS: Final = "pass"
T_RELEASE: Final = "release"
T_MODIFY: Final = "modify"
T_DISMANTLE: Final = "dismantle"
T_REMOVE: Final = "remove"

#: Tag colours and inspection results.
GREEN: Final = "green"
YELLOW: Final = "yellow"
RED: Final = "red"
PASS: Final = "pass"
CONDITIONAL: Final = "conditional"
FAIL: Final = "fail"

#: Fine access words (``schema/settings/access-words.yaml``).
VIEW: Final = "scaffold.view"
REGISTER: Final = "scaffold.register"
DESIGN: Final = "scaffold.design"
ERECT: Final = "scaffold.erect"
INSPECT: Final = "scaffold.inspect"
TAG_GREEN: Final = "scaffold.tag.green"
RELEASE: Final = "scaffold.release"
MODIFY_WORD: Final = "scaffold.modify"
DISMANTLE_WORD: Final = "scaffold.dismantle"
REMOVE: Final = "scaffold.remove"

#: The link from a scaffold to the request it was registered from.
BELONGS_TO: Final = "belongs_to"
RULE_LINK_SOURCE: Final = "rule"
FEED_NONE: Final = "none"

#: The setting the inspection interval comes from, and the job.
INTERVAL_SETTING: Final = "scaffold.inspection.interval_days"
JOB_KIND: Final = "scaffold.inspections_due"
JOB_PREFIX: Final = "inspdue:"
JOB_SOURCE: Final = f"job:{JOB_KIND}"
JOB_ACTOR: Final = f"svc:{JOB_KIND}"
