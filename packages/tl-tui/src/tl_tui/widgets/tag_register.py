"""The tag register: a project's engineering tags, their class, state and conformance (P1-I1-T09d).

A full-size modal opened with ``F8``, a ``LogScreen`` (P1-UX2-S3). The list shows the project's tags
by number; ``does not fit`` in the ``Number check`` column marks a number that breaks the registry
pattern, ``Conformance`` is the stored conformance level. The panel describes the highlighted tag:
its parts, why its number is refused or accepted, and what it still lacks. The actions bar offers
what the server says the viewer may do to the tag (``allowed_actions``). Enter on a row opens the
full record screen (P1-UX-T02); Esc returns to the same row. The filter keys narrow the list on the
screen (class, violations only, text); ``a`` asks the client for the ended tags too.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_engineering.views import TagView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
from tl_tui.log_actions import ACTION_UI, Runner, log_actions, screen_runner
from tl_tui.tag_text import COLUMNS, detail_lines, next_class, row_cells, summary_line
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

MAX_TAGS = 5000


class TagRegisterScreen(LogScreen[TagView]):
    """The tags of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Tags"
    KEY_HINTS: ClassVar[str] = (
        "c class  v violations only  a ended too  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "class_filter", "Class", show=False),
        Binding("v", "violations", "Violations only", show=False),
        Binding("a", "ended", "Ended too", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.class_code: str | None = None
        self.violations_only = False
        self.include_ended = False
        self.views: list[TagView] = []  # as listed, before the screen's own filters
        self.detail: TagView | None = None  # the highlighted tag with its issues
        self.labels = Labels()  # the labels of the tag screen, loaded with the first rows
        self._labelled = False

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return COLUMNS

    def load_rows(self) -> Sequence[TagView]:
        if not self._labelled:
            self.labels = load_labels(self.client, f"project:{self.project}", ("engineering.Tag",))
            self._labelled = True
        self.views = self.client.list_tags(
            self.project, include_ended=self.include_ended, limit=MAX_TAGS
        )
        return [
            v
            for v in self.views
            if (self.class_code is None or v.class_code == self.class_code)
            and (not self.violations_only or v.number_status == "violation")
        ]

    def row_key(self, row: TagView) -> str:
        return row.number

    def row_cells(self, row: TagView) -> Sequence[str]:
        return row_cells(row, self.labels)

    def row_record(self, row: TagView) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: TagView | None) -> str:
        """The highlighted tag with what it lacks (one ``get_tag`` call per tag)."""
        if row is None:
            self.detail = None  # nothing is highlighted, so nothing is described
            return "No tag matches."
        try:
            full = self.client.get_tag(self.project, row.number)
        except CLIENT_ERRORS as exc:
            full = row  # the listing's copy: no issues
            self.say(describe_error(exc), error=True)
        self.detail = full
        technical = mode_of(self.app).technical
        return "\n".join(detail_lines(full, self.labels, technical=technical))

    def actions_for(self, row: TagView) -> Sequence[LogAction]:
        offers = self.client.allowed_actions(row.id)
        return log_actions(offers, ACTION_UI, self._runner(), version=row.version)

    def summary_text(self) -> str:
        return summary_line(
            len(self.shown),
            len(self.views),
            class_code=self.class_code,
            violations_only=self.violations_only,
            include_ended=self.include_ended,
            text=self.filter_text,
            labels=self.labels,
        )

    def open_row(self, row: TagView) -> None:
        """Enter on a row opens its full record; Esc on that screen returns to this row."""
        actor = str(getattr(self.app, "actor", "user:dev"))
        open_record(self, self.client, f"project:{self.project}", self.project, actor, row.id)

    def _runner(self) -> Runner:
        actor = str(getattr(self.app, "actor", "user:dev"))
        return screen_runner(self, self.client, actor=actor, scope=f"project:{self.project}")

    # --- the log's own keys --------------------------------------------------------------

    def action_class_filter(self) -> None:
        """Show the next class: all, then each class that has a tag in the list, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        classes = [v.class_code for v in self.views if v.class_code is not None]
        self.class_code = next_class(self.class_code, classes)
        self.reload()

    def action_violations(self) -> None:
        """Show only the tags whose number breaks the pattern, or all again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.violations_only = not self.violations_only
        self.reload()

    def action_ended(self) -> None:
        """Include the superseded and deleted tags, or leave them out again (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.include_ended = not self.include_ended
        self.reload()
