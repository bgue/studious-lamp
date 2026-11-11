"""In-memory punch reads for `FakeClient` (P2-PUNCH-T04): the three reads and the one write door.

It holds the items a test gave it, per project (`load_punch`), and answers each read with the
filters of the matching view (``tl_mod_quality.views``): state, area, system, assignee, category,
the source key (``from``), overdue (Open and due before today). The list is sorted by key and cut
to ``limit`` (1 to 500); ``total`` counts the matches before the cut. A missing item raises
`RecordNotFoundError` with the route's text. `quality_command` records the command in
`punch_commands` after the same name check as the embedded client. `seed_punch` makes the six
items the punch screen tests share.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from tl_api.routes.punch import MSG_NOT_FOUND
from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality import views as punch_views
from tl_mod_quality.api import MSG_CATEGORY
from tl_mod_quality.module import PUNCH_COMMANDS
from tl_mod_quality.names import CLEARED, OPEN, VERIFIED, VOID

_STATES: tuple[str, ...] = (OPEN, CLEARED, VERIFIED, VOID)
_CATEGORIES = ("A", "B", "C")


class FakePunchSupport:
    """Mixin for `FakeClient`: call `_init_punch()` from its `__init__`."""

    def _init_punch(self) -> None:
        self._punch: dict[str, list[punch_views.PunchDetail]] = {}
        self.punch_commands: list[Command] = []  # every punch command, in call order

    # --- seeding -----------------------------------------------------------------------------

    def load_punch(self, project: str, details: Sequence[punch_views.PunchDetail]) -> None:
        """Replace one project's punch items. Each item's ``row`` is what the lists show."""
        self._punch[project] = list(details)

    def _punch_of(self, project: str) -> list[punch_views.PunchDetail]:
        return self._punch.get(project, [])

    # --- reads -------------------------------------------------------------------------------

    def list_punch_items(
        self,
        project: str,
        *,
        state: str | None = None,
        area: str | None = None,
        system: str | None = None,
        assignee: str | None = None,
        category: str | None = None,
        from_key: str | None = None,
        overdue: bool = False,
        limit: int = 200,
    ) -> punch_views.PunchPage:
        if state is not None and state not in _STATES:
            raise ValueError(punch_views.MSG_STATE)
        if category is not None and category not in _CATEGORIES:
            raise ValueError(MSG_CATEGORY)
        today = date.today().isoformat()
        cap = max(1, min(int(limit), punch_views.MAX_LIMIT))
        matches: list[punch_views.PunchRow] = []
        for item in sorted(self._punch_of(project), key=lambda d: d.row.key):
            row = item.row
            if state is not None and row.state != state:
                continue
            if area is not None and row.area != area:
                continue
            if system is not None and row.system != system:
                continue
            if assignee is not None and row.assignee != assignee:
                continue
            if category is not None and row.category != category:
                continue
            if from_key is not None and row.source_key != from_key:
                continue
            due = row.due_on is not None and row.due_on < today
            if overdue and not (row.state == OPEN and due):
                continue
            matches.append(row)
        return punch_views.PunchPage(rows=matches[:cap], total=len(matches))

    def get_punch_item(self, project: str, key: str) -> punch_views.PunchDetail:
        for item in self._punch_of(project):
            if item.row.key == key:
                return item
        raise RecordNotFoundError(MSG_NOT_FOUND)

    def get_punch_counts(self, project: str) -> dict[str, int]:
        counts: dict[str, int] = dict.fromkeys(_STATES, 0)
        for item in self._punch_of(project):
            if item.row.state in counts:
                counts[item.row.state] += 1
        return counts

    # --- the write door ----------------------------------------------------------------------

    def quality_command(self, name: str, cmd: Command) -> CommandResult:
        spec = next((c for c in PUNCH_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a quality command")
        self.punch_commands.append(cmd)
        return CommandResult(stream_id="PUN-1", key=None, version=1, events=[])


def _item(
    n: int,
    state: str,
    *,
    category: str,
    area: str,
    system: str,
    assignee: str | None,
    due_on: str | None = None,
    source_key: str | None = None,
) -> punch_views.PunchDetail:
    """One item of the seed: the row and the facts a state carries."""
    row = punch_views.PunchRow(
        id=f"PUN-{n}",
        key=f"P123-PUN-{n:04d}",
        subject=f"Punch item {n}",
        state=state,
        category=category,
        area=area,
        system=system,
        due_on=due_on,
        assignee=assignee,
        raised_by="user:uma",
        source_key=source_key,
    )
    cleared = state in (VERIFIED, CLEARED)
    return punch_views.PunchDetail(
        row=row,
        description=None,
        cleared_by="user:uma" if cleared else None,
        cleared_on="2026-10-02" if cleared else None,
        clear_note="Tightened" if cleared else None,
        verified_by="user:rob" if state == VERIFIED else None,
        verified_on="2026-10-05" if state == VERIFIED else None,
        reopen_count=0,
        last_reopen_reason=None,
        void_reason="Raised in error" if state == VOID else None,
        source_type="correspondence.Item" if source_key else None,
        version=1,
    )


def seed_punch(client: FakePunchSupport, project: str = "P123") -> list[str]:
    """Six items for ``project``, returned by key in key order.

    Three Open (one of them overdue, one raised from a source key), one Cleared, one Verified and
    one Void. Areas L1 to L3, systems HVAC, Piping and Electrical, categories A to C, two
    assignees and one unassigned item.
    """
    items = [
        _item(
            1,
            OPEN,
            category="A",
            area="L2",
            system="HVAC",
            assignee="Ferrari",
            due_on="2026-01-01",
        ),
        _item(
            2,
            OPEN,
            category="B",
            area="L3",
            system="Piping",
            assignee="Okafor",
            due_on="2099-12-31",
            source_key="P123-IWP-0001",
        ),
        _item(3, OPEN, category="B", area="L1", system="HVAC", assignee="Ferrari"),
        _item(4, CLEARED, category="B", area="L1", system="Electrical", assignee=None),
        _item(
            5,
            VERIFIED,
            category="C",
            area="L2",
            system="Electrical",
            assignee="Okafor",
            due_on="2099-12-31",
        ),
        _item(6, VOID, category="A", area="L3", system="Piping", assignee="Ferrari"),
    ]
    client.load_punch(project, items)
    return [item.row.key for item in items]
