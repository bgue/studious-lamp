"""Expected links (brief 7.1, `tl:expects_link`): what a record should be linked to.

An expectation says "a record of this type should have at least ``min_count`` active links of
``relation`` (in ``direction``) to records of ``target_type``, by workflow state ``by_state``".
Expectations are declared on LinkML classes with the ``tl:expects_link`` annotation (see
``schema/core/annotations.yaml``) and read here as plain YAML. A link satisfies an expectation
only while it is ``active`` and the record at its other end is not voided.

STUB (P0-I3-T04): the models and signatures are final; the bodies marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
        raise NotImplementedError

    def for_type(self, record_type: str) -> list[ExpectedLink]:
        """The expectations of a record type (a new list; empty when there are none)."""
        raise NotImplementedError

    def record_types(self) -> list[str]:
        """Record types that have at least one expectation, sorted."""
        raise NotImplementedError

    def merge(self, other: ExpectedLinkRegistry) -> None:
        """Append every expectation of ``other`` to this registry."""
        raise NotImplementedError


def parse_expected_links(text: str, *, source: str = "<string>") -> ExpectedLinkRegistry:
    """Read the ``tl:expects_link`` annotations of every class in one LinkML YAML document.

    The record type of a class is ``<module>.<ClassName>`` where ``<module>`` is the schema-level
    annotation ``tl:module``. The annotation value is a list of mappings (see ``ExpectedLink``);
    a single mapping is also accepted. A class without the annotation contributes nothing; a
    schema without ``tl:module`` raises. Raises ``ExpectedLinkError`` (message starts with
    ``source``) for invalid YAML, a document that is not a mapping, a missing ``tl:module`` on a
    schema that has expectations, or an entry that is not a valid ``ExpectedLink``.
    """
    raise NotImplementedError


def load_expected_links(path: Path) -> ExpectedLinkRegistry:
    """Read one YAML file, or every ``*.yaml`` file of a directory (not recursive, sorted by name).

    A missing directory gives an empty registry.
    """
    raise NotImplementedError


def default_expected_links() -> ExpectedLinkRegistry:
    """The expectations in ``<schema dir>/links`` (``TL_SCHEMA_DIR`` or ``schema/fixtures``)."""
    raise NotImplementedError


def unmet_expectations(
    uow: UnitOfWork, record_id: str, expectations: Sequence[ExpectedLink]
) -> list[MissingLink]:
    """The expectations that ``record_id`` does not meet yet, in the order given.

    Counts rows of ``cur_links`` with status ``active`` whose relation equals ``relation``; for
    ``out`` the record is ``from_id``, for ``in`` it is ``to_id``, for ``either`` both are
    counted. When ``target_type`` is set the record at the other end must have that ``type``;
    a voided record at the other end never counts. A link is counted once.
    """
    raise NotImplementedError


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
    raise NotImplementedError
