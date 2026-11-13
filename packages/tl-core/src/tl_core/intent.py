"""Event intent (ADR-0025): why a command was run, what comes next, what it moves toward.

``intent_json`` is the one function that turns an intent into the text a ledger stores and the
event hash covers. Adapters, the archive and restore call it or read the stored text; none dumps
the model itself.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Generator, Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Final, cast

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

    def __init__(self, *_: object) -> None:  # the text is fixed: whatever is passed is dropped
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
    "WHERE id = :v OR (key = :v AND scope IN (:scope, 'company')) "
    "ORDER BY (scope = 'company')"  # a key in both the command scope and company: the scope row
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
        category = unicodedata.category(ch)  # Cf: bidi controls, zero-width characters
        if (category == "Cc" and ch not in "\n\t") or category == "Cf":
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


def intent_ids(intent: Intent) -> set[str]:
    found = {item.target for item in intent.next if item.target}
    if intent.toward is not None:
        found.add(intent.toward.target)
    return found


def redact_intent_ids(intent: Intent, hidden: set[str]) -> Intent:
    nxt = [IntentRef(text=NOT_AVAILABLE) if item.target in hidden else item for item in intent.next]
    toward = intent.toward
    if toward is not None and toward.target in hidden:
        toward = IntentToward(target=NOT_AVAILABLE)
    return intent.model_copy(update={"next": nxt, "toward": toward})


#: Payload fields that name a record the viewer may not read, by stream type and event type:
#: ``(id fields to look up, fields shown as null when any of them is hidden)``. A hidden target
#: reads as a constraint raised with no target (the no-target twin of the constraint read,
#: ADR-0024 F7). A stream type listed here is not a scanned one: the stream stays visible.
#: An entry whose second part is empty nulls each hidden id field by itself (and a field of the
#: first part is a path: ``a[].b`` is ``b`` of each item of the list ``a``; a hidden id inside a
#: list is dropped from it). No event changes: the stored payload is the same, only the read.
_RequisitionRefs = dict[str, tuple[tuple[str, ...], tuple[str, ...]]]
_REQUISITION_RAISED: Final[_RequisitionRefs] = {
    "Requisition.Raised": (("for_record_id",), ()),
    "Requisition.Approved": (("work_order_id",), ()),
}
_WORK_ORDER_REQUISITION: Final = (("requisition_id",), ())
PAYLOAD_REFS: Final[dict[str, dict[str, tuple[tuple[str, ...], tuple[str, ...]]]]] = {
    "core.Constraint": {
        "Constraint.Raised": (
            ("target_id",),
            ("target_kind", "target_id", "target_ref_type", "target_ref_text"),
        ),
        "Constraint.Cleared": (("resolved_by",), ("resolved_by",)),
    },
    "awp.IWP": {
        "IWP.ReadinessEvaluated": (("checks[].resolve_via",), ()),
        "IWP.DocumentPinned": (("document_id", "revision_id"), ()),
        "IWP.ScopeAdded": (("record_id",), ()),
        "IWP.ScopeRemoved": (("record_id",), ()),
    },
    "materials.StockLot": {"StockLot.Moved": (("iwp_id", "requisition_id"), ())},
    "materials.MTO": {"MTO.Defined": (("derived_document_id", "revision_id"), ())},
    "materials.MTOLine": {"MTOLine.Assigned": (("work_package_id",), ())},
    "requisitions.LaborRequisition": _REQUISITION_RAISED,
    "requisitions.MaterialRequisition": _REQUISITION_RAISED,
    "requisitions.GeneralRequisition": _REQUISITION_RAISED,
    "requisitions.ScaffoldRequest": _REQUISITION_RAISED,
    "requisitions.WorkOrder": {
        event: _WORK_ORDER_REQUISITION
        for event in (
            "WorkOrder.Opened",
            "WorkOrder.Scheduled",
            "WorkOrder.Assigned",
            "WorkOrder.Started",
            "WorkOrder.Completed",
            "WorkOrder.Closed",
        )
    },
}


def _path_ids(data: Any, parts: Sequence[str]) -> Iterator[str]:
    """The ids at ``parts`` (``name`` or ``name[]``) below ``data``: a string, or a list of them."""
    if not parts:
        if isinstance(data, str):
            yield data
        elif isinstance(data, list):
            for item in cast("list[Any]", data):
                if isinstance(item, str):
                    yield item
        return
    if not isinstance(data, dict):
        return
    name = parts[0]
    each = name.endswith("[]")
    value = cast("dict[str, Any]", data).get(name.removesuffix("[]"))
    if each and isinstance(value, list):
        for item in cast("list[Any]", value):
            yield from _path_ids(item, parts[1:])
    elif not each and value is not None:
        yield from _path_ids(value, parts[1:])


def _with(source: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    changed: dict[str, Any] = {**source}
    changed[key] = value
    return changed


def _path_without(data: Any, parts: Sequence[str], hidden: set[str]) -> Any:
    """``data`` with each hidden id at ``parts`` null (a string) or dropped (inside a list)."""
    original: Any = data
    if not parts or not isinstance(original, dict):
        return original
    name = parts[0]
    key = name.removesuffix("[]")
    source = cast("dict[str, Any]", original)
    if key not in source:
        return source
    value = source[key]
    if name.endswith("[]"):
        if not isinstance(value, list):
            return source
        items = [_path_without(item, parts[1:], hidden) for item in cast("list[Any]", value)]
        return _with(source, key, items)
    if len(parts) > 1:
        return _with(source, key, _path_without(value, parts[1:], hidden))
    if isinstance(value, list):
        kept = [v for v in cast("list[Any]", value) if not (isinstance(v, str) and v in hidden)]
        return _with(source, key, kept)
    if isinstance(value, str) and value in hidden:
        return _with(source, key, None)
    return source


def payload_ref_ids(stream_type: str, event_type: str, payload: Any) -> set[str]:
    """The record ids in ``payload`` that ``PAYLOAD_REFS`` says may be hidden from a viewer."""
    rule = PAYLOAD_REFS.get(stream_type, {}).get(event_type)
    if rule is None or not isinstance(payload, dict):
        return set()
    return {i for f in rule[0] for i in _path_ids(payload, f.split("."))}


def redacted_payload(stream_type: str, event_type: str, payload: Any, hidden: set[str]) -> Any:
    """``payload`` with the fields of a hidden reference set to null (the same keys stay)."""
    rule = PAYLOAD_REFS.get(stream_type, {}).get(event_type)
    if rule is None or not payload_ref_ids(stream_type, event_type, payload) & hidden:
        return payload
    if rule[1]:
        shown: dict[str, Any] = {**cast("dict[str, Any]", payload)}
        shown.update({f: None for f in rule[1]})
        return shown
    result: Any = payload
    for f in rule[0]:
        result = _path_without(result, f.split("."), hidden)
    return result


def redact_for_viewer[E: BaseModel](
    conn: Connection, events: Sequence[E], viewer: Viewer | None = None
) -> list[E]:
    """``events`` as the viewer may read them: every unreadable reference of an intent is "not
    available" and the payload fields that name a hidden record (``PAYLOAD_REFS``) are null.

    Apply it after ``filter_events``, wherever events leave the core for a reader."""
    from tl_core import confidentiality

    who = viewer if viewer is not None else confidentiality.current_viewer()
    ids: set[str] = set()
    for event in events:
        found: Intent | None = getattr(event, "intent", None)
        if found is not None:
            ids |= intent_ids(found)
        ids |= payload_ref_ids(
            getattr(event, "stream_type", ""),
            getattr(event, "event_type", ""),
            getattr(event, "payload", None),
        )
    hidden: set[str] = confidentiality.hidden_among(conn, sorted(ids), who) if ids else set()
    if not hidden:
        return list(events)
    out: list[E] = []
    for event in events:
        update: dict[str, Any] = {}
        found = getattr(event, "intent", None)
        if found is not None:
            update["intent"] = redact_intent_ids(found, hidden)
        payload = getattr(event, "payload", None)
        shown = redacted_payload(
            getattr(event, "stream_type", ""), getattr(event, "event_type", ""), payload, hidden
        )
        if shown is not payload:
            update["payload"] = shown
        out.append(event.model_copy(update=update) if update else event)
    return out


redact_events = redact_for_viewer  # the name the intent redaction had before payloads joined it


def redact_intent(conn: Connection, intent: Intent | None, viewer: Viewer) -> IntentView | None:
    """``intent`` as ``viewer`` may read it: a reference they cannot read is "not available"."""
    from tl_core import confidentiality

    if intent is None:
        return None
    ids = intent_ids(intent)
    hidden: set[str] = confidentiality.hidden_among(conn, sorted(ids), viewer) if ids else set()
    return redact_intent_ids(intent, hidden) if hidden else intent
