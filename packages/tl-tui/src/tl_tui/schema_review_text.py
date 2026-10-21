"""Plain text for the review of a schema package version (P1-I8-T04b).

Pure functions of the views the client returns (`PackageDetail`, `ImpactReport`,
`SampleTestView`), so they are tested without a terminal. A list is cut at `MAX_LINES` entries and
ends with `... <n> more`. Nothing here changes anything.
"""

from __future__ import annotations

from tl_mod_schemareg.impact_types import ImpactReport
from tl_mod_schemareg.views import PackageDetail, SampleTestView

from tl_tui.schema_text import plain_ref

MAX_LINES = 30

#: state -> what comes next, for the line under the title.
NEXT_STEPS = {
    "Draft": "Next: analyse (a), then submit (s).",
    "InReview": "Next: approve (y) or ask for changes (c).",
    "Approved": "Next: publish (p).",
    "Published": "Published: adoption is per project (tl schema adopt).",
    "Deprecated": "Deprecated: no new adoptions.",
    "Retired": "Retired: out of every effective schema.",
}


def title_line(detail: PackageDetail, *, technical: bool = False) -> str:
    """`<key>  <state>  class <worst class or ->`; the key in words unless `technical`."""
    key = detail.key if technical else plain_ref(detail.key)
    return f"{key}  {detail.state}  class {detail.worst_class or '-'}"


def next_step(state: str) -> str:
    """The line for `state` in `NEXT_STEPS`; `State <state>.` for one that is not there."""
    return NEXT_STEPS.get(state, f"State {state}.")


def _cut(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_LINES:
        return lines
    return [*lines[:MAX_LINES], f"... {len(lines) - MAX_LINES} more"]


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def classification_lines(detail: PackageDetail, *, technical: bool = False) -> list[str]:
    """The classification report of the version, or why there is none.

    Without a report: `Not analysed: press a to analyse.` Otherwise `Worst <class>  auto-adoptable
    yes|no  blocks submit yes|no`, `Base <name@version or ->` (in words unless `technical`),
    then one line per change, `<class>  <path>  <detail>`, cut at `MAX_LINES`.
    """
    report = detail.classification
    if report is None:
        return ["Not analysed: press a to analyse."]
    base = (report.base if technical else plain_ref(report.base)) if report.base else "-"
    head = [
        f"Worst {report.worst}  auto-adoptable {_yes_no(report.auto_adoptable)}"
        f"  blocks submit {_yes_no(report.blocks_submit)}",
        f"Base {base}",
    ]
    changes = [f"{c.cls}  {c.path}  {c.detail}" for c in report.changes]
    return [*head, *_cut(changes)]


def impact_lines(report: ImpactReport | None, *, technical: bool = False) -> list[str]:
    """What the change touches, or why there is no report.

    Without a report: `No impact report: press a to analyse.` Otherwise `Scope <scope>`,
    `Digest <sha256>` (technical mode only), `Counts <section> <n>, ...` (a dash for none), then one
    line per entry, `<section>  <target>  <change>  <count or ->  <detail>`, cut at `MAX_LINES`; a
    report that was cut by the module ends with `(report cut)`.
    """
    if report is None:
        return ["No impact report: press a to analyse."]
    counts = ", ".join(f"{section} {n}" for section, n in report.counts.items()) or "-"
    entries = [
        f"{e.section}  {e.target}  {e.change}  {'-' if e.count is None else e.count}  {e.detail}"
        for e in report.entries
    ]
    lines = [f"Scope {report.scope}"]
    if technical:
        lines.append(f"Digest {report.digest}")
    lines.append(f"Counts {counts}")
    lines.extend(_cut(entries))
    if report.truncated:
        lines.append("(report cut)")
    return lines


def sample_lines(view: SampleTestView | None, *, technical: bool = False) -> list[str]:
    """The test on a sample, or the key that makes it.

    Without one: `Not run: press t to test on a sample of records.` Otherwise
    `Tested <package>  scope <scope>  sample <n>  checked <n>` (the package in words unless
    `technical`), `Newly nonconformant <n>  newly warning <n>  fixed <n>`, then one line per
    example, `<key>  <path>  <rule>  <message>`.
    """
    if view is None:
        return ["Not run: press t to test on a sample of records."]
    package = view.package if technical else plain_ref(view.package)
    return [
        f"Tested {package}  scope {view.scope}  sample {view.sample}  checked {view.checked}",
        f"Newly nonconformant {view.newly_nonconformant}  newly warning {view.newly_warning}"
        f"  fixed {view.fixed}",
        *(f"{e.key}  {e.path}  {e.rule}  {e.message}" for e in view.examples),
    ]
