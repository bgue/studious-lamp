"""The requisition and work order reads, on the embedded client and on ``ApiClient`` (P2-I4A T04c2).

The ledger is built by commands (``req_world.World``, loaded by path; no projection write), then
both clients read it: the embedded client in process, the ``ApiClient`` through a ``TestClient``
on the same ledger. Their answers must be equal, a missing key must raise the same
``RecordNotFoundError`` on both, and a person without ``requisitions.view`` is refused by the
embedded list.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from support import Pair
from tl_adapters.db import DbTarget, create_schema
from tl_api.app import create_app
from tl_api.backend import open_backend
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_core.auth import module_roles
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_tui.embedded import EmbeddedClient

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
ACTOR = "user:sue"  # the requisitions superuser: holds requisitions.view, may approve
VIEWER_WITHOUT_WORD = "user:vic"
IWP_1 = "P123-IWP-PIP-0001"
IWP_2 = "P123-IWP-PIP-0002"


def load_world() -> ModuleType:
    """The requisitions ``req_world`` helper, loaded by path (as the T04c1 route test does)."""
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


def plain(value: Any) -> Any:
    """Models and lists as plain JSON data, so two clients' answers can be compared."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


@pytest.fixture
def pair(
    tmp_path: Path, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Pair]:
    """A ledger with two labour requisitions (one approved and scheduled), and both clients."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    db = new_db()
    create_schema(db)
    world = load_world().World(db)
    world.people()
    world.person("vic", ("user",))
    world.editions()
    iwp_1 = world.record("awp.IWP", IWP_1)
    iwp_2 = world.record("awp.IWP", IWP_2)
    approved = world.raise_labor("uma", for_record_id=iwp_1)
    world.call(
        "sue", "ApproveRequisition", requisition=approved, expected_version=world.version(approved)
    )
    order = world.work_order_of(approved)
    world.call(
        "sue",
        "ScheduleWorkOrder",
        work_order=order,
        expected_version=world.version(order),
        planned_start="2026-11-02",
        planned_finish="2026-11-13",
    )
    world.raise_labor("rob", for_record_id=iwp_2)

    tokens_path = tmp_path / "tokens.json"
    token = add_token(tokens_path, ACTOR)
    factory = open_backend(db)
    app = create_app(
        factory,
        settings=ApiSettings(db_path=db, tokens_path=tokens_path),
        tokens=TokenStore(tokens_path),
    )
    http = TestClient(app, raise_server_exceptions=False)
    remote = ApiClient("http://testserver", token, http=http)
    built = Pair(remote, EmbeddedClient(factory, actor=ACTOR), factory, http)
    try:
        yield built
    finally:
        built.close()


def test_the_list_methods_give_equal_answers(pair: Pair) -> None:
    e, r = pair.embedded, pair.remote
    checks = {
        "list_requisitions": lambda c: c.list_requisitions(PROJECT),
        "list_requisitions_kind": lambda c: c.list_requisitions(PROJECT, kind="labor"),
        "list_requisitions_for": lambda c: c.list_requisitions(PROJECT, for_key=IWP_1),
        "list_requisitions_for_unknown": lambda c: c.list_requisitions(PROJECT, for_key="P123-X"),
        "list_requisitions_limit": lambda c: c.list_requisitions(PROJECT, limit=1),
        "list_work_orders": lambda c: c.list_work_orders(PROJECT),
        "list_work_orders_state": lambda c: c.list_work_orders(PROJECT, state="Scheduled"),
    }
    for name, call in checks.items():
        assert plain(call(r)) == plain(call(e)), name
    listed = r.list_requisitions(PROJECT)
    assert len(listed.rows) == listed.total == 2
    assert r.list_requisitions(PROJECT, for_key=IWP_1).total == 1


def test_the_detail_methods_give_equal_answers(pair: Pair) -> None:
    e, r = pair.embedded, pair.remote
    key = r.list_requisitions(PROJECT, for_key=IWP_1).rows[0].key
    order_key = r.list_work_orders(PROJECT).rows[0].key
    assert plain(r.get_requisition(PROJECT, key)) == plain(e.get_requisition(PROJECT, key))
    remote_order = plain(r.get_work_order(PROJECT, order_key))
    assert remote_order == plain(e.get_work_order(PROJECT, order_key))
    detail = r.get_requisition(PROJECT, key)
    assert detail.work_order is not None and detail.work_order.key == order_key


@pytest.mark.parametrize(
    ("call", "text"),
    [
        (lambda c: c.get_requisition(PROJECT, "P123-REQ-9999"), "no requisition 'P123-REQ-9999'"),
        (lambda c: c.get_work_order(PROJECT, "P123-WO-9999"), "no work order 'P123-WO-9999'"),
    ],
)
def test_a_missing_key_raises_one_record_not_found_text_on_both(
    pair: Pair, call: Callable[[Any], Any], text: str
) -> None:
    messages = []
    for client in (pair.embedded, pair.remote):
        with pytest.raises(RecordNotFoundError) as caught:
            call(client)
        messages.append(str(caught.value))
    assert messages[0] == messages[1] == text


def test_a_person_without_the_word_is_refused_by_the_embedded_list(
    pair: Pair, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = module_roles.holds_word

    def without_word(conn: Any, holder: Any, **kwargs: Any) -> bool:
        return False if holder.actor == VIEWER_WITHOUT_WORD else real(conn, holder, **kwargs)

    monkeypatch.setattr(module_roles, "holds_word", without_word)
    vic = EmbeddedClient(pair.factory, actor=VIEWER_WITHOUT_WORD)
    with pytest.raises(ForbiddenError):
        vic.list_requisitions(PROJECT)
