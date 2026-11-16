"""The permits module spec: three record types, their projectors, sixteen commands and the hooks.

Every hook ref names this package only (``tl_core.modules``; P2-X4). Marks live in the row's
``meta``: permits, isolations and gas tests are safety acts, so all sixteen commands are
``excluded:reserved`` (a policy that auto-accepts a permit request is an owner decision;
``RequestPermit`` has its agent row below and flipping it is a one-line ``meta`` change). The other
fifteen are in ``tests/tools/proposable_exclusions.toml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tl_core.modules import ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from tl_mod_permits import MODULE
from tl_mod_permits.commands import (
    ApprovePermit,
    CancelPermit,
    ClosePermit,
    HandBackPermit,
    IssuePermit,
    RejectPermit,
    RequestPermit,
    ResumePermit,
    RevalidatePermit,
    SuspendPermit,
)
from tl_mod_permits.handlers.gas_test import handle_record_gas_test
from tl_mod_permits.handlers.isolation import (
    handle_apply_isolation,
    handle_link_isolation,
    handle_remove_isolation,
    handle_unlink_isolation,
    handle_verify_isolation,
)
from tl_mod_permits.handlers.permit import (
    handle_approve_permit,
    handle_cancel_permit,
    handle_close_permit,
    handle_hand_back_permit,
    handle_issue_permit,
    handle_reject_permit,
    handle_request_permit,
    handle_resume_permit,
    handle_revalidate_permit,
    handle_suspend_permit,
)
from tl_mod_permits.iso_commands import (
    ApplyIsolation,
    LinkIsolation,
    RecordGasTest,
    RemoveIsolation,
    UnlinkIsolation,
    VerifyIsolation,
)
from tl_mod_permits.names import (
    APPROVE,
    CLOSE,
    GASTEST_RECORD,
    HANDBACK,
    ISOLATION_APPLY,
    ISOLATION_VERIFY,
    ISSUE,
    RECORD_TYPES,
    REQUEST,
    RESUME,
    REVALIDATE,
    SUSPEND,
)
from tl_mod_permits.projectors import GasTestProjector, IsolationProjector, PermitProjector


@dataclass(frozen=True)
class PermitCommand:
    """A command row: the model, its handler, its fine access word and its marks."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str
    meta: dict[str, str] = field(default_factory=dict[str, str])


_RESERVED = {"delegation": "excluded:reserved"}

COMMANDS: tuple[PermitCommand, ...] = (
    PermitCommand(RequestPermit, handle_request_permit, REQUEST, _RESERVED),
    PermitCommand(ApprovePermit, handle_approve_permit, APPROVE, _RESERVED),
    PermitCommand(RejectPermit, handle_reject_permit, APPROVE, _RESERVED),
    PermitCommand(IssuePermit, handle_issue_permit, ISSUE, _RESERVED),
    PermitCommand(RevalidatePermit, handle_revalidate_permit, REVALIDATE, _RESERVED),
    PermitCommand(SuspendPermit, handle_suspend_permit, SUSPEND, _RESERVED),
    PermitCommand(ResumePermit, handle_resume_permit, RESUME, _RESERVED),
    PermitCommand(HandBackPermit, handle_hand_back_permit, HANDBACK, _RESERVED),
    PermitCommand(ClosePermit, handle_close_permit, CLOSE, _RESERVED),
    PermitCommand(CancelPermit, handle_cancel_permit, CLOSE, _RESERVED),
    PermitCommand(ApplyIsolation, handle_apply_isolation, ISOLATION_APPLY, _RESERVED),
    PermitCommand(VerifyIsolation, handle_verify_isolation, ISOLATION_VERIFY, _RESERVED),
    PermitCommand(RemoveIsolation, handle_remove_isolation, ISOLATION_APPLY, _RESERVED),
    PermitCommand(LinkIsolation, handle_link_isolation, ISOLATION_APPLY, _RESERVED),
    PermitCommand(UnlinkIsolation, handle_unlink_isolation, ISOLATION_APPLY, _RESERVED),
    PermitCommand(RecordGasTest, handle_record_gas_test, GASTEST_RECORD, _RESERVED),
)

#: What an agent may propose: a permit request a person accepts (still ``excluded:reserved``).
PROPOSABLE = (ProposableCommand("propose_permit", RequestPermit, handle_request_permit, "user"),)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [PermitProjector(), IsolationProjector(), GasTestProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        proposable=PROPOSABLE,
        command_words={c.model.__name__: c.access for c in COMMANDS},
        commands="tl_mod_permits.module:COMMANDS",
        read_routers=("tl_mod_permits.routes:router",),
        tools=("tl_mod_permits.tools:register_tools",),
        cli_groups=(
            "tl_mod_permits.cli:permit_app",
            "tl_mod_permits.cli:isolation_app",
            "tl_mod_permits.cli:gastest_app",
        ),
    )
