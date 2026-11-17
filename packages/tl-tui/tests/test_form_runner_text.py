"""The pure text of the forms log, the record screen and the runner (V3-F1b)."""

from __future__ import annotations

from typing import Any

from fakes_forms import fld, submission, template
from tl_core.forms import runner
from tl_tui import form_runner_text as t
from tl_tui.layout import plain_lines

TPL, FIELDS = template(
    1,
    "Toolbox talk",
    [
        fld("topic", section="Talk", help="One line."),
        fld("count", "number", min=1, max=50, unit="people"),
        fld("ppe", "yes_no_na"),
        fld("hazards", "multi", choices=["Falls", "Lifting"], required=False),
        fld("pick", "choice", choices=["Low", "High"], required=False),
        fld("more", required=False, visible_when={"q": "ppe", "is": "no"}),
    ],
)


def step_of(fid: str) -> runner.Step:
    state = runner.start(FIELDS)
    # walk to the field: answer every earlier visible question with a valid value
    good: dict[str, Any] = {"topic": "x", "count": 3, "ppe": "yes", "hazards": ["Falls"]}
    while state.at != fid:
        state, problems = runner.answer(state, FIELDS, good[state.at or ""])
        assert not problems
    found = runner.step(state, FIELDS)
    assert found is not None
    return found


def test_a_number_is_a_number_and_a_miss_stays_text() -> None:
    step = step_of("count")
    assert t.parse_answer(step, " 12 ") == 12
    assert t.parse_answer(step, "2.5") == 2.5
    assert t.parse_answer(step, "many") == "many"


def test_yes_no_na_takes_short_forms_in_any_case() -> None:
    step = step_of("ppe")
    assert [t.parse_answer(step, w) for w in ("YES", "n", "N/A", "na")] == [
        "yes",
        "no",
        "na",
        "na",
    ]


def test_a_choice_is_taken_by_number_or_by_words() -> None:
    step = step_of("hazards")
    assert t.parse_answer(step, "1, lifting") == ["Falls", "Lifting"]
    assert t.parse_answer(step, "9") == ["9"]
    single = step_of("pick")
    assert t.parse_answer(single, "2") == "High"
    assert t.parse_answer(single, "high") == "High"


def test_step_text_names_the_question_how_to_answer_and_the_choices() -> None:
    lines = t.step_lines(step_of("count"))
    assert lines[0] == "Question count"
    assert "(required)" in lines
    assert "Answer with a number from 1 to 50 people." in lines
    hazards = t.step_lines(step_of("hazards"))
    assert "(optional, Enter on an empty line skips it)" in hazards
    assert "  1  Falls" in hazards and "  2  Lifting" in hazards
    first = runner.step(runner.start(FIELDS), FIELDS)
    assert first is not None
    assert t.step_lines(first)[:2] == ["Question topic", "One line."]
    assert t.step_head(first) == "Question 1 of 5 · Talk"


def test_a_hidden_field_is_not_counted_or_shown() -> None:
    first = runner.step(runner.start(FIELDS), FIELDS)
    assert first is not None and first.total == 5  # "more" is hidden until ppe is no


def test_the_value_comes_back_into_the_line_after_back() -> None:
    assert t.value_input(step_of("count")) == ""
    state = runner.start(FIELDS)
    state, _ = runner.answer(state, FIELDS, "x")
    state, _ = runner.answer(state, FIELDS, 7)
    state = runner.back(state, FIELDS)
    step = runner.step(state, FIELDS)
    assert step is not None and t.value_input(step) == "7"
    assert t.value_input(step_of("hazards")) == ""


def test_the_review_lists_answers_and_names_what_is_missing() -> None:
    state = runner.start(FIELDS)
    state, _ = runner.answer(state, FIELDS, "Ladders")
    view = runner.review(state, FIELDS)
    page = t.review_page(view, "Toolbox talk")
    lines = plain_lines(page)
    assert lines[0] == "Toolbox talk"
    assert any(line.startswith("Question topic") and "Ladders" in line for line in lines)
    assert "Missing" in lines and "count" in lines


def test_log_cells_use_words_and_dashes() -> None:
    sub = submission(7, TPL, "Accepted", "user:rob", [])
    cells = t.submission_cells(sub.row, {TPL.id: "Toolbox talk"})
    assert cells == ("P123-FRM-0007", "Toolbox talk", "Accepted", "rob", "2026-11-10")
    draft = submission(8, TPL, "Draft", "user:kim", [])
    assert t.submission_cells(draft.row, {})[0] == t.DRAFT_NUMBER
    assert t.submission_cells(draft.row, {})[1] == "—"
    assert t.template_cells(TPL) == ("TPL-0001", "Toolbox talk", "Published", "1", "6")


def test_summaries_count_by_state() -> None:
    assert t.submission_summary({"Submitted": 2, "Accepted": 1}, 3, 3) == (
        "3 form submissions: 2 Submitted, 1 Accepted"
    )
    assert t.submission_summary({}, 0, 0) == "0 form submissions"
    assert t.template_summary(1, 1) == "1 form template"
    assert t.template_summary(4, 2) == "2 of 4 form templates"


def test_the_record_page_shows_questions_by_their_words() -> None:
    sub = submission(
        2, TPL, "Accepted", "user:rob", [{"q": "topic", "value": "Drill", "note": "serviced"}]
    )
    lines = plain_lines(t.submission_page(sub, TPL, FIELDS))
    assert lines[0] == "P123-FRM-0002 · Toolbox talk"
    assert lines[1] == "Accepted"
    assert any(ln.startswith("Question topic") and "Drill (serviced)" in ln for ln in lines)
    assert any(ln.startswith("Reviewed by") and "ada" in ln for ln in lines)
    assert any(ln.startswith("Note") and "Checked and filed." in ln for ln in lines)
    panel = plain_lines(t.submission_page(sub, TPL, FIELDS, panel=True))
    assert not any("Question topic" in ln for ln in panel)  # answers are for the record screen


def test_a_list_answer_reads_joined_and_none_is_a_dash() -> None:
    assert t.answer_text(["Falls", "Lifting"]) == "Falls, Lifting"
    assert t.answer_text(None) == "—" and t.answer_text([]) == "—"
