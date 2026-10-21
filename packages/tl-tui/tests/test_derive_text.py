"""The text of the derivation screens, from the values the client returns (P1-I3)."""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from tl_mod_documents.derivation.publish import PublishDerivedTags
from tl_tui import derive_text as text

P = "P123"
GOOD = "ISD-001@A/instrument-index"
BAD = "ISD-002@A/instrument-index"
BUSY = "ISD-003@A/instrument-index"


def client() -> FakeClient:
    found = FakeClient()
    found.seed_derivation(P)
    return found


def test_a_row_has_one_cell_per_column() -> None:
    summaries = {d.key: d for d in client().list_derived_documents(P)}
    assert text.derived_cells(summaries[GOOD]) == (
        GOOD, "Valid", "2", "3", "0", "instrument-index@1.0.0",
    )  # fmt: skip
    assert text.derived_cells(summaries[BUSY])[3:5] == ("-", "-")  # nothing read yet
    assert len(text.DERIVED_COLUMNS) == len(text.derived_cells(summaries[GOOD]))


def test_the_detail_names_the_passes_and_the_running_job() -> None:
    lines = text.derived_detail_lines(client().get_derived_document(P, BUSY))
    assert lines[1].startswith("state Processing")
    assert any(line.startswith("job JOB-") and line.endswith(" running") for line in lines)
    assert "no pass yet" in lines[-1]
    good = text.derived_detail_lines(client().get_derived_document(P, GOOD))
    assert "passes:" in good and sum(1 for line in good if line.startswith("  ")) == 2


def test_a_report_lists_its_issues_and_says_when_it_cuts() -> None:
    report = client().get_derived_report(P, BAD)
    lines = text.report_lines(report)
    assert lines[0] == "instrument-index@1.0.0: invalid"
    assert lines[1] == "rows checked 2  with errors 1  errors 2  warnings 1"
    assert "  error   row 2 type: 'XX' is not one of CV, HV, PSV" in lines
    assert "  warning file: column 'note' is ignored" in lines
    cut = text.report_lines(report, limit=1)
    assert len(cut) == 4 and cut[-1] == "  ... 2 more issues not shown"


def test_a_diff_lists_added_removed_and_changed_rows() -> None:
    lines = text.diff_lines(client().get_derived_diff(P, GOOD))
    assert lines[0] == "added 1  removed 0  changed 1  unchanged 1"
    assert "  + 47-HV-2001" in lines and "  ~ 47-FV-1002: size_in 8 -> 6" in lines


def test_jobs_show_their_try_and_their_error() -> None:
    jobs = {j.state: j for j in client().list_processing_jobs(P)}
    assert text.job_cells(jobs["failed"]) == (
        jobs["failed"].key, "extract", "failed", "1/3", BAD, "extractor timed out",
    )  # fmt: skip
    lines = text.job_detail_lines(jobs["failed"])
    assert lines[-1] == "error timeout: extractor timed out"
    assert text.jobs_summary(1, 3, state="failed") == "1 of 3 jobs  state failed"


def test_the_publish_preview_and_when_it_may_be_applied() -> None:
    plan = client().get_publish_preview(P, GOOD)
    header = text.plan_header_lines(plan)
    assert header[0] == f"{GOOD} pass 2 to tags (instrument-index@1.0.0)"
    assert header[1] == "create 2  exists 1  differs 0  invalid 0"
    assert "rows exist already: publishing needs 'skip existing'" in header
    assert text.plan_cells(plan)[2] == ("3", "47-HV-2001", "exists", "-")
    assert not text.can_apply(plan, skip_existing=False)
    assert text.can_apply(plan, skip_existing=True)
    assert text.can_apply(plan.model_copy(update={"needs_skip_existing": False}), False)
    assert not text.can_apply(plan.model_copy(update={"can_publish": False}), True)


def test_compensation_lines_name_each_record_and_what_blocks() -> None:
    fake = client()
    derived = fake.get_derived_document(P, GOOD)
    base: dict[str, Any] = {"actor": "user:a", "source": "tui", "scope": "project:P123"}
    fake.publish_derived_tags(
        PublishDerivedTags(
            **base, derived_id=derived.id, expected_content_rev=2, skip_existing=True
        )
    )
    lines = text.compensation_lines(fake.get_compensation_preview(P, GOOD))
    assert lines[0].startswith(f"{GOOD}  correlation COR")
    assert lines[1] == "  delete_tag 47-FV-1001 Active  reversible"


def test_next_choice_cycles_through_all_then_each() -> None:
    assert text.next_choice(None, ["Valid", "Invalid", "Valid"]) == "Invalid"
    assert text.next_choice("Invalid", ["Valid", "Invalid"]) == "Valid"
    assert text.next_choice("Valid", ["Valid", "Invalid"]) is None


def test_plain_schema_text_has_no_package_name_or_version() -> None:
    """The Schema column, the detail line and the report header: plain words, technical keeps it."""
    summaries = {d.key: d for d in client().list_derived_documents(P)}
    plain = text.derived_cells(summaries[GOOD], technical=False)
    assert plain[-1] == "Instrument index"
    assert text.derived_cells(summaries[GOOD])[-1] == "instrument-index@1.0.0"
    assert "@" not in plain[-1]
    detail = text.derived_detail_lines(client().get_derived_document(P, GOOD), technical=False)
    assert any(line.startswith("schema Instrument index  |  validation ") for line in detail)
    assert not any("instrument-index@" in line for line in detail)
    report = text.report_lines(client().get_derived_report(P, BAD), technical=False)
    assert report[0] == "Instrument index: invalid"
    assert text.report_lines(client().get_derived_report(P, BAD))[0] == (
        "instrument-index@1.0.0: invalid"
    )


def test_plain_publish_header_names_the_schema_without_its_version() -> None:
    plan = client().get_publish_preview(P, GOOD)
    assert text.plan_header_lines(plan)[0] == f"{GOOD} pass 2 to tags (instrument-index@1.0.0)"
    plain = text.plan_header_lines(plan, technical=False)
    assert plain[0] == f"{GOOD} pass 2 to tags (Instrument index)"
    assert "@1.0.0" not in plain[0]
