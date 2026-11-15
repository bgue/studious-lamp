"""Review commands: accept, return, void (P2-FORMS S3).

A controller accepts or returns a submitted form, never the one they filled themselves
(``MSG_SELF_REVIEW``, whatever their role). A void is the controller's too; it also voids the
envelope (``Record.Voided``) after the ``void`` transition, because a voided record takes no
transition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_forms.errors import MSG_SELF_REVIEW, FormStateError
from tl_mod_forms.handlers.common import (
    Submission,
    append,
    correlated,
    load_submission,
    move,
    require_project,
    require_version,
    silent,
)
from tl_mod_forms.names import (
    ACCEPTED,
    RETURNED,
    SUBMISSION,
    SUBMISSION_ACCEPTED,
    SUBMISSION_RETURNED,
    SUBMISSION_VOIDED,
    SUBMITTED,
    T_ACCEPT,
    T_RETURN,
    T_VOID,
)

if TYPE_CHECKING:
    from tl_mod_forms.commands import AcceptFormSubmission, ReturnFormSubmission, VoidFormSubmission


def _require_state(sub: Submission, command: str, *states: str) -> None:
    if sub.state not in states:
        raise FormStateError(
            f"a form that is {sub.state} does not take {command}; it needs {' or '.join(states)}"
        )


def _review(
    uow: UnitOfWork,
    cmd: Any,
    command: str,
    event_type: str,
    transition: str,
    payload: dict[str, Any],
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    sub = load_submission(uow, cmd, cmd.submission_id, own=False)
    _require_state(sub, command, SUBMITTED)
    if sub.author == cmd.actor:
        raise ForbiddenError(MSG_SELF_REVIEW)
    require_version(uow, sub.id, cmd.expected_version)
    return _step(uow, cmd, sub, event_type, transition, payload)


def _step(
    uow: UnitOfWork,
    cmd: Command,
    sub: Submission,
    event_type: str,
    transition: str,
    payload: dict[str, Any],
) -> CommandResult:
    """Append the module's event, then run the workflow transition (one unit of work)."""
    done = append(
        uow, cmd, sub.id, SUBMISSION, [NewEvent(event_type=event_type, payload=silent(payload))]
    )
    moved = move(uow, cmd, sub.id, transition)
    return CommandResult(
        stream_id=sub.id, key=sub.key, version=moved.version, events=[*done.events, *moved.events]
    )


def handle_accept_form_submission(uow: UnitOfWork, cmd: AcceptFormSubmission) -> CommandResult:
    """Submitted to Accepted, by someone other than the author."""
    return _review(
        uow, cmd, "AcceptFormSubmission", SUBMISSION_ACCEPTED, T_ACCEPT, {"note": cmd.note}
    )


def handle_return_form_submission(uow: UnitOfWork, cmd: ReturnFormSubmission) -> CommandResult:
    """Submitted to Returned, by someone other than the author."""
    return _review(
        uow, cmd, "ReturnFormSubmission", SUBMISSION_RETURNED, T_RETURN, {"note": cmd.note}
    )


def handle_void_form_submission(uow: UnitOfWork, cmd: VoidFormSubmission) -> CommandResult:
    """Submitted, Accepted or Returned to Voided, the final state; the envelope is voided too."""
    require_project(cmd)
    cmd = correlated(cmd)
    sub = load_submission(uow, cmd, cmd.submission_id, own=False)
    _require_state(sub, "VoidFormSubmission", SUBMITTED, ACCEPTED, RETURNED)
    require_version(uow, sub.id, cmd.expected_version)
    stepped = _step(uow, cmd, sub, SUBMISSION_VOIDED, T_VOID, {"reason": cmd.reason})
    voided = append(
        uow,
        cmd,
        sub.id,
        SUBMISSION,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=sub.id,
        key=sub.key,
        version=voided.new_version,
        events=[*stepped.events, *voided.events],
    )


__all__ = [
    "handle_accept_form_submission",
    "handle_return_form_submission",
    "handle_void_form_submission",
]
