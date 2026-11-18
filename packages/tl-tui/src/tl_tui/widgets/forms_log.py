"""The forms log, a submission's record screen and the fill runner (V3-F1b; skill ``tui-layout``).

``FormsLogScreen`` is a ``LogScreen`` with two views: ``1`` the project's submissions (number, form,
state, author, submitted) and ``2`` the published templates; Tab walks them. Enter on a submission
opens ``FormSubmissionScreen`` (everything, each question in words with its answer), except one of
the person's own drafts, which opens the runner with the saved answers in place (resume); Enter
or ``f`` on a published template opens ``FormRunnerScreen``, which fills it one question at a
time through ``tl_core.forms.runner`` (Enter answers, Up goes back, an empty line skips an
optional question, the review page and Enter send it). The send is ``SubmitForm`` through
``client.form_command`` as the person; what the server refuses is the status line, in the words
``tl form`` prints. A hidden or another person's draft submission is never in the rows, and its
key opens the same "not found" a missing key does (the client reads under the viewer's filter).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_core.forms import runner
from tl_mod_forms.commands import SubmitForm
from tl_mod_forms.views import SubmissionDetail, SubmissionRow, TemplateRow

from tl_tui import form_runner_text as text
from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Adaptive, Page, Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen

PUBLISHED = "Published"
DRAFT = "Draft"
LIST_LIMIT = 500
SENT = "Submitted "
Row = SubmissionRow | TemplateRow


class FormsLogScreen(LogScreen[Row]):
    """The forms of ``project`` (the id, not the scope): submissions, or published templates."""

    LOG_NAME: ClassVar[str] = text.VIEW_TITLES[text.SUBMISSIONS]
    KEY_HINTS: ClassVar[str] = (
        "1 submissions  2 templates  Tab next view  / filter  F5 reload  Esc back"
    )
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("1 submissions", "2 templates", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("1", "Show the project's form submissions"),
        ("2", "Show the form templates (f or Enter fills a published one)"),
        ("Tab", "Show the other view"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "view('submissions')", "Submissions", show=False),
        Binding("2", "view('templates')", "Templates", show=False),
        Binding("tab", "next_view", "Next view", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.forms_view = text.SUBMISSIONS
        self.templates: dict[str, TemplateRow] = {}  # by id, as last read
        self.total = 0
        self._summary = ""
        self._sent = ""  # the number just sent, named in the status line until the view changes

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return (
            text.SUBMISSION_COLUMNS
            if self.forms_view == text.SUBMISSIONS
            else text.TEMPLATE_COLUMNS
        )

    def drop_order(self) -> Sequence[str]:
        return text.SUBMISSION_DROP if self.forms_view == text.SUBMISSIONS else text.TEMPLATE_DROP

    def shrink_columns(self) -> Sequence[str]:
        return ("Author",)

    def load_rows(self) -> Sequence[Row]:
        """The view's rows, as the client gives them (hidden ones are not there)."""
        if self.forms_view == text.TEMPLATES:
            page = self.client.list_form_templates(state=PUBLISHED, limit=LIST_LIMIT)
            self.templates.update({r.id: r for r in page.rows})
            self.total = page.total
            self._summary = text.template_summary(page.total, len(page.rows))
            return page.rows
        try:
            self.templates = {
                r.id: r for r in self.client.list_form_templates(limit=LIST_LIMIT).rows
            }
        except CLIENT_ERRORS:
            self.templates = {}  # the titles are a convenience; the submissions still list
        subs = self.client.list_form_submissions(self.project, limit=LIST_LIMIT)
        self.total = subs.total
        self._summary = text.submission_summary(
            text.counts_of(subs.rows), subs.total, len(subs.rows)
        )
        return subs.rows

    def row_key(self, row: Row) -> str:
        return (row.key or row.id) if isinstance(row, SubmissionRow) else row.id

    def row_cells(self, row: Row) -> Sequence[str]:
        if isinstance(row, SubmissionRow):
            titles = {i: t.title or "" for i, t in self.templates.items()}
            return text.submission_cells(row, titles)
        return text.template_cells(row)

    def row_record(self, row: Row) -> tuple[str, str]:
        if isinstance(row, SubmissionRow):
            template = self.templates.get(row.template_id or "")
            return (text.submission_number(row), (template.title or "") if template else "")
        return (row.key or "", row.title or "")

    def panel_text(self, row: Row | None) -> Panel:
        if row is None:
            return "No form matches."
        technical = mode_of(self.app).technical
        if isinstance(row, TemplateRow):
            return render(text.template_page(row, technical=technical, panel=True))
        try:
            detail = self.client.get_form_submission(self.project, row.key or row.id)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This form could not be read."
        template = self.templates.get(row.template_id or "")
        return render(text.submission_page(detail, template, technical=technical, panel=True))

    def actions_for(self, row: Row) -> Sequence[LogAction]:
        """A published template is filled with ``f``; a submission has no action in the log."""
        if isinstance(row, TemplateRow) and row.state == PUBLISHED:
            return [LogAction("f", "Fill this form", lambda: self._fill_form(row))]
        return []

    def summary_text(self) -> str:
        return f"{SENT}{self._sent} · {self._summary}" if self._sent else self._summary

    def open_row(self, row: Row) -> None:
        if isinstance(row, SubmissionRow) and row.state == DRAFT:
            self._resume_draft(row)
        elif isinstance(row, SubmissionRow):
            self.app.push_screen(FormSubmissionScreen(self.client, self.project, row.key or row.id))
        elif row.state == PUBLISHED:
            self._fill_form(row)
        else:
            self.say("Only a published template can be filled.")

    # --- views ---------------------------------------------------------------------------

    def action_view(self, which: str) -> None:
        if which in text.VIEW_TITLES and which != self.forms_view:
            self._switch(which)

    def action_next_view(self) -> None:
        self._switch(text.TEMPLATES if self.forms_view == text.SUBMISSIONS else text.SUBMISSIONS)

    def _switch(self, which: str) -> None:
        """Show another view: its columns first, then its rows."""
        self.forms_view = which
        self._sent = ""
        self.LOG_NAME = text.VIEW_TITLES[which]  # pyright: ignore[reportAttributeAccessIssue]
        self.rows = []  # the rows of the other view are not rows of this one
        table = self.query_one("#log-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.columns())
        self._fill(None)
        self.reload()

    # --- filling -------------------------------------------------------------------------

    def _fill_form(self, row: TemplateRow) -> None:
        self.app.push_screen(FormRunnerScreen(self.client, self.project, row), self._filled)

    def _resume_draft(self, row: SubmissionRow) -> None:
        """Enter on one of the person's own drafts: the runner, with the saved answers in place."""
        template = self.templates.get(row.template_id or "")
        if template is None:
            self.say("The form of this draft could not be read.", error=True)
            return
        self.app.push_screen(
            FormRunnerScreen(self.client, self.project, template, draft=row), self._filled
        )

    def _filled(self, number: str | None) -> None:
        """The runner closed: after a send, show the submissions with the new number in them."""
        if number is None:
            return
        self._switch(text.SUBMISSIONS)
        self._sent = number


class FormSubmissionScreen(ModalScreen[None]):
    """One submission in full. Esc closes it, F5 reads it again. A key that is not a submission
    this person may read is one "not found", whether it is missing, hidden or another's draft."""

    KEY_HINTS: ClassVar[str] = "Esc back  F5 reload"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
    ]

    DEFAULT_CSS = """
    FormSubmissionScreen { background: $surface; }
    FormSubmissionScreen #fs-body { height: 1fr; padding: 0 1; }
    FormSubmissionScreen #fs-keys { height: 1; color: $text-muted; }
    FormSubmissionScreen #fs-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self.detail: SubmissionDetail | None = None
        self._gen = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="fs-body"):
                yield Static("", markup=False, id="fs-page")
            yield Static(self.KEY_HINTS, markup=False, id="fs-keys")
            yield Static("", markup=False, id="fs-status")

    def on_mount(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical), group="form", exclusive=True
        )

    def _read(self) -> tuple[SubmissionDetail, TemplateRow | None, list[dict[str, Any]]]:
        detail = self.client.get_form_submission(self.project, self.key)
        template: TemplateRow | None = None
        fields: list[dict[str, Any]] = []
        try:
            rows = self.client.list_form_templates(limit=LIST_LIMIT).rows
            template = next((r for r in rows if r.id == detail.row.template_id), None)
            if template is not None and template.key and template.version:
                body = self.client.get_form_template(
                    template.key, detail.row.template_version or template.version
                )
                fields = list(body["fields"])
        except CLIENT_ERRORS:
            pass  # the questions' words are a convenience; the answers still show by id
        return detail, template, fields

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            detail, template, fields = await asyncio.to_thread(self._read)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self.detail = None
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self.detail = detail
            self._show(text.submission_page(detail, template, fields, technical=technical), "")

    def _show(self, page: Page | None, error: str) -> None:
        body: Adaptive | str = render(page) if page is not None else "This form could not be read."
        self.query_one("#fs-page", Static).update(body)
        self.query_one("#fs-status", Static).update(("! " + error) if error else "")

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)


class FormRunnerScreen(ModalScreen[str | None]):
    """Fill one published template, one visible question at a time (``tl_core.forms.runner``).

    Closes with the new number after a send, with ``None`` when cancelled."""

    KEY_FILL: ClassVar[str] = "Enter answer  Up back  Esc cancel"
    KEY_REVIEW: ClassVar[str] = "Enter send  Up back  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "back", "Back", show=False),
        Binding("enter", "send", "Send", show=False),
    ]

    DEFAULT_CSS = """
    FormRunnerScreen { background: $surface; }
    FormRunnerScreen > Vertical { padding: 0 1; }
    FormRunnerScreen #fr-head { height: 1; text-style: bold; }
    FormRunnerScreen #fr-body { height: 1fr; }
    FormRunnerScreen #fr-input { height: 3; }
    FormRunnerScreen #fr-keys { height: 1; color: $text-muted; }
    FormRunnerScreen #fr-status { height: 1; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        template: TemplateRow,
        draft: SubmissionRow | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.template = template
        self.draft = draft  # a draft being resumed: its answers fill the steps, its id is sent
        self.fields: list[dict[str, Any]] = []
        self.state: runner.RunnerState | None = None
        self.ready = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="fr-head")
            with VerticalScroll(id="fr-body"):
                yield Static("", markup=False, id="fr-page")
            yield Input(placeholder="Answer", id="fr-input")
            yield Static(self.KEY_FILL, markup=False, id="fr-keys")
            yield Static("", markup=False, id="fr-status")

    def on_mount(self) -> None:
        self.run_worker(self._load(), group="runner", exclusive=True)

    def _read(self) -> tuple[Any, list[dict[str, Any]]]:
        """The template version the form was started with, and the draft's saved answers."""
        version = (self.draft.template_version if self.draft else None) or self.template.version
        body = self.client.get_form_template(self.template.key or "", version or 1)
        if self.draft is None:
            return body, []
        found = self.client.get_form_submission(self.project, self.draft.key or self.draft.id)
        self.draft = found.row  # the version read now is the one the send expects
        return body, list(found.answers)

    async def _load(self) -> None:
        try:
            body, saved = await asyncio.to_thread(self._read)
        except CLIENT_ERRORS as exc:
            if self.is_attached:
                self._status(describe_error(exc), error=True)
                self.query_one("#fr-input", Input).display = False
            return
        if not self.is_attached:
            return
        self.fields = list(body["fields"])
        fmt = int(body["row"].get("format_version") or 2)
        self.state = runner.start(self.fields, fmt=fmt, answers=saved)
        self.ready = True
        self._draw()

    # --- drawing -------------------------------------------------------------------------

    def _title(self) -> str:
        return self.template.title or self.template.key or "Form"

    def _status(self, line: str, *, error: bool = False) -> None:
        self.query_one("#fr-status", Static).update(("! " if error else "") + line)

    def _draw(self) -> None:
        assert self.state is not None
        head = self.query_one("#fr-head", Static)
        page = self.query_one("#fr-page", Static)
        field = self.query_one("#fr-input", Input)
        keys = self.query_one("#fr-keys", Static)
        current = runner.step(self.state, self.fields)
        if current is None:  # the review
            head.update(f"{self._title()} · Review")
            page.update(
                render(text.review_page(runner.review(self.state, self.fields), self._title()))
            )
            field.display = False
            field.value = ""
            keys.update(self.KEY_REVIEW)
            self.set_focus(None)
            return
        head.update(f"{self._title()} · {text.step_head(current)}")
        page.update("\n".join(text.step_lines(current)))
        field.display = True
        field.value = text.value_input(current)
        keys.update(self.KEY_FILL)
        field.focus()
        field.select_all()  # a typed answer replaces the one shown after Back

    # --- keys ----------------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter on the answer line: answer (or skip an empty optional line) and move on."""
        event.stop()
        if self.state is None:
            return
        current = runner.step(self.state, self.fields)
        if current is None:
            return
        raw = event.value.strip()
        if not raw:
            moved, problems = runner.skip(self.state, self.fields)
        else:
            moved, problems = runner.answer(
                self.state, self.fields, text.parse_answer(current, raw)
            )
        if problems:
            self._status(text.problems_text(problems), error=True)
            return
        self.state = moved
        self._status("")
        self._draw()

    def action_back(self) -> None:
        if self.state is None:
            return
        self.state = runner.back(self.state, self.fields)
        self._status("")
        self._draw()

    def action_send(self) -> None:
        """Enter on the review page: send the confirmed answers as the person."""
        if self.state is None or self.state.phase != "review":
            return
        try:
            answers = runner.confirm(self.state, self.fields)
        except runner.RunnerError as exc:
            self._status(text.problems_text(exc.problems), error=True)
            return
        try:
            cmd = SubmitForm(
                actor=str(getattr(self.app, "actor", "user:dev")),
                source="tui",
                scope=f"project:{self.project}",
                template_id=None if self.draft else self.template.id,
                draft_id=self.draft.id if self.draft else None,
                answers=answers,
                expected_version=self.draft.version if self.draft else None,
            )
            made = self.client.form_command("SubmitForm", cmd)
        except CLIENT_ERRORS as exc:
            self._status(describe_error(exc), error=True)
            return
        self.dismiss(str(made.key or made.stream_id))

    def action_cancel(self) -> None:
        self.dismiss(None)
