"""``GET /schema/forms`` with ``record_id``: the sets a record's class binds (P1-UX-S2, ADR-0010).

A hidden record answers as one that never existed (ADR-0016): the route hands the id to
``psets.form_metadata`` only when the viewer may read the record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import SCOPE, Harness
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.services import psets
from tl_mod_correspondence.confseed import seed_hidden_world
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.handlers.tags import CreateTag, handle_create_tag
from tl_mod_engineering.loader import load_standards

ACME = (
    Path(__file__).resolve().parents[3]
    / "schema"
    / "fixtures"
    / "standards"
    / "co.acme.standards@1.0.0.yaml"
)
TAG = "engineering.Tag"
PASSWORD = "correct horse battery"
FAKE_ID = "01J000000000000000000000"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def tag_id(harness: Harness) -> str:
    """A tag of the class ControlValve, which binds the set ``valve_data``."""
    base: dict[str, Any] = {"actor": "user:seed", "source": "test"}
    with harness.backend(False) as uow:
        load_standards(uow, load_standards_file(ACME), actor="user:seed", source="test")
        made = handle_create_tag(
            uow, CreateTag(**base, scope=SCOPE, number="47-FV-1001", class_code="ControlValve")
        )
    return made.stream_id


def forms(client: Any, record_type: str, record_id: str | None = None, **headers: str) -> Any:
    params = {"scope": SCOPE, "record_type": record_type}
    if record_id is not None:
        params["record_id"] = record_id
    return client.get("/schema/forms", params=params, headers=headers)


def group_names(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [g["name"] for g in response.json()["psets"]]


def test_a_tag_id_adds_the_sets_its_class_binds(harness: Harness, tag_id: str) -> None:
    without = forms(harness.client, TAG)
    with_id = forms(harness.client, TAG, tag_id)
    assert "valve_data" not in group_names(without)
    assert "valve_data" in group_names(with_id)
    assert set(with_id.json()) == set(without.json())  # the shape is the same


def test_the_route_hands_the_id_on_only_for_a_visible_record(
    harness: Harness, tag_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str | None] = []
    real = psets.form_metadata

    def spy(uow: Any, scope: str, record_type: str, record_id: str | None = None) -> Any:
        seen.append(record_id)
        return real(uow, scope, record_type, record_id)

    monkeypatch.setattr(psets, "form_metadata", spy)
    forms(harness.client, TAG, tag_id)
    forms(harness.client, TAG, FAKE_ID)
    forms(harness.client, TAG)
    assert seen == [tag_id, None, None]


def test_a_hidden_record_and_a_missing_one_answer_like_no_record_id(
    harness: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hidden = seed_hidden_world(harness.target or harness.db, harness.service, tmp_path)
    with harness.backend(False) as uow:
        accounts.create_account(
            uow, username="bob", display_name="Bob", kind="person", roles=["user"],
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
    _, token = sessions.sign_in(harness.backend, username="bob", password=PASSWORD)
    bob = {"Authorization": f"Bearer {token}"}
    client = harness.client_for(None)
    seen: list[str | None] = []
    real = psets.form_metadata

    def spy(uow: Any, scope: str, record_type: str, record_id: str | None = None) -> Any:
        seen.append(record_id)
        return real(uow, scope, record_type, record_id)

    monkeypatch.setattr(psets, "form_metadata", spy)
    plain = forms(client, TAG, **bob)
    assert plain.status_code == 200
    for kind in ("restricted", "privileged", "bogus", "document"):
        for record_type in (TAG, "correspondence.Correspondence"):
            hidden_answer = forms(client, record_type, hidden.ids[kind], **bob)
            missing = forms(client, record_type, FAKE_ID, **bob)
            bare = forms(client, record_type, **bob)
            assert hidden_answer.status_code == missing.status_code == bare.status_code == 200
            assert hidden_answer.content == missing.content == bare.content, kind
    assert seen and set(seen) == {None}  # a hidden id never reached the service
    # the open item is readable: its id is handed on
    forms(client, "correspondence.Correspondence", hidden.ids["open"], **bob)
    assert seen[-1] == hidden.ids["open"]


def test_the_api_client_sends_record_id_and_equals_the_embedded_answer(
    harness: Harness, tag_id: str
) -> None:
    api = harness.api()
    sent: list[dict[str, str]] = []
    real = api._get_json  # noqa: SLF001

    def record(path: str, params: dict[str, str] | None = None) -> Any:
        sent.append(dict(params or {}))
        return real(path, params)

    api._get_json = record  # type: ignore[method-assign]  # noqa: SLF001
    bound = api.form_metadata(SCOPE, TAG, tag_id)
    plain = api.form_metadata(SCOPE, TAG)
    assert sent[0] == {"scope": SCOPE, "record_type": TAG, "record_id": tag_id}
    assert "record_id" not in sent[1]
    with harness.backend(True) as uow:
        assert bound == psets.form_metadata(uow, SCOPE, TAG, tag_id)
        assert plain == psets.form_metadata(uow, SCOPE, TAG)
    assert [g.name for g in bound.psets if g.name == "valve_data"] == ["valve_data"]
