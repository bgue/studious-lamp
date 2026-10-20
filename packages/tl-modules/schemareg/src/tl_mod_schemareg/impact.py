# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false
"""``impact_report``: what a change of the effective schema touches (brief 27.4, 27.7; T03).

STUB: this file is the interface P1-I8-T03 implements. Until then it answers "nothing is touched".
Remove this paragraph, the two directive lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_schema.effective import EffectiveProperty, EffectiveSchema
from tl_schema.generators.promoted import PromotedColumn, promoted_columns

from tl_mod_schemareg.impact_types import (
    MAX_ENTRIES,
    SECTION_ORDER,
    ImpactEntry,
    ImpactFacts,
    ImpactReport,
    Reference,
    Section,
    empty_report,
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
    ``psets.valve_data.x.fat_witness_by``. Walk ``schema.psets`` and ``pset.all_properties()``.
    """
    raise NotImplementedError("STEPS: see the docstring")


def _change_code(old: EffectiveProperty, new: EffectiveProperty) -> str | None:
    """The code of the first group of ``_GROUPS`` with a field that differs, else ``None``.

    Compare each field of the group with ``getattr(old, f) != getattr(new, f)``. A difference in
    ``label``, ``description``, ``origin`` or ``order`` alone is not a change.
    """
    raise NotImplementedError("STEPS: see the docstring")


def _columns(schema: EffectiveSchema | None) -> dict[str, PromotedColumn]:
    """Promoted columns by column name (``{}`` for ``None``): ``promoted_columns(schema)``."""
    raise NotImplementedError("STEPS: see the docstring")


def impact_report(
    old: EffectiveSchema | None, new: EffectiveSchema, facts: ImpactFacts
) -> ImpactReport:
    """The impact of moving a scope from ``old`` (or from nothing) to ``new``.

    Pure and deterministic: the same arguments give the same report, entries in a fixed order.
    """
    # STEPS
    # 1. codes: path -> code for every path that is in only one schema ("property_added" when only
    #    new has it, "property_removed" when only old has it) or in both with
    #    _change_code(...) not None (that code). Use _properties(old) and _properties(new).
    # 2. hurt = codes without the "property_added" paths. For each path in sorted(hurt) whose
    #    facts.value_counts.get(path, 0) is above 0 add a "records" entry: target the path,
    #    change hurt[path], count that number, detail
    #    f"{n} record(s) hold a value at {path}; {what}" where what is
    #    "the values stay in history and the lake and leave the forms" for a removed property and
    #    "they are checked again against the new definition" otherwise.
    # 3. columns: for each column name in sorted(old columns | new columns): only in new ->
    #    change "column_added", detail f"cur_core_record gains the column {name} ({linkml_type})";
    #    only in old -> "column_dropped", detail
    #    f"the column {name} stays in cur_core_record and is no longer written"; in both with a
    #    different linkml_type -> "column_type_changed", detail
    #    f"the column {name} changes type from {old_type} to {new_type}". Section "columns", target
    #    the column name.
    # 4. views: when the set of column names differs, or any code is "property_added" or
    #    "property_removed", add one "views" entry: target f"project views of {new.scope}", change
    #    "views_regenerated", detail
    #    "the generated views are rebuilt for the new set of properties and columns".
    # 5. mappings and reports: for each ref in facts.references (in the order given) whose path is
    #    in hurt: section "reports" when ref.kind == "report", else "mappings" (only for the kinds
    #    in _MAPPING_KINDS); target f"{ref.kind} {ref.name}", change hurt[ref.path], detail
    #    f"{ref.kind} {ref.name} names {ref.path}, which {verb}" with verb "is removed" for a
    #    removed property and "has changed" otherwise.
    # 6. mcp_schemas: for each path in codes (added ones too) find its pset (name = the second
    #    dot-separated part of the path) in new.psets, else in old.psets; each record type in
    #    pset.applies_to collects the path. For each record type in sorted order add an entry:
    #    target f"{record_type} tool input schema", change "schema_regenerated", detail
    #    f"the input schema for {record_type} changes ({n} property)" with "propert" + "y" when
    #    n == 1 and "ies" otherwise (n = how many paths the type collected).
    # 7. sort the entries by (SECTION_ORDER.index(section), target, change). truncated is
    #    len(entries) > MAX_ENTRIES (read the module name MAX_ENTRIES at call time, a test
    #    patches it); keep entries[:MAX_ENTRIES]; counts is the number of KEPT entries per
    #    section, in SECTION_ORDER, only sections that have any.
    # 8. return ImpactReport(scope=new.scope, old_hash=old.hash or None when old is None,
    #    new_hash=new.hash, changed_paths=tuple(sorted(codes)), entries=..., counts=...,
    #    truncated=...).
    # Remove the line below when the steps are done.
    return empty_report(new.scope, old.hash if old is not None else None, new.hash)
