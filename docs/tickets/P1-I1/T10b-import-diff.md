# P1-I1-T10b — Import diff: new, changed, unchanged, removed, invalid

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I1-S3 (`imports/model.py`, on `p1/i1`); no other ticket
Branch: `p1/i1-t10b-import-diff`

## Goal
The second step of a bulk tag import: compare the rows of a tag list with the tags a project already holds and say what an import
would do, before it does anything. `imports/diff.py` has three functions with their signatures and docstrings final and their
bodies raising `NotImplementedError` (`same_value`, `row_changes`, `plan_import`) and one helper that is done
(`_existing_value`). You implement the three. One provided test file (`13` test functions, 22 cases) must pass.

## Brief references (pasted)
> **Brief 9 M2 Behaviour.** Bulk import from derived documents (instrument index, line list, equipment list) with diff preview: new / changed / removed tags, property changes per pset. Property values carry source provenance (which document revision supplied them).

### Specification
- Everything is pure: no database, no ledger, no clock.
- A file only changes what it states: a row field that is `None`, and a pset property the row does not mention, are never a change. A value the tag lacks (`None` in the tag) and the row states is a change even when the row's value is falsy (`0`, `False`).
- `same_value`: a `bool` equals only a `bool` of the same value (`True` is not `1`); two numbers are equal when `float(a) == float(b)` (`4` equals `4.0`); everything else by `==`.
- `row_changes` keeps a fixed order: `class`, `service`, then `psets.<pset>.<property>` sorted by pset then property. The property key may be `x.name` for a custom property: `psets.valve_data.x.fat_by`. A tag stores a custom property under `psets["valve_data"]["x"]["fat_by"]`; `_existing_value` already reads that.
- `plan_import` rules, in the order the rows come:
  - a row with `problems` is `invalid` and takes no further part;
  - a later row with a number an earlier *valid* row already used is `invalid`: a new `ImportRow` with the same fields and `problems=["duplicate of row <n>"]` where `<n>` is the first row's `line`;
  - a valid row with no existing tag of that number is `new`; with one, `changed` (a `RowChange`) if `row_changes` finds anything, else its number goes to `unchanged`;
  - `removed` holds every existing tag whose number no row mentions (valid or not, any non-empty number counts), sorted by number.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/engineering/src/tl_mod_engineering/imports/diff.py` (the stub you complete):
```python
"""Comparing a tag list with the tags a project holds (brief 9 M2; P1-I1-T10b).

``plan_import`` is pure: it reads ``ImportRow`` values (``mapping.read_rows``) and ``ExistingTag``
values and returns an ``ImportPlan``. A row that is blank in the file leaves the tag's value alone:
the file only changes what it states.

STUB (P1-I1-T10b): ``same_value``, ``row_changes`` and ``plan_import`` raise NotImplementedError;
the signatures, the docstrings and ``_existing_value`` are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the ``ruff: noqa`` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_mod_engineering.imports.model import (
    ExistingTag,
    FieldChange,
    ImportPlan,
    ImportRow,
    RowChange,
)


def same_value(old: Any, new: Any) -> bool:
    """Equal values; a number equals the same number written as int or float, a bool is a bool."""
    # STEPS
    # 1. If either value is a bool: equal only when both are bools and equal.
    # 2. Else if both are int or float: compare float(old) == float(new).
    # 3. Else old == new, as a bool.
    raise NotImplementedError


def _existing_value(psets: dict[str, Any], pset: str, key: str) -> Any:
    """The value of ``pset.key`` (``key`` may be ``x.name`` for a custom property), or ``None``."""
    node: Any = psets.get(pset)
    for part in key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def row_changes(row: ImportRow, existing: ExistingTag) -> list[FieldChange]:
    """The fields the row states that differ from ``existing``, in a fixed order.

    Order: ``class``, ``service``, then ``psets.<pset>.<property>`` sorted by name. A field the row
    leaves unset (``None``, or a pset property it does not mention) is never a change.
    """
    # STEPS
    # 1. changes = []. If row.class_code is not None and differs from existing.class_code, append
    #    FieldChange("class", existing.class_code, row.class_code).
    # 2. If row.service is not None and differs from existing.service, append
    #    FieldChange("service", existing.service, row.service).
    # 3. For pset in sorted(row.psets), for key in sorted(row.psets[pset]): new = the row's value,
    #    old = _existing_value(existing.psets, pset, key). If old is None or not
    #    same_value(old, new), append FieldChange(f"psets.{pset}.{key}", old, new).
    # 4. return changes.
    raise NotImplementedError


def plan_import(rows: Sequence[ImportRow], existing: Sequence[ExistingTag]) -> ImportPlan:
    """What importing ``rows`` into a project that holds ``existing`` would do.

    * A row with ``problems`` is ``invalid`` and takes no further part.
    * A second row with a number an earlier row already used is ``invalid`` too: a copy of the row
      with the problem ``duplicate of row <n>`` added (the first one is judged on its own).
    * A valid row whose number no existing tag has is ``new``.
    * A valid row whose number matches an existing tag is ``changed`` when ``row_changes`` finds
      anything, else its number is ``unchanged``.
    * An existing tag no row of the file mentions, valid or not, is ``removed``.

    Every list keeps file order; ``removed`` is ordered by number.
    """
    # STEPS
    # 1. by_number = {tag.number: tag for tag in existing}; plan = ImportPlan();
    #    first_seen: dict[str, int] = {} (number to the row number of its first valid row);
    #    mentioned: set[str] = set() (every non-empty row.number, valid or not).
    # 2. For each row in order: add row.number to mentioned when it is not empty. If row.problems:
    #    append the row to plan.invalid and continue.
    # 3. If row.number is already in first_seen: append to plan.invalid a new ImportRow with the
    #    row's own fields (line, number, class_code, service, psets, raw) and
    #    problems=[f"duplicate of row {first_seen[row.number]}"]; continue.
    # 4. first_seen[row.number] = row.line. tag = by_number.get(row.number). If tag is None, append
    #    the row to plan.new. Else changes = row_changes(row, tag): if there are any, append
    #    RowChange(row.line, row.number, tag.id, changes) to plan.changed, else append row.number
    #    to plan.unchanged.
    # 5. plan.removed = the existing tags whose number is not in mentioned, sorted by number.
    # 6. return plan.
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/imports/model.py`:
```python
"""The values the tag-list import passes between its steps (brief 9 M2, bulk import).

