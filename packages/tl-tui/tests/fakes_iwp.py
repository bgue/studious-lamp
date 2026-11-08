"""In-memory IWP, constraint and readiness reads for `FakeClient` (P2-I2 T04c2).

The fake answers from the lists a test gives it (`load_iwps`, `load_constraints`, `load_readiness`).
It filters and sorts them the way the views and routes do (IWPs by number, scope by type then
number, constraints by key, the review groups through `tl_core.constraints.review`), clamps limits
the way the views clamp them, and raises `RecordNotFoundError` with the views' one text for an
unknown or unloaded IWP number, a constraint key that is not loaded, and a readiness that was never
loaded. The fake has no viewer: what a test loads is what a reader may see.

`seed_iwp` gives it the shape the acceptance seed uses: 4 IWPs (Draft, Ready, Issued, and one
oversize Draft), 6 scope rows on the first IWP, 5 constraints on two subjects (owners, categories,
ages 2, 9 and 20 days, one blocking), and one readiness of 9 checks (2 blocked, 5 `n_a`, and one
blocked check with a `resolve_via`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from decimal import Decimal

from tl_api.routes.awp import CheckBody, ReadinessBody
from tl_api.routes.constraints import (
    ConstraintGroupRow,
    ConstraintGroups,
    ConstraintList,
    ConstraintRow,
)
from tl_core.constraints import review as constraint_review
from tl_core.constraints.queries import MAX_LIMIT
from tl_core.readiness.types import RecordRef
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import iwp_views
from tl_mod_awp.names import IWP, SCOPE_ITEM, TAG_TYPE

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
ITEM_KEYS = tuple(f"{PROJECT}-SI-{n:04d}" for n in range(1, 6))


def _clamp(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


class FakeIwpSupport:
    """Mixin for `FakeClient`: call `_init_iwp()` from its `__init__`."""

    def _init_iwp(self) -> None:
        self._iwps: dict[str, list[iwp_views.IwpDetail]] = {}
        self._iwp_scope: dict[str, dict[str, list[iwp_views.ScopeRow]]] = {}
        self._constraints: dict[str, list[ConstraintRow]] = {}
        self._readiness: dict[tuple[str, str], ReadinessBody] = {}

    # --- seeding -----------------------------------------------------------------------------

    def load_iwps(
        self,
        project: str,
        iwps: Iterable[iwp_views.IwpDetail] = (),
        *,
        scope: Mapping[str, Iterable[iwp_views.ScopeRow]] | None = None,
    ) -> None:
        """Replace the IWPs of ``project``; ``scope`` maps an IWP number to its scope rows."""
        self._iwps[project] = list(iwps)
        self._iwp_scope[project] = {number: list(rows) for number, rows in (scope or {}).items()}

    def load_constraints(self, project: str, rows: Iterable[ConstraintRow] = ()) -> None:
        """Replace the constraints of ``project`` (every constraint a test wants visible)."""
        self._constraints[project] = list(rows)

    def load_readiness(self, project: str, number: str, view: ReadinessBody) -> None:
        """The last readiness evaluation of IWP ``number`` of ``project``."""
        self._readiness[(project, number)] = view.model_copy(deep=True)

    # --- the reads ---------------------------------------------------------------------------

    def list_iwps(
        self,
        project: str,
        *,
        state: str | None = None,
        discipline: str | None = None,
        foreman: str | None = None,
        limit: int = 200,
    ) -> list[iwp_views.IwpRow]:
        found = sorted(self._iwps.get(project, []), key=lambda d: d.number)
        rows = [
            iwp_views.IwpRow(**detail.model_dump(include=set(iwp_views.IwpRow.model_fields)))
            for detail in found
        ]
        visible = [
            row
            for row in rows
            if (state is None or row.state == state)
            and (discipline is None or row.discipline == discipline)
            and (foreman is None or row.foreman == foreman)
        ]
        return visible[: _clamp(limit)]

    def get_iwp(self, project: str, number: str) -> iwp_views.IwpDetail:
        for detail in self._iwps.get(project, []):
            if detail.number == number:
                return detail.model_copy(deep=True)
        raise RecordNotFoundError(f"no IWP {number!r}")

    def list_iwp_scope(
        self, project: str, number: str, *, limit: int = 200
    ) -> list[iwp_views.ScopeRow]:
        if not any(detail.number == number for detail in self._iwps.get(project, [])):
            raise RecordNotFoundError(f"no IWP {number!r}")
        rows = self._iwp_scope.get(project, {}).get(number, [])
        ordered = sorted(rows, key=lambda row: (row.type, row.number or ""))
        return [row.model_copy(deep=True) for row in ordered[: _clamp(limit)]]

    def get_iwp_readiness(self, project: str, number: str) -> ReadinessBody:
        view = self._readiness.get((project, number))
        if view is None:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return view.model_copy(deep=True)

    def list_constraints(
        self,
        project: str,
        *,
        subject: str | None = None,
        state: str | None = None,
        category: str | None = None,
        phase: str | None = None,
        blocking: bool | None = None,
        owner: str | None = None,
        limit: int = 200,
    ) -> ConstraintList:
        found = sorted(self._constraints.get(project, []), key=lambda row: row.key)
        matching = [
            row
            for row in found
            if (subject is None or row.subject_key == subject)
            and (state is None or row.state == state)
            and (category is None or row.category == category)
            and (phase is None or row.phase == phase)
            and (blocking is None or (row.severity == "blocking") == blocking)
            and (owner is None or row.owner == owner)
        ]
        rows = [deepcopy(row) for row in matching[: _clamp(limit)]]
        return ConstraintList(rows=rows, total=len(matching))

    def constraint_groups(self, project: str, by: str) -> ConstraintGroups:
        if by not in constraint_review.BY_WORDS:
            raise ValueError(f"by must be one of {', '.join(constraint_review.BY_WORDS)}")
        found = sorted(self._constraints.get(project, []), key=lambda row: row.key)
        views = found[:MAX_LIMIT]
        by_key = {row.key: row for row in views}
        groups = [
            ConstraintGroupRow(
                label=group.label,
                count=group.count,
                blocking=group.blocking,
                aging=group.aging,
                keys=list(group.keys),
                members=[deepcopy(by_key[k]) for k in group.keys if k in by_key],
            )
            for group in constraint_review.review_groups(views, by)
        ]
        return ConstraintGroups(groups=groups, truncated=len(found) > MAX_LIMIT)

    def get_constraint(self, project: str, key: str) -> ConstraintRow:
        for row in self._constraints.get(project, []):
            if row.key == key:
                return deepcopy(row)
        raise RecordNotFoundError(f"no constraint {key!r}")


# --- the acceptance seed ---------------------------------------------------------------------


def _iwp(
    n: int,
    discipline: str,
    title: str,
    state: str,
    *,
    foreman: str | None,
    hours: str | None,
    scope_by_type: dict[str, int],
    pins: int,
    open_constraints: int,
    cwp: str | None = None,
) -> iwp_views.IwpDetail:
    number = f"{PROJECT}-IWP-{discipline}-{n:04d}"
    return iwp_views.IwpDetail(
        id=f"IWP-{n}",
        number=number,
        title=title,
        state=state,
        discipline=discipline,
        planned_start="2026-12-01",
        planned_finish="2026-12-15",
        foreman=foreman,
        estimated_hours=None if hours is None else Decimal(hours),
        cwp_number=cwp,
        scope_count=sum(scope_by_type.values()),
        crew_text=None,
        signoffs=[],
        pin_count=pins,
        open_constraints=open_constraints,
        scope_by_type=scope_by_type,
    )


def _scope_rows() -> list[iwp_views.ScopeRow]:
    items = [
        iwp_views.ScopeRow(
            id=f"SI-{n}",
            number=key,
            type=SCOPE_ITEM,
            commodity="pipe",
            description=f"Spool {n}",
            qty=Decimal("1"),
            uom="ea",
            est_hours=Decimal("1.0"),
        )
        for n, key in enumerate(ITEM_KEYS, start=1)
    ]
    tag = iwp_views.ScopeRow(
        id="TAG-1", number=None, type=TAG_TYPE, commodity=None, description="Support tag",
        qty=None, uom=None, est_hours=None,
    )  # fmt: skip
    return [*items, tag]


def _con(
    n: int,
    subject: iwp_views.IwpDetail,
    *,
    state: str,
    severity: str,
    category: str,
    owner: str | None,
    age_days: int,
) -> ConstraintRow:
    return ConstraintRow(
        id=f"CON-{n}",
        key=f"{PROJECT}-CON-{n:04d}",
        state=state,
        scope=SCOPE,
        subject_id=subject.id,
        phase="issue",
        severity=severity,
        category=category,
        source="manual",
        owner=owner,
        description=f"Constraint {n}",
        check_name=None,
        clear_reason=None,
        target_kind=None,
        target_id=None,
        target_ref_type=None,
        target_ref_text=None,
        effective_at=None,
        due_at=None,
        cleared_at=None,
        cleared_by=None,
        raised_on="2026-10-26",
        age_days=age_days,
        aging=state in ("Open", "Assigned") and age_days >= 15,
        phase_ungated=False,
        subject_key=subject.number,
        subject_type=IWP,
    )


def _readiness(iwp: iwp_views.IwpDetail) -> ReadinessBody:
    def check(name: str, state: str, detail: str, ok: int | None, total: int | None,
              via: list[RecordRef] | None = None) -> CheckBody:  # fmt: skip
        return CheckBody(
            name=name, version="1", state=state, detail=detail,
            resolve_via=via or [], count_ok=ok, count_total=total,
        )  # fmt: skip

    doc = RecordRef(record_id="DOC-2", record_type="documents.Document", key=f"{PROJECT}-DWG-0002")
    checks = [
        check("constraints_cleared", "blocked", "2 open constraints", 0, 2),
        check("crew_assigned", "ok", "crew named", None, None),
        check("documents_current", "blocked", "2 of 5 drawings current", 3, 5, [doc]),
        check("drawings_issued", "n_a", "no drawing gate", None, None),
        check("materials_reserved", "n_a", "no material gate", None, None),
        check("permits_in_place", "n_a", "no permit gate", None, None),
        check("predecessors_complete", "ok", "predecessors complete", 1, 1),
        check("rfis_closed", "n_a", "no RFI gate", None, None),
        check("scaffold_tagged", "n_a", "no scaffold gate", None, None),
    ]
    return ReadinessBody(
        iwp_id=iwp.id,
        evaluated_at="2026-11-06T09:00:00+00:00",
        today="2026-11-06",
        ready=False,
        checks=checks,
    )


def seed_iwp(client: FakeIwpSupport, project: str = PROJECT) -> None:
    """The acceptance seed's shape on ``client``: 4 IWPs, 6 scope rows, 5 constraints on two
    subjects, and one readiness of 9 checks for the first IWP."""
    first = _iwp(
        1, "PIP", "Pipe spools, level 1", "Draft", foreman="user:uma", hours="120",
        scope_by_type={SCOPE_ITEM: 5, TAG_TYPE: 1}, pins=2, open_constraints=3,
        cwp="P123-CWP-0001",
    )  # fmt: skip
    second = _iwp(
        2, "PIP", "Pipe supports", "Ready", foreman="user:sue", hours="64",
        scope_by_type={}, pins=0, open_constraints=2,
    )  # fmt: skip
    third = _iwp(
        1, "CIV", "Civil foundations", "Issued", foreman="user:sue", hours="80",
        scope_by_type={}, pins=0, open_constraints=0,
    )  # fmt: skip
    oversize = _iwp(
        2, "CIV", "Plant, all areas", "Draft", foreman=None, hours="480",
        scope_by_type={}, pins=0, open_constraints=0,
    )  # fmt: skip
    iwps = [first, second, third, oversize]
    constraints = [
        _con(
            1,
            first,
            state="Open",
            severity="blocking",
            category="materials",
            owner="user:uma",
            age_days=2,
        ),  # fmt: skip
        _con(
            2,
            first,
            state="Assigned",
            severity="advisory",
            category="permit",
            owner="user:sue",
            age_days=9,
        ),  # fmt: skip
        _con(
            3,
            first,
            state="Open",
            severity="advisory",
            category="engineering",
            owner=None,
            age_days=20,
        ),  # fmt: skip
        _con(
            4,
            second,
            state="Open",
            severity="advisory",
            category="rfi",
            owner="user:sue",
            age_days=2,
        ),  # fmt: skip
        _con(
            5,
            second,
            state="Open",
            severity="advisory",
            category="labour",
            owner="user:uma",
            age_days=9,
        ),  # fmt: skip
    ]
    client.load_iwps(project, iwps, scope={first.number: _scope_rows()})
    client.load_constraints(project, constraints)
    client.load_readiness(project, first.number, _readiness(first))
