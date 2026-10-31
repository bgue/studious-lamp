"""What the RFI log shows, as text (P1-I6-T07a)."""

from __future__ import annotations

from fakes import FakeClient
from fakes_correspondence import seed_domains
from tl_tui import rfi_text as rt


def seeded() -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    return client


def test_a_log_row_has_eleven_cells_in_the_order_of_the_columns() -> None:
    log = seeded().list_rfis("P123")
    cells = {line.number: rt.rfi_cells(line) for line in log.lines}
    assert all(len(c) == len(rt.RFI_COLUMNS) for c in cells.values())
    assert rt.RFI_COLUMNS[:4] == ("Number", "Subject", "State", "Kind")
    assert cells["P123-RFI-0001"] == (
        "P123-RFI-0001",
        "Beam B12 clashes with line 47",
        "Answered",
        "rfi",
        "structural",
        "2026-10-05",
        "2026-10-19",
        "2026-10-12",
        "7",
        "on time",
        "C:yes S:no",
    )
    assert cells["P123-RFI-0003"][4:] == (
        "—",
        "2026-10-05",
        "—",
        "—",
        "—",
        "—",
        "C:(unknown) S:(unknown)",
    )


def test_the_timing_says_overdue_late_on_time_or_nothing() -> None:
    log = seeded().list_rfis("P123")
    one, two, three = log.lines
    assert [rt.timing_text(x) for x in (one, two, three)] == ["on time", "overdue 1d", "—"]
    late = one.model_copy(update={"on_time": False})
    assert rt.timing_text(late) == "late"
    # overdue wins over the answer's timing, and the days come from the report
    both = late.model_copy(update={"overdue": True, "days_overdue": 12})
    assert rt.timing_text(both) == "overdue 12d"


def test_the_impact_is_the_answerers_statement_or_the_raisers_flag_in_brackets() -> None:
    one, two, three = seeded().list_rfis("P123").lines
    assert rt.impact_text(one) == "C:yes S:no"
    assert rt.impact_text(two) == "C:(unknown) S:(yes)"
    assert rt.impact_text(three) == "C:(unknown) S:(unknown)"
    mixed = two.model_copy(update={"cost_impact": "no"})
    assert rt.impact_text(mixed) == "C:no S:(yes)"


def test_the_summary_counts_and_names_the_filters_that_are_on() -> None:
    client = seeded()
    log = client.list_rfis("P123")
    assert rt.rfi_summary(log) == ("3 items | answered 1 | open 2 | overdue 1 | impact yes 1")
    only = client.list_rfis("P123", only_overdue=True)
    assert rt.rfi_summary(only, only_open=True, only_overdue=True, only_impact=True) == (
        "1 item | answered 0 | open 1 | overdue 1 | impact yes 0 | filter: open, overdue, impact"
    )
    averaged = log.model_copy(update={"average_response_days": 6.04})
    assert rt.rfi_summary(averaged).endswith("impact yes 1 | average answer 6.0 days")


def test_the_panel_shows_the_question_the_answer_the_escalation_and_the_clocks() -> None:
    client = seeded()
    answered = rt.rfi_lines(client.get_rfi("P123", "P123-RFI-0001"))
    assert answered[0] == "P123-RFI-0001 · Beam B12 clashes with line 47"
    assert answered[1] == "Answered"
    assert answered[2] == "structural · needed by 2026-10-19 · to Meridian"
    assert "Question\nPlease confirm: Beam B12 clashes with line 47" in "\n".join(answered)
    assert "Proposed solution\n—" in "\n".join(answered)  # a fixed section keeps its shape
    assert "Answer\nRe-route above the beam.\nAnswered on  2026-10-12" in "\n".join(answered)
    assert "Discipline       structural" in answered
    assert "Needed by        2026-10-19" in answered
    assert "Issued           2026-10-05" in answered
    assert "Cost impact      Raiser: Unknown · Answer: Yes" in answered
    assert "Schedule impact  Raiser: Unknown · Answer: No" in answered
    assert "Escalated to     P123-EW-0001 (Draft)" in answered
    assert "Response clocks" not in answered and "Review" not in "\n".join(answered)
    waiting = rt.rfi_lines(client.get_rfi("P123", "P123-RFI-0002"))
    assert "Answer" not in waiting and not any(x.startswith("Escalated") for x in waiting)
    assert waiting[waiting.index("Response clocks") + 1].split() == [
        "Clock", "State", "Due", "Days", "left",
    ]  # fmt: skip
    assert waiting[-1].startswith("Answer required  Expired  2026-10-19  -1 ")
    technical = rt.rfi_lines(client.get_rfi("P123", "P123-RFI-0002"), technical=True)
    assert technical[technical.index("Technical details") + 1].endswith(
        "P123-RFI-0002-C01 · calendar P123-default@1"
    )
    assert technical[-1].startswith("Record id") and technical[-1].endswith("ID-P123-RFI-0002")


