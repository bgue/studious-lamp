"""``registry.list_tags``: filters, order, paging and the tags that left service."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import seed_registry
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import CommandResult
from tl_mod_engineering import registry
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RenameTag,
    handle_create_tag,
    handle_rename_tag,
)

pytestmark = pytest.mark.usefixtures("fixture_schemas")
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "project:P123"}


def make(db: DbTarget, number: str, **more: Any) -> CommandResult:
    with open_uow(db) as uow:
        return handle_create_tag(uow, CreateTag(**BASE, number=number, **more))


def listed(db: DbTarget, **filters: Any) -> list[str]:
    with open_uow(db, readonly=True) as uow:
        return [t.number for t in registry.list_tags(uow.conn(), "project:P123", **filters)]


@pytest.fixture
def ledger(db: DbTarget) -> DbTarget:
    seed_registry(db)
    make(db, "47-FV-1002", class_code="ControlValve")
    make(db, "47-FV-1001", class_code="ControlValve")
    make(db, "10-PT-0001")
    make(db, "10-HV-0001", class_code="ManualValve")
    make(db, "LEGACY-1", pattern_policy="record", origin="import")
    return db


def test_tags_come_in_number_order(ledger: DbTarget) -> None:
    assert listed(ledger) == ["10-HV-0001", "10-PT-0001", "47-FV-1001", "47-FV-1002", "LEGACY-1"]


def test_each_filter_narrows_the_list(ledger: DbTarget) -> None:
    assert listed(ledger, class_code="ControlValve") == ["47-FV-1001", "47-FV-1002"]
    assert listed(ledger, mnemonic="PT") == ["10-PT-0001"]
    assert listed(ledger, area="47") == ["47-FV-1001", "47-FV-1002"]
    assert listed(ledger, number_status="violation") == ["LEGACY-1"]
    assert listed(ledger, class_code="ControlValve", area="10") == []
    assert listed(ledger, status="Design") == []


def test_paging_cuts_the_ordered_list(ledger: DbTarget) -> None:
    assert listed(ledger, limit=2) == ["10-HV-0001", "10-PT-0001"]
    assert listed(ledger, limit=2, offset=4) == ["LEGACY-1"]


def test_a_tag_that_left_service_is_listed_only_when_asked(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        old = registry.find_tag(uow.conn(), "project:P123", "47-FV-1001")
    assert old is not None
    with open_uow(ledger) as uow:
        handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=old.id, new_number="47-FV-1009", reason="r")
        )
    assert "47-FV-1001" not in listed(ledger)
    assert "47-FV-1009" in listed(ledger)
    assert "47-FV-1001" in listed(ledger, include_ended=True)
    assert listed(ledger, status="Superseded") == ["47-FV-1001"]


def test_another_project_sees_none_of_them(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        assert registry.list_tags(uow.conn(), "project:P999") == []
