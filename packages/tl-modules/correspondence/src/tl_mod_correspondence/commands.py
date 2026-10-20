"""The commands the correspondence module offers to the API (brief 11.1, 25.2; P1-I5).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:

* ``controller``: an admin or a document controller (action ``control.command.<Name>``);
* ``admin``: only an admin (none of this module's commands);
* ``user``: any signed-in person.

The **controlling acts** belong to the document controller role (ADR-0013): issuing a letter,
setting the confidentiality class and naming who may read a privileged item, voiding a received
item, replacing an item, registering parties and clauses, and sweeping the clocks. Everything that
prepares or answers stays open to any signed-in person: receiving, updating, drafting, triaging,
reclassifying before issue, recording an answer, closing, linking, and working a clock.

An agent never changes a record: its call is a proposal a person accepts, and a command is closed
to agents until ``tl_core.auth.provider`` lists it. The one correspondence proposal is the triage
(``propose_triage``, ``ConfirmTriage``). Who may read an item is ADR-0016, not an access word:
a command that names an item the person may not read answers "no such record".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_correspondence.handlers.clauses import (
    DefineClause,
    RetireClause,
    handle_define_clause,
    handle_retire_clause,
)
from tl_mod_correspondence.handlers.clocks import (
    CancelClock,
    MeetClock,
    PauseClock,
    RestartClock,
    ResumeClock,
    StartClock,
    SweepClocks,
    handle_cancel_clock,
    handle_meet_clock,
    handle_pause_clock,
    handle_restart_clock,
    handle_resume_clock,
    handle_start_clock,
    handle_sweep_clocks,
)
from tl_mod_correspondence.handlers.confidentiality import (
    GrantClearance,
    SetCorrespondenceConfidentiality,
    WithdrawClearance,
    handle_grant_clearance,
    handle_set_confidentiality,
    handle_withdraw_clearance,
)
from tl_mod_correspondence.handlers.issue import IssueCorrespondence, handle_issue_correspondence
from tl_mod_correspondence.handlers.items import (
    ReceiveCorrespondence,
    UpdateCorrespondence,
    handle_receive_correspondence,
    handle_update_correspondence,
)
from tl_mod_correspondence.handlers.parties import (
    AddContact,
    EndContact,
    RegisterParty,
    RetireParty,
    handle_add_contact,
    handle_end_contact,
    handle_register_party,
    handle_retire_party,
)
from tl_mod_correspondence.handlers.responses import (
    CloseCorrespondence,
    DraftCorrespondence,
    RecordResponse,
    VoidCorrespondence,
    VoidDraft,
    handle_close_correspondence,
    handle_draft_correspondence,
    handle_record_response,
    handle_void_correspondence,
    handle_void_draft,
)
from tl_mod_correspondence.handlers.threads import (
    AssignThread,
    SupersedeCorrespondence,
    handle_assign_thread,
    handle_supersede_correspondence,
)
from tl_mod_correspondence.handlers.triage import (
    ConfirmTriage,
    ReclassifyCorrespondence,
    handle_confirm_triage,
    handle_reclassify_correspondence,
)

Access = Literal["admin", "controller", "user"]  # a typo is a type error, not an open door


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    # items
    ApiCommand(ReceiveCorrespondence, handle_receive_correspondence, "user"),
    ApiCommand(UpdateCorrespondence, handle_update_correspondence, "user"),
    ApiCommand(DraftCorrespondence, handle_draft_correspondence, "user"),
    ApiCommand(ConfirmTriage, handle_confirm_triage, "user"),
    ApiCommand(ReclassifyCorrespondence, handle_reclassify_correspondence, "user"),
    ApiCommand(IssueCorrespondence, handle_issue_correspondence, "controller"),
    ApiCommand(RecordResponse, handle_record_response, "user"),
    ApiCommand(CloseCorrespondence, handle_close_correspondence, "user"),
    ApiCommand(VoidDraft, handle_void_draft, "user"),
    ApiCommand(VoidCorrespondence, handle_void_correspondence, "controller"),
    ApiCommand(AssignThread, handle_assign_thread, "user"),
    ApiCommand(SupersedeCorrespondence, handle_supersede_correspondence, "controller"),
    # confidentiality (ADR-0016)
    ApiCommand(SetCorrespondenceConfidentiality, handle_set_confidentiality, "controller"),
    ApiCommand(GrantClearance, handle_grant_clearance, "controller"),
    ApiCommand(WithdrawClearance, handle_withdraw_clearance, "controller"),
    # clocks
    ApiCommand(StartClock, handle_start_clock, "user"),
    ApiCommand(PauseClock, handle_pause_clock, "user"),
    ApiCommand(ResumeClock, handle_resume_clock, "user"),
    ApiCommand(RestartClock, handle_restart_clock, "user"),
    ApiCommand(MeetClock, handle_meet_clock, "user"),
    ApiCommand(CancelClock, handle_cancel_clock, "user"),
    ApiCommand(SweepClocks, handle_sweep_clocks, "controller"),
    # parties and clauses
    ApiCommand(RegisterParty, handle_register_party, "controller"),
    ApiCommand(AddContact, handle_add_contact, "controller"),
    ApiCommand(EndContact, handle_end_contact, "controller"),
    ApiCommand(RetireParty, handle_retire_party, "controller"),
    ApiCommand(DefineClause, handle_define_clause, "controller"),
    ApiCommand(RetireClause, handle_retire_clause, "controller"),
)
