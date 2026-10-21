"""Plain text for the schema workbench: table cells and the three detail tabs (P1-I8-T04a).

Pure functions of the views the client returns (`PackageSummary`, `PackageDetail`,
`LintIssueView`) and of the package YAML, so they are tested without a terminal. State is never
colour alone. Nothing here changes anything.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_schemareg.views import LintIssueView, PackageDetail, PackageSummary
from tl_schema.packages import PropertyDef
from tl_schema.registry import PackageError, parse_package

from tl_tui.display import Labels, actor_label, humanize

COLUMNS = ("Package", "Version", "State", "Class", "Scope", "Drafted by")


def plain_ref(ref: str) -> str:
    """A `name@version` reference in words: `Engineering, version 3.2.0`.

    Split on the last `@`; a reference without one is just its humanized name.
    """
    name, sep, version = ref.rpartition("@")
    if not sep:
        return humanize(ref)
    return f"{humanize(name)}, version {version}"


def tree_cells(rows: Sequence[PackageSummary], *, technical: bool = False) -> list[tuple[str, ...]]:
    """One tuple of cells per row, in the order given.

    The package name is shown on the first row of a run of rows with that name and is empty on the
    others, so the versions of a package read as a tree. In plain mode the name is the row's title,
    else its humanized package name; technical mode shows the package name. `Class` is the worst
    class of change, `-` when none, with ` (stale)` after it when the content changed since
    `analysed`.
    """
    cells: list[tuple[str, ...]] = []
    previous: str | None = None
    for row in rows:
        shown = row.package if technical else (row.title or humanize(row.package))
        name = "" if row.package == previous else shown
        previous = row.package
        worst = row.worst_class or "-"
        if row.worst_class and not row.analysed:
            worst += " (stale)"
        cells.append((name, row.version, row.state, worst, row.scope, row.drafted_by))
    return cells


def header_lines(detail: PackageDetail, *, technical: bool = False) -> list[str]:
    """Five lines above the tabs: who and where the version is.

    Plain mode names the version in words and the people by their short labels; technical mode
    shows the `name@version` key and the raw actor references.
    """
    if technical:
        drafted = detail.drafted_by
        submitted = detail.submitted_by or "-"
        approved = detail.approved_by or "-"
        key = detail.key
    else:
        labels = Labels()
        drafted = actor_label(labels, detail.drafted_by)
        submitted = actor_label(labels, detail.submitted_by) if detail.submitted_by else "-"
        approved = actor_label(labels, detail.approved_by) if detail.approved_by else "-"
        key = plain_ref(detail.key)
    return [
        f"{key}  {detail.state}",
        f"Kind {detail.kind}  Scope {detail.scope}  Project {detail.project or '-'}",
        f"Drafted by {drafted}  Submitted by {submitted}  Approved by {approved}",
        f"Class {detail.worst_class or '-'}  Analysed {'yes' if detail.analysed else 'no'}  "
        f"Published {detail.published_at or '-'}",
        f"Changelog {detail.changelog or '-'}",
    ]


def _required(prop: PropertyDef) -> str:
    if prop.required:
        return "*"
    return ",".join(prop.required_in_states) or "-"


def property_lines(content: str) -> list[str]:
    """The package YAML as a list of what it defines; `! ...` when it does not parse.

    Code lists first (`list <Name>  <policy>  <n> values`), then each pset
    (`pset <name>  <enforcement>  <adoption>  applies to <types>`) with one indented line per
    property (`  <name>  <range>  <enforcement>  req <states>  <policy>`; `*` for every state),
    then each extension (`extends <ref>`) with `  tighten <property>  <field>=<value> ...`,
    `  add <list>  <code>  -> <crosswalk>` and `  custom x.<name>  <range>` lines. A dash for
    none; `Nothing defined.` for a package with none of these.
    """
    try:
        doc = parse_package(content, source="package")
    except PackageError as exc:
        return [f"! The package does not parse: {exc}"]
    lines: list[str] = []
    for name, code_list in doc.code_lists.items():
        lines.append(f"list {name}  {code_list.value_list_policy}  {len(code_list.values)} values")
    for pset_name, pset in doc.psets.items():
        types = ", ".join(pset.applies_to) or "-"
        lines.append(f"pset {pset_name}  {pset.enforcement}  {pset.adoption}  applies to {types}")
        for prop_name, prop in pset.properties.items():
            lines.append(
                f"  {prop_name}  {prop.range}  {prop.enforcement or pset.enforcement}"
                f"  req {_required(prop)}  {prop.value_list_policy or '-'}"
            )
    for ext in doc.extends:
        lines.append(f"extends {ext.ref}")
        for prop_name, tight in ext.tighten.items():
            fields = " ".join(
                f"{key}={','.join(value) if isinstance(value, list) else value}"
                for key, value in tight.model_dump(exclude_none=True).items()
            )
            lines.append(f"  tighten {prop_name}  {fields}")
        for list_name, values in ext.add_values.items():
            for value in values:
                lines.append(f"  add {list_name}  {value.code}  -> {value.crosswalk or '-'}")
        for prop_name, prop in ext.custom.items():
            lines.append(f"  custom x.{prop_name}  {prop.range}")
    return lines or ["Nothing defined."]


def lint_lines(issues: Sequence[LintIssueView]) -> list[str]:
    """`Lint: <e> errors, <w> warnings`, then one line per finding.

    A finding is `<severity>  <rule>  <path>  <message>`.
    """
    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    lines = [f"Lint: {errors} errors, {warnings} warnings"]
    lines.extend(f"{i.severity}  {i.rule}  {i.path}  {i.message}" for i in issues)
    return lines


def diff_lines(detail: PackageDetail) -> list[str]:
    """The diff against the base, or the reason there is none; `(diff cut)` ends a cut one."""
    if not detail.diff:
        if detail.classification is None:
            return ["Not analysed yet: the diff against the version below is made by analyse."]
        return ["No base to compare with (first version)."]
    lines = detail.diff.splitlines()
    if detail.diff_truncated:
        lines.append("(diff cut)")
    return lines
