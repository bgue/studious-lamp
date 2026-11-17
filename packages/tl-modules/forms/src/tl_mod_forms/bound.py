"""Send a filled form through the typed command of its binding (V3-F1s).

``record`` is the one door for a record that offers a form (an inspection, a permit): it reads the
binding of the record under the viewer (hidden, absent and typeless all answer ``MSG_UNKNOWN``),
then checks, in this order, that the binding is available, that the actor holds the typed
command's own access word (the module's refusal, never a forms one), that the answers fit the
template under the source's own rules, and only then builds the module's command and runs its
handler in the caller's unit of work. No event is written before the answers pass, and a refusal
by the handler rolls back the caller's block. The forms module adds no word and no event: the
events are the typed module's own.

A source adds three calls to the contract of ``tl_core.forms.types.FormSource``: ``fields`` (the
questions of the binding's template), ``problems`` (the module's answer rules) and ``arguments``
(answers to the command's arguments). A source without them cannot be sent through here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, cast

from pydantic import ValidationError
from sqlalchemy import Connection, text
from tl_core.auth.module_roles import require_command_access
from tl_core.confidentiality import Viewer, use_viewer
from tl_core.forms.registry import load_form_sources
from tl_core.forms.types import FormBinding
from tl_core.modules import module_commands
from tl_core.services.commands import CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

from tl_mod_forms import views
from tl_mod_forms.errors import MSG_UNKNOWN, FormAnswersError, FormRuleError, FormStateError

MSG_NOT_AVAILABLE = "that record takes no form now"
MSG_NO_SEND = "that record's form cannot be sent from here"
MSG_ARGS = "the form does not make a valid command for that record"


class SendableSource(Protocol):
    """What a source adds to ``FormSource`` to be sent through ``record``."""

    def fields(
        self, conn: Connection, binding: FormBinding, viewer: Viewer
    ) -> list[dict[str, Any]]: ...

    def problems(
        self, fields: list[dict[str, Any]], answers: list[dict[str, Any]]
    ) -> list[str]: ...

    def arguments(self, binding: FormBinding, answers: list[dict[str, Any]]) -> dict[str, Any]: ...


def _safe(problem: str, ids: set[str]) -> str:
    """A rule's problem as ``<id>: <what>`` for a known question; never an answer value."""
    head, _, rest = problem.partition(": ")
    return f"{head if head in ids else 'an answer'}: {rest}" if rest else "an answer: not valid"


def binding_of(
    conn: Connection, record_id: str, *, now: datetime, viewer: Viewer
) -> FormBinding | None:
    """The binding the record's source answers for the viewer (``None``: hidden or absent)."""
    with use_viewer(viewer):
        return views.form_for(conn, record_id, now=now, viewer=viewer)


def fields_of(conn: Connection, binding: FormBinding, viewer: Viewer) -> list[dict[str, Any]]:
    """The questions of the binding's template (``[]`` for a source that cannot be sent)."""
    produced = load_form_sources().get(binding.record_type)
    if produced is None or not hasattr(produced, "fields") or not binding.available:
        return []
    return cast(SendableSource, produced).fields(conn, binding, viewer)


def record(
    uow: UnitOfWork,
    *,
    record_id: str,
    answers: list[dict[str, Any]],
    actor: str,
    scope: str,
    source: str,
    now: datetime,
    viewer: Viewer,
) -> CommandResult:
    """Send ``answers`` for the record ``record_id`` through its binding's typed command."""
    conn = uow.conn()
    binding = binding_of(conn, record_id, now=now, viewer=viewer)
    found_scope = conn.execute(
        text("SELECT scope FROM cur_core_record WHERE id = :id"), {"id": record_id}
    ).scalar_one_or_none()
    if binding is None or found_scope != scope:  # hidden, absent, typeless or in another scope
        raise RecordNotFoundError(MSG_UNKNOWN)
    produced = load_form_sources().get(binding.record_type)
    row = next((c for c in module_commands() if c.name == binding.command), None)
    if (
        produced is None
        or row is None
        or row.needs_holds
        or row.takes_roles
        or not all(hasattr(produced, n) for n in ("fields", "problems", "arguments"))
    ):
        raise FormRuleError(MSG_NO_SEND)
    sendable = cast(SendableSource, produced)
    # the typed command's own word, before the state of the record and the answers
    require_command_access(conn, row.model.model_construct(actor=actor, source=source, scope=scope))
    if not binding.available:
        raise FormStateError(
            f"{MSG_NOT_AVAILABLE} ({binding.reason})" if binding.reason else MSG_NOT_AVAILABLE
        )
    fields = sendable.fields(conn, binding, viewer)
    found = sendable.problems(fields, answers)
    if found:
        ids = {str(f.get("id")) for f in fields}
        raise FormAnswersError(tuple(_safe(p, ids) for p in found))
    args = {
        **sendable.arguments(binding, answers),
        "actor": actor,
        "source": source,
        "scope": scope,
    }
    try:
        command = row.model.model_validate(args)
    except ValidationError:
        raise FormRuleError(MSG_ARGS) from None
    with use_viewer(viewer):
        return row.handler(uow, command)


__all__ = ["MSG_ARGS", "MSG_NOT_AVAILABLE", "MSG_NO_SEND", "binding_of", "fields_of", "record"]
