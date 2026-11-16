"""Runner model for a form fill (P2-FORMS T02): one visible field at a time.

Also back, skip, review and confirm.

Pure: no I/O, no clock, no database. Every step returns a new state; inputs are never mutated.
Visibility and answer checks come from ``tl_core.forms.rules``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tl_core.forms import rules

_FILL = "fill"
_REVIEW = "review"


class RunnerError(ValueError):
    """Refused runner call; ``problems`` are the reasons, ``str()`` joins them with ``"; "``."""

    problems: list[str]

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class RunnerState:
    fmt: int  # 1 or 2
    values: Mapping[str, Any]  # field id -> value, only visible fields
    notes: Mapping[str, str]  # field id -> note text
    at: str | None  # id of the current field; None in review
    phase: str  # "fill" | "review"


@dataclass(frozen=True)
class Step:
    """The current field as the screen shows it."""

    id: str
    text: str
    kind: str
    required: bool
    section: str | None
    help: str | None
    unit: str | None
    min: float | None
    max: float | None
    choices: tuple[str, ...]
    value: Any
    note: str | None
    number: int  # 1-based position among the visible fields
    total: int  # count of visible fields now


@dataclass(frozen=True)
class ReviewLine:
    id: str
    text: str
    kind: str
    value: Any
    note: str | None


@dataclass(frozen=True)
class Review:
    lines: tuple[ReviewLine, ...]  # visible fields in order
    missing: tuple[str, ...]  # visible required ids with no value


# ---- helpers --------------------------------------------------------------------------------


def _usable_ids(fields: list[dict[str, Any]]) -> list[str]:
    """Field ids in field order (the same fields ``rules`` reads)."""
    return [f["id"] for f in fields if isinstance(f.get("id"), str)]


def _by_id(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in fields if isinstance(f.get("id"), str)}


def _answer_list(values: Mapping[str, Any], notes: Mapping[str, str]) -> list[dict[str, Any]]:
    """Answers in the shape ``rules`` takes; every answer carries a ``note`` key."""
    return [{"q": k, "value": v, "note": notes.get(k)} for k, v in values.items()]


def _visible(
    fields: list[dict[str, Any]], values: Mapping[str, Any], notes: Mapping[str, str]
) -> list[str]:
    answers = [{"q": k, "value": v} for k, v in values.items()]
    return rules.visible_ids(fields, answers)


def _pruned(
    fields: list[dict[str, Any]], values: Mapping[str, Any], notes: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Drop the values and notes of fields that are not visible for these values."""
    shown = set(_visible(fields, values, notes))
    kept_values = {k: v for k, v in values.items() if k in shown}
    kept_notes = {k: n for k, n in notes.items() if k in shown}
    return kept_values, kept_notes


def _advance(
    state: RunnerState,
    fields: list[dict[str, Any]],
    values: dict[str, Any],
    notes: dict[str, str],
) -> RunnerState:
    """The state after the current field: the next visible field in field order, else review."""
    order = _usable_ids(fields)
    position = {fid: i for i, fid in enumerate(order)}
    here = position.get(state.at or "", -1)
    nxt: str | None = None
    for fid in _visible(fields, values, notes):
        if position.get(fid, -1) > here:
            nxt = fid
            break
    if nxt is None:
        return RunnerState(state.fmt, values, notes, None, _REVIEW)
    return RunnerState(state.fmt, values, notes, nxt, _FILL)


# ---- the runner -----------------------------------------------------------------------------


def start(
    fields: list[dict[str, Any]],
    *,
    fmt: int = 2,
    answers: Sequence[Mapping[str, Any]] | None = None,
) -> RunnerState:
    """A state at the first visible field, with the given answers kept where still visible."""
    values: dict[str, Any] = {}
    notes: dict[str, str] = {}
    for ans in answers or []:
        qid = ans.get("q")
        if not isinstance(qid, str) or ans.get("value") is None or qid in values:
            continue
        values[qid] = ans["value"]
        note = ans.get("note")
        if isinstance(note, str):
            notes[qid] = note
    values, notes = _pruned(fields, values, notes)
    state = RunnerState(fmt, values, notes, None, _REVIEW)
    visible = _visible(fields, values, notes)
    if not visible:
        return state
    return RunnerState(fmt, values, notes, visible[0], _FILL)


