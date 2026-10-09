"""Links tab: a record's links grouped by relation, suggestions, and expected-but-missing links.

(P0-I3-T13; brief 7.4, sketch 12.) One table: a header row per group (``▾ raised against (2)``),
then a row per link with the record at the other end, the link's status, its pin and note;
suggestions form the last group. Below the table, one line per expected link the record lacks.
Row keys act on the highlighted link: Enter follows it, a/d accept or decline a suggestion,
u re-pins, v verifies, x retracts. Every command goes through `ClientInterface`; after one
succeeds the tab posts `RecordChanged` so the record view (and the grid) reload.

STUB (P0-I3-T13): the layout (`compose`), constructor, attributes and key bindings are final; the
functions and methods marked `raise NotImplementedError` (and the two lines marked `STUB`) are the
ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from tl_core.links.expected import MissingLink
from tl_core.services.link_queries import LinkView

from tl_tui.client import ClientInterface

COLUMNS: tuple[str, ...] = ("", "Key", "Title", "Status", "Pin", "Note")
SUGGESTED = "suggested"


@dataclass(frozen=True)
class TableRow:
    """A table row: a group header (``link_id`` is ``None``) or one link."""

    link_id: str | None
    cells: tuple[str, ...]


def status_text(view: LinkView) -> str:
    """The link's status as text and symbol (never colour alone): ``active``, ``✓ verified``,
    ``! stale``, ``✗ broken``, ``? suggested (0.82)``, ``declined`` or ``retracted``."""
    raise NotImplementedError


def pin_text(view: LinkView) -> str:
    """``floating`` when the link has no pin, else ``▪ <pin>``."""
    raise NotImplementedError


def group_title(label: str, count: int) -> str:
    """``▾ raised against (2)``."""
    raise NotImplementedError


def missing_line(missing: MissingLink) -> str:
    """``! expected but missing: supporting record (rule: references@Approved)``.

    The rule shows the relation, then ``@<state>`` when the expectation has a ``by_state``, then
    ``, <found> of <needed>`` when more than one link is needed.
    """
    raise NotImplementedError


def build_rows(views: Sequence[LinkView]) -> list[TableRow]:
    """Group header rows and link rows, in this order.

    Links that are not suggestions are grouped by (direction, relation) in the order given, each
    group headed by ``group_title(label, count)`` with the label of its first link. Suggested links
    form one last group headed ``group_title("suggested", n)``; their first cell is the label so the
    relation stays visible. A link row is ``("", key, title, status_text, pin_text, note)`` with
    ``—`` for a missing key and ``""`` for a missing note.
    """
    raise NotImplementedError


class LinksTab(Vertical, can_focus=True):
    """Shows the links of one record. Row actions call the client and post `RecordChanged`."""

    KEY_HINTS: ClassVar[str] = (
        "Enter follow  l link  R tray  a accept  d decline  u re-pin  v verify  x retract  t trace"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "follow", show=False),
        Binding("a", "accept", show=False),
        Binding("d", "decline", show=False),
        Binding("u", "repin", show=False),
        Binding("v", "verify", show=False),
        Binding("x", "retract", show=False),
    ]

    DEFAULT_CSS = """
    LinksTab { height: auto; }
    LinksTab > DataTable { height: auto; max-height: 18; }
    LinksTab > #links-missing { height: auto; padding: 0 1; }
    LinksTab > #links-note { height: auto; padding: 0 1; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        actor: str = "user:dev",
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.actor = actor
        self.record: dict[str, Any] | None = None
        self.views: dict[str, LinkView] = {}
        self.text = ""  # the last "empty" or "unavailable" note

    def compose(self) -> ComposeResult:
        yield DataTable(id="links-table", cursor_type="row")
        yield Static("", id="links-missing", markup=False)
        yield Static("", id="links-note", markup=False)

    def on_mount(self) -> None:
        self.query_one("#links-table", DataTable).add_columns(*COLUMNS)

    def on_focus(self) -> None:
        self.query_one("#links-table", DataTable).focus()

    def show_record(self, record: dict[str, Any]) -> None:
        self.record = record  # STUB: the ticket also calls ``self.reload()`` here

    def reload(self) -> None:
        """Read the links again and redraw. On a client error the display is kept."""
        raise NotImplementedError

    def _note(self, text: str) -> None:
        raise NotImplementedError

    def _highlighted(self) -> LinkView | None:
        raise NotImplementedError

    def highlighted_other(self) -> dict[str, Any] | None:
        """The record at the other end of the highlighted link row, or ``None``."""
        return None  # STUB: the ticket returns the record at the other end of the highlighted row

    # --- actions -----------------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        raise NotImplementedError

    def action_follow(self) -> None:
        raise NotImplementedError

    def _need_link(self) -> LinkView | None:
        raise NotImplementedError

    def _run(self, call: Any, done: str) -> None:
        raise NotImplementedError

    def action_accept(self) -> None:
        raise NotImplementedError

    def action_verify(self) -> None:
        raise NotImplementedError

    def action_decline(self) -> None:
        raise NotImplementedError

    def action_repin(self) -> None:
        raise NotImplementedError

    def action_retract(self) -> None:
        raise NotImplementedError
