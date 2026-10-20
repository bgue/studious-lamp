"""``impact_report``: what a change of the effective schema touches (brief 27.4, 27.7; T03).

Pure and deterministic: no database, no clock, no file, no randomness. Everything the ledger knows
arrives in ``ImpactFacts``. A path is ``psets.<pset>.<property>`` (layer-aware, see
``EffectiveProperty.relative_key``); a path is added, removed or modified, and a modified path gets
the code of the first group of fields that changed.
"""

from __future__ import annotations

from tl_schema.effective import EffectiveProperty, EffectivePset, EffectiveSchema
from tl_schema.generators.promoted import PromotedColumn, promoted_columns

from tl_mod_schemareg.impact_types import (
    MAX_ENTRIES,
    SECTION_ORDER,
    ImpactEntry,
    ImpactFacts,
    ImpactReport,
    Section,
)

#: Fields of a property that decide its change code; the first group with a difference wins.
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("type_changed", ("kind", "unit", "code_list")),
    ("values_changed", ("enum_values", "enum_meanings", "value_list_policy")),
    ("rule_changed", ("required_in_states", "enforcement", "minimum", "maximum", "pattern")),
    ("definition_changed", ("default", "exact_mappings", "materialize")),
)
_MAPPING_KINDS = frozenset({"mapping", "rule", "endpoint", "enricher", "action"})


def _properties(schema: EffectiveSchema | None) -> dict[str, tuple[str, EffectiveProperty]]:
    """Path to ``(pset name, property)`` for every property of the schema (``{}`` for ``None``).

    The path is ``psets.<pset name>.<prop.relative_key()>``, so a custom property is
    ``psets.valve_data.x.fat_witness_by``.
    """
    found: dict[str, tuple[str, EffectiveProperty]] = {}
    if schema is None:
        return found
    for pset in schema.psets.values():
        for prop in pset.all_properties():
            found[f"psets.{pset.name}.{prop.relative_key()}"] = (pset.name, prop)
    return found


def _change_code(old: EffectiveProperty, new: EffectiveProperty) -> str | None:
    """The code of the first group of ``_GROUPS`` with a field that differs, else ``None``.

    Compare each field of the group with ``getattr(old, f) != getattr(new, f)``. A difference in
    ``label``, ``description``, ``origin`` or ``order`` alone is not a change.
    """
    for code, fields in _GROUPS:
        if any(getattr(old, field) != getattr(new, field) for field in fields):
            return code
    return None


def _columns(schema: EffectiveSchema | None) -> dict[str, PromotedColumn]:
    """Promoted columns by column name (``{}`` for ``None``): ``promoted_columns(schema)``."""
    if schema is None:
        return {}
    return {column.name: column for column in promoted_columns(schema)}


def _pset_of(path: str, schema: EffectiveSchema) -> EffectivePset | None:
    """The property set a path ``psets.<pset>.<property>`` names, or ``None``.

    A pset name may hold dots (``prj.shutdown_tie_in``), so the name is the longest one in the
    schema that the path continues with a dot.
    """
    if not path.startswith("psets."):
        return None
    rest = path[len("psets.") :]
    best: str | None = None
    for name in schema.psets:
        if rest.startswith(f"{name}.") and (best is None or len(name) > len(best)):
            best = name
    return schema.psets[best] if best is not None else None


