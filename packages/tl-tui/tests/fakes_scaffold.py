"""In-memory scaffold reads for `FakeClient` (P2-I4B-T09b2): the four reads.

It holds the scaffolds a test gave it, per project (`load_scaffolds`), and answers each read with
the filters of the matching view (``tl_mod_scaffold.views``): state, tag, overdue (a standing
scaffold past its next inspection day), and the due list (standing, due on or before today). The
list is sorted by key and cut to ``limit`` (1 to 500); ``total`` counts the matches before the cut.
The export takes the matches, cut to the route's export cap, and renders them with the real
``views.export_rows``. A missing scaffold raises `RecordNotFoundError` with the route's text.
`seed_scaffolds` makes the five scaffolds the scaffold screen tests share.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from tl_api.routes.scaffold import MSG_NOT_FOUND
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold import views as scaffold_views
from tl_mod_scaffold.names import (
    DESIGNED_STATE,
    DISMANTLE,
    ERECTING_STATE,
    IN_USE,
    INSPECTED_STATE,
    MODIFY,
    REMOVED,
    REQUESTED,
)
from tl_mod_scaffold.rules import STANDING_STATES

_STATES: tuple[str, ...] = (
    REQUESTED,
    DESIGNED_STATE,
    ERECTING_STATE,
    INSPECTED_STATE,
    IN_USE,
    MODIFY,
    DISMANTLE,
    REMOVED,
)
_TAGS: tuple[str, ...] = ("green", "yellow", "red")


class FakeScaffoldSupport:
    """Mixin for `FakeClient`: call `_init_scaffold()` from its `__init__`."""

    def _init_scaffold(self) -> None:
        self._scaffold: dict[str, list[scaffold_views.ScaffoldDetail]] = {}

    # --- seeding -----------------------------------------------------------------------------

    def load_scaffolds(
        self, project: str, details: Sequence[scaffold_views.ScaffoldDetail]
    ) -> None:
        """Replace one project's scaffolds. Each scaffold's ``row`` is what the lists show."""
        self._scaffold[project] = list(details)

    def _scaffold_of(self, project: str) -> list[scaffold_views.ScaffoldDetail]:
        return self._scaffold.get(project, [])

    def _scaffold_matches(
        self,
        project: str,
        *,
        state: str | None,
        tag: str | None,
        overdue: bool,
    ) -> list[scaffold_views.ScaffoldRow]:
        """The rows the filters keep, sorted by key then id (the view's order)."""
        today = date.today().isoformat()
        if state is not None and state not in _STATES:
            raise ValueError(scaffold_views.MSG_STATE)
        if tag is not None and tag not in _TAGS:
            raise ValueError(scaffold_views.MSG_TAG)
        matches: list[scaffold_views.ScaffoldRow] = []
        for item in sorted(self._scaffold_of(project), key=lambda d: (d.row.key, d.row.id)):
            row = item.row
            if state is not None and row.state != state:
                continue
            if tag is not None and row.tag != tag:
                continue
            if overdue and not (
                row.state in STANDING_STATES
                and row.next_due_on is not None
                and row.next_due_on < today
            ):
                continue
            matches.append(row)
        return matches

    # --- reads -------------------------------------------------------------------------------

    def list_scaffolds(
        self,
        project: str,
        *,
        state: str | None = None,
        tag: str | None = None,
        overdue: bool = False,
        limit: int = 200,
    ) -> scaffold_views.ScaffoldPage:
        matches = self._scaffold_matches(project, state=state, tag=tag, overdue=overdue)
        cap = max(1, min(int(limit), scaffold_views.MAX_LIMIT))
        return scaffold_views.ScaffoldPage(rows=matches[:cap], total=len(matches))

    def get_scaffold(self, project: str, key: str) -> scaffold_views.ScaffoldDetail:
        for item in self._scaffold_of(project):
            if item.row.key == key:
                return item
        raise RecordNotFoundError(MSG_NOT_FOUND)

    def list_scaffolds_due(
        self, project: str, *, limit: int = 200
    ) -> list[scaffold_views.ScaffoldRow]:
        today = date.today().isoformat()
        due = [
            item.row
            for item in self._scaffold_of(project)
            if item.row.state in STANDING_STATES
            and item.row.next_due_on is not None
            and item.row.next_due_on <= today
        ]
        due.sort(key=lambda r: (r.next_due_on or "", r.key, r.id))
        cap = max(1, min(int(limit), scaffold_views.MAX_LIMIT))
        return due[:cap]

    def export_scaffolds(
        self,
        project: str,
        *,
        fmt: str = "csv",
        state: str | None = None,
        tag: str | None = None,
        overdue: bool = False,
    ) -> str:
        if fmt not in scaffold_views.EXPORT_FORMATS:
            raise ValueError(scaffold_views.MSG_FORMAT)
        matches = self._scaffold_matches(project, state=state, tag=tag, overdue=overdue)
        return scaffold_views.export_rows(matches[: scaffold_views.MAX_LIMIT], fmt)


def _row(
    n: int,
    state: str,
    *,
    tag: str | None = None,
    tagged_on: str | None = None,
    last_inspected_on: str | None = None,
    next_due_on: str | None = None,
    location: str | None = None,
) -> scaffold_views.ScaffoldRow:
    return scaffold_views.ScaffoldRow(
        id=f"SCF-{n}",
        key=f"P123-SCF-{n:04d}",
        subject=f"Scaffold {n}",
        state=state,
        tag=tag,
        tagged_on=tagged_on,
        last_inspected_on=last_inspected_on,
        next_due_on=next_due_on,
        location=location,
        elevation="+12.0",
        gridline="C-4",
        load_class="Light",
        request_key=None,
    )


def _inspection(
    n: int, inspected_on: str, result: str, tag: str, note: str | None
) -> scaffold_views.InspectionRow:
    return scaffold_views.InspectionRow(
        key=f"P123-INS-{n:04d}",
        inspected_on=inspected_on,
        inspector="uma",
        result=result,
        tag=tag,
        note=note,
    )


def _detail(
    row: scaffold_views.ScaffoldRow,
    inspections: list[scaffold_views.InspectionRow] | None = None,
    *,
    modify_reason: str | None = None,
) -> scaffold_views.ScaffoldDetail:
    found = inspections or []
    return scaffold_views.ScaffoldDetail(
        row=row,
        inspection_count=len(found),
        modify_reason=modify_reason,
        dismantle_reason=None,
        for_key=None,
        version=1,
        inspections=found,
    )


def seed_scaffolds(client: FakeScaffoldSupport, project: str = "P123") -> list[str]:
    """Five scaffolds for ``project``, returned by key in key order.

    Designed and Erecting (no tag), Inspected (green, due 2026-01-01: past), In Use (green, due
    2099-12-31: future), and Modify (red, due 2026-10-09: past, after a failed inspection, so two
    inspections: a pass, then the fail). Requested is not a row: a request is not a scaffold yet.
    """
    items = [
        _detail(_row(1, DESIGNED_STATE, location="Unit 1")),
        _detail(_row(2, ERECTING_STATE, location="Unit 2")),
        _detail(
            _row(
                3,
                INSPECTED_STATE,
                tag="green",
                tagged_on="2026-01-01",
                last_inspected_on="2026-01-01",
                next_due_on="2026-01-01",
                location="Unit 3",
            ),
            [_inspection(1, "2026-01-01", "pass", "green", None)],
        ),
        _detail(
            _row(
                4,
                IN_USE,
                tag="green",
                tagged_on="2026-01-01",
                last_inspected_on="2026-01-01",
                next_due_on="2099-12-31",
                location="Unit 4",
            ),
            [_inspection(2, "2026-01-01", "pass", "green", None)],
        ),
        _detail(
            _row(
                5,
                MODIFY,
                tag="red",
                tagged_on="2026-01-01",
                last_inspected_on="2026-10-02",
                next_due_on="2026-10-09",
                location="Unit 5",
            ),
            [
                _inspection(3, "2026-09-01", "pass", "green", None),
                _inspection(4, "2026-10-02", "fail", "red", "Cracked toe board"),
            ],
            modify_reason="Cracked toe board",
        ),
    ]
    client.load_scaffolds(project, items)
    return [item.row.key for item in items]
