"""The requisition and work order read routes (P2-I4A-T04c1): four GET routes, walked as five kinds
of reader on a ledger built by commands (``req_world.World``, loaded by path; no projection writes).

Readers: ``anon`` (no token: 401), ``vic`` (a user who holds no ``requisitions.view`` word: 403
before any lookup), ``triage`` (an agent: 403, the word is closed to agents), ``uma`` (a user of the
lowest clearance: sees the visible rows only) and ``ada`` (an admin, cleared: sees the restricted
requisition too). A hidden requisition answers the same 404 as a missing one.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_api.tokens import add_token
from tl_core import confidentiality as cf
from tl_core import modules as tl_modules
from tl_core.auth import module_roles, sessions
from tl_core.modules import ConfidentialSource
from tl_mod_requisitions import views

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
PROJECT = "/projects/P123"
IWP = "awp.IWP"
MISSING = "P123-REQ-9999"
CLASS_TABLE = "p2i4a_t04c1_class"


def load_world() -> ModuleType:
    """The requisitions ``req_world`` helper, loaded by path as ``test_api_awp.load_world`` does."""
    name = "req_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "requisitions" / "tests" / "req_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Rig:
    h: Harness
    world: Any
    raised: str  # requisition key, raised by uma for IWP-1 (no work order)
    other: str  # requisition key, raised by rob for IWP-2
    approved: str  # requisition key, raised by uma for IWP-1 and approved (has a work order)
    work_order: str  # key of the work order of the approved one
    hidden: str  # requisition key, raised for a restricted record (lowest clearance: hidden)

    def client(self, username: str | None) -> Any:
        client = self.h.client_for(None)
        if username is not None:
            _, token = sessions.sign_in(self.h.backend, username=username, password=PASSWORD)
            client.headers.update({"Authorization": f"Bearer {token}"})
        return client


def _key(world: Any, record: str) -> str:
    return str(world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=record)[0]["key"])


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    h = Harness.build(tmp_path)
    try:
        target = h.target or h.db
        world = load_world().World(target)
        world.people()
        world.editions()
        world.person("vic", ("user",))
        iwp_1 = world.record(IWP, "IWP-1")
        iwp_2 = world.record(IWP, "IWP-2")
        restricted = world.record(IWP, "IWP-S")
        raised = world.raise_labor("uma", for_record_id=iwp_1)
        other = world.raise_labor("rob", for_record_id=iwp_2)
        approved, work_order = world.approved("uma")
        hidden = world.raise_labor("ada", for_record_id=restricted)
        # the class source goes in after the seed: the restricted IWP is read by a cleared reader
        # only, and its requisition inherits that class (test class table, as the constraint tests)
        with open_uow(target) as uow:
            conn = uow.conn()
            conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT)"))
            for record in (iwp_1, iwp_2, restricted):
                cls = "restricted" if record == restricted else "internal"
                conn.execute(
                    text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                    {"i": record, "c": cls},
                )
        source = ConfidentialSource(
            record_types=frozenset({IWP}), table=CLASS_TABLE, id_column="id", class_column="cls"
        )
        original = tl_modules.confidential_sources
        monkeypatch.setattr(cf, "confidential_sources", lambda: [*original(), source])
        yield Rig(
            h=h,
            world=world,
            raised=_key(world, raised),
            other=_key(world, other),
            approved=_key(world, approved),
            work_order=_key(world, work_order),
            hidden=_key(world, hidden),
        )
    finally:
        h.close()


def _get(rig: Rig, who: str | None, path: str, **params: Any) -> Any:
    return rig.client(who).get(path, params=params)


# --- the four routes: shape, filters, totals --------------------------------------------------


def test_the_list_holds_the_visible_requisitions_and_total_is_the_row_count(rig: Rig) -> None:
    body = _get(rig, "uma", f"{PROJECT}/requisitions").json()
    keys = {row["key"] for row in body["rows"]}
    assert keys == {rig.raised, rig.other, rig.approved}  # the hidden one is left out
    assert body["total"] == len(body["rows"]) == 3
    assert all(set(row) >= {"id", "key", "kind", "state", "requester"} for row in body["rows"])
    assert all("hash" not in key for row in body["rows"] for key in row)


def test_the_list_filters_reach_the_view(rig: Rig) -> None:
    rows = _get(rig, "uma", f"{PROJECT}/requisitions", kind="labor").json()["rows"]
    assert len(rows) == 3
    assert _get(rig, "uma", f"{PROJECT}/requisitions", kind="general").json() == {
        "rows": [],
        "total": 0,
    }
    by_requester = _get(rig, "uma", f"{PROJECT}/requisitions", requester="user:rob").json()
    assert [row["key"] for row in by_requester["rows"]] == [rig.other]
    assert by_requester["total"] == 1
    assert _get(rig, "uma", f"{PROJECT}/requisitions", limit=1).json()["total"] == 1


def test_the_for_filter_names_an_iwp_key_and_an_unknown_key_is_empty(rig: Rig) -> None:
    for_iwp_2 = _get(rig, "uma", f"{PROJECT}/requisitions", **{"for": "IWP-2"}).json()
    assert [row["key"] for row in for_iwp_2["rows"]] == [rig.other]
    unknown = _get(rig, "uma", f"{PROJECT}/requisitions", **{"for": "IWP-404"})
    assert unknown.status_code == 200 and unknown.json() == {"rows": [], "total": 0}
    hidden_for = _get(rig, "uma", f"{PROJECT}/requisitions", **{"for": "IWP-S"})
    assert hidden_for.json() == {"rows": [], "total": 0}  # a hidden key: as an unknown one
    cleared = _get(rig, "ada", f"{PROJECT}/requisitions", **{"for": "IWP-S"}).json()
    assert [row["key"] for row in cleared["rows"]] == [rig.hidden]


def test_an_unknown_kind_is_422(rig: Rig) -> None:
    assert _get(rig, "uma", f"{PROJECT}/requisitions", kind="x").status_code == 422


def test_the_detail_carries_the_kind_fields_and_the_work_order_or_null(rig: Rig) -> None:
    raised = _get(rig, "uma", f"{PROJECT}/requisitions/{rig.raised}").json()
    assert raised["row"]["key"] == rig.raised
    assert raised["fields"]["craft"] == "Pipefitter"
    assert raised["work_order"] is None
    approved = _get(rig, "uma", f"{PROJECT}/requisitions/{rig.approved}").json()
    assert approved["work_order"] is not None
    assert approved["work_order"]["key"] == rig.work_order
    assert approved["work_order"]["requisition_id"] == approved["row"]["id"]


def test_the_work_order_list_and_detail(rig: Rig) -> None:
    listed = _get(rig, "uma", f"{PROJECT}/work-orders").json()
    assert [row["key"] for row in listed["rows"]] == [rig.work_order]
    assert listed["total"] == 1
    detail = _get(rig, "uma", f"{PROJECT}/work-orders/{rig.work_order}").json()
    assert detail["requisition_key"] == rig.approved
    assert detail["row"]["key"] == rig.work_order


# --- five kinds of reader on every route ------------------------------------------------------

ROUTES = [
    ("list", f"{PROJECT}/requisitions", {}),
    ("detail", f"{PROJECT}/requisitions/{{visible}}", {}),
    ("work-orders", f"{PROJECT}/work-orders", {}),
    ("work-order", f"{PROJECT}/work-orders/{{work_order}}", {}),
]


def _path(rig: Rig, name: str) -> str:
    for route, path, _ in ROUTES:
        if route == name:
            return path.format(visible=rig.approved, work_order=rig.work_order)
    raise KeyError(name)


@pytest.mark.parametrize("name", [r[0] for r in ROUTES])
def test_no_token_is_401(rig: Rig, name: str) -> None:
    assert _get(rig, None, _path(rig, name)).status_code == 401


@pytest.mark.parametrize("name", [r[0] for r in ROUTES])
def test_a_person_without_the_word_is_403_before_any_lookup(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    real = module_roles.holds_word

    def without_word(conn: Any, holder: Any, **kwargs: Any) -> bool:
        return False if holder.actor == "user:vic" else real(conn, holder, **kwargs)

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a requisition read ran before the word check")

    monkeypatch.setattr(module_roles, "holds_word", without_word)
    for function in (
        "requisition_list",
        "requisition_detail",
        "work_order_list",
        "work_order_detail",
    ):
        monkeypatch.setattr(views, function, boom)
    assert _get(rig, "vic", _path(rig, name)).status_code == 403


@pytest.mark.parametrize("name", [r[0] for r in ROUTES])
def test_an_agent_is_403_even_with_the_word(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    token = add_token(rig.h.settings.tokens_path, "agent:triage")
    client = rig.h.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    monkeypatch.setattr(module_roles, "holds_word", lambda *a, **k: True)
    assert client.get(_path(rig, name)).status_code == 403


@pytest.mark.parametrize("name", [r[0] for r in ROUTES])
def test_the_lowest_clearance_reader_sees_the_visible_rows(rig: Rig, name: str) -> None:
    response = _get(rig, "uma", _path(rig, name))
    assert response.status_code == 200
    assert rig.hidden not in response.text


def test_the_cleared_reader_sees_the_same_rows_and_the_restricted_one(rig: Rig) -> None:
    low = _get(rig, "uma", f"{PROJECT}/requisitions").json()
    high = _get(rig, "ada", f"{PROJECT}/requisitions").json()
    low_keys = {row["key"] for row in low["rows"]}
    high_keys = {row["key"] for row in high["rows"]}
    assert low_keys <= high_keys
    assert high_keys - low_keys == {rig.hidden}
    assert _get(rig, "ada", f"{PROJECT}/requisitions/{rig.hidden}").status_code == 200


def test_a_hidden_key_answers_as_a_missing_one(rig: Rig) -> None:
    hidden = _get(rig, "uma", f"{PROJECT}/requisitions/{rig.hidden}")
    elsewhere = _get(rig, "uma", f"/projects/P999/requisitions/{rig.hidden}")
    assert hidden.status_code == elsewhere.status_code == 404
    assert hidden.json()["error"] == "record_not_found"
    assert hidden.content == elsewhere.content
    missing = _get(rig, "uma", f"{PROJECT}/requisitions/{MISSING}")
    assert missing.status_code == 404 and missing.json()["error"] == "record_not_found"
