"""Expected links (brief 7.1, `tl:expects_link`): what a record should be linked to.

An expectation says "a record of this type should have at least ``min_count`` active links of
``relation`` (in ``direction``) to records of ``target_type``, by workflow state ``by_state``".
Expectations are declared on LinkML classes with the ``tl:expects_link`` annotation (see
``schema/core/annotations.yaml``) and read here as plain YAML. A link satisfies an expectation
only while it is ``active`` and the record at its other end is not voided.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from tl_schema.registry import default_schema_dir

from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork


class ExpectedLink(BaseModel):
    """One declared expectation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation: str  # forward relation code, e.g. "requires"
    direction: Literal["out", "in", "either"] = "out"  # "out": the record is the `from` end
    target_type: str | None = None  # record type of the other end; None means any type
    by_state: str | None = None  # workflow state by which the link must exist; None: no state
    label: str | None = None  # how people name it, e.g. "permit-to-work"
    min_count: int = Field(default=1, ge=1)

    @property
    def display(self) -> str:
        """``label`` when given, else the relation code."""
        return self.label or self.relation


class MissingLink(BaseModel):
    """An expectation that is not met: how many matching links exist and how many are needed."""

    expectation: ExpectedLink
    found: int
    needed: int


class ExpectedLinkError(ValueError):
    """An expected-link declaration that cannot be read. The message names the source."""


class ExpectedLinkRegistry:
    """Expectations by record type (``core.Record``), in declaration order."""

    def __init__(self, by_type: Mapping[str, Sequence[ExpectedLink]] | None = None) -> None:
        self._by_type: dict[str, list[ExpectedLink]] = {
            record_type: list(links) for record_type, links in (by_type or {}).items()
        }

    def add(self, record_type: str, expectation: ExpectedLink) -> None:
        """Declare an expectation for a record type."""
        self._by_type.setdefault(record_type, []).append(expectation)

    def for_type(self, record_type: str) -> list[ExpectedLink]:
        """The expectations of a record type (a new list; empty when there are none)."""
        return list(self._by_type.get(record_type, []))

    def record_types(self) -> list[str]:
        """Record types that have at least one expectation, sorted."""
        return sorted(record_type for record_type, links in self._by_type.items() if links)

    def merge(self, other: ExpectedLinkRegistry) -> None:
        """Append every expectation of ``other`` to this registry."""
        for record_type, links in other._by_type.items():
            for expectation in links:
                self.add(record_type, expectation)


def _as_mapping(value: object) -> dict[str, Any] | None:
    """``value`` as a mapping, or None when it is not one."""
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


def parse_expected_links(text: str, *, source: str = "<string>") -> ExpectedLinkRegistry:
    """Read the ``tl:expects_link`` annotations of every class in one LinkML YAML document.

    The record type of a class is ``<module>.<ClassName>`` where ``<module>`` is the schema-level
    annotation ``tl:module``. The annotation value is a list of mappings (see ``ExpectedLink``);
    a single mapping is also accepted. An empty file declares nothing. A class without the
    annotation contributes nothing; a schema without ``tl:module`` raises. Raises
    ``ExpectedLinkError`` (message starts with ``source``) for invalid YAML, a document that is not
    a mapping, a missing ``tl:module`` on a schema that has expectations, or an entry that is not a
    valid ``ExpectedLink``.
    """
    try:
        loaded: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExpectedLinkError(f"{source}: invalid YAML: {exc}") from exc
    if loaded is None:
        return ExpectedLinkRegistry()  # an empty file declares nothing
    document = _as_mapping(loaded)
    if document is None:
        raise ExpectedLinkError(f"{source}: a schema file must be a YAML mapping")
    registry = ExpectedLinkRegistry()
    classes = _as_mapping(document.get("classes"))
    if classes is None:
        return registry
    schema_annotations = _as_mapping(document.get("annotations"))
    module: Any = schema_annotations.get("tl:module") if schema_annotations is not None else None
    for class_key, class_value in classes.items():
        class_name = str(class_key)
        class_def = _as_mapping(class_value)
        if class_def is None:
            continue
        class_annotations = _as_mapping(class_def.get("annotations"))
        if class_annotations is None or "tl:expects_link" not in class_annotations:
            continue
        if not isinstance(module, str) or not module:
            raise ExpectedLinkError(
                f"{source}: class {class_name} has tl:expects_link but the schema has no tl:module"
            )
        entries: Any = class_annotations["tl:expects_link"]
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise ExpectedLinkError(
                f"{source}: {class_name}.tl:expects_link must be a mapping or a list of mappings"
            )
        for index, entry in enumerate(cast(list[Any], entries)):
            try:
                expectation = ExpectedLink.model_validate(entry)
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                raise ExpectedLinkError(
                    f"{source}: {class_name}.tl:expects_link[{index}]: {problems}"
                ) from exc
            registry.add(f"{module}.{class_name}", expectation)
    return registry


