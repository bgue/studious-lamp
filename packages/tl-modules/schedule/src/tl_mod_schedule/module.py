"""What the schedule module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``schedule`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector

from tl_mod_schedule import MODULE
from tl_mod_schedule.guards import snapshot_upload
from tl_mod_schedule.handlers.publish import (
    PublishScheduleSnapshot,
    handle_publish_schedule_snapshot,
)
from tl_mod_schedule.names import ACTIVITY_REF, RECORD_TYPES, SCHEDULE, SCHEDULE_SNAPSHOT
from tl_mod_schedule.projectors import (
    ActivityRefProjector,
    ScheduleProjector,
    ScheduleTables,
    SnapshotProjector,
)

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A schedule takes links (to a contract, a calendar of record, a document). A snapshot takes links
#: and the person's XER file in the slot ``xer`` (``snapshot_upload`` guards state and slot);
#: its state moves only through the module's commands. An activity reference takes nothing: links
#: *to* it are made with ``LinkActivity``, and nothing starts at it.
SCHEDULE_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE
SNAPSHOT_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE

#: What an agent may propose (ADR-0015). Accepting runs the command as the accepting person, who
#: needs the access written here: publishing a snapshot is the document controller's.
PROPOSABLE = (
    ProposableCommand(
        "propose_publish_schedule_snapshot",
        PublishScheduleSnapshot,
        handle_publish_schedule_snapshot,
        "controller",
    ),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [ScheduleProjector(), SnapshotProjector(), ActivityRefProjector(), ScheduleTables()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            SCHEDULE: SCHEDULE_GENERIC_COMMANDS,
            SCHEDULE_SNAPSHOT: SNAPSHOT_GENERIC_COMMANDS,
            ACTIVITY_REF: frozenset(),
        },
        generic_guards={(SCHEDULE_SNAPSHOT, "AttachFile"): snapshot_upload},
        proposable=PROPOSABLE,
    )
