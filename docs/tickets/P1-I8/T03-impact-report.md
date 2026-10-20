# P1-I8-T03 — Impact report of a schema change

Status: ready
Tier: haiku
Labels: core, schema-registry
Depends on: P1-I8-S1 (the classification engine) and P1-I8-S2 (the schema registry module `tl_mod_schemareg`) on `p1/i8`; no other ticket
Branch: `p1/i8-t03-impact-report`

## Goal
Before a package version goes to review, and before a project pins one, a person reads what the change touches. `packages/tl-modules/schemareg/src/tl_mod_schemareg/impact.py` holds the pure function `impact_report(old, new, facts)`: it compares two effective schemas and says which records hold values at changed paths, which promoted columns appear or stay, whether the generated views are rebuilt, which mappings and reports name a changed path, and which MCP tool input schemas change. Today three helpers raise `NotImplementedError` and `impact_report` answers "nothing is touched". You implement the helpers and the function by their STEPS comments, so the one provided test file passes. The workbench, `tl schema impact` and the adoption command read this report.

## Brief references (pasted)
> **Brief 27.4.** A `SchemaPackage` is itself a ledgered record: name, namespace, semver, owner, dependencies, content (LinkML YAML), changelog, **classification report, impact report**, approvals. *Adoption is per project: constraining or renaming versions need the project data manager to adopt after reviewing their project-specific impact report.*
>
> **Brief 27.7 (propagation on publish/adopt).**
>
> | Target | What happens |
> |---|---|
> | Current-state tables | DDL diff: new promoted columns, regenerated project views; type changes trigger a shadow rebuild of that type only |
> | Conformance | Re-evaluated asynchronously for affected records |
> | MCP | Tool input schemas regenerated; `tools/list_changed` sent to connected agents |
> | Webhooks & inbound mappings | Paths checked against the new schema; broken mappings flagged |
> | Saved views, reports, rules, overlays | Path references validated and aliased; broken ones listed in the impact report |
> | Lakehouse | Table schemas evolved (add columns; renames via view aliases); history preserved |

### Specification
- Pure and deterministic: no database, no clock, no file, no randomness. Everything the ledger knows arrives in `facts`.
- A *path* is layer-aware: `psets.valve_data.size_in`, and `psets.valve_data.x.fat_witness_by` for a custom-section property (`prop.relative_key()` gives `size_in` or `x.fat_witness_by`).
- A path is *added* when only the new schema has it, *removed* when only the old one has it, *modified* when both have it and `_change_code` finds a difference. `old` may be `None` (a first schema): then every path is added and every promoted column is new.
- The records section lists only removed and modified paths that hold at least one value (`facts.value_counts`). An added path has no values to be hurt.
- Entries, counts and `changed_paths` follow the STEPS exactly; the strings in `detail` are compared by the tests.
- `MAX_ENTRIES` must be read from this module's namespace when the function runs (a test patches `tl_mod_schemareg.impact.MAX_ENTRIES`).

