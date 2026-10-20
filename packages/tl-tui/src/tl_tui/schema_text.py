# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""Plain text for the schema workbench: table cells and the three detail tabs (P1-I8-T04a).

STUB: this file is the interface P1-I8-T04a implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `COLUMNS` is complete.

Pure functions of the views the client returns (`PackageSummary`, `PackageDetail`,
`LintIssueView`) and of the package YAML, so they are tested without a terminal. State is never
colour alone. Nothing here changes anything.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_schemareg.views import LintIssueView, PackageDetail, PackageSummary
from tl_schema.packages import PackageDoc, PropertyDef
from tl_schema.registry import PackageError, parse_package

COLUMNS = ("Package", "Version", "State", "Class", "Scope", "Drafted by")


def tree_cells(rows: Sequence[PackageSummary]) -> list[tuple[str, ...]]:
    """One tuple of cells per row, in the order given.

    The package name is shown on the first row of a run of rows with that name and is empty on the
    others, so the versions of a package read as a tree. `Class` is the worst class of change, `-`
    when none, with ` (stale)` after it when the content changed since `analysed`.
    """
    # STEPS
    # For each row make the tuple (package, version, state, class, scope, drafted_by). The
    #    package is the empty string when it equals the previous row's package. The class is
    #    row.worst_class or '-', with ' (stale)' added when worst_class is set and the row
    #    is not analysed.
    raise NotImplementedError("STEPS: see the comments")


def header_lines(detail: PackageDetail) -> list[str]:
    """Five lines above the tabs: who and where the version is."""
    # STEPS
    # Five f-strings, exactly as the provided test pins them (a dash for None or empty).
    raise NotImplementedError("STEPS: see the comments")


def _required(prop: PropertyDef) -> str:
    # STEPS
    # '*' when prop.required; otherwise the required_in_states joined by ',' or '-'.
    raise NotImplementedError("STEPS: see the comments")


def property_lines(content: str) -> list[str]:
    """The package YAML as a list of what it defines; `! ...` when it does not parse.

    Code lists first (`list <Name>  <policy>  <n> values`), then each pset
    (`pset <name>  <enforcement>  <adoption>  applies to <types>`) with one indented line per
    property (`  <name>  <range>  <enforcement>  req <states>  <policy>`; `*` for every state),
    then each extension (`extends <ref>`) with `  tighten <property>  <field>=<value> ...`,
    `  add <list>  <code>  -> <crosswalk>` and `  custom x.<name>  <range>` lines. A dash for
    none; `Nothing defined.` for a package with none of these.
    """
    # STEPS
    # 1. Parse with parse_package(content, source='package'); on PackageError return [f'!
    #    The package does not parse: {exc}'].
    # 2. Append the lines in the order the docstring gives: code lists, then psets with
    #    their properties, then extensions with their tighten, add and custom lines. For
    #    tighten, format each non-None field of tight.model_dump(exclude_none=True) as k=v
    #    (a list joined by ',').
    # 3. Return the lines, or ['Nothing defined.'] when there are none.
    raise NotImplementedError("STEPS: see the comments")


def lint_lines(issues: Sequence[LintIssueView]) -> list[str]:
    """`Lint: <e> errors, <w> warnings`, then one line per finding.

    A finding is `<severity>  <rule>  <path>  <message>`.
    """
    # STEPS
    # Count the issues whose severity is 'error' and 'warning'; the count line first, then
    #    one line per issue.
    raise NotImplementedError("STEPS: see the comments")


def diff_lines(detail: PackageDetail) -> list[str]:
    """The diff against the base, or the reason there is none; `(diff cut)` ends a cut one."""
    # STEPS
    # 1. With no detail.diff: the 'Not analysed yet...' line when detail.classification is
    #    None, else 'No base to compare with (first version).'.
    # 2. Otherwise the diff split into lines (no trailing newline), plus '(diff cut)' when
    #    detail.diff_truncated.
    raise NotImplementedError("STEPS: see the comments")
