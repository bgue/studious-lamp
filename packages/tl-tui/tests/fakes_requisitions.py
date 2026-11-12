"""In-memory requisition and work order reads for `FakeClient` (P2-I4A T04c2).

The fake answers from the lists a test gives it (`load_requisitions`, `load_work_orders`). Each
list holds the route's detail models, so a requisition's work order and a work order's requisition
key are what the test loaded. It filters and sorts them the way the views and routes do (by key,
then id; limits clamped to the views' 1..500), and reports `total` as the number of rows it returns.
It raises `RecordNotFoundError` with the views' text for an unknown key. The fake has no viewer:
what a test loads is what a reader may see.

The fake has no record ids for the IWP or CWP a requisition serves, so `for_key` is matched against
the requisition's `for_record_id`, which the seed fills with the IWP or CWP key.

`seed_requisitions` gives the acceptance shape: 5 requisitions (two labour, one material, one
general, one scaffold; the first labour one Approved with a Scheduled work order, the scaffold one
Rejected) and 2 work orders.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from tl_api.routes.requisitions import (
    RequisitionDetailBody,
    RequisitionList,
    WorkOrderDetailBody,
    WorkOrderList,
)
from tl_core.services.errors import RecordNotFoundError
from tl_mod_requisitions.api import RequisitionRow, WorkOrderRow
from tl_mod_requisitions.names import (
    GENERAL,
    LABOR,
    MATERIAL,
    SCAFFOLD,
    ST_APPROVED,
    ST_OPEN,
    ST_REJECTED,
    ST_REQUESTED,
    ST_SCHEDULED,
)
from tl_mod_requisitions.views import MAX_LIMIT, MIN_LIMIT

PROJECT = "P123"


def _clamp(limit: int) -> int:
    return min(max(int(limit), MIN_LIMIT), MAX_LIMIT)


class FakeRequisitionSupport:
    """Mixin for `FakeClient`: call `_init_requisitions()` from its `__init__`."""

    def _init_requisitions(self) -> None:
        self._requisitions: dict[str, list[RequisitionDetailBody]] = {}
        self._work_orders: dict[str, list[WorkOrderDetailBody]] = {}

    # --- seeding -----------------------------------------------------------------------------

    def load_requisitions(self, project: str, items: Iterable[RequisitionDetailBody] = ()) -> None:
        """Replace the requisitions of ``project`` (each detail carries its row, fields and work
        order)."""
        self._requisitions[project] = list(items)

    def load_work_orders(self, project: str, items: Iterable[WorkOrderDetailBody] = ()) -> None:
        """Replace the work orders of ``project``."""
        self._work_orders[project] = list(items)

    # --- the reads ---------------------------------------------------------------------------

    def list_requisitions(
        self,
        project: str,
        *,
        kind: str | None = None,
        state: str | None = None,
        requester: str | None = None,
        for_key: str | None = None,
        limit: int = 200,
    ) -> RequisitionList:
        found = sorted(
            (detail.row for detail in self._requisitions.get(project, [])),
            key=lambda row: (row.key, row.id),
        )
        matching = [
            row
            for row in found
            if (kind is None or row.kind == kind)
            and (state is None or row.state == state)
            and (requester is None or row.requester == requester)
            and (for_key is None or row.for_record_id == for_key)
        ]
        rows = [deepcopy(row) for row in matching[: _clamp(limit)]]
        return RequisitionList(rows=rows, total=len(rows))

    def get_requisition(self, project: str, key: str) -> RequisitionDetailBody:
        for detail in self._requisitions.get(project, []):
            if detail.row.key == key:
                return deepcopy(detail)
        raise RecordNotFoundError(f"no requisition {key!r}")

    def list_work_orders(
        self,
        project: str,
        *,
        state: str | None = None,
        assigned_to: str | None = None,
        limit: int = 200,
    ) -> WorkOrderList:
        found = sorted(
            (detail.row for detail in self._work_orders.get(project, [])),
            key=lambda row: (row.key, row.id),
        )
        matching = [
            row
            for row in found
            if (state is None or row.state == state)
            and (assigned_to is None or row.assigned_to == assigned_to)
        ]
        rows = [deepcopy(row) for row in matching[: _clamp(limit)]]
        return WorkOrderList(rows=rows, total=len(rows))

    def get_work_order(self, project: str, key: str) -> WorkOrderDetailBody:
        for detail in self._work_orders.get(project, []):
            if detail.row.key == key:
                return deepcopy(detail)
        raise RecordNotFoundError(f"no work order {key!r}")


# --- the acceptance seed ---------------------------------------------------------------------


def _key(n: int) -> str:
    return f"{PROJECT}-REQ-{n:04d}"


def _requisition(
    n: int,
    record_type: str,
    kind: str,
    state: str,
    *,
    requester: str,
    for_record_id: str,
    work_order: WorkOrderRow | None,
    fields: dict[str, str | None],
) -> RequisitionDetailBody:
    row = RequisitionRow(
        id=f"REQ-{n}",
        key=_key(n),
        kind=kind,
        record_type=record_type,
        subject=f"Requisition {n}",
        state=state,
        requester=requester,
        priority="normal",
        need_by="2026-11-20",
        for_record_id=for_record_id,
        approved_by="user:sue" if state == ST_APPROVED else None,
        work_order_id=None if work_order is None else work_order.id,
        version=1,
    )
    return RequisitionDetailBody(row=row, fields=fields, work_order=work_order)


def _work_order(n: int, requisition: int, state: str, *, assigned_to: str | None) -> WorkOrderRow:
    scheduled = state == ST_SCHEDULED
    return WorkOrderRow(
        id=f"WO-{n}",
        key=f"{PROJECT}-WO-{n:04d}",
        requisition_id=f"REQ-{requisition}",
        work_kind="labor",
        state=state,
        assigned_to=assigned_to,
        planned_start="2026-11-02" if scheduled else None,
        planned_finish="2026-11-13" if scheduled else None,
        actual_start=None,
        actual_finish=None,
        hours_planned="48" if scheduled else None,
        hours_actual=None,
        version=1,
    )


def seed_requisitions(client: FakeRequisitionSupport, project: str = PROJECT) -> None:
    """The acceptance shape on ``client``: 5 requisitions and 2 work orders.

    The second work order is Open and names the second labour requisition, which is still
    Requested; the seed does not say which requisition holds it, so the fake keeps it as loaded.
    """
    scheduled = _work_order(1, 1, ST_SCHEDULED, assigned_to=None)
    open_order = _work_order(2, 2, ST_OPEN, assigned_to="user:uma")
    client.load_requisitions(
        project,
        [
            _requisition(
                1,
                LABOR,
                "labor",
                ST_APPROVED,
                requester="user:uma",
                for_record_id=f"{PROJECT}-IWP-PIP-0001",
                work_order=scheduled,
                fields={"craft": "Pipefitter", "headcount": "6", "start_date": "2026-11-02"},
            ),
            _requisition(
                2,
                LABOR,
                "labor",
                ST_REQUESTED,
                requester="user:rob",
                for_record_id=f"{PROJECT}-IWP-PIP-0002",
                work_order=None,
                fields={"craft": "Welder", "headcount": "2", "start_date": "2026-11-16"},
            ),
            _requisition(
                3,
                MATERIAL,
                "material",
                ST_REQUESTED,
                requester="user:uma",
                for_record_id=f"{PROJECT}-IWP-PIP-0001",
                work_order=None,
                fields={"item": "Pipe 6in", "quantity": "40", "uom": "m"},
            ),
            _requisition(
                4,
                GENERAL,
                "general",
                ST_REQUESTED,
                requester="user:sue",
                for_record_id=f"{PROJECT}-CWP-0001",
                work_order=None,
                fields={"general_type": "Hire", "description": "Telehandler"},
            ),
            _requisition(
                5,
                SCAFFOLD,
                "scaffold",
                ST_REJECTED,
                requester="user:uma",
                for_record_id=f"{PROJECT}-IWP-CIV-0001",
                work_order=None,
                fields={"area": "Level 2", "bays": "4"},
            ),
        ],
    )
    client.load_work_orders(
        project,
        [
            WorkOrderDetailBody(row=scheduled, requisition_key=_key(1)),
            WorkOrderDetailBody(row=open_order, requisition_key=_key(2)),
        ],
    )
