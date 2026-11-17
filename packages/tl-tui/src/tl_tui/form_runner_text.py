"""The text of the forms log, a submission's record screen and the fill runner (V3-F1b).

Pure functions over ``tl_mod_forms.views`` rows and ``tl_core.forms.runner`` steps: no client call,
no I/O, no ``textual`` import (skill ``tui-layout``). A record's id is carried for commands and
never printed. Answers typed on the runner's line are read the way ``tl form`` reads ``--answer`` (a
number is a number, ``multi`` and ``photo`` take comma-separated values); a value that does not fit
stays text, and the rules refuse it with their own message, which the screen shows as the CLI does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from tl_tui.awp_text import date_text
from tl_tui.details import DetailRow, rows_page
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import (
    EMPTY,
    Page,
    Prop,
    Section,
    identity_line,
    join_facts,
    state_line,
)

if TYPE_CHECKING:
    from tl_core.forms.runner import Review, Step
    from tl_mod_forms.views import SubmissionDetail, SubmissionRow, TemplateRow

SUBMISSION_COLUMNS = ("Number", "Form", "State", "Author", "Submitted")
SUBMISSION_DROP = ("Author", "Submitted")  # dropped first at narrow width
TEMPLATE_COLUMNS = ("Number", "Title", "State", "Ver", "Fields")
TEMPLATE_DROP = ("Fields", "Ver")

SUBMISSIONS = "submissions"
TEMPLATES = "templates"
VIEW_TITLES = {SUBMISSIONS: "Form submissions", TEMPLATES: "Form templates"}

DRAFT_NUMBER = "(draft)"  # a draft has no number yet
ANSWERS = "Answers"
REVIEWING = "Review"
YES_NO_NA = ("yes", "no", "na")
_YES_NO_ALIAS = {"y": "yes", "n": "no", "n/a": "na"}

HINTS = {
    "yes_no_na": "Answer yes, no or na.",
    "number": "Answer with a number.",
    "date": "Answer with a date as YYYY-MM-DD.",
    "text": "Answer in a few words.",
    "photo": "Answer with photo file ids, separated by commas.",
}


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def _val(value: object) -> str:
    """The value as a reader sees it: ``—`` for none and for an empty text."""
    if value is None:
        return EMPTY
    text = str(value)
    return text if text.strip() else EMPTY


def _who(labels: Labels, actor: str | None, technical: bool) -> str:
    if not actor:
        return EMPTY
    return actor if technical else actor_label(labels, actor)


def count_text(total: int, noun: str) -> str:
    """``1 form submission``, ``7 form submissions``."""
    return f"{total} {noun}" if total == 1 else f"{total} {noun}s"


# --- the logs ---------------------------------------------------------------------------------


def submission_number(row: SubmissionRow) -> str:
    return row.key or DRAFT_NUMBER


def submission_cells(
    row: SubmissionRow,
    titles: Mapping[str, str],
    labels: Labels | None = None,
) -> tuple[str, ...]:
    """The cells in the order of ``SUBMISSION_COLUMNS``; ``titles``: template id to title."""
    return (
        submission_number(row),
        _val(titles.get(row.template_id or "")),
        humanize(row.state),
        _who(_labels(labels), row.author, technical=False),
        date_text(row.submitted_on),
    )


def template_cells(row: TemplateRow) -> tuple[str, ...]:
    """The cells in the order of ``TEMPLATE_COLUMNS``."""
    return (
        _val(row.key),
        _val(row.title),
        humanize(row.state),
        _val(row.version),
        _val(row.field_count),
    )


def submission_summary(
    counts: Mapping[str, int], total: int, shown: int, *, state: str | None = None
) -> str:
    """``7 form submissions: 2 Submitted, 1 Accepted``; with a state ``2 of 7 form submissions``."""
    noun = "form submission"
    if state is not None:
        return f"{shown} of {count_text(total, noun)}, state {humanize(state)}"
    if total == 0:
        return count_text(0, noun)
    by_state = ", ".join(f"{n} {humanize(s)}" for s, n in counts.items() if n)
    return f"{count_text(total, noun)}: {by_state}"


def template_summary(total: int, shown: int) -> str:
    noun = "form template"
    return count_text(total, noun) if shown == total else f"{shown} of {count_text(total, noun)}"


def counts_of(rows: Sequence[SubmissionRow]) -> dict[str, int]:
    """Rows by state, in the order the states first appear."""
    out: dict[str, int] = {}
    for row in rows:
        out[row.state] = out.get(row.state, 0) + 1
    return out


# --- the record screen and the panel ----------------------------------------------------------


def answer_text(value: Any) -> str:
    """An answer as a reader sees it: a list joined, a missing value ``—``."""
    if value is None:
        return EMPTY
    if isinstance(value, list):
        parts = [str(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
        return ", ".join(parts) if parts else EMPTY
    return _val(value)


def submission_page(
    detail: SubmissionDetail,
    template: TemplateRow | None,
    fields: Sequence[Mapping[str, Any]] = (),
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The submission as a page: identity ``<number> · <form>``, the state line, a panel's summary,
    then Review (who, when, the note or void reason) and Answers (each question's text, then the
    answer)."""
    lab = _labels(labels)
    row = detail.row
    title = template.title if template and template.title else ""
    rows: list[DetailRow] = [
        DetailRow("Author", _who(lab, row.author, technical), section="People"),
        DetailRow("Submitted", date_text(row.submitted_on), section="People"),
    ]
    if row.reviewed_by:
        rows.append(
            DetailRow(
                "Reviewed by",
                _val(join_facts(_who(lab, row.reviewed_by, technical), row.reviewed_on)),
                section=REVIEWING,
            )
        )
    if detail.review_note:
        rows.append(DetailRow("Note", detail.review_note, section=REVIEWING))
    if detail.void_reason:
        rows.append(DetailRow("Void reason", detail.void_reason, section=REVIEWING))
    texts = {str(f.get("id")): str(f.get("text") or f.get("id")) for f in fields}
    for ans in detail.answers:
        q = str(ans.get("q"))
        text = texts.get(q, q)
        value = answer_text(ans.get("value"))
        note = ans.get("note")
        rows.append(
            DetailRow(text, f"{value} ({note})" if note else value, section=ANSWERS, panel=False)
        )
    state = state_line(humanize(row.state))
    summary = join_facts(_who(lab, row.author, technical), row.submitted_on)
    return rows_page(
        rows,
        identity=identity_line(submission_number(row), title),
        state=state,
        summary=summary,
        technical=technical,
        panel=panel,
    )


