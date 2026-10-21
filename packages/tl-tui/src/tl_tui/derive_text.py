"""What the derivation screens show, as pure functions (P1-I3; ADR-0014).

The derived-document table, the detail panel, the validation report, the diff, the job table and
the publish preview are text built from the values the client returns
(``tl_mod_documents.derivation.views`` and the report, diff and plan models) and nothing else, so
the tests check them without a terminal. None of it decides anything: whether a document can be
published, which row is invalid and what a publication would create are the module's findings,
shown here as they come.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_documents.derivation.diff import DerivedDiff
from tl_mod_documents.derivation.publish import CompensationPlan, PublishPlan
from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.derivation.views import DerivedSummary, DerivedView, JobView

from tl_tui.display import humanize

DERIVED_COLUMNS = ("Key", "State", "Pass", "Rows", "Errors", "Schema")
JOB_COLUMNS = ("Job", "Kind", "State", "Try", "Derived", "Note")
PLAN_COLUMNS = ("Row", "Key", "Action", "Note")
MAX_REPORT_LINES = 200
MAX_CELL = 60


def short(value: object, width: int = MAX_CELL) -> str:
    """``-`` for none, one line, cut to ``width`` characters."""
    text = "-" if value is None or value == "" else " ".join(str(value).split())
    return text if len(text) <= width else text[: width - 1] + "…"


# --- derived documents -----------------------------------------------------------------------


def schema_text(code: str, version: str, *, technical: bool = True) -> str:
    """The schema as a derived-document screen shows it: ``instrument-index@1.0.0`` when
    ``technical``, else its plain label (``Instrument index``). Plain text never shows the
    package name or the version."""
    if technical:
        return f"{code}@{version}"
    return humanize(code.replace("-", " "))


def derived_cells(view: DerivedSummary, *, technical: bool = True) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``DERIVED_COLUMNS``."""
    return (
        view.key,
        view.state,
        str(view.content_rev),
        short(view.row_count),
        short(view.error_count),
        schema_text(view.schema_code, view.schema_version, technical=technical),
    )


def derived_detail_lines(view: DerivedView, *, technical: bool = True) -> list[str]:
    """The panel under the table: facts, the running job, and one line per pass."""
    schema = schema_text(view.schema_code, view.schema_version, technical=technical)
    lines = [
        f"{view.key}  {view.title}",
        f"state {view.state}  |  method {view.method}  |  source {view.source_ref}",
        f"schema {schema}  |  validation {view.validation_status}",
    ]
    if view.published_count is not None:
        lines.append(f"published {view.published_count} records at {view.published_at}")
    if view.active_job is not None:
        lines.append(f"job {view.active_job.key} {view.active_job.state}")
    if view.contents:
        lines.append("passes:")
        for c in view.contents:
            lines.append(
                f"  {c.content_rev}  {c.extractor} {c.extraction_status}  rows {c.row_count}  "
                f"validation {c.validation_status}  errors {c.error_count}"
                + ("  published" if c.published else "")
            )
    else:
        lines.append("no pass yet: attach a CSV or XLSX, or start an extraction")
    return lines


def report_lines(
    report: ValidationReport, limit: int = MAX_REPORT_LINES, *, technical: bool = True
) -> list[str]:
    """The report: a header, the counts, then one line per issue (at most ``limit``)."""
    schema = schema_text(report.schema_code, report.schema_version, technical=technical)
    lines = [
        f"{schema}: {report.status}",
        f"rows checked {report.rows_checked}  with errors {report.rows_with_errors}  "
        f"errors {report.error_count}  warnings {report.warning_count}",
    ]
    for issue in report.issues[:limit]:
        where = f"row {issue.row}" if issue.row is not None else "file"
        column = f" {issue.column}" if issue.column else ""
        lines.append(f"  {issue.level:<7} {where}{column}: {issue.message}")
    hidden = len(report.issues) - limit
    if hidden > 0:
        lines.append(f"  ... {hidden} more issues not shown")
    elif report.truncated:
        lines.append("  ... the report was cut; the counts above are exact")
    return lines