def step(state: RunnerState, fields: list[dict[str, Any]]) -> Step | None:
    """The current field as the screen shows it, or None in review."""
    if state.at is None:
        return None
    field = _by_id(fields).get(state.at)
    visible = _visible(fields, state.values, state.notes)
    if field is None or state.at not in visible:
        return None
    return Step(
        id=state.at,
        text=str(field.get("text")),
        kind=str(field.get("kind")),
        required=bool(field.get("required")),
        section=field.get("section"),
        help=field.get("help"),
        unit=field.get("unit"),
        min=field.get("min"),
        max=field.get("max"),
        choices=tuple(field.get("choices") or ()),
        value=state.values.get(state.at),
        note=state.notes.get(state.at),
        number=visible.index(state.at) + 1,
        total=len(visible),
    )


def answer(
    state: RunnerState,
    fields: list[dict[str, Any]],
    value: Any,
    note: str | None = None,
) -> tuple[RunnerState, list[str]]:
    """Set the current field's answer and move on; refused answers leave the state unchanged."""
    if state.phase == _REVIEW or state.at is None:
        return state, ["not at a field"]
    values = dict(state.values)
    notes = dict(state.notes)
    values[state.at] = value
    if note is None:
        notes.pop(state.at, None)
    else:
        notes[state.at] = note
    values, notes = _pruned(fields, values, notes)
    problems = rules.validate_answers(
        fields, _answer_list(values, notes), fmt=state.fmt, partial=True
    )
    if problems:
        return state, problems
    return _advance(state, fields, values, notes), []


def skip(state: RunnerState, fields: list[dict[str, Any]]) -> tuple[RunnerState, list[str]]:
    """Skip an optional current field (its value and note are dropped); required fields refuse."""
    if state.phase == _REVIEW or state.at is None:
        return state, ["not at a field"]
    field = _by_id(fields).get(state.at, {})
    if field.get("required"):
        return state, [f"{state.at}: answer required"]
    values = dict(state.values)
    notes = dict(state.notes)
    values.pop(state.at, None)
    notes.pop(state.at, None)
    values, notes = _pruned(fields, values, notes)
    problems = rules.validate_answers(
        fields, _answer_list(values, notes), fmt=state.fmt, partial=True
    )
    if problems:
        return state, problems
    return _advance(state, fields, values, notes), []


def back(state: RunnerState, fields: list[dict[str, Any]]) -> RunnerState:
    """The previous visible field (the last one from review); answers are kept."""
    visible = _visible(fields, state.values, state.notes)
    if state.phase == _REVIEW:
        if not visible:
            return state
        return RunnerState(state.fmt, state.values, state.notes, visible[-1], _FILL)
    if state.at is None or state.at not in visible:
        return state
    idx = visible.index(state.at)
    if idx == 0:
        return state
    return RunnerState(state.fmt, state.values, state.notes, visible[idx - 1], _FILL)


def review(state: RunnerState, fields: list[dict[str, Any]]) -> Review:
    """The visible fields in order with their values and notes, and the missing required ids."""
    by_id = _by_id(fields)
    lines: list[ReviewLine] = []
    missing: list[str] = []
    for fid in _visible(fields, state.values, state.notes):
        field = by_id[fid]
        lines.append(
            ReviewLine(
                id=fid,
                text=str(field.get("text")),
                kind=str(field.get("kind")),
                value=state.values.get(fid),
                note=state.notes.get(fid),
            )
        )
        if field.get("required") and fid not in state.values:
            missing.append(fid)
    return Review(lines=tuple(lines), missing=tuple(missing))


def confirm(state: RunnerState, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The final answers of the visible fields that have a value, in field order."""
    if state.phase != _REVIEW:
        raise RunnerError(["not finished"])
    view = review(state, fields)
    if view.missing:
        raise RunnerError([f"{fid}: answer required" for fid in view.missing])
    out: list[dict[str, Any]] = []
    for line in view.lines:
        if line.value is None:
            continue
        if state.fmt == 1:
            out.append({"q": line.id, "value": line.value, "note": line.note})
        else:
            item: dict[str, Any] = {"q": line.id, "value": line.value}
            if line.note is not None:
                item["note"] = line.note
            out.append(item)
    return out
