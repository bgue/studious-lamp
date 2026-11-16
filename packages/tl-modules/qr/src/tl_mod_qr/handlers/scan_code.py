"""The three scan code handlers: each is the service minus the returned code."""

from __future__ import annotations

from tl_core.services.commands import CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_qr import service
from tl_mod_qr.commands import IssueScanCode, RevokeScanCode, RotateScanCode


def handle_issue_scan_code(uow: UnitOfWork, cmd: IssueScanCode) -> CommandResult:
    """Issue a code nobody sees (the secret is dropped here; the CLI and the web form call
    ``service.issue`` and show it once)."""
    return service.issue(uow, cmd).result


def handle_revoke_scan_code(uow: UnitOfWork, cmd: RevokeScanCode) -> CommandResult:
    return service.revoke(uow, cmd)


def handle_rotate_scan_code(uow: UnitOfWork, cmd: RotateScanCode) -> CommandResult:
    """Rotate; the new code is dropped here (``service.rotate`` returns it to its caller)."""
    return service.rotate(uow, cmd).result
