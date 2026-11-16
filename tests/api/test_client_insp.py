"""The inspection and checklist reads and the quality command door on both clients (P2-INSP-T08).

The ledger is built by the quality module's commands (``insp_world.py``, loaded by path after
``punch_world.py``, never a projection write) on one database. The embedded client and ``ApiClient``
over a ``TestClient`` sit on that database, one per person: they must give equal answers for the
four reads, and the command door must change what the next read shows. An inspection on a
restricted correspondence item is hidden from the lowest-clearance reader (``uma``); a document
controller (``dora``) reads it.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tl_adapters.db import create_schema
from tl_api.app import create_app
from tl_api.backend import open_backend
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality.commands import (
    PlanInspection,
    RaisePunchItem,
    RecordInspectionResult,
    ScheduleInspection,
    VerifyInspection,
)
from tl_mod_quality.handlers.inspection import MSG_SELF_VERIFY
from tl_tui.embedded import EmbeddedClient

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
PEOPLE = (
    "uma",
    "rob",
    "dora",
    "vera",
)  # uma: the lowest clearance; rob: superuser; dora: restricted
MISSING_INSPECTION = "P123-INS-9999"
MISSING_CHECKLIST = "P123-CHK-9999"


def _load(name: str) -> ModuleType:
    """A quality-module test helper, loaded by path (the module is not on the import path)."""
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def insp_world() -> ModuleType:
    """``insp_world`` imports ``punch_world`` by name, so the punch helper is loaded first."""
    _load("punch_world")
    return _load("insp_world")


def plain(value: Any) -> Any:
    """Dataclasses, lists and dicts as plain data, so two clients' answers can be compared."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


@dataclass
class Rig:
    world: Any
    api: dict[str, ApiClient]
    embedded: dict[str, EmbeddedClient]
    ids: dict[str, str]
    keys: dict[str, str]
    checklist: str


@pytest.fixture
def rig(
    tmp_path: Path, new_db: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Rig]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    db = new_db()
    create_schema(db)
    factory = open_backend(db)
    helper = insp_world()
    world = helper.InspWorld(db)
    world.people()
    tokens_path = tmp_path / "tokens.json"  # the API's static-token file; no static token is used
    # Each person signs in, so the API reads as that person's roles (a static token has none).
    tokens = {
        who: sessions.sign_in(factory, username=who, password=_load("punch_world").PASSWORD)[1]
        for who in PEOPLE
    }
    app = create_app(
        factory,
        settings=ApiSettings(db_path=db, tokens_path=tokens_path),
        tokens=TokenStore(tokens_path),
    )
    http = TestClient(app, raise_server_exceptions=False)
    api = {who: ApiClient("http://testserver", tokens[who], http=http) for who in PEOPLE}
    embedded = {who: EmbeddedClient(factory, actor=f"user:{who}") for who in PEOPLE}

    checklist = world.checklist()
    subject = world.record(helper.IWP, "P123-IWP-0001")
    ids: dict[str, str] = {"subject": subject, "checklist": checklist}
    ids["planned"] = world.plan(subject, title="Flange make-up")
    ids["scheduled"] = world.scheduled(subject, checklist=checklist)
    ids["done"] = world.scheduled(subject, checklist=checklist)
    world.recorded(ids["done"], answers=helper.answers(q1="no"))
    ids["verified"] = world.scheduled(subject, checklist=checklist)
    world.recorded(ids["verified"], answers=helper.answers())
    world.call("sue", "VerifyInspection", inspection=ids["verified"])
    ids["secret"] = world.hidden_record()
    ids["from_secret"] = world.plan(ids["secret"], who="dora", title="Behind the restricted item")
    keys = {
        name: str(world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record))
        for name, record in ids.items()
    }
    try:
        yield Rig(world, api, embedded, ids, keys, checklist)
    finally:
        http.close()
        factory.close()


@pytest.mark.parametrize("who", PEOPLE)
def test_the_four_reads_give_equal_answers_on_both_clients(rig: Rig, who: str) -> None:
    api, emb = rig.api[who], rig.embedded[who]
    assert plain(api.list_inspections(PROJECT)) == plain(emb.list_inspections(PROJECT))
    assert plain(api.list_inspections(PROJECT, state="Done", point="hold")) == plain(
        emb.list_inspections(PROJECT, state="Done", point="hold")
    )
    assert plain(api.get_inspection(PROJECT, rig.keys["verified"])) == plain(
        emb.get_inspection(PROJECT, rig.keys["verified"])
    )
    assert plain(api.list_checklists(PROJECT)) == plain(emb.list_checklists(PROJECT))
    assert plain(api.get_checklist(PROJECT, _checklist_key(rig))) == plain(
        emb.get_checklist(PROJECT, _checklist_key(rig))
    )


