"""Read views of the forms module: the template list and detail, the submission list and detail, and
the form a record offers (``form_for``). Nothing here writes, and no access word is checked (the
entry points check ``forms.view``).

Every function takes ``viewer=`` keyword-only; its default is ``confidentiality.LOWEST``, never the
ambient viewer. The hidden filter is applied inside the statement and before ``LIMIT`` and the
count: a hidden submission (a draft read by its author alone, or a submission whose answer class
the viewer may not read) is absent from lists and from ``total``, and its detail is ``None``, as a
missing one is. Limits are clamped to 1..``MAX_LIMIT``. A list runs two statements: the rows and
the count. The JSON columns are decoded here; a column that is not valid JSON gives an empty list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Connection, Row, text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, holds_word, normalise_word
from tl_core.forms.registry import load_form_sources
from tl_core.forms.types import FormBinding

from tl_mod_forms.names import (
    DRAFT,
    SUBMISSION_STATES,
    SUBMISSION_VIEW,
    TEMPLATE_STATES,
    TEMPLATE_VIEW,
)

MAX_LIMIT: Final = 500
MIN_LIMIT: Final = 1
MSG_UNKNOWN_STATE: Final = "unknown state"
#: The intake values a template may carry (``template.yaml``: ``public``, or null for none).
INTAKE_VALUES: Final = ("public",)

_TEMPLATE_COLUMNS: Final = (
    "v.id, v.key, v.title, v.template_version AS version, COALESCE(v.status, :draft) AS state, "
    "v.format_version, v.field_count, v.content_hash, v.bound_record_type, v.answer_class, "
    "v.intake, v.purpose, v.published_on, v.retired_on"
)
_SUBMISSION_COLUMNS: Final = (
    "v.id, v.key, COALESCE(v.status, :draft) AS state, v.template_id, "
    "v.template_version, v.subject_id, "
    "v.answer_class, v.author, v.submitted_on, v.reviewed_by, v.reviewed_on, v.draft_saves, "
    "v.version"
)


@dataclass(frozen=True)
class TemplateRow:
    """A template, without its fields list (``TemplateDetail`` carries it)."""

    id: str
    key: str | None
    title: str | None
    version: int | None
    state: str
    format_version: int | None
    field_count: int | None
    content_hash: str | None
    bound_record_type: str | None
    answer_class: str | None
    intake: str | None
    purpose: str | None
    published_on: str | None
    retired_on: str | None


@dataclass(frozen=True)
class TemplateDetail:
    """A template with its decoded fields and the record types it is accepted as."""

    row: TemplateRow
    fields: list[dict[str, Any]]
    accepts_as: list[str]


@dataclass(frozen=True)
class SubmissionRow:
    """A submission, without its answers and notes (``SubmissionDetail`` carries them)."""

    id: str
    key: str | None
    state: str
    template_id: str | None
    template_version: int | None
    subject_id: str | None
    answer_class: str | None
    author: str | None
    submitted_on: str | None
    reviewed_by: str | None
    reviewed_on: str | None
    draft_saves: int | None
    version: int


@dataclass(frozen=True)
class SubmissionDetail:
    """A submission with its decoded answers, its review note and its void reason."""

    row: SubmissionRow
    answers: list[dict[str, Any]]
    review_note: str | None
    void_reason: str | None


@dataclass(frozen=True)
class Page[T]:
    """One page of rows; ``total`` counts only the rows the viewer may read."""

    rows: list[T]
    total: int


def _clamp(limit: int) -> int:
    return min(max(int(limit), MIN_LIMIT), MAX_LIMIT)


def _offset(offset: int) -> int:
    return max(int(offset), 0)


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


def _opt_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _json_list(value: object) -> list[Any]:
    """The decoded JSON list of a column; anything else (NULL, not JSON, not a list) is empty."""
    if value is None:
        return []
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def _template(row: Row[Any]) -> TemplateRow:
    return TemplateRow(
        id=str(row.id),
        key=_opt(row.key),
        title=_opt(row.title),
        version=_opt_int(row.version),
        state=str(row.state),
        format_version=_opt_int(row.format_version),
        field_count=_opt_int(row.field_count),
        content_hash=_opt(row.content_hash),
        bound_record_type=_opt(row.bound_record_type),
        answer_class=_opt(row.answer_class),
        intake=_opt(row.intake),
        purpose=_opt(row.purpose),
        published_on=_opt(row.published_on),
        retired_on=_opt(row.retired_on),
    )


def _submission(row: Row[Any]) -> SubmissionRow:
    return SubmissionRow(
        id=str(row.id),
        key=_opt(row.key),
        state=str(row.state),
        template_id=_opt(row.template_id),
        template_version=_opt_int(row.template_version),
        subject_id=_opt(row.subject_id),
        answer_class=_opt(row.answer_class),
        author=_opt(row.author),
        submitted_on=_opt(row.submitted_on),
        reviewed_by=_opt(row.reviewed_by),
        reviewed_on=_opt(row.reviewed_on),
        draft_saves=_opt_int(row.draft_saves),
        version=int(row.version),
    )


def template_list(
    conn: Connection,
    *,
    state: str | None = None,
    intake: str | None = None,
    key: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> Page[TemplateRow]:
    """The templates by title, version and id, that match the filters. Hidden ones are left out
    of the rows and of ``total``."""
    if state is not None and state not in TEMPLATE_STATES:
        raise ValueError(MSG_UNKNOWN_STATE)
    if intake is not None and intake not in INTAKE_VALUES:
        raise ValueError(MSG_UNKNOWN_STATE)
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    conditions = ["v.voided = :no", visible]
    params: dict[str, Any] = {"no": False, "draft": DRAFT, **extra}
    if state is not None:
        conditions.append("COALESCE(v.status, :draft) = :state")
        params["state"] = state
    if intake is not None:
        conditions.append("v.intake = :intake")
        params["intake"] = intake
    if key is not None:
        conditions.append("v.key = :key")
        params["key"] = key
    where = " AND ".join(conditions)
    rows = conn.execute(
        text(
            f"SELECT {_TEMPLATE_COLUMNS} FROM {TEMPLATE_VIEW} v WHERE {where} "
            "ORDER BY v.title, v.template_version, v.id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": _clamp(limit), "offset": _offset(offset)},
    )
    listed = [_template(row) for row in rows]
    total = conn.execute(
        text(f"SELECT count(*) FROM {TEMPLATE_VIEW} v WHERE {where}"), params
    ).scalar_one()
    return Page(rows=listed, total=int(total))


def template_detail(
    conn: Connection,
    template_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> TemplateDetail | None:
    """The template with this id, with its decoded fields and accepted record types. ``None`` when
    there is no such template or the viewer may not read it."""
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    row = conn.execute(
        text(
            f"SELECT {_TEMPLATE_COLUMNS}, v.form_fields_json, v.accepts_as_json "
            f"FROM {TEMPLATE_VIEW} v WHERE v.id = :id AND v.voided = :no AND {visible} LIMIT 1"
        ),
        {"id": template_id, "no": False, "draft": DRAFT, **extra},
    ).first()
    if row is None:
        return None
    return TemplateDetail(
        row=_template(row),
        fields=[item for item in _json_list(row.form_fields_json) if isinstance(item, dict)],
        accepts_as=[item for item in _json_list(row.accepts_as_json) if isinstance(item, str)],
    )


def submission_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    template_id: str | None = None,
    subject_id: str | None = None,
    author: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> Page[SubmissionRow]:
    """The submissions of ``scope``, the latest submitted first (``submitted_on`` is NULL for a
    draft, so it sorts last), then by id. A draft is listed for its author alone; a hidden
    submission is left out of the rows and of ``total``."""
    if state is not None and state not in SUBMISSION_STATES:
        raise ValueError(MSG_UNKNOWN_STATE)
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    conditions = ["v.scope = :scope", "v.voided = :no", visible]
    params: dict[str, Any] = {"scope": scope, "no": False, "draft": DRAFT, "never": "", **extra}
    if state is not None:
        conditions.append("COALESCE(v.status, :draft) = :state")
        params["state"] = state
    if template_id is not None:
        conditions.append("v.template_id = :template_id")
        params["template_id"] = template_id
    if subject_id is not None:
        conditions.append("v.subject_id = :subject_id")
        params["subject_id"] = subject_id
    if author is not None:
        conditions.append("v.author = :author")
        params["author"] = author
    where = " AND ".join(conditions)
    rows = conn.execute(
        text(
            f"SELECT {_SUBMISSION_COLUMNS} FROM {SUBMISSION_VIEW} v WHERE {where} "
            "ORDER BY COALESCE(v.submitted_on, :never) DESC, v.id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": _clamp(limit), "offset": _offset(offset)},
    )
    listed = [_submission(row) for row in rows]
    total = conn.execute(
        text(f"SELECT count(*) FROM {SUBMISSION_VIEW} v WHERE {where}"), params
    ).scalar_one()
    return Page(rows=listed, total=int(total))


def submission_detail(
    conn: Connection,
    scope: str,
    ref: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> SubmissionDetail | None:
    """The submission of ``scope`` whose key or id is ``ref`` (an id match wins over a key match),
    with its decoded answers. ``None`` when there is no such submission or the viewer may not read
    it (a draft is read by its author alone)."""
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    row = conn.execute(
        text(
            f"SELECT {_SUBMISSION_COLUMNS}, v.answers_json, v.review_note, v.void_reason "
            f"FROM {SUBMISSION_VIEW} v WHERE v.scope = :scope AND v.voided = :no "
            "AND (v.key = :ref OR v.id = :ref) "
            f"AND {visible} ORDER BY CASE WHEN v.id = :ref THEN 0 ELSE 1 END LIMIT 1"
        ),
        {"scope": scope, "no": False, "draft": DRAFT, "ref": ref, **extra},
    ).first()
    if row is None:
        return None
    return SubmissionDetail(
        row=_submission(row),
        answers=[item for item in _json_list(row.answers_json) if isinstance(item, dict)],
        review_note=_opt(row.review_note),
        void_reason=_opt(row.void_reason),
    )


def _view_word_held(conn: Connection, actor: str, word: str, scope: str) -> bool:
    """Whether ``actor`` holds the source's ``view_word`` in ``scope`` (fail closed)."""
    if not actor:
        return False
    try:
        return holds_word(
            conn,
            holder_for_actor(conn, actor),
            scope=scope,
            module=word.partition(".")[0],
            word=normalise_word(word),
        )
    except Exception:
        return False


def form_for(
    conn: Connection,
    record_id: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> FormBinding | None:
    """The form a record offers: the binding of the source of the record's type. ``None`` when the
    record is absent, hidden from the viewer, or its type has no source. A hidden record never
    reaches a source."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    row = conn.execute(
        text(
            "SELECT r.type AS record_type, r.scope AS scope FROM cur_core_record r "
            f"WHERE r.id = :id AND r.voided = :no AND {visible} LIMIT 1"
        ),
        {"id": record_id, "no": False, **extra},
    ).first()
    if row is None:
        return None
    source = load_form_sources().get(str(row.record_type))
    if source is None or not _view_word_held(conn, viewer.actor, source.view_word, str(row.scope)):
        return None
    return source.binding(conn, record_id, viewer, now)


__all__ = [
    "MAX_LIMIT",
    "MIN_LIMIT",
    "Page",
    "SubmissionDetail",
    "SubmissionRow",
    "TemplateDetail",
    "TemplateRow",
    "form_for",
    "submission_detail",
    "submission_list",
    "template_detail",
    "template_list",
]