def test_a_review_and_the_item_that_carried_the_answer_are_shown_when_there_are_any() -> None:
    view = (
        seeded()
        .get_rfi("P123", "P123-RFI-0001")
        .model_copy(
            update={
                "answer_item_number": "P123-COR-0007",
                "review_decision": "rejected",
                "reviewed_on": "2026-10-13",
                "review_note": "does not answer the clash",
            }
        )
    )
    lines = rt.rfi_lines(view)
    assert "Answered in item  P123-COR-0007" in lines
    assert "Review            Rejected on 2026-10-13: does not answer the clash" in lines
    bare = view.model_copy(update={"review_note": None})
    assert "Review            Rejected on 2026-10-13" in rt.rfi_lines(bare)


def test_a_draft_shows_dashes_for_what_it_does_not_have_yet() -> None:
    lines = rt.rfi_lines(seeded().get_rfi("P123", "P123-RFI-0003"))
    assert lines[0] == "P123-RFI-0003 · Anchor bolt spacing"
    assert lines[1] == "Draft"
    for label in ("Discipline      ", "Needed by       ", "Issued          "):
        assert f"{label} —" in lines
    assert "Proposed solution\n—" in "\n".join(lines)
    # no answer, review, escalation or clocks
    assert not {"Answer", "Response clocks"} & set(lines)
    assert not any(x.startswith(("Review", "Escalated")) for x in lines)


def test_an_answer_without_text_or_statement_still_shows_its_day() -> None:
    view = (
        seeded()
        .get_rfi("P123", "P123-RFI-0001")
        .model_copy(
            update={"answer": None, "answer_cost_impact": None, "answer_schedule_impact": None}
        )
    )
    lines = rt.rfi_lines(view)
    assert "Answer\n—\nAnswered on  2026-10-12" in "\n".join(lines)
    assert "Cost impact      Raiser: Unknown" in lines  # no answerer's view yet
    assert "Schedule impact  Raiser: Unknown" in lines


def test_an_average_of_zero_days_is_still_shown() -> None:
    log = seeded().list_rfis("P123").model_copy(update={"average_response_days": 0.0})
    assert rt.rfi_summary(log).endswith("| average answer 0.0 days")


def test_the_discipline_reads_as_its_label_in_plain_mode_and_stays_a_code_in_technical() -> None:
    from tl_tui.display import Labels  # noqa: PLC0415

    line = seeded().list_rfis("P123").lines[0]
    labels = Labels(code_labels={"discipline": {"structural": "Structural works"}})
    assert rt.rfi_cells(line, labels, technical=False)[4] == "Structural works"
    assert rt.rfi_cells(line, labels, technical=True)[4] == "structural"
    assert rt.rfi_cells(line, Labels(), technical=False)[4] == "structural"  # no list: the code
    view = seeded().get_rfi("P123", line.number)
    plain = rt.rfi_lines(view, labels)
    assert plain[2].startswith("Structural works · needed by")
    assert "Discipline       Structural works" in plain
    # the panel reads the discipline as its label in both modes; the log's cell has the code
    assert "Discipline       Structural works" in rt.rfi_lines(view, labels, technical=True)