def load_expected_links(path: Path) -> ExpectedLinkRegistry:
    """Read one YAML file, or every ``*.yaml`` file of a directory (not recursive, sorted by name).

    A missing directory gives an empty registry.
    """
    registry = ExpectedLinkRegistry()
    if path.is_dir():
        files = sorted((p for p in path.glob("*.yaml") if p.is_file()), key=lambda p: p.name)
    elif path.is_file():
        files = [path]
    else:
        return registry
    for file in files:
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ExpectedLinkError(f"{file.name}: cannot read file: {exc}") from exc
        registry.merge(parse_expected_links(content, source=file.name))
    return registry


def default_expected_links() -> ExpectedLinkRegistry:
    """The expectations in ``<schema dir>/links`` (``TL_SCHEMA_DIR`` or ``schema/fixtures``)."""
    return load_expected_links(default_schema_dir() / "links")


def unmet_expectations(
    uow: UnitOfWork, record_id: str, expectations: Sequence[ExpectedLink]
) -> list[MissingLink]:
    """The expectations that ``record_id`` does not meet yet, in the order given.

    Counts rows of ``cur_links`` with status ``active`` whose relation equals ``relation``; for
    ``out`` the record is ``from_id``, for ``in`` it is ``to_id``, for ``either`` both are
    counted. When ``target_type`` is set the record at the other end must have that ``type``;
    a voided record at the other end never counts. A link is counted once.
    """
    missing: list[MissingLink] = []
    for expectation in expectations:
        found = _count_matching(uow, record_id, expectation)
        if found < expectation.min_count:
            missing.append(
                MissingLink(expectation=expectation, found=found, needed=expectation.min_count)
            )
    return missing


_COUNT_OUT = (
    "SELECT COUNT(*) FROM cur_links l JOIN cur_core_record r ON r.id = l.to_id "
    "WHERE l.from_id = :id AND l.relation = :relation AND l.status = 'active' AND r.voided = :no"
)
_COUNT_IN = (
    "SELECT COUNT(*) FROM cur_links l JOIN cur_core_record r ON r.id = l.from_id "
    "WHERE l.to_id = :id AND l.relation = :relation AND l.status = 'active' AND r.voided = :no"
)


def _count_matching(uow: UnitOfWork, record_id: str, expectation: ExpectedLink) -> int:
    """How many active links of the expectation's relation and direction the record has."""
    if expectation.direction == "out":
        statements = [_COUNT_OUT]
    elif expectation.direction == "in":
        statements = [_COUNT_IN]
    else:
        # A self-link (not creatable through the commands) would match both ways: count it once.
        statements = [_COUNT_OUT, _COUNT_IN + " AND l.from_id <> l.to_id"]
    total = 0
    for statement in statements:
        params: dict[str, Any] = {
            "id": record_id,
            "relation": expectation.relation,
            "no": False,
        }
        if expectation.target_type is not None:
            statement += " AND r.type = :target_type"
            params["target_type"] = expectation.target_type
        total += int(uow.conn().execute(text(statement), params).scalar_one())
    return total


def missing_expected_links(
    uow: UnitOfWork,
    record_id: str,
    *,
    registry: ExpectedLinkRegistry | None = None,
    by_state: str | None = None,
) -> list[MissingLink]:
    """The unmet expectations of a record, using its type from ``cur_core_record``.

    ``registry`` defaults to ``default_expected_links()``. With ``by_state`` only expectations
    whose ``by_state`` equals it are checked; without it, all of the type's expectations are.
    Raises ``RecordNotFoundError`` when the record does not exist.
    """
    row = (
        uow.conn()
        .execute(text("SELECT type FROM cur_core_record WHERE id = :id"), {"id": record_id})
        .first()
    )
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    record_type = cast(str, row[0])
    if registry is None:
        registry = default_expected_links()
    expectations = registry.for_type(record_type)
    if by_state is not None:
        expectations = [e for e in expectations if e.by_state == by_state]
    return unmet_expectations(uow, record_id, expectations)
