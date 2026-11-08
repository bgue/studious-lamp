"""Event intent (ADR-0025): why a command was run, what comes next, what it moves toward.

``intent_json`` is the one function that turns an intent into the text a ledger stores and the
event hash covers. Adapters, the archive and restore call it or read the stored text; none dumps
the model itself.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import Connection

    from tl_core.confidentiality import Viewer


class IntentRef(BaseModel):
    """One next item: ``{command, target}`` or ``{text}``."""

    model_config = ConfigDict(extra="forbid")

    command: str | None = None
    target: str | None = None
    text: str | None = None


class IntentToward(BaseModel):
    """What the work moves toward: a target with a state xor a condition."""

    model_config = ConfigDict(extra="forbid")

    target: str
    state: str | None = None
    condition: str | None = None


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    why: str | None = None
    next: list[IntentRef] = []
    toward: IntentToward | None = None
    goal_ref: str | None = None


class IntentInvalid(ValueError):
    code = "intent_invalid"


def _dump(intent: Intent) -> dict[str, Any]:
    data: dict[str, Any] = intent.model_dump(mode="json", exclude_none=True)
    if not data.get("next"):
        data.pop("next", None)
    else:
        data["next"] = [item for item in data["next"] if item]
        if not data["next"]:
            del data["next"]
    return data


def intent_json(intent: Intent | None) -> str | None:
    """The stored text of an intent; ``None`` for no intent or an empty one (``{}``, all null)."""
    if intent is None:
        return None
    data = _dump(intent)
    if not data:
        return None
    from tl_core.ledger.hashing import canonical_json  # not at top: ledger.types imports us

    return canonical_json(data)


class IntentReferenceUnknown(ValueError):
    """A reference that does not resolve for the actor: unknown, hidden and voided look the same."""

    code = "intent_reference_unknown"
    MESSAGE: Final = "intent reference not found"

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


WHY_MAX: Final = 500
TEXT_MAX: Final = 200
CONDITION_MAX: Final = 200
NEXT_MAX: Final = 5
CANONICAL_MAX_BYTES: Final = 4000
NOT_AVAILABLE: Final = "not available"
_GOAL_REF = re.compile(r"[a-z0-9_-]{1,64}")

#: What a read returns: the stored shape, with a reference the viewer cannot read replaced by
#: ``{"text": "not available"}`` (a next item) or ``target = "not available"`` (toward).
IntentView = Intent

_RECORD_SQL = text(
    "SELECT id, type, scope, voided FROM cur_core_record "
    "WHERE id = :v OR (key = :v AND scope IN (:scope, 'company'))"
)

_REGISTERED: set[str] = set()


def register_command_names(names: Iterable[str]) -> None:
    """The entry point (the API) tells which command names exist beyond the core table."""
    _REGISTERED.update(names)


def _command_names() -> set[str]:
    from tl_core.auth.module_roles import command_index
    from tl_core.services.proposals import command_table

    return {*command_table(), *command_index(), *_REGISTERED}


def _clean(value: str | None, limit: int, what: str) -> None:
    if value is None:
        return
    if len(value) > limit:
        raise IntentInvalid(f"intent {what} is longer than {limit} characters")
    for ch in value:
        if unicodedata.category(ch) == "Cc" and ch not in "\n\t":
            raise IntentInvalid(f"intent {what} holds a control character")


def _resolve(conn: Connection, target: str, scope: str, viewer: Viewer) -> Any:
    """The record row a reference names for ``viewer``; ``IntentReferenceUnknown`` otherwise.

    Hidden, voided, out-of-scope and missing take the same path, ending in one error; the
    visibility lookup runs for every reference, found or not, so the cost does not tell them apart.
    """
    from tl_core import confidentiality

    rows = conn.execute(_RECORD_SQL, {"v": target, "scope": scope}).all()
    row = next((r for r in rows if r.id == target), rows[0] if rows else None)
    hidden = confidentiality.is_hidden(conn, str(row.id) if row is not None else target, viewer)
    if row is None or hidden or row.voided or row.scope not in (scope, "company"):
        raise IntentReferenceUnknown
    return row


def _states(row: Any) -> list[str] | None:
    from tl_core.workflow.provider import get_workflows

    definition = get_workflows().find(row.type, row.scope)
    return None if definition is None else definition.state_names()


def validate_intent(conn: Connection, command: Any, *, viewer: Viewer) -> Intent | None:
    """The checked intent of ``command`` with every reference as a record id; ``{}`` is ``None``.

    Raises ``IntentInvalid`` (a size, a character, a shape, a state, a command name) or
    ``IntentReferenceUnknown`` (one fixed message, whatever the reason).
    """
    intent: Intent | None = getattr(command, "intent", None)
    if intent is None or intent_json(intent) is None:
        return None
    scope: str = command.scope
    _clean(intent.why, WHY_MAX, "why")
    if intent.goal_ref is not None and _GOAL_REF.fullmatch(intent.goal_ref) is None:
        raise IntentInvalid("intent goal_ref must be 1 to 64 of a-z, 0-9, _ and -")
    items = [item for item in intent.next if item.model_dump(exclude_none=True)]
    if len(items) > NEXT_MAX:
        raise IntentInvalid(f"intent next holds more than {NEXT_MAX} items")
    names: set[str] | None = None
    nxt: list[IntentRef] = []
    for item in items:
        _clean(item.text, TEXT_MAX, "next text")
        if item.text is not None:
            if item.command is not None or item.target is not None:
                raise IntentInvalid("an intent next item is a text or a command, not both")
            nxt.append(IntentRef(text=item.text))
            continue
        if item.command is None:
            raise IntentInvalid("an intent next item with a target needs a command")
        names = _command_names() if names is None else names
        if item.command not in names:
            raise IntentInvalid("intent next names a command that does not exist")
        target = None if item.target is None else str(_resolve(conn, item.target, scope, viewer).id)
        nxt.append(IntentRef(command=item.command, target=target))
    toward: IntentToward | None = None
    if intent.toward is not None:
        row = _resolve(conn, intent.toward.target, scope, viewer)
        want = intent.toward
        if (want.state is None) == (want.condition is None):
            raise IntentInvalid("intent toward needs a state or a condition, not both or neither")
        _clean(want.condition, CONDITION_MAX, "toward condition")
        if want.state is not None:
            states = _states(row)
            if states is None or want.state not in states:
                raise IntentInvalid("intent toward state is not a state of the target")
        toward = IntentToward(target=str(row.id), state=want.state, condition=want.condition)
    out = Intent(why=intent.why, next=nxt, toward=toward, goal_ref=intent.goal_ref)
    stored = intent_json(out)
    if stored is None:
        return None
    if len(stored.encode()) > CANONICAL_MAX_BYTES:
        raise IntentInvalid(f"intent is larger than {CANONICAL_MAX_BYTES} bytes")
    return out


def check_intent(command: Any, conn: Connection, viewer: Viewer) -> Any:
    """``command`` with its intent validated and id-resolved (``None`` when empty)."""
    if getattr(command, "intent", None) is None:
        return command
    return command.model_copy(update={"intent": validate_intent(conn, command, viewer=viewer)})


# --- the carrier --------------------------------------------------------------------------------

_INTENT: ContextVar[Intent | None] = ContextVar("tl_intent", default=None)


def current_intent() -> Intent | None:
    """The intent of the innermost ``intent_scope`` block, else ``None``."""
    return _INTENT.get()


@contextmanager
def intent_scope(intent: Intent | None) -> Generator[None]:
    """Events appended inside the block without their own intent carry ``intent`` (like
    ``effective_time``: per thread and task, nested blocks restore, ``None`` clears)."""
    token = _INTENT.set(intent)
    try:
        yield
    finally:
        _INTENT.reset(token)


# --- reads --------------------------------------------------------------------------------------


def _ids(intent: Intent) -> set[str]:
    found = {item.target for item in intent.next if item.target}
    if intent.toward is not None:
        found.add(intent.toward.target)
    return found


def _redacted(intent: Intent, hidden: set[str]) -> Intent:
    nxt = [IntentRef(text=NOT_AVAILABLE) if item.target in hidden else item for item in intent.next]
    toward = intent.toward
    if toward is not None and toward.target in hidden:
        toward = IntentToward(target=NOT_AVAILABLE)
    return intent.model_copy(update={"next": nxt, "toward": toward})


def redact_events[E: BaseModel](
    conn: Connection, events: Sequence[E], viewer: Viewer | None = None
) -> list[E]:
    """``events`` with every unreadable reference of an intent shown as "not available"."""
    from tl_core import confidentiality

    who = viewer if viewer is not None else confidentiality.current_viewer()
    ids: set[str] = set()
    for event in events:
        found: Intent | None = getattr(event, "intent", None)
        if found is not None:
            ids |= _ids(found)
    hidden: set[str] = confidentiality.hidden_among(conn, sorted(ids), who) if ids else set()
    if not hidden:
        return list(events)
    return [
        event.model_copy(update={"intent": _redacted(found, hidden)})
        if (found := getattr(event, "intent", None)) is not None
        else event
        for event in events
    ]


def redact_intent(conn: Connection, intent: Intent | None, viewer: Viewer) -> IntentView | None:
    """``intent`` as ``viewer`` may read it: a reference they cannot read is "not available"."""
    from tl_core import confidentiality

    if intent is None:
        return None
    ids = _ids(intent)
    hidden: set[str] = confidentiality.hidden_among(conn, sorted(ids), viewer) if ids else set()
    return _redacted(intent, hidden) if hidden else intent
