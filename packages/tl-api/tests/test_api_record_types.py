"""``GET /record-types`` (OC-T1): one row per record type with its offline class, no record data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from harness import Harness
from tl_api.client import ApiClient
from tl_core.auth import accounts
from tl_core.offline import RecordTypeRow, record_type_rows
from tl_schema.generated.offline_classes import OFFLINE_CLASSES

FIELDS = {"record_type", "label", "module", "offline", "drafting_commands"}


def test_the_rows_equal_the_record_type_rows_of_the_core(harness: Harness) -> None:
    response = harness.client.get("/record-types")
    assert response.status_code == 200, response.text
    assert response.json() == [row.model_dump() for row in record_type_rows()]


def test_there_is_one_row_per_offline_table_key_sorted(harness: Harness) -> None:
    rows = harness.client.get("/record-types").json()
    assert [r["record_type"] for r in rows] == sorted(OFFLINE_CLASSES)
    assert {r["record_type"]: r["offline"] for r in rows} == dict(OFFLINE_CLASSES)


def test_engineering_tag_is_full_and_lists_no_drafting_command(harness: Harness) -> None:
    by_type = {r["record_type"]: r for r in harness.client.get("/record-types").json()}
    tag = by_type["engineering.Tag"]
    assert (tag["offline"], tag["module"], tag["drafting_commands"]) == ("full", "engineering", [])
    assert tag["label"] == "Tag"


def test_a_draft_only_type_lists_its_drafting_commands_and_a_none_type_does_not(
    harness: Harness,
) -> None:
    by_type = {r["record_type"]: r for r in harness.client.get("/record-types").json()}
    revision = by_type["documents.Revision"]
    assert revision["offline"] == "draft_only"
    assert revision["drafting_commands"] == ["CreateRevision", "VoidRevision"]
    assert by_type["documents.ReviewCycle"]["offline"] == "none"
    assert by_type["documents.ReviewCycle"]["drafting_commands"] == []
    assert by_type["core.Record"]["module"] == "core"


def test_every_row_has_exactly_the_five_fields(harness: Harness) -> None:
    rows = harness.client.get("/record-types").json()
    assert rows and all(set(row) == FIELDS for row in rows)
    assert all(isinstance(row["drafting_commands"], list) for row in rows)


def test_an_unauthenticated_call_is_refused(harness: Harness) -> None:
    response = harness.client_for(None).get("/record-types")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_a_bad_token_is_refused(harness: Harness) -> None:
    response = harness.client_for(None).get(
        "/record-types", headers={"Authorization": "Bearer nonsense"}
    )
    assert response.status_code == 401


def test_the_route_takes_no_write_method(harness: Harness) -> None:
    assert harness.client.post("/record-types", json={}).status_code in (404, 405)
    assert harness.client.delete("/record-types").status_code in (404, 405)


def test_an_agent_token_may_read_it(harness: Harness) -> None:
    with harness.backend(False) as uow:
        bot = accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
        _, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="record-types",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    response = harness.client_for(None).get(
        "/record-types", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    assert [r["record_type"] for r in response.json()] == sorted(OFFLINE_CLASSES)


def test_the_http_client_returns_the_same_rows_as_models(harness: Harness) -> None:
    api: ApiClient = harness.api()
    rows = api.record_types()
    assert all(isinstance(row, RecordTypeRow) for row in rows)
    assert rows == record_type_rows()
