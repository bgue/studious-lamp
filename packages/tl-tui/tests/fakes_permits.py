"""In-memory permit, isolation and gas-test reads for `FakeClient` (P2-PTW-T10).

It holds the permits, isolations and gas tests a test gave it, per project (`load_permits`,
`load_isolations`, and `load_gas_tests` keyed by the permit's key), and answers each read with the
filters of the matching view (``tl_mod_permits.views``, ``iso_views``): shown state, type, area and
holder for permits; state and energy for isolations. Each list is sorted by key; ``total`` counts
the matches before the cut to ``limit`` (and ``offset``). The board is built from the permit list
the way ``permit_board`` builds it: live permits (Lapsed, Suspended, Active) grouped by area, areas
by name with no area last, Lapsed and Suspended before Active, then by key; the counts are the live
states. A gas test list is newest first. A missing or hidden key raises `RecordNotFoundError` with
the route's text. `permit_command` takes any model of ``tl_mod_permits.module.COMMANDS`` and records
it in `punch_commands` (the list the quality fakes use), after the same name check as the embedded
client. `seed_permits` makes the eight permits, three isolations and three gas tests the permit
screen tests share.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits import iso_views
from tl_mod_permits import views as permit_views
from tl_mod_permits.module import COMMANDS as PERMIT_COMMANDS
from tl_mod_permits.routes import MSG_NO_ISOLATION, MSG_NOT_FOUND

SEED_PROJECT = "P123"
_LIVE = permit_views.LIVE_STATES
_ISSUED = datetime(2026, 12, 1, 7, 0, tzinfo=UTC)
_VALID_UNTIL = datetime(2026, 12, 1, 18, 0, tzinfo=UTC)


class FakePermitSupport:
    """Mixin for `FakeClient`: call `_init_permits()` from its `__init__`."""

    punch_commands: list[Command]  # set by the punch mixin's `_init_punch()`

    def _init_permits(self) -> None:
        self._permits: dict[str, list[permit_views.PermitDetail]] = {}
        self._isolations: dict[str, list[iso_views.IsolationDetail]] = {}
        self._gas: dict[str, dict[str, list[iso_views.GasRow]]] = {}

    # --- seeding -----------------------------------------------------------------------------

    def load_permits(self, project: str, details: Sequence[permit_views.PermitDetail]) -> None:
        """Replace one project's permits. Each detail's ``row`` is what the lists show."""
        self._permits[project] = list(details)

    def load_isolations(self, project: str, details: Sequence[iso_views.IsolationDetail]) -> None:
        """Replace one project's isolations. Each detail's ``row`` is what the lists show."""
        self._isolations[project] = list(details)

    def load_gas_tests(
        self, project: str, permit_key: str, rows: Sequence[iso_views.GasRow]
    ) -> None:
        """Replace the gas tests of one permit of a project (by the permit's key)."""
        self._gas.setdefault(project, {})[permit_key] = list(rows)

    # --- reads -------------------------------------------------------------------------------

    def list_permits(
        self,
        project: str,
        *,
        state: str | None = None,
        permit_type: str | None = None,
        area: str | None = None,
        holder: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> permit_views.PermitPage:
        matches: list[permit_views.PermitRow] = []
        for item in self._sorted_permits(project):
            row = item.row
            if state is not None and row.state != state:
                continue
            if permit_type is not None and row.permit_type != permit_type:
                continue
            if area is not None and row.area != area:
                continue
            if holder is not None and row.holder != holder:
                continue
            matches.append(row)
        cap = max(1, min(int(limit), permit_views.MAX_LIMIT))
        start = max(0, int(offset))
        return permit_views.PermitPage(rows=matches[start : start + cap], total=len(matches))

    def get_permit(self, project: str, key: str) -> permit_views.PermitDetail:
        for item in self._permits.get(project, []):
            if item.row.key == key:
                return item
        raise RecordNotFoundError(MSG_NOT_FOUND)

    def get_permit_board(
        self, project: str, *, area: str | None = None
    ) -> permit_views.PermitBoard:
        counts: dict[str, int] = dict.fromkeys(_LIVE, 0)
        groups: dict[str | None, list[permit_views.PermitRow]] = {}
        live = [
            item.row
            for item in self._sorted_permits(project)
            if item.row.state in _LIVE and (area is None or item.row.area == area)
        ]
        # Lapsed and Suspended first (rank 0), then Active (rank 1), then by key (stable sort).
        live.sort(key=lambda row: 1 if row.state == "Active" else 0)
        for row in live:
            counts[row.state] += 1
            groups.setdefault(row.area, []).append(row)
        names = sorted(name for name in groups if name is not None)
        areas = [permit_views.BoardArea(area=name, rows=groups[name]) for name in names]
        if None in groups:
            areas.append(permit_views.BoardArea(area=None, rows=groups[None]))
        return permit_views.PermitBoard(areas=areas, counts=counts)

    def list_isolations(
        self,
        project: str,
        *,
        state: str | None = None,
        energy: str | None = None,
        limit: int = 100,
    ) -> iso_views.IsolationPage:
        matches: list[iso_views.IsolationRow] = []
        for item in sorted(self._isolations.get(project, []), key=lambda d: d.row.key):
            row = item.row
            if state is not None and row.state != state:
                continue
            if energy is not None and row.energy != energy:
                continue
            matches.append(row)
        cap = max(1, min(int(limit), iso_views.MAX_LIMIT))
        return iso_views.IsolationPage(rows=matches[:cap], total=len(matches))

    def get_isolation(self, project: str, key: str) -> iso_views.IsolationDetail:
        for item in self._isolations.get(project, []):
            if item.row.key == key:
                return item
        raise RecordNotFoundError(MSG_NO_ISOLATION)

    def list_gas_tests(self, project: str, permit_key: str) -> list[iso_views.GasRow]:
        if not any(item.row.key == permit_key for item in self._permits.get(project, [])):
            raise RecordNotFoundError(MSG_NOT_FOUND)
        rows = self._gas.get(project, {}).get(permit_key, [])
        return sorted(rows, key=lambda r: (r.taken_at, r.key), reverse=True)

    # --- the write door ----------------------------------------------------------------------

    def permit_command(self, name: str, cmd: Command) -> CommandResult:
        spec = next((c for c in PERMIT_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a permit command")
        self.punch_commands.append(cmd)
        return CommandResult(stream_id="PTW-1", key=None, version=1, events=[])

    # --- helpers -----------------------------------------------------------------------------

    def _sorted_permits(self, project: str) -> list[permit_views.PermitDetail]:
        return sorted(self._permits.get(project, []), key=lambda d: d.row.key)


_APPROVED_STATES = ("Approved", "Active", "Lapsed", "Suspended", "Handed back", "Closed")
_ISSUED_STATES = ("Active", "Lapsed", "Suspended", "Handed back", "Closed")


def _permit(
    n: int, state: str, *, permit_type: str, area: str | None, holder: str
) -> permit_views.PermitDetail:
    """One permit of the seed: the row and the facts its state carries."""
    issued = state in _ISSUED_STATES
    row = permit_views.PermitRow(
        id=f"PTW-{n}",
        key=f"P123-PTW-{n:04d}",
        subject=f"Permit {n}",
        permit_type=permit_type,
        state=state,
        area=area,
        holder=holder,
        issued_at=_ISSUED if issued else None,
        valid_until=_VALID_UNTIL if issued else None,
        revalidation_count=0,
        closed_by="user:pam" if state == "Closed" else None,
        for_key=None,
    )
    return permit_views.PermitDetail(
        row=row,
        description=f"Work {n}",
        location_text="Pump room",
        requested_by="user:rob",
        needed_from="2026-12-01",
        needed_until="2026-12-31",
        approved_by="user:sue" if state in _APPROVED_STATES else None,
        issued_by="user:pam" if issued else None,
        precautions=["fire_watch"] if issued else [],
        suspend_reason="Gas test failed" if state == "Suspended" else None,
        handback_note="Area returned" if state == "Handed back" else None,
        reject_reason="Scope unclear" if state == "Rejected" else None,
        cancel_reason=None,
        version=1,
    )


def _isolation(n: int, state: str, *, energy: str) -> iso_views.IsolationDetail:
    """One isolation of the seed: the row and the facts its state carries."""
    removed = state == "Removed"
    verified = state == "Verified"
    row = iso_views.IsolationRow(
        id=f"ISL-{n}",
        key=f"P123-ISL-{n:04d}",
        point_text=f"Pump P-10{n} breaker",
        energy=energy,
        method="Lock and tag",
        lock_number=f"L-{n}",
        tag_number=f"T-{n}",
        state=state,
        applied_by="user:uma",
        applied_at=_APPLIED,
        verified_by="user:sue" if verified else None,
        verified_at=_VERIFIED if verified else None,
        depends=1 if state == "Applied" else 0,
    )
    return iso_views.IsolationDetail(
        row=row,
        point_record_id=None,
        removed_by="user:uma" if removed else None,
        removed_at=_REMOVED if removed else None,
        version=1,
        permits=["P123-PTW-0003"] if state == "Applied" else [],
    )


_APPLIED = datetime(2026, 12, 1, 7, 30, tzinfo=UTC)
_VERIFIED = datetime(2026, 12, 1, 7, 45, tzinfo=UTC)
_REMOVED = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


def _gas(n: int, taken: datetime, result: str, co: str) -> iso_views.GasRow:
    return iso_views.GasRow(
        key=f"P123-GAS-{n:04d}",
        taken_at=taken,
        result=result,
        tester="user:uma",
        instrument_text="MX6",
        o2_pct=Decimal("20.9"),
        lel_pct=None,
        h2s_ppm=None,
        co_ppm=Decimal(co),
        note=None,
    )


def seed_permits(client: FakePermitSupport, project: str = SEED_PROJECT) -> list[str]:
    """Eight permits (one of each shown state; two with an area), three isolations and three gas
    tests on the Active permit (newest a pass) for ``project``; the permit keys in key order.

    Permits: Requested, Approved, Active (area A1), Lapsed (area A2), Suspended, Handed back,
    Closed, Rejected. Isolations: Applied (needed by the Active permit), Verified, Removed.
    """
    permits = [
        _permit(1, "Requested", permit_type="general", area=None, holder="Rob"),
        _permit(2, "Approved", permit_type="hot_work", area=None, holder="Rob"),
        _permit(3, "Active", permit_type="confined_space", area="A1", holder="Rob"),
        _permit(4, "Lapsed", permit_type="general", area="A2", holder="Ann"),
        _permit(5, "Suspended", permit_type="work_at_height", area=None, holder="Rob"),
        _permit(6, "Handed back", permit_type="general", area=None, holder="Ann"),
        _permit(7, "Closed", permit_type="hot_work", area=None, holder="Rob"),
        _permit(8, "Rejected", permit_type="general", area=None, holder="Rob"),
    ]
    client.load_permits(project, permits)
    client.load_isolations(
        project,
        [
            _isolation(1, "Applied", energy="electrical"),
            _isolation(2, "Verified", energy="mechanical"),
            _isolation(3, "Removed", energy="process"),
        ],
    )
    client.load_gas_tests(
        project,
        "P123-PTW-0003",
        [
            _gas(1, datetime(2026, 12, 1, 7, 10, tzinfo=UTC), "fail", "35"),
            _gas(2, datetime(2026, 12, 1, 7, 40, tzinfo=UTC), "pass", "4"),
            _gas(3, datetime(2026, 12, 1, 8, 20, tzinfo=UTC), "pass", "2"),
        ],
    )
    return [item.row.key for item in permits]