### Learnings that apply
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused (`Reference`, `ImpactEntry`... whichever the finished file does not use).
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes: run it with a 600 000 ms timeout (or in the background and wait for it). Run `uv run ruff format <file>` first: the format check rewrites a hand-wrapped line.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns. pyright is strict for `tl_schema` and `tl_core`; this package runs as `standard`.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/schemareg/src/tl_mod_schemareg/impact_types.py` (fixed; do not edit):
```python
"""The shapes of the impact report (brief 27.4, 27.7; P1-I8-T03).

An impact report says what a change of the effective schema touches: the records that hold values
at changed paths, the promoted columns of the current-state tables, the regenerated views, the
mappings and reports that name a changed path, and the MCP tool schemas that change. It is made
from two effective schemas and the ``ImpactFacts`` read from the ledger, by the pure function
``tl_mod_schemareg.impact.impact_report``; nothing here touches a database.

The report is data a reviewer reads and an adopter acknowledges: ``digest`` is the SHA-256 of its
canonical JSON, so "I read this report" is a hash the adoption command checks.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

Section = Literal["records", "columns", "views", "mappings", "reports", "mcp_schemas"]

#: Order of the sections in a report and in its counts.
SECTION_ORDER: tuple[Section, ...] = (
    "records",
    "columns",
    "views",
    "mappings",
    "reports",
    "mcp_schemas",
)

#: A report holds at most this many entries; ``truncated`` says when it was cut.
MAX_ENTRIES = 500

ReferenceKind = Literal["mapping", "rule", "endpoint", "enricher", "action", "report"]


@dataclass(frozen=True)
class Reference:
    """Something outside the registry that names a property path (a mapping, a rule, a report)."""

    kind: ReferenceKind
    name: str  # the thing's own name or key, for example the document schema code
    path: str  # a layer-aware path as written: ``psets.valve_data.size_in``


@dataclass(frozen=True)
class ImpactFacts:
    """What the ledger says about the paths of a change, gathered before the pure function runs.

    ``value_counts`` maps a layer-aware property path (``psets.valve_data.size_in``) to the number
    of records that hold a current value there, in the scope of the report. ``references`` are the
    things that name a path, found by scanning stored mappings, rules, endpoints, enrichers,
    actions and the registered reports. A path with no entry holds no value / is named by nothing.
    """

    value_counts: Mapping[str, int] = field(default_factory=lambda: {})
    references: Sequence[Reference] = ()


class ImpactEntry(BaseModel):
    """One thing the change touches."""

    model_config = ConfigDict(frozen=True)

    section: Section
    target: str  # what is touched: a path, a column, a view, a mapping or report name
    change: str  # why: a code such as ``property_removed`` or ``column_added``
    count: int | None = None  # records affected, where that has a meaning
    detail: str  # one sentence a person reads


class ImpactReport(BaseModel):
    """What a change of the effective schema of ``scope`` touches."""

    model_config = ConfigDict(frozen=True)

    scope: str
    old_hash: str | None  # None when there was no schema before
    new_hash: str
    changed_paths: tuple[
        str, ...
    ]  # sorted; the paths whose definition was added, removed or changed
    entries: tuple[ImpactEntry, ...]  # ordered by section, then target, then change
    counts: dict[str, int]  # entries per section that has any
    truncated: bool  # entries were cut at ``MAX_ENTRIES``

    @property
    def digest(self) -> str:
        """SHA-256 of the canonical JSON of the report."""
        return report_digest(self)


def report_digest(report: ImpactReport) -> str:
    body = json.dumps(
        report.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def empty_report(scope: str, old_hash: str | None, new_hash: str) -> ImpactReport:
    """A report that says nothing is touched."""
    return ImpactReport(
        scope=scope,
        old_hash=old_hash,
        new_hash=new_hash,
        changed_paths=(),
        entries=(),
        counts={},
        truncated=False,
    )
```

`packages/tl-modules/schemareg/src/tl_mod_schemareg/impact.py` (the stub you complete; the whole file):
```python
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
```

From `tl_schema.effective` (read-only): `EffectiveSchema` has `scope`, `hash`, `psets: dict[str, EffectivePset]`; `EffectivePset` has `applies_to: list[str]`, `properties`, `custom` and `all_properties()`; `EffectiveProperty` has the fields named in `_GROUPS`, plus `name`, `layer`, `label`, `description`, `origin`, `order` and `relative_key()`. From `tl_schema.generators.promoted`: `promoted_columns(schema) -> list[PromotedColumn]`; a `PromotedColumn` has `name`, `pset`, `property` and `linkml_type`.

## Context (read these, nothing else)
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/impact.py`
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/impact_types.py`
- `docs/tickets/P1-I8/provided/t03-test_impact.py.txt`
- `packages/tl-schema/src/tl_schema/effective.py` (the `EffectiveProperty` and `EffectivePset` classes only)
- `packages/tl-schema/src/tl_schema/generators/promoted.py` (`promoted_columns` and `PromotedColumn`)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/impact.py` (modify)
- `packages/tl-modules/schemareg/tests/test_impact.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T03.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I8/provided/t03-test_impact.py.txt packages/tl-modules/schemareg/tests/test_impact.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; it fails (22 of 28 cases) against the stub.
3. Implement `_properties`, `_change_code`, `_columns` and `impact_report` by the STEPS. Remove the STUB paragraph of the docstring, the two directive lines at the top, every STEPS comment and the placeholder `return` at the end. Remove imports the finished file does not use.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-modules/schemareg
uv run pytest packages/tl-modules/schemareg/tests/test_impact.py -q
uv run pytest packages/tl-modules/schemareg -q
just check
```
Expected: `28 passed` for the provided file (21 test functions; one is parametrized over 8 cases); the whole module passes (it has 62 other tests); `just check` is clean (run it with a 600 000 ms timeout).

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T03.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test case fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change `impact_types.py`, the test, or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