def diff_lines(diff: DerivedDiff, limit: int = MAX_REPORT_LINES) -> list[str]:
    """What changed: the counts, then ``+`` added, ``-`` removed and ``~`` changed rows."""
    lines = [
        f"added {diff.added_count}  removed {diff.removed_count}  changed {diff.changed_count}  "
        f"unchanged {diff.unchanged_count}"
    ]
    lines.extend(f"  + {key}" for key in diff.added)
    lines.extend(f"  - {key}" for key in diff.removed)
    for change in diff.changed:
        fields = "; ".join(f"{f.column} {short(f.old)} -> {short(f.new)}" for f in change.fields)
        lines.append(f"  ~ {change.key}: {fields}")
    if diff.columns_added or diff.columns_removed:
        lines.append(
            f"columns +{', '.join(diff.columns_added) or '-'}  "
            f"-{', '.join(diff.columns_removed) or '-'}"
        )
    if len(lines) > limit:
        lines = [*lines[:limit], f"  ... {len(lines) - limit} more lines not shown"]
    elif diff.truncated:
        lines.append("  ... the lists were cut; the counts above are exact")
    return lines


def summary_line(shown: int, total: int, *, state: str | None, text: str) -> str:
    """The status line under the derived-documents table."""
    parts = [f"{shown} of {total} derived documents"]
    if state is not None:
        parts.append(f"state {state}")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  ".join(parts)


# --- jobs ------------------------------------------------------------------------------------


def job_cells(job: JobView) -> tuple[str, ...]:
    """The six cells of a job row, in the order of ``JOB_COLUMNS``."""
    return (
        job.key,
        job.kind,
        job.state,
        f"{job.attempt}/{job.max_attempts}",
        job.derived_key,
        short(job.error_message),
    )


def job_detail_lines(job: JobView) -> list[str]:
    """The panel under the job table."""
    lines = [
        f"{job.key}  {job.kind} for {job.derived_key}",
        f"state {job.state}  |  attempt {job.attempt} of {job.max_attempts}  "
        f"|  by {job.requested_by}",
        f"extractor {job.extractor or 'chosen by file type'}  |  worker {job.worker or '-'}",
        f"started {job.started_at or '-'}  |  finished {job.finished_at or '-'}",
    ]
    if job.error_message:
        lines.append(f"error {job.error_code or '-'}: {job.error_message}")
    if job.result:
        lines.append("result " + ", ".join(f"{k} {v}" for k, v in sorted(job.result.items())))
    return lines


def jobs_summary(shown: int, total: int, *, state: str | None) -> str:
    parts = [f"{shown} of {total} jobs"]
    if state is not None:
        parts.append(f"state {state}")
    return "  ".join(parts)


# --- publication -----------------------------------------------------------------------------


def plan_cells(plan: PublishPlan, limit: int | None = None) -> list[tuple[str, ...]]:
    """One row per mapped data row: ``(row, key, action, note)``."""
    rows = plan.rows if limit is None else plan.rows[:limit]
    return [(str(r.row), short(r.key), r.action, short("; ".join(r.problems), 80)) for r in rows]


def plan_header_lines(plan: PublishPlan, *, technical: bool = True) -> list[str]:
    """What the preview says before the table: the target, the counts and what stops it.

    Plain text names the schema by its label, without the package name or version."""
    counts = plan.counts
    if technical or plan.schema_key is None:
        schema = plan.schema_key or "no schema"
    else:
        schema = schema_text(plan.schema_key.split("@", 1)[0], "", technical=False)
    lines = [
        f"{plan.derived_key} pass {plan.content_rev} to {plan.target or '-'} ({schema})",
        f"create {counts.get('create', 0)}  exists {counts.get('exists', 0)}  "
        f"differs {counts.get('differs', 0)}  invalid {counts.get('invalid', 0)}",
    ]
    lines.extend(f"! {problem}" for problem in plan.problems)
    if plan.needs_skip_existing:
        lines.append("rows exist already: publishing needs 'skip existing'")
    if plan.truncated:
        lines.append("the list is cut; the counts are exact")
    return lines


def can_apply(plan: PublishPlan, skip_existing: bool) -> bool:
    """Whether publishing may be offered: the module says it can, and existing rows are skipped."""
    return plan.can_publish and (skip_existing or not plan.needs_skip_existing)


def compensation_lines(plan: CompensationPlan) -> list[str]:
    """What rolling the publication back would end."""
    lines = [f"{plan.derived_key}  correlation {plan.import_correlation_id or '-'}"]
    for item in plan.items:
        state = "reversible" if item.reversible else f"blocked: {item.problem}"
        lines.append(f"  {item.action} {item.key or item.record_id} {short(item.state)}  {state}")
    lines.extend(f"! {problem}" for problem in plan.problems)
    return lines


def next_choice(current: str | None, choices: Sequence[str]) -> str | None:
    """The filter after ``current``: ``None`` (all), then each distinct choice, then ``None``."""
    cycle: list[str | None] = [None, *sorted(set(choices))]
    if current not in cycle:
        return None
    return cycle[(cycle.index(current) + 1) % len(cycle)]
