"""Names the schedule module shares: record types, event types, tables, states, slots, relations.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

SCHEDULE: Final = "schedule.Schedule"
SCHEDULE_SNAPSHOT: Final = "schedule.ScheduleSnapshot"
ACTIVITY_REF: Final = "schedule.ActivityRef"
RECORD_TYPES: Final = frozenset({SCHEDULE, SCHEDULE_SNAPSHOT, ACTIVITY_REF})

# Tables of the records (generated from schema/modules/schedule/*.yaml) and their flat views.
SCHEDULE_TABLE: Final = "cur_schedule_schedule"
SNAPSHOT_TABLE: Final = "cur_schedule_schedule_snapshot"
ACTIVITY_REF_TABLE: Final = "cur_schedule_activity_ref"
SCHEDULE_VIEW: Final = "v_schedule_schedule"
SNAPSHOT_VIEW: Final = "v_schedule_schedule_snapshot"
ACTIVITY_REF_VIEW: Final = "v_schedule_activity_ref"

# The operational typed tables of a snapshot (ADR-0015), by the name of the typed table in tl_xer.
CALENDAR_TABLE: Final = "sched_calendar"
WBS_TABLE: Final = "sched_wbs"
ACTIVITY_TABLE: Final = "sched_activity"
RELATIONSHIP_TABLE: Final = "sched_relationship"
CODE_TABLE: Final = "sched_activity_code"
UDF_TABLE: Final = "sched_udf_value"
TYPED_TABLES: Final = {
    "calendars": CALENDAR_TABLE,
    "wbs": WBS_TABLE,
    "activities": ACTIVITY_TABLE,
    "relationships": RELATIONSHIP_TABLE,
    "codes": CODE_TABLE,
    "udfs": UDF_TABLE,
}

# Event types. The *Defined event follows Record.Created in the same append.
SCHEDULE_DEFINED: Final = "Schedule.Defined"
SCHEDULE_SNAPSHOT_PUBLISHED: Final = "Schedule.SnapshotPublished"
SNAPSHOT_DEFINED: Final = "ScheduleSnapshot.Defined"
SNAPSHOT_QUEUED: Final = "ScheduleSnapshot.Queued"
BUILD_STARTED: Final = "ScheduleSnapshot.BuildStarted"
BUILD_FAILED: Final = "ScheduleSnapshot.BuildFailed"
SNAPSHOT_BUILT: Final = "ScheduleSnapshot.Built"
SNAPSHOT_REJECTED: Final = "ScheduleSnapshot.Rejected"
SNAPSHOT_MADE_CURRENT: Final = "ScheduleSnapshot.MadeCurrent"
REF_DEFINED: Final = "ActivityRef.Defined"
REF_PRESENCE: Final = "ActivityRef.PresenceChanged"

# Workflow states of a snapshot (schema/fixtures/workflows/schedule-schedule-snapshot.yaml).
UPLOADED: Final = "Uploaded"
PROCESSING: Final = "Processing"
INVALID: Final = "Invalid"
VALID: Final = "Valid"
PUBLISHED: Final = "Published"
SUPERSEDED: Final = "Superseded"
VOID: Final = "Void"
#: States in which a snapshot's typed rows exist.
BUILT_STATES: Final = (VALID, PUBLISHED, SUPERSEDED)

# File slots of a snapshot: a person attaches ``xer``; the module writes ``report`` and ``raw``.
SLOT_XER: Final = "xer"
SLOT_REPORT: Final = "report"
SLOT_RAW: Final = "raw"

#: The job kind of a snapshot build in the claim queue (ADR-0014): the job id is the snapshot id.
JOB_KIND_BUILD: Final = "schedule.build"

SCHEDULE_TYPES: Final = ("baseline", "current", "look_ahead", "what_if")

#: Relation of the link from a record to the activity it is scheduled by. The vocabulary of links
#: is the thirteen of brief 7.1 (``references`` is the default); the activity is told by the type
#: of the record the link points at (``schedule.ActivityRef``), as a document is.
ACTIVITY_RELATION: Final = "references"
#: The reason the module gives when a publication flags a link; a link flagged with it is restored
#: when the activity comes back, and only such a link.
ORPHAN_REASON: Final = "activity is not in the published snapshot"
