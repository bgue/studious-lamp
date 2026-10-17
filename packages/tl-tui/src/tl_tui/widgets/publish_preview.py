"""The publish preview: what publishing a derived document would create, and the approval (P1-I3).

Opened from the derived-documents screen with ``p``. It shows the module's plan for the latest
pass: how many records would be created, which rows exist already or are invalid, and what stops
the whole publication. ``s`` says "skip existing rows" (rows whose key exists are left alone).
``p`` publishes: the first press asks, the second creates the records as one correlated import;
publishing into tags needs the admin role and into documents the document controller role
(ADR-0014), and the screen does not offer it to anyone else. ``c`` shows what compensating the
publication in force would take back and ``u`` does it (admin, also asked twice). The screen decides
nothing: whether a publication can go ahead is the plan's ``can_publish``.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    CompensationPlan,
    PublishDerivedDocuments,
    PublishDerivedTags,
    PublishPlan,
)

from tl_tui.client import ClientInterface
from tl_tui.derive_text import (
    PLAN_COLUMNS,
    can_apply,
    compensation_lines,
    plan_cells,
    plan_header_lines,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error

MAX_PLAN_ROWS = 2000


class PublishPreviewScreen(ModalScreen[bool]):
    """Dismisses with ``True`` when records were created or taken back, else ``False``."""

    KEY_HINTS: ClassVar[str] = (
        "p publish (twice)  s skip existing  c compensation  u undo (twice)  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("p", "publish", "Publish", show=False),
        Binding("s", "skip_existing", "Skip existing", show=False),
        Binding("c", "compensation", "Compensation", show=False),
        Binding("u", "compensate", "Undo", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    PublishPreviewScreen { background: $surface; }
    PublishPreviewScreen > Vertical { padding: 0 1; }
    PublishPreviewScreen #pp-title { text-style: bold; height: 1; }
    PublishPreviewScreen #pp-header { height: auto; max-height: 8; }
    PublishPreviewScreen #pp-table { height: 1fr; min-height: 6; }
    PublishPreviewScreen #pp-detail { height: 8; border-top: solid $accent; padding: 0 1; }
    PublishPreviewScreen #pp-status { height: 2; }
    PublishPreviewScreen #pp-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        actor: str,
        derived: str,
        *,
        is_admin: bool = False,
        is_controller: bool = False,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.derived = derived  # the derived document's key or id
        self.is_admin = is_admin
        self.is_controller = is_controller or is_admin
        self.skip_existing = False
        self.show_compensation = False
        self.confirming: str | None = None  # "publish" or "compensate": the next press does it
        self.changed = False  # records were created or taken back
        self.plan: PublishPlan | None = None
        self.compensation: CompensationPlan | None = None

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Publish {self.derived}", markup=False, id="pp-title")
            yield Static("", markup=False, id="pp-header")
            yield DataTable[str](id="pp-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="pp-detail")
            yield Static("", markup=False, id="pp-status")
            yield Static(self.KEY_HINTS, markup=False, id="pp-hints")

    def on_mount(self) -> None:
        self.query_one("#pp-table", DataTable).add_columns(*PLAN_COLUMNS)
        self.reload()
        self.query_one("#pp-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the plan and the compensation preview again and show them."""
        self.confirming = None
        try:
            self.plan = self.client.get_publish_preview(self.project, self.derived)
            self.compensation = self.client.get_compensation_preview(self.project, self.derived)
        except CLIENT_ERRORS as exc:
            self.plan = None
            self.compensation = None
            self._say(describe_error(exc), error=True)
            self._fill()
            return
        self._fill()

    def _fill(self) -> None:
        """Show the header, the rows and the panel for the plan (or the compensation) read."""
        table = self.query_one("#pp-table", DataTable)
        table.clear()
        header = self.query_one("#pp-header", Static)
        detail = self.query_one("#pp-detail", Static)
        if self.plan is None:
            header.update("")
            detail.update("")
            return
        header.update("\n".join(plan_header_lines(self.plan)))
        for cells in plan_cells(self.plan, MAX_PLAN_ROWS):
            table.add_row(*(Text(cell) for cell in cells))
        if self.show_compensation and self.compensation is not None:
            detail.update("\n".join(compensation_lines(self.compensation)))
        else:
            detail.update(self._offer())

    def _offer(self) -> str:
        """What the person may do now, in one or two lines."""
        plan = self.plan
        if plan is None:
            return ""
        if not can_apply(plan, self.skip_existing):
            if plan.needs_skip_existing and plan.can_publish:
                return "Rows exist already: press s to skip them, then p to publish the rest."
            return "This derived document cannot be published as it stands."
        needs = "admin" if plan.target == "tags" else "document controller"
        allowed = self.is_admin if plan.target == "tags" else self.is_controller
        suffix = "" if allowed else f" (needs the {needs} role: not offered to you)"
        skip = " skipping the rows that exist" if self.skip_existing else ""
        return (
            f"Press p twice to create {plan.counts.get('create', 0)} {plan.target}{skip}.{suffix}"
        )

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#pp-status", Static).update(("! " if error else "") + text)

    # --- actions -------------------------------------------------------------------------

    def action_skip_existing(self) -> None:
        """Say whether rows whose key exists are left alone."""
        self.skip_existing = not self.skip_existing
        self.confirming = None
        self._say("Skipping rows that exist." if self.skip_existing else "Not skipping rows.")
        self._fill()

    def action_compensation(self) -> None:
        """Switch the panel between the offer and what compensating would take back."""
        self.show_compensation = not self.show_compensation
        self.confirming = None
        self._fill()

    def action_publish(self) -> None:
        """Ask on the first press; on the second create the records as one correlated import."""
        plan = self.plan
        if plan is None:
            self._say("There is no plan to publish.", error=True)
            return
        allowed = self.is_admin if plan.target == "tags" else self.is_controller
        if not allowed:
            role = "admin" if plan.target == "tags" else "document controller"
            self._say(f"Publishing into {plan.target} needs the {role} role.", error=True)
            return
        if not can_apply(plan, self.skip_existing):
            self._say(self._offer(), error=True)
            return
        if self.confirming != "publish":
            self.confirming = "publish"
            self._say(
                f"Create {plan.counts.get('create', 0)} {plan.target} from {plan.derived_key}? "
                "Press p again to confirm, Esc to leave."
            )
            return
        self.confirming = None
        fields = {
            "actor": self.actor,
            "source": "tui",
            "scope": f"project:{self.project}",
            "derived_id": plan.derived_id,
            "expected_content_rev": plan.content_rev,
            "skip_existing": self.skip_existing,
        }
        try:
            if plan.target == "tags":
                self.client.publish_derived_tags(PublishDerivedTags(**fields))
            else:
                self.client.publish_derived_documents(PublishDerivedDocuments(**fields))
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            self.reload()
            return
        self.changed = True
        self.reload()
        self._say(f"Published {plan.counts.get('create', 0)} {plan.target}.")

    def action_compensate(self) -> None:
        """Ask on the first press; on the second take the publication in force back (admin)."""
        compensation = self.compensation
        if compensation is None or not compensation.can_compensate:
            self._say("There is no publication that can be taken back.", error=True)
            return
        if not self.is_admin:
            self._say("Compensating a publication needs the admin role.", error=True)
            return
        if self.confirming != "compensate":
            self.confirming = "compensate"
            self.show_compensation = True
            self._fill()
            self._say(
                f"Take back {len(compensation.items)} items of {compensation.derived_key}? "
                "Press u again to confirm, Esc to leave."
            )
            return
        self.confirming = None
        try:
            self.client.compensate_publication(
                CompensatePublication(
                    actor=self.actor,
                    source="tui",
                    scope=f"project:{self.project}",
                    derived_id=compensation.derived_id,
                    reason="compensated in the TUI",
                )  # fmt: skip
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            self.reload()
            return
        self.changed = True
        self.show_compensation = False
        self.reload()
        self._say("Publication taken back.")

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if self.confirming is not None:
            self.confirming = None
            self._say("Not confirmed.")
            return
        self.dismiss(self.changed)
