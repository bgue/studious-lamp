# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""Plain text for the review of a schema package version (P1-I8-T04b).

STUB: this file is the interface P1-I8-T04b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `MAX_LINES`, `NEXT_STEPS` and `_cut`
are complete.

Pure functions of the views the client returns (`PackageDetail`, `ImpactReport`,
`SampleTestView`), so they are tested without a terminal. A list is cut at `MAX_LINES` entries and
ends with `... <n> more`. Nothing here changes anything.
"""

from __future__ import annotations

from tl_mod_schemareg.impact_types import ImpactReport
from tl_mod_schemareg.views import PackageDetail, SampleTestView

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


def title_line(detail: PackageDetail) -> str:
    """`<key>  <state>  class <worst class or ->`."""
    # STEPS
    # f'{detail.key}  {detail.state}  class {detail.worst_class or "-"}'.
    raise NotImplementedError("STEPS: see the comments")


def next_step(state: str) -> str:
    """The line for `state` in `NEXT_STEPS`; `State <state>.` for one that is not there."""
    # STEPS
    # NEXT_STEPS.get(state, f'State {state}.').
    raise NotImplementedError("STEPS: see the comments")


def _cut(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_LINES:
        return lines
    return [*lines[:MAX_LINES], f"... {len(lines) - MAX_LINES} more"]


def classification_lines(detail: PackageDetail) -> list[str]:
    """The classification report of the version, or why there is none.

    Without a report: `Not analysed: press a to analyse.` Otherwise `Worst <class>  auto-adoptable
    yes|no  blocks submit yes|no`, `Base <name@version or ->`, then one line per change,
    `<class>  <path>  <detail>`, cut at `MAX_LINES`.
    """
    # STEPS
    # 1. detail.classification is None: return ['Not analysed: press a to analyse.'].
    # 2. Otherwise the two head lines of the docstring (`yes`/`no` for the two flags; `-`
    #    for no base), then one line per change `<cls>  <path>  <detail>`, passed through
    #    `_cut`.
    raise NotImplementedError("STEPS: see the comments")


def impact_lines(report: ImpactReport | None) -> list[str]:
    """What the change touches, or why there is no report.

    Without a report: `No impact report: press a to analyse.` Otherwise `Scope <scope>`,
    `Digest <sha256>`, `Counts <section> <n>, ...` (a dash for none), then one line per entry,
    `<section>  <target>  <change>  <count or ->  <detail>`, cut at `MAX_LINES`; a report that was
    cut by the module ends with `(report cut)`.
    """
    # STEPS
    # 1. None: return ['No impact report: press a to analyse.'].
    # 2. Counts are `<section> <n>` joined by ', ' (report.counts is in section order), or
    #    '-'. An entry's count is '-' when None. The entry lines go through `_cut`; the
    #    report's digest is `report.digest`.
    # 3. Add '(report cut)' as the last line when report.truncated.
    raise NotImplementedError("STEPS: see the comments")


def sample_lines(view: SampleTestView | None) -> list[str]:
    """The test on a sample, or the key that makes it.

    Without one: `Not run: press t to test on a sample of records.` Otherwise
    `Tested <package>  scope <scope>  sample <n>  checked <n>`,
    `Newly nonconformant <n>  newly warning <n>  fixed <n>`, then one line per example,
    `<key>  <path>  <rule>  <message>`.
    """
    # STEPS
    # 1. None: return ['Not run: press t to test on a sample of records.'].
    # 2. Otherwise the two lines and the example lines of the docstring.
    raise NotImplementedError("STEPS: see the comments")
