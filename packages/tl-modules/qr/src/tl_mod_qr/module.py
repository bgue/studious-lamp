"""What the QR module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``qr`` names ``spec``. Three commands (issue, revoke,
rotate), each marked for delegation in its row, and the hooks for the module's own routes, tools
and CLI group (all of them in this package).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from tl_mod_qr import MODULE
from tl_mod_qr.commands import IssueScanCode, RevokeScanCode, RotateScanCode
from tl_mod_qr.handlers.scan_code import (
    handle_issue_scan_code,
    handle_revoke_scan_code,
    handle_rotate_scan_code,
)
from tl_mod_qr.names import ISSUE, RECORD_TYPES, REVOKE
from tl_mod_qr.projectors import ScanCodeProjector


@dataclass(frozen=True)
class QrCommand:
    """A command row: the model, its handler, its fine access word and its marks."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str
    meta: dict[str, str] = field(default_factory=dict[str, str])


#: Marks (delegation): a label is a bearer path to site status, so issuing is a person's act
#: (``excluded:access``); revoking is the controller's decision (``excluded:reserved``).
COMMANDS: tuple[QrCommand, ...] = (
    QrCommand(IssueScanCode, handle_issue_scan_code, ISSUE, {"delegation": "excluded:access"}),
    QrCommand(RevokeScanCode, handle_revoke_scan_code, REVOKE, {"delegation": "excluded:reserved"}),
    QrCommand(RotateScanCode, handle_rotate_scan_code, ISSUE, {"delegation": "excluded:access"}),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [ScanCodeProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        command_words={row.model.__name__: row.access for row in COMMANDS},
        proposable=(),
        commands="tl_mod_qr.module:COMMANDS",
        read_routers=("tl_mod_qr.routes:router",),
        tools=("tl_mod_qr.tools:register_tools",),
        cli_groups=("tl_mod_qr.cli:qr_app",),
        reports=("tl_mod_qr.report_rows:REPORTS",),
    )