``mapping.read_rows`` turns a file into ``ImportRow`` values; ``diff.plan_import`` compares them
with the tags the project already has (``ExistingTag``) and returns an ``ImportPlan``: what would
be created, changed or left out, and which rows cannot be imported. Nothing here touches the
ledger; applying a plan is ``tl_mod_engineering.imports.apply``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportRow:
    """One data row of the file, after the mapping."""

    line: int  # row number of the file; the header is row 1, so the first data row is 2
    number: str  # the tag number as written (stripped); empty when the cell was blank
    class_code: str | None  # the mapped class code; None when the cell was blank
    service: str | None  # the service description (becomes the tag's title); None when blank
    psets: dict[str, dict[str, Any]]  # {"valve_data": {"size_in": 4.0}}; blank cells are absent
    problems: list[str] = field(default_factory=lambda: [])  # why the row cannot be used
    raw: dict[str, str] = field(default_factory=lambda: {})  # the row by column header


@dataclass(frozen=True)
class ExistingTag:
    """A tag the project already holds, as far as the import compares it."""

    id: str
    number: str
    class_code: str | None
    service: str  # the record title
    psets: dict[str, Any]  # the record's psets object
    version: int


@dataclass(frozen=True)
class FieldChange:
    field: str  # "class", "service" or "psets.<pset>.<property>"
    old: Any
    new: Any


@dataclass(frozen=True)
class RowChange:
    line: int
    number: str
    tag_id: str
    changes: list[FieldChange]


@dataclass
class ImportPlan:
    new: list[ImportRow] = field(default_factory=lambda: [])
    changed: list[RowChange] = field(default_factory=lambda: [])
    unchanged: list[str] = field(default_factory=lambda: [])  # tag numbers
    removed: list[ExistingTag] = field(default_factory=lambda: [])  # not in the file
    invalid: list[ImportRow] = field(default_factory=lambda: [])  # rows that cannot be imported

    def counts(self) -> dict[str, int]:
        """``{"new": 3, "changed": 1, "unchanged": 10, "removed": 0, "invalid": 2}``."""
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "removed": len(self.removed),
            "invalid": len(self.invalid),
        }
```

## Context (read these, nothing else)
- `packages/tl-modules/engineering/src/tl_mod_engineering/imports/diff.py` (the file you edit)
- `packages/tl-modules/engineering/src/tl_mod_engineering/imports/model.py`
- `docs/tickets/P1-I1/provided/t10b-test_import_diff.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-modules`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- This ticket is pure code. `ImportPlan` and the other values are plain dataclasses; build `RowChange(line, number, tag_id, changes)` and `FieldChange(field, old, new)` positionally.

## Allowed paths
- `packages/tl-modules/engineering/src/tl_mod_engineering/imports/diff.py` (edit)
- `packages/tl-modules/engineering/tests/test_import_diff.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T10b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t10b-test_import_diff.py.txt` to `packages/tl-modules/engineering/tests/test_import_diff.py`.
3. Implement the three functions by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/engineering/tests/test_import_diff.py -q
uv run pytest packages/tl-modules -q
```
Expected: `just check` clean; 22 passed; the whole module package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `model.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
