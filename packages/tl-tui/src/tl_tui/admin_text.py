"""Plain text for the accounts screen: table cells and the detail panel (P1-I0-T09).

Pure functions of an `AccountView` or `AgentTokenView`, so they are tested without a terminal.
Status is never colour alone: `✓` active, `✗` disabled or revoked, `!` expired, `■` locked.

STUB (P1-I0-T09): the function bodies raise NotImplementedError; the constants and signatures are
final. Each body has a STEPS comment. Implement them, then delete this paragraph, the STEPS
comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tl_core.auth.types import AccountView, AgentTokenView

ACCOUNT_COLUMNS = ("Name", "Kind", "Roles", "Status", "Lock")
TOKEN_COLUMNS = ("Agent", "Label", "Expires", "State", "Id")


def moment(stamp: str) -> str:
    """``2026-10-11T12:15:00.123456Z`` as ``2026-10-11 12:15`` (UTC)."""
    # STEPS: datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    raise NotImplementedError


def status_text(view: AccountView) -> str:
    """``✓ active`` or ``✗ disabled``."""
    # STEPS: by view.status.
    raise NotImplementedError


def lock_text(view: AccountView) -> str:
    """``■ until 2026-10-11 12:15`` while a lockout is in force, else an empty string."""
    # STEPS: view.locked_until is None -> ""; else f"■ until {moment(view.locked_until)}".
    raise NotImplementedError


def account_cells(view: AccountView) -> tuple[str, str, str, str, str]:
    """The five cells of an account row, in the order of `ACCOUNT_COLUMNS`."""
    # STEPS: (username, kind, roles joined with ", ", status_text(view), lock_text(view)).
    raise NotImplementedError


def token_state(token: AgentTokenView, now: str) -> str:
    """``✗ revoked``, ``! expired`` (``expires_at`` is not after ``now``), else ``✓ active``."""
    # STEPS: check revoked first, then expiry. Both stamps are ISO UTC text that sorts as text.
    raise NotImplementedError


def token_cells(
    token: AgentTokenView, names: dict[str, str], now: str
) -> tuple[str, str, str, str, str]:
    """The five cells of a token row, in the order of `TOKEN_COLUMNS` (``?``: unknown agent)."""
    # STEPS: (names.get(token.account_id, "?"), token.label, "never" when expires_at is None
    # else moment(expires_at), token_state(token, now), token.token_id).
    raise NotImplementedError


def detail_lines(view: AccountView, tokens: Sequence[AgentTokenView], now: str) -> list[str]:
    """The panel under the table: one ``Label   value`` line per fact; agents also count tokens."""
    # STEPS
    # 1. Pairs, in this order: Name (username), Shown as (display_name), Kind, Roles (", "
    #    joined), Status (status_text), Lock ("none", or f"■ locked until {moment(...)} UTC"),
    #    Created (moment(view.created_at)).
    # 2. For an agent account add Tokens: of the tokens whose account_id is this account's,
    #    f"{live} live, {revoked} revoked" where live counts token_state == "✓ active" and
    #    revoked counts token.revoked.
    # 3. Each line is f"{label:<10}{value}".
    raise NotImplementedError