def impact_report(
    old: EffectiveSchema | None, new: EffectiveSchema, facts: ImpactFacts
) -> ImpactReport:
    """The impact of moving a scope from ``old`` (or from nothing) to ``new``.

    Pure and deterministic: the same arguments give the same report, entries in a fixed order.
    """
    old_props = _properties(old)
    new_props = _properties(new)

    # path -> change code, for paths added, removed or modified
    codes: dict[str, str] = {}
    for path in old_props.keys() | new_props.keys():
        if path not in old_props:
            codes[path] = "property_added"
        elif path not in new_props:
            codes[path] = "property_removed"
        else:
            code = _change_code(old_props[path][1], new_props[path][1])
            if code is not None:
                codes[path] = code

    entries: list[ImpactEntry] = []

    # records: removed and modified paths that hold at least one value
    hurt = {path: code for path, code in codes.items() if code != "property_added"}
    for path in sorted(hurt):
        count = facts.value_counts.get(path, 0)
        if count > 0:
            if hurt[path] == "property_removed":
                what = "the values stay in history and the lake and leave the forms"
            else:
                what = "they are checked again against the new definition"
            entries.append(
                ImpactEntry(
                    section="records",
                    target=path,
                    change=hurt[path],
                    count=count,
                    detail=f"{count} record(s) hold a value at {path}; {what}",
                )
            )

    # columns: promoted columns of cur_core_record
    old_columns = _columns(old)
    new_columns = _columns(new)
    for name in sorted(old_columns.keys() | new_columns.keys()):
        if name not in old_columns:
            column_type = new_columns[name].linkml_type
            entries.append(
                ImpactEntry(
                    section="columns",
                    target=name,
                    change="column_added",
                    detail=f"cur_core_record gains the column {name} ({column_type})",
                )
            )
        elif name not in new_columns:
            entries.append(
                ImpactEntry(
                    section="columns",
                    target=name,
                    change="column_dropped",
                    detail=f"the column {name} stays in cur_core_record and is no longer written",
                )
            )
        elif old_columns[name].linkml_type != new_columns[name].linkml_type:
            old_type = old_columns[name].linkml_type
            new_type = new_columns[name].linkml_type
            entries.append(
                ImpactEntry(
                    section="columns",
                    target=name,
                    change="column_type_changed",
                    detail=f"the column {name} changes type from {old_type} to {new_type}",
                )
            )

    # views: regenerated when the columns or the set of properties change
    if old_columns.keys() != new_columns.keys() or any(
        code in ("property_added", "property_removed") for code in codes.values()
    ):
        entries.append(
            ImpactEntry(
                section="views",
                target=f"project views of {new.scope}",
                change="views_regenerated",
                detail="the generated views are rebuilt for the new set of properties and columns",
            )
        )

    # mappings and reports that name a removed or modified path
    for ref in facts.references:
        if ref.path not in hurt:
            continue
        section: Section
        if ref.kind == "report":
            section = "reports"
        elif ref.kind in _MAPPING_KINDS:
            section = "mappings"
        else:
            continue
        verb = "is removed" if hurt[ref.path] == "property_removed" else "has changed"
        entries.append(
            ImpactEntry(
                section=section,
                target=f"{ref.kind} {ref.name}",
                change=hurt[ref.path],
                detail=f"{ref.kind} {ref.name} names {ref.path}, which {verb}",
            )
        )

    # mcp_schemas: the tool input schemas of the record types whose psets change
    collected: dict[str, set[str]] = {}
    for path in codes:
        pset = _pset_of(path, new) or (_pset_of(path, old) if old is not None else None)
        if pset is None:
            continue
        for record_type in pset.applies_to:
            collected.setdefault(record_type, set()).add(path)
    for record_type in sorted(collected):
        count = len(collected[record_type])
        noun = "property" if count == 1 else "properties"
        entries.append(
            ImpactEntry(
                section="mcp_schemas",
                target=f"{record_type} tool input schema",
                change="schema_regenerated",
                detail=f"the input schema for {record_type} changes ({count} {noun})",
            )
        )

    entries.sort(key=lambda entry: (SECTION_ORDER.index(entry.section), entry.target, entry.change))
    truncated = len(entries) > MAX_ENTRIES
    kept = entries[:MAX_ENTRIES]
    counts: dict[str, int] = {}
    for section_name in SECTION_ORDER:
        n = sum(1 for entry in kept if entry.section == section_name)
        if n:
            counts[section_name] = n

    return ImpactReport(
        scope=new.scope,
        old_hash=old.hash if old is not None else None,
        new_hash=new.hash,
        changed_paths=tuple(sorted(codes)),
        entries=tuple(kept),
        counts=counts,
        truncated=truncated,
    )
