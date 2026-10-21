"""Plain text for the accounts screen: table cells and the detail panel (P1-I0-T09).

Pure functions of an `AccountView` or `AgentTokenView`, so they are tested without a terminal.
Status is never colour alone: `✓` active, `✗` disabled or revoked, `!` expired, `■` locked.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tl_core.auth.types import AccountView, AgentTokenView

ACCOUNT_COLUMNS = ("Name", "Kind", "Roles", "Status", "Lock")
TOKEN_COLUMNS = ("Agent", "Label", "Expires", "State")
TECHNICAL_TOKEN_COLUMNS = (*TOKEN_COLUMNS, "Id")


def moment(stamp: str) -> str:
    """``2026-10-11T12:15:00.123456Z`` as ``2026-10-11 12:15`` (UTC)."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")


def status_text(view: AccountView) -> str:
    """``✓ active`` or ``✗ disabled``."""
    return "✗ disabled" if view.status == "disabled" else "✓ active"


def lock_text(view: AccountView) -> str:
    """``■ until 2026-10-11 12:15`` while a lockout is in force, else an empty string."""
    if view.locked_until is None:
        return ""
    return f"■ until {moment(view.locked_until)}"


def account_cells(view: AccountView) -> tuple[str, str, str, str, str]:
    """The five cells of an account row, in the order of `ACCOUNT_COLUMNS`."""
    return (
        view.username,
        view.kind,
        ", ".join(view.roles),
        status_text(view),
        lock_text(view),
    )


def token_state(token: AgentTokenView, now: str) -> str:
    """``✗ revoked``, ``! expired`` (``expires_at`` is not after ``now``), else ``✓ active``."""
    if token.revoked:
        return "✗ revoked"
    if token.expires_at is not None and token.expires_at <= now:
        return "! expired"
    return "✓ active"


def token_cells(
    token: AgentTokenView, names: dict[str, str], now: str, *, technical: bool = False
) -> tuple[str, ...]:
    """The cells of a token row, in the order of `TOKEN_COLUMNS` (``?``: unknown agent).

    The token id is a fifth cell, shown only in technical mode (`TECHNICAL_TOKEN_COLUMNS`).
    """
    expires = "never" if token.expires_at is None else moment(token.expires_at)
    cells = (
        names.get(token.account_id, "?"),
        token.label,
        expires,
        token_state(token, now),
    )
    return (*cells, token.token_id) if technical else cells


def detail_lines(view: AccountView, tokens: Sequence[AgentTokenView], now: str) -> list[str]:
    """The panel under the table: one ``Label   value`` line per fact; agents also count tokens."""
    lock = (
        "none" if view.locked_until is None else f"■ locked until {moment(view.locked_until)} UTC"
    )
    pairs: list[tuple[str, str]] = [
        ("Name", view.username),
        ("Shown as", view.display_name),
        ("Kind", view.kind),
        ("Roles", ", ".join(view.roles)),
        ("Status", status_text(view)),
        ("Lock", lock),
        ("Created", moment(view.created_at)),
    ]
    if view.kind == "agent":
        mine = [token for token in tokens if token.account_id == view.account_id]
        live = sum(1 for token in mine if token_state(token, now) == "✓ active")
        revoked = sum(1 for token in mine if token.revoked)
        pairs.append(("Tokens", f"{live} live, {revoked} revoked"))
    return [f"{label:<10}{value}" for label, value in pairs]
