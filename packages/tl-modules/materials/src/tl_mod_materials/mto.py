"""The MTO seam: the ``mto`` publish target, ``PublishDerivedMto``, ``AssignMtoLines`` (S4).

``commands.py`` and ``actions.py`` splat ``MTO_COMMANDS`` and ``MTO_RULES``; the work is in
``handlers/mto.py``. The MTO events (``MTO.Defined``, ``MTOLine.Defined``, ``MTOLine.Assigned``)
project in ``projectors/mto.py``. ``mto_target()`` is the entry point ``mto`` of the group
``throughline.publish_targets``: it plans, creates and reverses a take-off for the documents
module's publication pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection
from tl_core.uow import UnitOfWork
from tl_mod_documents.derivation.publish_targets import PublishTarget

from tl_mod_materials.common import CommandSpec
from tl_mod_materials.handlers.mto import (
    MAPPING_FIELDS,
    TARGET_MTO,
    AssignMtoLines,
    PublishDerivedMto,
    compensate_mto,
    compensation_check,
    create_mto,
    handle_assign_mto_lines,
    handle_publish_derived_mto,
    plan_mto,
)
from tl_mod_materials.names import MTO, MTO_LINE

PUBLISH = "materials.mto.publish"
ASSIGN = "materials.mto.assign"


@dataclass(frozen=True)
class MtoRule:
    """A command a screen may offer on a record (the five names ``actions.rule_rows`` reads)."""

    record_type: str
    condition: str
    label: str
    command: str
    word: str


MTO_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(PublishDerivedMto, handle_publish_derived_mto, PUBLISH),
    CommandSpec(AssignMtoLines, handle_assign_mto_lines, ASSIGN),
)
MTO_RULES: tuple[MtoRule, ...] = (
    MtoRule(MTO_LINE, "no reservation", "Assign to work package", "AssignMtoLines", ASSIGN),
)


class _MtoPublishTarget:
    """The ``mto`` publish target: a take-off and its lines from a derived document."""

    name = TARGET_MTO
    module = "materials"
    record_type = MTO
    #: What a mapping may send a column to.
    mapping_fields = MAPPING_FIELDS
    #: A take-off takes no property sets (the generic ``SetPsetValues`` is not on its allow-list).
    takes_provenance = False

    def plan_rows(self, conn: Any, scope: str, mapped: list[Any]) -> tuple[Any, Any, Any]:
        raise NotImplementedError("the mto target plans with its derived document (plan_rows_for)")

    def plan_rows_for(
        self, conn: Connection, scope: str, derived: Any, mapped: list[Any]
    ) -> tuple[Any, Any, Any]:
        return plan_mto(conn, scope, derived, mapped)

    def create(
        self, uow: UnitOfWork, base: dict[str, Any], built: Any, provenance: dict[str, str]
    ) -> list[str]:
        return create_mto(uow, base, built, provenance)

    def compensation_item(
        self, conn: Connection, record_id: str, scope: str
    ) -> tuple[bool, str | None]:
        return compensation_check(conn, record_id, scope)

    def reverse(self, uow: UnitOfWork, base: dict[str, Any], record_id: str, reason: str) -> None:
        compensate_mto(uow, base, record_id, reason)


def mto_target() -> PublishTarget:
    """Entry point ``mto`` of the group ``throughline.publish_targets``."""
    return _MtoPublishTarget()
