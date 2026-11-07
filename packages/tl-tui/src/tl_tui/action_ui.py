"""The terminal's action table without the terminal: what an action asks, how it builds a command.

``ACTION_UI`` maps a command name to a key, the questions to ask first and how to build the command
from the answers (``ActionUi``, ``FormField``). Nothing here imports ``textual`` or any other
``tl_tui`` module, so the web client can use the same table (P2-WEB1). A command is built with a
placeholder envelope (``ENVELOPE``); ``stamp`` puts the real actor and scope on it just before it is
sent. ``log_actions`` and ``widgets.action_form`` re-export these names.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from tl_core.services.commands import Command
from tl_mod_correspondence.handlers.commercial import (
    ReturnCommercial,
    ReviewCommercial,
    SubmitCommercial,
)
from tl_mod_correspondence.handlers.commercial_flow import (
    AssessCommercial,
    CloseCommercial,
    IssueCommercial,
    ReferCommercialToLegal,
)
from tl_mod_correspondence.handlers.escalate import EscalateTechnical
from tl_mod_correspondence.handlers.issue import IssueCorrespondence
from tl_mod_correspondence.handlers.responses import (
    CloseCorrespondence,
    VoidCorrespondence,
    VoidDraft,
)
from tl_mod_correspondence.handlers.technical import ReturnTechnical, SubmitTechnical
from tl_mod_correspondence.handlers.technical_flow import (
    AnswerTechnical,
    CloseTechnical,
    IssueTechnical,
    ReissueTechnical,
    ReviewTechnicalAnswer,
)
from tl_mod_engineering.handlers.tags import ReclassifyTag, RenameTag


@dataclass(frozen=True)
class FormField:
    """One thing the form asks. ``name`` is the key in the returned dict."""

    name: str
    label: str
    kind: Literal["line", "text", "choice"] = "line"
    choices: tuple[str, ...] = ()
    required: bool = True
    default: str = ""


#: The placeholder envelope of a built command; ``stamp`` replaces it before the command is sent.
ENVELOPE: dict[str, Any] = {"actor": "", "source": "tui", "scope": "company"}

Build = Callable[[dict[str, str], str, int | None], Command]
#: ``(form values) -> (command name, command)``: what the runner sends once it has the answers.
Prepare = Callable[[dict[str, str]], tuple[str, Command]]


@dataclass(frozen=True)
class ActionUi:
    """How one command is presented: its key, what it asks first and how the command is built."""

    key: str
    fields: tuple[FormField, ...] = ()
    confirm: str | None = None
    build: Build = field(kw_only=True)  # (form values, record id, version) -> command model


def _reason(label: str = "Reason", *, required: bool = True) -> FormField:
    return FormField("reason", label, kind="line", required=required)


def _flag(name: str, label: str) -> FormField:
    return FormField(
        name, label, kind="choice", choices=("unknown", "yes", "no"), default="unknown"
    )


def _opt(values: dict[str, str], name: str) -> str | None:
    return values.get(name, "").strip() or None


def _stream(model: type[Command], **more: Callable[[dict[str, str]], Any]) -> Build:
    """A build that sets ``stream_id`` and ``expected_version`` and each extra from the answers."""

    def build(values: dict[str, str], record_id: str, version: int | None) -> Command:
        extras = {name: pick(values) for name, pick in more.items()}
        base = {**ENVELOPE, "stream_id": record_id, "expected_version": version}
        return model.model_validate({**base, **extras})

    return build


def _stream_only(model: type[Command]) -> Build:
    """A build for a command with no ``expected_version`` (escalation)."""

    def build(values: dict[str, str], record_id: str, version: int | None) -> Command:
        return model.model_validate({**ENVELOPE, "stream_id": record_id})

    return build


_DECISIONS = {"accept": "accepted", "reject": "rejected"}
_ASSESSMENTS = {"agreed": "agreed", "partly agreed": "partially_agreed", "disputed": "disputed"}

#: Keys are unique across the table so that no two offers on one record can meet. A log that binds
#: one of these letters itself (the tag register binds ``c``, ``v``, ``a``) is not offered it.
ACTION_UI: Mapping[str, ActionUi] = {
    # Technical items (RFIs)
    "SubmitTechnical": ActionUi("p", build=_stream(SubmitTechnical)),
    "ReturnTechnical": ActionUi(
        "r", (_reason(),), build=_stream(ReturnTechnical, reason=lambda v: v["reason"])
    ),
    "IssueTechnical": ActionUi(
        "u", confirm="Issue this item to the other party?", build=_stream(IssueTechnical)
    ),
    "AnswerTechnical": ActionUi(
        "a",
        (
            FormField("answer", "Answer", kind="text"),
            _flag("cost_impact", "Cost impact"),
            _flag("schedule_impact", "Schedule impact"),
        ),
        build=_stream(
            AnswerTechnical,
            answer=lambda v: v["answer"],
            cost_impact=lambda v: v.get("cost_impact", "unknown"),
            schedule_impact=lambda v: v.get("schedule_impact", "unknown"),
        ),
    ),
    "ReviewTechnicalAnswer": ActionUi(
        "w",
        (
            FormField("decision", "Decision", kind="choice", choices=tuple(_DECISIONS)),
            _reason("Note", required=False),
        ),
        build=_stream(
            ReviewTechnicalAnswer,
            decision=lambda v: _DECISIONS[v["decision"]],
            note=lambda v: _opt(v, "reason"),
        ),
    ),
    "ReissueTechnical": ActionUi(
        "x", (_reason(),), build=_stream(ReissueTechnical, reason=lambda v: v["reason"])
    ),
    "CloseTechnical": ActionUi(
        "c",
        (_reason("Reason (optional)", required=False),),
        build=_stream(CloseTechnical, reason=lambda v: _opt(v, "reason")),
    ),
    "EscalateTechnical": ActionUi(
        "e",
        confirm="Raise an early warning from this answered RFI?",
        build=_stream_only(EscalateTechnical),
    ),
    # Commercial items (controllers)
    "SubmitCommercial": ActionUi("p", build=_stream(SubmitCommercial)),
    "ReviewCommercial": ActionUi(
        "w",
        confirm="Approve the review of this notice?",
        build=_stream(ReviewCommercial),
    ),
    "ReturnCommercial": ActionUi(
        "r", (_reason(),), build=_stream(ReturnCommercial, reason=lambda v: v["reason"])
    ),
    "IssueCommercial": ActionUi(
        "u", confirm="Issue this notice to the other party?", build=_stream(IssueCommercial)
    ),
    "AssessCommercial": ActionUi(
        "k",
        (
            FormField("status", "Assessment", kind="choice", choices=tuple(_ASSESSMENTS)),
            FormField("value", "Assessed value (optional)", required=False),
            _reason("Note (optional)", required=False),
        ),
        build=_stream(
            AssessCommercial,
            status=lambda v: _ASSESSMENTS[v["status"]],
            assessed_value=lambda v: _opt(v, "value"),
            note=lambda v: _opt(v, "reason"),
        ),
    ),
    "CloseCommercial": ActionUi(
        "c",
        (_reason("Reason (optional)", required=False),),
        build=_stream(CloseCommercial, reason=lambda v: _opt(v, "reason")),
    ),
    "ReferCommercialToLegal": ActionUi(
        "g", (_reason(),), build=_stream(ReferCommercialToLegal, reason=lambda v: v["reason"])
    ),
    # Letters and minutes
    "IssueCorrespondence": ActionUi(
        "u", confirm="Issue this letter?", build=_stream(IssueCorrespondence)
    ),
    "CloseCorrespondence": ActionUi(
        "c",
        (_reason("Reason (optional)", required=False),),
        build=_stream(CloseCorrespondence, reason=lambda v: _opt(v, "reason")),
    ),
    # Voiding: the offers share one word, so the first applicable rule wins on the server
    "VoidDraft": ActionUi(
        "d", (_reason(),), build=_stream(VoidDraft, reason=lambda v: v["reason"])
    ),
    "VoidCorrespondence": ActionUi(
        "d", (_reason(),), build=_stream(VoidCorrespondence, reason=lambda v: v["reason"])
    ),
    # Tags
    "ReclassifyTag": ActionUi(
        "l",
        (FormField("class_code", "New class"), _reason()),
        build=_stream(
            ReclassifyTag, class_code=lambda v: v["class_code"], reason=lambda v: v["reason"]
        ),
    ),
    "RenameTag": ActionUi(
        "n",
        (FormField("new_number", "New number"), _reason()),
        build=_stream(
            RenameTag, new_number=lambda v: v["new_number"], reason=lambda v: v["reason"]
        ),
    ),
    # Not here, because the command needs something a form cannot ask for without a picker:
    # MergeTags (the other tags) and RecordResponse (the response item).
}


def stamp(cmd: Command, *, actor: str, scope: str) -> Command:
    """The command with the real actor and scope in place of the placeholder envelope."""
    return cmd.model_copy(update={"actor": actor, "source": "tui", "scope": scope})


def without_keys(ui: Mapping[str, ActionUi], keys: frozenset[str]) -> dict[str, ActionUi]:
    """``ui`` minus the entries whose key a log binds itself (the log's own keys win)."""
    return {name: entry for name, entry in ui.items() if entry.key not in keys}
