"""The commands the schema registry module offers to the API (brief 11.1, 25.2; P1-I8).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:
``admin`` (action ``admin.command.<Name>``) or ``user`` (any signed-in person). FANOUT D2:
drafting, revising, analysing and submitting a package, and asking for a waiver, are any signed-in
person's (the handlers also bind the first four to the actor that drafted the package); sending a
package back, approving, publishing, deprecating, retiring, adopting a version and approving or
revoking a waiver are the administrator's. An agent never changes a record: its calls are
proposals a person accepts, and a command is closed to agents until ``tl_core.auth.provider``
lists it (none of these is).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage, handle_adopt_schema_package
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DeprecateSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
    RequestSchemaChanges,
    RetireSchemaPackage,
    ReviseSchemaPackage,
    SubmitSchemaPackage,
    handle_analyse_schema_package,
    handle_approve_schema_package,
    handle_deprecate_schema_package,
    handle_draft_schema_package,
    handle_publish_schema_package,
    handle_request_schema_changes,
    handle_retire_schema_package,
    handle_revise_schema_package,
    handle_submit_schema_package,
)
from tl_mod_schemareg.handlers.waivers import (
    ApproveWaiver,
    RequestWaiver,
    RevokeWaiver,
    handle_approve_waiver,
    handle_request_waiver,
    handle_revoke_waiver,
)

Access = Literal["admin", "controller", "user"]  # a typo is a type error, not an open door


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    ApiCommand(DraftSchemaPackage, handle_draft_schema_package, "user"),
    ApiCommand(ReviseSchemaPackage, handle_revise_schema_package, "user"),
    ApiCommand(AnalyseSchemaPackage, handle_analyse_schema_package, "user"),
    ApiCommand(SubmitSchemaPackage, handle_submit_schema_package, "user"),
    ApiCommand(RequestSchemaChanges, handle_request_schema_changes, "admin"),
    ApiCommand(ApproveSchemaPackage, handle_approve_schema_package, "admin"),
    ApiCommand(PublishSchemaPackage, handle_publish_schema_package, "admin"),
    ApiCommand(DeprecateSchemaPackage, handle_deprecate_schema_package, "admin"),
    ApiCommand(RetireSchemaPackage, handle_retire_schema_package, "admin"),
    ApiCommand(AdoptSchemaPackage, handle_adopt_schema_package, "admin"),
    ApiCommand(RequestWaiver, handle_request_waiver, "user"),
    ApiCommand(ApproveWaiver, handle_approve_waiver, "admin"),
    ApiCommand(RevokeWaiver, handle_revoke_waiver, "admin"),
)
