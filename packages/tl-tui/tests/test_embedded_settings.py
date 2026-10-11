"""EmbeddedClient settings over the real services on a temporary ledger (P0-I8-T09)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.db import DbTarget, create_schema
from tl_core.services.errors import (
    InvalidSettingValueError,
    ReasonRequiredError,
    RiskNotAcceptedError,
    SettingLockedError,
    SettingOutOfBoundsError,
    SettingRevertNotLatestError,
    SettingScopeError,
    UnknownSettingError,
)
from tl_core.settings.types import SettingChange
from tl_core.settings.views import SettingView
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

KEY = "feed.reactions.enabled"
TAGS = "feed.signal_tags"


@pytest.fixture
def client(new_db: Callable[[], DbTarget]) -> Iterator[EmbeddedClient]:
    db = new_db()
    create_schema(db)
    found = EmbeddedClient.for_target(db)
    yield found
    found.close()


def test_it_satisfies_the_client_interface_for_settings(client: EmbeddedClient) -> None:
    typed: ClientInterface = client
    assert typed.list_settings() is not None


def test_list_and_get_return_views_sorted_by_key(client: EmbeddedClient) -> None:
    rows = client.list_settings()
    keys = [row.effective.key for row in rows]
    assert keys == sorted(keys) and len(keys) == 10
    assert all(isinstance(row, SettingView) for row in rows)
    one = client.get_setting(KEY)
    assert one.definition.type == "bool" and one.effective.value is True
    assert [r.effective.key for r in client.list_settings(prefix="feed.")] == [KEY, TAGS]
    with pytest.raises(UnknownSettingError):
        client.get_setting("no.such")


def test_a_project_value_is_seen_by_that_project_only(client: EmbeddedClient) -> None:
    done = client.set_setting(KEY, layer="project:P1", value=False)
    assert done.effective.value is False and done.effective.origin == "project"
    assert done.effective.modified_here
    assert client.get_setting(KEY).effective.value is True
    assert client.get_setting(KEY, project="P1").effective.value is False
    assert [r.effective.key for r in client.list_settings(project="P1", modified_only=True)] == [
        KEY
    ]
    assert client.list_settings(project="P2", modified_only=True) == []


def test_the_change_is_recorded_for_the_clients_actor_with_source_tui(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    mine = EmbeddedClient.for_sqlite(db, actor="user:kim")
    mine.set_setting(KEY, layer="company", value=False)
    (row,) = mine.setting_history(KEY)
    assert isinstance(row, SettingChange)
    assert (row.actor, row.layer, row.new_value, row.reset) == ("user:kim", "company", False, False)
    default = EmbeddedClient.for_sqlite(db)
    default.set_setting(KEY, layer="project:P1", value=True)
    assert default.setting_history(KEY, layer="project:P1")[0].actor == "user:dev"
    events = default.change_feed()
    assert events is not None  # the same ledger and bus feed the live view


def test_reset_gives_the_value_back_and_history_keeps_both(client: EmbeddedClient) -> None:
    client.set_setting(KEY, layer="project:P1", value=False)
    back = client.reset_setting(KEY, layer="project:P1")
    assert back.effective.value is True and back.effective.origin == "default"
    assert [(r.new_value, r.reset) for r in client.setting_history(KEY)] == [
        (False, False),
        (None, True),
    ]
    assert client.setting_history(KEY, layer="company") == []


def test_a_scheduled_change_is_listed_and_not_in_force(client: EmbeddedClient) -> None:
    later = datetime.now(UTC) + timedelta(days=30)
    done = client.set_setting(KEY, layer="company", value=False, applies_at=later)
    assert done.effective.value is True
    assert [s.new_value for s in done.effective.scheduled] == [False]


def test_refusals_are_the_service_exceptions(client: EmbeddedClient) -> None:
    with pytest.raises(InvalidSettingValueError):
        client.set_setting(KEY, layer="project:P1", value="yes")
    with pytest.raises(UnknownSettingError):
        client.set_setting("no.such", layer="company", value=1)
    with pytest.raises(SettingScopeError):
        client.set_setting(KEY, layer="elsewhere", value=True)
    with pytest.raises(ReasonRequiredError):
        client.set_setting("webhooks.retry.max_hours", layer="company", value=48)
    allow = "webhooks.egress.allowlist"
    with pytest.raises(RiskNotAcceptedError):
        client.set_setting(allow, layer="company", value=["a.example.com"], reason="r")
    ok = client.set_setting(
        allow, layer="company", value=["a.example.com"], reason="partner", accept_risk=True
    )
    assert ok.effective.value == ["a.example.com"]


def test_a_lock_refuses_projects_and_bounds_limit_their_values(client: EmbeddedClient) -> None:
    locked = client.lock_setting(KEY, locked=True, reason="policy")
    assert locked.effective.locked
    with pytest.raises(SettingLockedError):
        client.set_setting(KEY, layer="project:P1", value=False)
    client.lock_setting(KEY, locked=False, reason="done")
    client.lock_setting("project.mode", locked=False, bounds={"choices": ["live"]}, reason="p")
    with pytest.raises(SettingOutOfBoundsError):
        client.set_setting("project.mode", layer="project:P1", value="sandbox", reason="r")


def test_only_the_latest_change_is_reverted(client: EmbeddedClient) -> None:
    client.set_setting(TAGS, layer="project:P1", value=["a"])
    client.set_setting(TAGS, layer="project:P1", value=["b"])
    with pytest.raises(SettingRevertNotLatestError):
        client.revert_setting(TAGS, layer="project:P1", seq=1)
    undone = client.revert_setting(TAGS, layer="project:P1", seq=2)
    assert undone.effective.value == ["a"]


# --- the fake behaves like the real thing for what the screens do --------------------------------

Script = list[Callable[[Any], Any]]


def shape(view: SettingView) -> tuple[Any, ...]:
    e = view.effective
    return (e.key, e.value, e.origin, e.modified_here, e.locked, e.bounds)


def test_the_fake_client_answers_a_script_like_the_embedded_client(client: EmbeddedClient) -> None:
    fake = FakeClient()
    script: Script = [
        lambda c: c.set_setting(KEY, layer="project:P1", value=False),
        lambda c: c.set_setting(TAGS, layer="company", value=["a", "b"]),
        lambda c: c.get_setting(TAGS, project="P1"),
        lambda c: c.lock_setting(KEY, locked=True, reason="policy"),
        lambda c: c.get_setting(KEY, project="P1"),
        lambda c: c.lock_setting(KEY, locked=False, reason="policy"),
        lambda c: c.reset_setting(KEY, layer="project:P1"),
        lambda c: c.set_setting("ui.tui.keymap", layer="user:kim", value="vim"),
        lambda c: c.get_setting("ui.tui.keymap", user="kim"),
    ]
    for step in script:
        assert shape(step(fake)) == shape(step(client))
    assert [shape(v) for v in fake.list_settings(project="P1")] == [
        shape(v) for v in client.list_settings(project="P1")
    ]
    assert [(c.layer, c.new_value, c.reset) for c in fake.setting_history(KEY)] == [
        (c.layer, c.new_value, c.reset) for c in client.setting_history(KEY)
    ]
