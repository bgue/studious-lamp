"""Load a standards document into the ledger: one edition becomes registry records.

``plan_load`` reads the registry and says, for each entry of the document, whether loading would
create it or skip it; it writes nothing. ``load_standards`` does it: code lists with their values
(in file order, sort order 10, 20, ...), mnemonics, numbering patterns, then tag classes, all in
the caller's unit of work with one correlation id, through the registry commands, so every rule of
those commands applies. The caller commits, so a failure anywhere leaves nothing behind.

Loading is idempotent. An entry is skipped when the registry already holds its code: a list,
mnemonic or pattern of the same code (any edition), a value of the same list and code, a tag class
of the same code. A second edition of a standard is therefore not loaded by this function: its
entries change through the individual commands, where each change is a decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Connection
from tl_core.schema_provider import get_provider
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_engineering import registry
from tl_mod_engineering.document import StandardsDoc
from tl_mod_engineering.errors import StandardsLoadError
from tl_mod_engineering.handlers.standards import (
    AddCodeValue,
    RegisterCodeList,
    RegisterMnemonic,
    RegisterNumberingPattern,
    handle_add_code_value,
    handle_register_code_list,
    handle_register_mnemonic,
    handle_register_numbering_pattern,
)
from tl_mod_engineering.handlers.tag_class import DefineTagClass, handle_define_tag_class
from tl_mod_engineering.names import COMPANY

ItemKind = Literal["code_list", "code_value", "mnemonic", "numbering_pattern", "tag_class"]


@dataclass(frozen=True)
class LoadItem:
    """One entry of the document and what loading does with it."""

    kind: ItemKind
    code: str  # ``Area``, ``Area.10`` for a value, ``FV``, ``tag``, ``ControlValve``
    action: Literal["create", "skip"]
    reason: str | None = None  # why it is skipped


@dataclass(frozen=True)
class LoadReport:
    """The outcome (or, for ``plan_load``, the expectation) of loading one document."""

    edition: str
    items: list[LoadItem]

    def count(self, kind: ItemKind, action: Literal["create", "skip"]) -> int:
        return sum(1 for item in self.items if item.kind == kind and item.action == action)

    @property
    def created(self) -> int:
        return sum(1 for item in self.items if item.action == "create")

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.items if item.action == "skip")


def _skip_standard(conn: Connection, kind: str, code: str, edition: str) -> str | None:
    found = registry.find_standards(conn, scope=COMPANY, kind=kind, code=code)
    if not found:
        return None
    if any(row.edition == edition for row in found):
        return "already registered"
    return f"already registered in {found[-1].edition}"


def _problems(doc: StandardsDoc) -> list[str]:
    """What the company effective schema cannot satisfy: a required pset it does not define."""
    schema = get_provider().effective(COMPANY)
    found: list[str] = []
    for tag_class in doc.tag_classes:
        for name in tag_class.required_psets:
            if schema.find_pset(name) is None:
                found.append(
                    f"tag class {tag_class.code}: pset {name!r} is not in the company schema"
                )
    return found


def plan_load(conn: Connection, doc: StandardsDoc) -> LoadReport:
    """What ``load_standards`` would do with ``doc`` on this ledger, in loading order."""
    items: list[LoadItem] = []

    def standard(kind: ItemKind, code: str) -> bool:
        reason = _skip_standard(conn, kind, code, doc.edition)
        items.append(LoadItem(kind, code, "skip" if reason else "create", reason))
        return reason is None

    for name, code_list in doc.code_lists.items():
        standard("code_list", name)
        have = {row.code for row in registry.code_values(conn, COMPANY, name)}
        for value in code_list.values:
            skip = value.code in have
            items.append(
                LoadItem(
                    "code_value",
                    f"{name}.{value.code}",
                    "skip" if skip else "create",
                    "already defined" if skip else None,
                )
            )
    for mnemonic in doc.mnemonics:
        standard("mnemonic", mnemonic.code)
    for pattern in doc.numbering_patterns:
        standard("numbering_pattern", pattern.code)
    for tag_class in doc.tag_classes:
        taken = registry.find_tag_classes(conn, COMPANY, code=tag_class.code)
        items.append(
            LoadItem(
                "tag_class",
                tag_class.code,
                "skip" if taken else "create",
                "already defined" if taken else None,
            )
        )
    return LoadReport(edition=doc.edition, items=items)


def load_standards(
    uow: UnitOfWork,
    doc: StandardsDoc,
    *,
    actor: str,
    source: str,
    correlation_id: str | None = None,
) -> LoadReport:
    """Register every entry of ``doc`` that the ledger does not hold yet.

    Raises ``StandardsLoadError`` before anything is written when a tag class requires a pset the
    company schema does not define; the registry commands' own errors propagate from the entry that
    fails. All commands share ``correlation_id`` (a new one when ``None``).
    """
    plan = plan_load(uow.conn(), doc)
    problems = _problems(doc)
    if problems:
        raise StandardsLoadError(
            f"{doc.edition} cannot be loaded: " + "; ".join(problems), problems=problems
        )
    todo = {(item.kind, item.code) for item in plan.items if item.action == "create"}
    common: dict[str, Any] = {
        "actor": actor,
        "source": source,
        "scope": COMPANY,
        "correlation_id": correlation_id or new_ulid(),
    }
    for name, code_list in doc.code_lists.items():
        if ("code_list", name) in todo:
            handle_register_code_list(
                uow,
                RegisterCodeList(
                    **common,
                    code=name,
                    label=code_list.label,
                    definition=code_list.definition,
                    edition=doc.edition,
                    owner=code_list.owner or doc.owner,
                    adoption=code_list.adoption,
                    effective_from=doc.effective_from,
                    value_list_policy=code_list.value_list_policy,
                ),
            )
        for position, value in enumerate(code_list.values, start=1):
            if ("code_value", f"{name}.{value.code}") in todo:
                handle_add_code_value(
                    uow,
                    AddCodeValue(
                        **common,
                        code_list=name,
                        code=value.code,
                        label=value.label,
                        meaning=value.meaning,
                        sort_order=position * 10,
                        effective_from=value.effective_from or doc.effective_from,
                        effective_to=value.effective_to,
                        attributes=value.attributes,
                        edition=doc.edition,
                    ),
                )
    for mnemonic in doc.mnemonics:
        if ("mnemonic", mnemonic.code) in todo:
            handle_register_mnemonic(
                uow,
                RegisterMnemonic(
                    **common,
                    code=mnemonic.code,
                    label=mnemonic.label,
                    definition=mnemonic.definition,
                    edition=doc.edition,
                    owner=doc.owner,
                    effective_from=doc.effective_from,
                    class_hint=mnemonic.class_hint,
                    discipline=mnemonic.discipline,
                ),
            )
    for pattern in doc.numbering_patterns:
        if ("numbering_pattern", pattern.code) in todo:
            handle_register_numbering_pattern(
                uow,
                RegisterNumberingPattern(
                    **common,
                    code=pattern.code,
                    label=pattern.label,
                    definition=pattern.definition,
                    edition=doc.edition,
                    owner=doc.owner,
                    effective_from=doc.effective_from,
                    record_type=pattern.record_type,
                    template=pattern.template,
                    segments=pattern.segments,
                    allocate=pattern.allocate,
                    gap_free=pattern.gap_free,
                    scope_selector=pattern.scope,
                    reserved=pattern.reserved,
                ),
            )
    for tag_class in doc.tag_classes:
        if ("tag_class", tag_class.code) in todo:
            handle_define_tag_class(
                uow,
                DefineTagClass(
                    **common,
                    code=tag_class.code,
                    label=tag_class.label,
                    definition=tag_class.definition,
                    family=tag_class.family,
                    required_psets=tag_class.required_psets,
                    itr_templates=tag_class.itr_templates,
                    mnemonics=tag_class.mnemonics,
                    edition=doc.edition,
                ),
            )
    return plan