def template_page(
    row: TemplateRow, labels: Labels | None = None, technical: bool = False, panel: bool = False
) -> Page:
    """A template as a page: identity ``<key> · <title>``, state, and a Form section."""
    rows = [
        DetailRow("Questions", _val(row.field_count), section="Form"),
        DetailRow("Version", _val(row.version), section="Form"),
        DetailRow("Published", date_text(row.published_on), section="Form"),
    ]
    summary = join_facts(f"version {row.version}", count_text(row.field_count or 0, "question"))
    return rows_page(
        rows,
        identity=identity_line(_val(row.key), row.title or ""),
        state=state_line(humanize(row.state)),
        summary=summary,
        technical=technical,
        panel=panel,
    )


# --- the runner -------------------------------------------------------------------------------


def parse_answer(step: Step, raw: str) -> Any:
    """The typed line as the value the question takes. A value that does not fit stays text."""
    text = raw.strip()
    kind = step.kind
    if kind == "number":
        try:
            number = float(text)
        except ValueError:
            return text
        return int(number) if number.is_integer() and "." not in text else number
    if kind == "yes_no_na":
        low = text.lower()
        return _YES_NO_ALIAS.get(low, low)
    if kind == "choice":
        return _choice(step.choices, text)
    if kind == "multi":
        return [_choice(step.choices, part.strip()) for part in text.split(",") if part.strip()]
    if kind == "photo":
        return [part.strip() for part in text.split(",") if part.strip()]
    return text


def _choice(choices: Sequence[str], text: str) -> str:
    """A choice by its number in the list, or by its words in any case; else the text as typed."""
    if text.isdigit() and 1 <= int(text) <= len(choices):
        return choices[int(text) - 1]
    for choice in choices:
        if choice.lower() == text.lower():
            return choice
    return text


def value_input(step: Step) -> str:
    """The current answer as the line shows it again (after Back)."""
    value = step.value
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)  # pyright: ignore[reportUnknownVariableType]
    return str(value)


def step_head(step: Step) -> str:
    """``Question 2 of 6 · Talk``."""
    base = f"Question {step.number} of {step.total}"
    return f"{base} · {step.section}" if step.section else base


def step_lines(step: Step) -> list[str]:
    """What the screen shows above the answer line: the question, its help, how to answer."""
    need = "required" if step.required else "optional, Enter on an empty line skips it"
    lines = [step.text]
    if step.help:
        lines.append(step.help)
    lines.append("")
    lines.append(f"({need})")
    if step.kind in ("choice", "multi"):
        several = ", several separated by commas" if step.kind == "multi" else ""
        lines.append(f"Choose by number or words{several}.")
        lines.extend(f"  {i}  {c}" for i, c in enumerate(step.choices, 1))
    else:
        hint = HINTS.get(step.kind, "")
        if step.kind == "number":
            bounds = _bounds(step)
            hint = f"{hint[:-1]}{bounds}."
        if hint:
            lines.append(hint)
    return lines


def _bounds(step: Step) -> str:
    unit = f" {step.unit}" if step.unit else ""
    if step.min is not None and step.max is not None:
        return f" from {step.min:g} to {step.max:g}{unit}"
    if step.min is not None:
        return f" of at least {step.min:g}{unit}"
    if step.max is not None:
        return f" of at most {step.max:g}{unit}"
    return f" in {step.unit}" if step.unit else ""


def review_page(review: Review, title: str) -> Page:
    """The review before the form is sent: each visible question with its answer, and the
    required ones still missing."""
    props: list[Prop | str] = []
    for line in review.lines:
        value = answer_text(line.value)
        if line.note:
            value = f"{value} ({line.note})"
        props.append(Prop(line.text, value))
    sections = [Section(ANSWERS, tuple(props), note="No answers")]
    if review.missing:
        sections.append(Section("Missing", tuple(review.missing)))
    return Page(
        identity=identity_line(title, ""),
        state=state_line("Review"),
        sections=tuple(sections),
    )


def problems_text(problems: Sequence[str]) -> str:
    """The runner's reasons as one line, as ``tl form`` prints them."""
    return "; ".join(problems)
