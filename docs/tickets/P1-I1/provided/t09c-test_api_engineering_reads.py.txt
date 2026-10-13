"""The engineering read routes: standards, code lists, tag classes and tags (P1-I1-T09c)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import ALICE, Harness
from tl_core.auth import accounts
from tl_core.services.commands import CommandResult
from tl_mod_engineering import registry
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.handlers.standards import (
    AddCodeValue,
    CloseStandard,
    handle_add_code_value,
    handle_close_standard,
)
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RecordTag,
    RenameTag,
    handle_create_tag,
    handle_record_tag,
    handle_rename_tag,
)
from tl_mod_engineering.loader import load_standards
from tl_mod_engineering.names import COMPANY

ACME = (
    Path(__file__).resolve().parents[3]
    / "schema"
    / "fixtures"
    / "standards"
    / "co.acme.standards@1.0.0.yaml"
)
PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:seed", "source": "test"}


@pytest.fixture
def world(harness: Harness) -> Harness:
    """The acme standards loaded, a project value, and four tags (one renamed away)."""
    with harness.backend() as uow:
        load_standards(uow, load_standards_file(ACME), actor="user:seed", source="test")
        handle_add_code_value(
            uow,
            AddCodeValue(
                **BASE,
                scope=PROJECT,
                code_list="Area",
                code="T1",
                label="Temporary",
                crosswalk="47",
            ),
        )
    made: dict[str, CommandResult] = {}
    tags: tuple[tuple[str, dict[str, Any]], ...] = (
        ("47-FV-1001", {"class_code": "ControlValve", "service": "Feed gas"}),
        ("47-FV-1002", {"class_code": "ControlValve"}),
        ("47-HV-1003", {"class_code": "ManualValve"}),
    )
    with harness.backend() as uow:
        for number, more in tags:
            made[number] = handle_create_tag(
                uow, CreateTag(**BASE, scope=PROJECT, number=number, **more)
            )
    with harness.backend() as uow:
        handle_record_tag(  # a legacy number, kept as a violation the way an import keeps it
            uow, RecordTag(**BASE, scope=PROJECT, number="LEGACY-1"), origin="import"
        )
        handle_rename_tag(
            uow,
            RenameTag(
                **BASE,
                scope=PROJECT,
                stream_id=made["47-HV-1003"].stream_id,
                new_number="47-HV-1004",
                reason="renumbered",
            ),
        )
    return harness


def get(world: Harness, path: str, **params: Any) -> Any:
    response = world.client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def missing(world: Harness, path: str, code: str) -> None:
    response = world.client.get(path)
    assert response.status_code == 404 and response.json()["error"] == code, response.text


def test_standards_lists_the_registry_by_kind_and_code(world: Harness) -> None:
    every = get(world, "/standards")
    kinds = [item["kind"] for item in every]
    assert kinds == sorted(kinds, key=["code_list", "mnemonic", "numbering_pattern"].index)
    lists = get(world, "/standards", kind="code_list")
    assert [item["code"] for item in lists] == sorted(item["code"] for item in lists)
    assert {"Area", "Discipline", "WeldType"} <= {item["code"] for item in lists}
    area = next(item for item in lists if item["code"] == "Area")
    assert area["value_list_policy"] == "extensible" and area["key"] == "CL:Area@1.0.0"
    assert area["edition"] == "co.acme.standards@1.0.0" and area["lifecycle"] == "active"
    assert len(every) == len(lists) + len(get(world, "/standards", kind="mnemonic")) + 1


def test_closed_entries_are_listed_only_when_asked(world: Harness) -> None:
    with world.backend() as uow:
        row = registry.active_standard(uow.conn(), COMPANY, "mnemonic", "FV")
        assert row is not None
        handle_close_standard(
            uow, CloseStandard(**BASE, scope=COMPANY, stream_id=row.id, reason="retired prefix")
        )
    assert "FV" not in {i["code"] for i in get(world, "/standards", kind="mnemonic")}
    kept = get(world, "/standards", kind="mnemonic", include_closed="true")
    assert next(i for i in kept if i["code"] == "FV")["lifecycle"] == "retired"


def test_get_standard_returns_one_entry_or_a_404(world: Harness) -> None:
    pattern = get(world, "/standards/numbering_pattern/tag")
    assert pattern["data"]["template"] == "{area}-{mnemonic}-{seq:4}"
    assert pattern["data"]["record_type"] == "engineering.Tag"
    missing(world, "/standards/code_list/Nope", "standard_not_found")
    assert world.client.get("/standards/tree/Area").status_code == 422


def test_code_values_come_in_list_order_and_a_project_sees_its_own(world: Harness) -> None:
    company = get(world, "/code-lists/Area/values")
    assert [v["code"] for v in company][:3] == ["10", "20", "30"]
    assert all(v["origin"] == "company" and v["usable"] for v in company)
    assert "T1" not in {v["code"] for v in company}
    mine = get(world, "/code-lists/Area/values", project="P123")
    own = next(v for v in mine if v["code"] == "T1")
    assert (own["origin"], own["company_code"], own["scope"]) == ("project", "47", PROJECT)
    missing(world, "/code-lists/Nope/values", "unknown_code_list")


def test_tag_classes_list_and_show(world: Harness) -> None:
    classes = get(world, "/tag-classes")
    assert [c["code"] for c in classes] == sorted(c["code"] for c in classes)
    safety = next(c for c in classes if c["code"] == "SafetyValve")
    assert safety["required_psets"] == ["valve_data", "safety_data"]
    one = get(world, "/tag-classes/ControlValve")
    assert one["family"] == "valve" and "FV" in one["mnemonics"] and one["key"] == "TC:ControlValve"
    missing(world, "/tag-classes/Nope", "tag_class_not_found")


def test_tags_list_by_number_with_filters_and_without_the_ended_ones(world: Harness) -> None:
    path = "/projects/P123/tags"
    numbers = [t["number"] for t in get(world, path)]
    assert numbers == ["47-FV-1001", "47-FV-1002", "47-HV-1004", "LEGACY-1"]
    assert [t["number"] for t in get(world, path, **{"class": "ControlValve"})] == [
        "47-FV-1001",
        "47-FV-1002",
    ]
    assert [t["number"] for t in get(world, path, number_status="violation")] == ["LEGACY-1"]
    assert [t["number"] for t in get(world, path, mnemonic="HV")] == ["47-HV-1004"]
    assert len(get(world, path, include_ended="true")) == 5
    assert [t["number"] for t in get(world, path, limit=2, offset=1)] == [
        "47-FV-1002",
        "47-HV-1004",
    ]
    assert get(world, "/projects/OTHER/tags") == []


def test_one_tag_comes_with_its_segments_and_what_it_lacks(world: Harness) -> None:
    tag = get(world, "/projects/P123/tags/47-FV-1001")
    assert tag["title"] == "Feed gas" and tag["class_code"] == "ControlValve"
    assert tag["segments"] == {"area": "47", "mnemonic": "FV", "seq": "1001"}
    assert tag["number_status"] == "ok" and tag["conformance"] == "nonconformant"
    assert any(i["level"] == "nonconformant" and "valve_data" in i["path"] for i in tag["issues"])
    legacy = get(world, "/projects/P123/tags/LEGACY-1")
    assert legacy["number_status"] == "violation" and legacy["violations"]
    missing(world, "/projects/P123/tags/47-FV-9999", "tag_not_found")


def test_an_agent_token_may_read_all_of_it(world: Harness) -> None:
    with world.backend() as uow:
        bot = accounts.create_account(
            uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
            password=None, by="svc:test",
        )  # fmt: skip
        _, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="t",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    agent = TestClient(world.app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/standards", "/tag-classes", "/projects/P123/tags", "/code-lists/Area/values"):
        assert agent.get(path, headers=headers).status_code == 200, path
    assert ALICE not in token
