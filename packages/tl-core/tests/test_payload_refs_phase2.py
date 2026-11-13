"""Payload ids of Phase 2 events are null (or dropped from a list) for a reader without access.

One case per ``PAYLOAD_REFS`` entry added for the awp, materials and requisitions events (P2-I6-S1,
ADR-0016): the hidden id is gone for the lowest viewer, present for one who may read the record, and
a visible id beside a hidden one is kept. Which ids are hidden is stubbed; the lookup itself is
covered by ``constraints/test_constraint_payload_twin.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import BaseModel
from tl_core import confidentiality as cf
from tl_core.intent import PAYLOAD_REFS, payload_ref_ids, redact_for_viewer

if TYPE_CHECKING:
    from sqlalchemy import Connection

HIDDEN = "01HIDDEN0000000000000000AA"
SHOWN = "01SHOWN00000000000000000BB"
CONTROLLER = cf.Viewer("user:controller", 1, "user:controller")


class Seen(BaseModel):
    stream_type: str
    event_type: str
    payload: dict[str, Any]


def _check(via: list[str]) -> dict[str, Any]:
    return {"name": "n", "state": "blocked", "resolve_via": via}


def _payload(field: str, value: str) -> dict[str, Any]:
    return {field: value, "other": "x"}


#: (stream type, event type, payload with the hidden id, payload with only the shown id, expected)
ADDED: list[tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any]]] = [
    (
        "awp.IWP",
        "IWP.ReadinessEvaluated",
        {"iwp_id": SHOWN, "checks": [_check([SHOWN, HIDDEN]), _check([HIDDEN])]},
        {"iwp_id": SHOWN, "checks": [_check([SHOWN])]},
        {"iwp_id": SHOWN, "checks": [_check([SHOWN]), _check([])]},
    ),
    (
        "awp.IWP",
        "IWP.DocumentPinned",
        {"document_id": HIDDEN, "revision_id": SHOWN},
        {"document_id": SHOWN, "revision_id": SHOWN},
        {"document_id": None, "revision_id": SHOWN},
    ),
    (
        "awp.IWP",
        "IWP.ScopeAdded",
        _payload("record_id", HIDDEN),
        _payload("record_id", SHOWN),
        _payload("record_id", None),  # type: ignore[arg-type]
    ),
    (
        "awp.IWP",
        "IWP.ScopeRemoved",
        _payload("record_id", HIDDEN),
        _payload("record_id", SHOWN),
        _payload("record_id", None),  # type: ignore[arg-type]
    ),
    (
        "materials.StockLot",
        "StockLot.Moved",
        {"iwp_id": SHOWN, "requisition_id": HIDDEN},
        {"iwp_id": SHOWN, "requisition_id": SHOWN},
        {"iwp_id": SHOWN, "requisition_id": None},
    ),
    (
        "materials.StockLot",
        "StockLot.Moved",
        {"iwp_id": HIDDEN, "requisition_id": None},
        {"iwp_id": SHOWN, "requisition_id": None},
        {"iwp_id": None, "requisition_id": None},
    ),
    (
        "materials.MTO",
        "MTO.Defined",
        {"derived_document_id": HIDDEN, "revision_id": HIDDEN},
        {"derived_document_id": SHOWN, "revision_id": SHOWN},
        {"derived_document_id": None, "revision_id": None},
    ),
    (
        "materials.MTOLine",
        "MTOLine.Assigned",
        _payload("work_package_id", HIDDEN),
        _payload("work_package_id", SHOWN),
        _payload("work_package_id", None),  # type: ignore[arg-type]
    ),
    *[
        (
            stream,
            "Requisition.Raised",
            _payload("for_record_id", HIDDEN),
            _payload("for_record_id", SHOWN),
            _payload("for_record_id", None),  # type: ignore[arg-type]
        )
        for stream in (
            "requisitions.LaborRequisition",
            "requisitions.MaterialRequisition",
            "requisitions.GeneralRequisition",
            "requisitions.ScaffoldRequest",
        )
    ],
    *[
        (
            stream,
            "Requisition.Approved",
            _payload("work_order_id", HIDDEN),
            _payload("work_order_id", SHOWN),
            _payload("work_order_id", None),  # type: ignore[arg-type]
        )
        for stream in (
            "requisitions.LaborRequisition",
            "requisitions.MaterialRequisition",
            "requisitions.GeneralRequisition",
            "requisitions.ScaffoldRequest",
        )
    ],
    *[
        (
            "requisitions.WorkOrder",
            event,
            _payload("requisition_id", HIDDEN),
            _payload("requisition_id", SHOWN),
            _payload("requisition_id", None),  # type: ignore[arg-type]
        )
        for event in (
            "WorkOrder.Opened",
            "WorkOrder.Scheduled",
            "WorkOrder.Assigned",
            "WorkOrder.Started",
            "WorkOrder.Completed",
            "WorkOrder.Closed",
        )
    ],
]


@pytest.fixture(autouse=True)
def hidden_from_the_lowest(monkeypatch: pytest.MonkeyPatch) -> None:
    def hidden_among(_conn: object, ids: list[str], viewer: cf.Viewer) -> set[str]:
        return {HIDDEN} & set(ids) if viewer == cf.LOWEST else set()

    monkeypatch.setattr(cf, "hidden_among", hidden_among)


def _read(stream: str, event: str, payload: dict[str, Any], viewer: cf.Viewer) -> dict[str, Any]:
    seen = [Seen(stream_type=stream, event_type=event, payload=payload)]
    out = redact_for_viewer(cast("Connection", None), seen, viewer)
    return out[0].payload


@pytest.mark.parametrize(("stream", "event", "named", "visible", "expected"), ADDED)
def test_a_hidden_id_is_null_for_a_reader_without_access_and_present_for_one_with(
    stream: str,
    event: str,
    named: dict[str, Any],
    visible: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    assert HIDDEN in str(payload_ref_ids(stream, event, named))
    assert _read(stream, event, named, cf.LOWEST) == expected
    assert HIDDEN not in str(_read(stream, event, named, cf.LOWEST))
    assert _read(stream, event, named, CONTROLLER) == named
    assert _read(stream, event, visible, cf.LOWEST) == visible


def test_every_added_entry_has_a_case() -> None:
    cases = {(s, e) for s, e, *_ in ADDED}
    entries = {
        (s, e) for s, events in PAYLOAD_REFS.items() if not s.startswith("core.") for e in events
    }
    assert entries == cases
