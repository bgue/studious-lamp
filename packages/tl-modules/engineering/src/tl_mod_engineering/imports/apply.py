"""Applying an import plan to a project's tags (brief 9 M2, bulk import; P1-I1-T10c).

``existing_tags`` reads the tags a project holds in the shape ``plan_import`` compares against.
``apply_plan`` writes a plan through the tag commands, in the caller's unit of work: a new row
becomes a tag (a number that breaks the pattern is kept as a violation, as a legacy list needs), a
changed row becomes a reclassification, a title update and pset writes, and every event of the
import carries the same correlation id and the source ``import:<job>``. The caller commits, so a
failure on any row leaves the project exactly as it was. Tags the file does not mention are never
touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection
from tl_core.services.commands import UpdateRecord
from tl_core.services.errors import ServiceError
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_update_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_engineering import registry
from tl_mod_engineering.errors import ImportApplyError
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    ReclassifyTag,
    handle_create_tag,
    handle_reclassify_tag,
)
from tl_mod_engineering.imports.model import ExistingTag, ImportPlan, ImportRow, RowChange


@dataclass(frozen=True)
class ApplyResult:
    """What an import did, in rows."""

    created: int
    changed: int
    unchanged: int
    not_in_file: int  # tags the file does not mention; left as they are
    skipped: int  # invalid rows left out (only with ``skip_invalid``)
    correlation_id: str


def existing_tags(conn: Connection, scope: str) -> list[ExistingTag]:
    """The tags in service in ``scope`` (not superseded or deleted), by number."""
    return [
        ExistingTag(
            id=row.id,
            number=row.number,
            class_code=row.class_code,
            service=row.title,
            psets=row.psets,
            version=row.version,
        )
        for row in registry.list_tags(conn, scope, limit=1_000_000)
    ]


def _split(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Standard values and custom (``x.``) values of one pset."""
    standard = {k: v for k, v in values.items() if not k.startswith("x.")}
    custom = {k: v for k, v in values.items() if k.startswith("x.")}
    return standard, custom


def _version(uow: UnitOfWork, tag_id: str) -> int:
    row = registry.get_tag(uow.conn(), tag_id)
    assert row is not None
    return row.version


def _create(uow: UnitOfWork, base: dict[str, Any], row: ImportRow) -> None:
    standard_psets: dict[str, dict[str, Any]] = {}
    custom: dict[str, dict[str, Any]] = {}
    for pset, values in row.psets.items():
        standard, extra = _split(values)
        if standard:
            standard_psets[pset] = standard
        if extra:
            custom[pset] = extra
    made = handle_create_tag(
        uow,
        CreateTag(
            **base,
            number=row.number,
            class_code=row.class_code,
            service=row.service,
            psets=standard_psets,
            pattern_policy="record",
            origin="import",
        ),
    )
    for pset, values in sorted(custom.items()):
        handle_set_pset_values(
            uow,
            SetPsetValues(
                **base,
                stream_id=made.stream_id,
                expected_version=_version(uow, made.stream_id),
                pset=pset,
                layer="custom",
                values=values,
            ),
        )


def _change(uow: UnitOfWork, base: dict[str, Any], change: RowChange, reason: str) -> None:
    by_pset: dict[str, dict[str, Any]] = {}
    for item in change.changes:
        if item.field == "class":
            handle_reclassify_tag(
                uow,
                ReclassifyTag(**base, stream_id=change.tag_id, class_code=item.new, reason=reason),
            )
        elif item.field == "service":
            handle_update_record(
                uow,
                UpdateRecord(
                    **base,
                    stream_id=change.tag_id,
                    expected_version=_version(uow, change.tag_id),
                    changes={"title": item.new},
                ),
            )
        else:
            _, pset, key = item.field.split(".", 2)
            by_pset.setdefault(pset, {})[key] = item.new
    for pset, values in sorted(by_pset.items()):
        for layer, part in zip(("standard", "custom"), _split(values), strict=True):
            if part:
                handle_set_pset_values(
                    uow,
                    SetPsetValues(
                        **base,
                        stream_id=change.tag_id,
                        expected_version=_version(uow, change.tag_id),
                        pset=pset,
                        layer=layer,  # type: ignore[arg-type]
                        values=part,
                    ),
                )


def apply_plan(
    uow: UnitOfWork,
    scope: str,
    plan: ImportPlan,
    *,
    actor: str,
    source: str,
    reason: str,
    skip_invalid: bool = False,
    correlation_id: str | None = None,
) -> ApplyResult:
    """Write ``plan`` into ``scope``: create the new tags, update the changed ones.

    Rows of ``plan.invalid`` stop the import (``ImportApplyError`` listing ``line <n>: <problem>``
    for each, before anything is written) unless ``skip_invalid`` leaves them out. A row that the
    tag commands refuse (a class that does not exist, a pset the class does not allow, a value the
    schema rejects structurally) raises ``ImportApplyError`` naming the line and the number, with
    the command's own message; the caller's unit of work is then abandoned. Tags in
    ``plan.removed`` and ``plan.unchanged`` are not written.
    """
    if plan.invalid and not skip_invalid:
        problems = [f"line {row.line}: {'; '.join(row.problems)}" for row in plan.invalid]
        raise ImportApplyError(
            f"{len(plan.invalid)} row(s) cannot be imported; fix them or skip them", problems
        )
    correlation = correlation_id or new_ulid()
    base: dict[str, Any] = {
        "actor": actor,
        "source": source,
        "scope": scope,
        "correlation_id": correlation,
    }
    for row in plan.new:
        try:
            _create(uow, base, row)
        except ServiceError as exc:
            raise ImportApplyError(f"line {row.line} ({row.number}): {exc}") from exc
    for change in plan.changed:
        try:
            _change(uow, base, change, reason)
        except ServiceError as exc:
            raise ImportApplyError(f"line {change.line} ({change.number}): {exc}") from exc
    return ApplyResult(
        created=len(plan.new),
        changed=len(plan.changed),
        unchanged=len(plan.unchanged),
        not_in_file=len(plan.removed),
        skipped=len(plan.invalid) if skip_invalid else 0,
        correlation_id=correlation,
    )