def _checklist_key(rig: Rig) -> str:
    return str(rig.world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=rig.checklist))


def test_the_command_door_plans_schedules_and_records_through_both(rig: Rig) -> None:
    scope = SCOPE
    before = rig.api["uma"].list_inspections(PROJECT, state="Planned").total
    planned = rig.api["uma"].quality_command(
        "PlanInspection",
        PlanInspection(
            actor="user:uma",
            source="tui",
            scope=scope,
            title="Door check",
            subject_id=rig.ids["subject"],
            point="hold",
        ),
    )
    assert planned.stream_id
    assert rig.embedded["uma"].list_inspections(PROJECT, state="Planned").total == before + 1
    assert rig.api["uma"].list_inspections(PROJECT, state="Planned").total == before + 1

    rig.embedded["uma"].quality_command(
        "ScheduleInspection",
        ScheduleInspection(
            actor="user:uma",
            source="tui",
            scope=scope,
            inspection=planned.stream_id,
            checklist=rig.checklist,
            scheduled_for="2026-12-01",
            inspector="M. Okafor",
        ),
    )
    key = str(
        rig.world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=planned.stream_id)
    )
    assert rig.api["uma"].get_inspection(PROJECT, key).row.state == "Scheduled"
    assert rig.embedded["uma"].get_inspection(PROJECT, key).row.state == "Scheduled"

    rig.api["rob"].quality_command(
        "RecordInspectionResult",
        RecordInspectionResult(
            actor="user:rob",
            source="tui",
            scope=scope,
            inspection=planned.stream_id,
            answers=_answers(),
        ),
    )
    assert rig.api["uma"].get_inspection(PROJECT, key).row.state == "Done"
    assert rig.embedded["uma"].get_inspection(PROJECT, key).row.state == "Done"


def _answers() -> list[dict[str, Any]]:
    return _load("insp_world").answers()


def test_the_recorder_may_not_verify_through_either_client(rig: Rig) -> None:
    recorded = rig.world.scheduled(rig.ids["subject"], checklist=rig.checklist)
    rig.world.recorded(recorded, answers=_answers())
    key = str(rig.world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=recorded))
    verify = VerifyInspection(actor="user:rob", source="tui", scope=SCOPE, inspection=recorded)
    with pytest.raises(ForbiddenError) as embedded:
        rig.embedded["rob"].quality_command("VerifyInspection", verify)
    with pytest.raises(ForbiddenError) as remote:
        rig.api["rob"].quality_command("VerifyInspection", verify)
    assert MSG_SELF_VERIFY in str(embedded.value)
    assert MSG_SELF_VERIFY in str(remote.value)
    assert rig.embedded["rob"].get_inspection(PROJECT, key).row.state == "Done"


def test_a_missing_key_is_one_not_found_text_on_both(rig: Rig) -> None:
    texts: set[str] = set()
    for client in (rig.api["uma"], rig.embedded["uma"]):
        for key in (MISSING_INSPECTION, rig.keys["from_secret"]):
            with pytest.raises(RecordNotFoundError) as raised:
                client.get_inspection(PROJECT, key)
            texts.add(str(raised.value))
    assert len(texts) == 1
    assert "no inspection" in texts.pop()


def test_a_missing_checklist_is_the_checklist_not_found_text_on_both(rig: Rig) -> None:
    texts: set[str] = set()
    for client in (rig.api["uma"], rig.embedded["uma"]):
        with pytest.raises(RecordNotFoundError) as raised:
            client.get_checklist(PROJECT, MISSING_CHECKLIST)
        texts.add(str(raised.value))
    assert len(texts) == 1
    assert "no checklist" in texts.pop()


def test_the_lowest_clearance_reader_does_not_see_the_restricted_inspection(rig: Rig) -> None:
    secret = rig.keys["from_secret"]
    for client in (rig.api["uma"], rig.embedded["uma"]):
        page = client.list_inspections(PROJECT)
        assert secret not in [row.key for row in page.rows]
        assert page.total == len(page.rows) == 4
        with pytest.raises(RecordNotFoundError):
            client.get_inspection(PROJECT, secret)
    for client in (rig.api["dora"], rig.embedded["dora"]):
        assert secret in [row.key for row in client.list_inspections(PROJECT).rows]
        assert client.get_inspection(PROJECT, secret).row.subject_key is not None


def test_a_punch_command_still_runs_through_the_same_door(rig: Rig) -> None:
    before = rig.api["uma"].list_punch_items(PROJECT).total
    result = rig.api["uma"].quality_command(
        "RaisePunchItem",
        RaisePunchItem(actor="user:uma", source="tui", scope=SCOPE, subject="Via the door"),
    )
    assert result.stream_id
    assert rig.api["uma"].list_punch_items(PROJECT).total == before + 1
