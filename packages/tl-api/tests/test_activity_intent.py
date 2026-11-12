"""``GET /records/{id}/activity`` redacts an intent that names a hidden record (P2-INT-T04).

The controller makes a record whose intent points at the restricted item; readers who may not read
it get the text "not available" in the activity rows, never the id. The controller sees the id.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from test_intent_walk import (  # pyright: ignore[reportMissingImports]
    CANNOT_READ_RESTRICTED,
    call,
    make,
)
from tl_api_walk import Seed, seed  # pyright: ignore[reportMissingImports]
from tl_core.intent import NOT_AVAILABLE


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    return seed(harness, tmp_path)


def intent(where: str, ref: str) -> dict[str, Any]:
    if where == "toward":
        return {"toward": {"target": ref, "condition": "x"}}
    return {"next": [{"command": "UpdateRecord", "target": ref}]}


@pytest.mark.parametrize("reader", CANNOT_READ_RESTRICTED)
@pytest.mark.parametrize("where", ["toward", "next"])
@pytest.mark.parametrize("revisions_only", [False, True])
def test_the_activity_route_redacts_an_intent_naming_a_hidden_record(
    harness: Harness, seeded: Seed, reader: str, where: str, revisions_only: bool
) -> None:
    hidden = seeded.ids["restricted"]
    made = make(harness, seeded, "ctl", "R-ACT", intent(where, hidden))
    assert made.status_code == 200, made.text
    record_id = made.json()["stream_id"]
    params = {"revisions_only": "true"} if revisions_only else {}
    seen = call(harness, seeded, reader, "get", f"/records/{record_id}/activity", params=params)
    assert seen.status_code == 200, seen.text
    assert hidden not in seen.text and NOT_AVAILABLE in seen.text
    own = call(harness, seeded, "ctl", "get", f"/records/{record_id}/activity", params=params)
    assert hidden in own.text  # the controller may read the item
