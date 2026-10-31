"""Plain text for the accounts screen: table cells and the detail panel (P1-I0-T09).

Pure functions of an `AccountView` or `AgentTokenView`, so they are tested without a terminal.
Status is never colour alone: `✓` active, `✗` disabled or revoked, `!` expired, `■` locked.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tl_core.auth.module_role_views import EffectiveRoleView, ModuleRoleGrantView
from tl_core.auth.types import AccountView, AgentTokenView

from tl_tui.display import humanize
from tl_tui.layout import Page, Prop, Section, state_line

ACCOUNT_COLUMNS = ("Name", "Kind", "Roles", "Status", "Lock")
TOKEN_COLUMNS = ("Agent", "Label", "Expires", "State")
TECHNICAL_TOKEN_COLUMNS = (*TOKEN_COLUMNS, "Id")
MODULE_ROLE_COLUMNS = ("Account", "Module", "Role", "Granted by", "Since")
TECHNICAL_MODULE_ROLE_COLUMNS = (*MODULE_ROLE_COLUMNS, "Id")
ALL_MODULES = "*"


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


# --- module roles (RM-S3): the module roles log -----------------------------------------------

#: The resolver's source words (``Source``) in plain language, for a property line.
SOURCE_WORDS = {
    "granted": "granted",
    "granted_all_modules": "granted, all modules",
    "derived": "derived",
    "admin": "admin",
    "service": "service",
    "none": "none",
}


def module_label(module: str) -> str:
    """``documents`` as ``Documents``; ``*`` as ``All modules``."""
    return "All modules" if module == ALL_MODULES else humanize(module)


def person_label(actor: str, names: dict[str, str]) -> str:
    """Who an actor is: the account's shown name, else the part after ``user:`` (never an id)."""
    name = actor.partition(":")[2] or actor
    return names.get(name, name)


def grant_cells(
    grant: ModuleRoleGrantView,
    names: dict[str, str],
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of a grant row, in the order of ``MODULE_ROLE_COLUMNS``.

    ``names`` maps a username to the name shown for it. The account id is a sixth cell, shown only
    in technical mode (``TECHNICAL_MODULE_ROLE_COLUMNS``).
    """
    cells = (
        names.get(grant.username, grant.username),
        module_label(grant.module),
        grant.role.capitalize(),
        person_label(grant.granted_by, names),
        moment(grant.granted_at),
    )
    return (*cells, grant.account_id) if technical else cells


def role_state(views: Sequence[EffectiveRoleView]) -> str:
    """``Admin``, ``Granted``, ``Derived`` or ``No roles``: where the account's roles come from."""
    sources = {view.source for view in views if view.roles}
    if "admin" in sources:
        return "Admin"
    if sources & {"granted", "granted_all_modules"}:
        return "Granted"
    if "derived" in sources:
        return "Derived"
    return "No roles"


def effective_line(view: EffectiveRoleView) -> str:
    """``superuser (granted)`` or ``none``: the value of one module's property line."""
    if not view.roles:
        return "none"
    return f"{', '.join(view.roles)} ({SOURCE_WORDS.get(view.source, view.source)})"


def effective_page(display_name: str, views: Sequence[EffectiveRoleView]) -> Page:
    """The panel of a grant row: the account's name, where its roles come from, and one property
    line per module under **Effective roles**."""
    return Page(
        identity=display_name,
        state=state_line(role_state(views)),
        sections=(
            Section(
                "Effective roles",
                tuple(Prop(module_label(v.module), effective_line(v)) for v in views),
                note="No modules.",
            ),
        ),
    )
