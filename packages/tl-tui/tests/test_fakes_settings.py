"""The settings half of `FakeClient` (P0-I8-S18)."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from tl_core.services.errors import (
    InvalidSettingValueError,
    ReasonRequiredError,
    RiskNotAcceptedError,
    SettingChangeNotFoundError,
    SettingLockedError,
    SettingNotLockableError,
    SettingRevertNotLatestError,
    SettingScopeError,
    UnknownSettingError,
)

KEY = "feed.reactions.enabled"


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


def test_the_platform_definitions_are_listed_with_their_defaults(client: FakeClient) -> None:
    rows = client.list_settings()
    assert len(rows) == 10 and [r.effective.key for r in rows] == sorted(
        r.effective.key for r in rows
    )
    assert client.get_setting(KEY).effective.origin == "default"
    assert client.setting_calls[0] == ("list_settings", {"project": None, "prefix": None})


def test_a_user_value_beats_a_project_value_beats_a_company_value(client: FakeClient) -> None:
    key = "ui.tui.keymap"
    client.seed_setting(key, "user:kim", "vim")
    assert client.get_setting(key, user="kim").effective.origin == "user"
    assert client.get_setting(key, user="sam").effective.origin == "default"
    client.seed_setting(KEY, "company", False)
    client.seed_setting(KEY, "project:P1", True)
    assert client.get_setting(KEY, project="P1").effective.value is True
    assert client.get_setting(KEY, project="P2").effective.value is False
    assert client.get_setting(KEY).effective.origin == "company"


def test_writes_are_checked_like_the_service_checks_them(client: FakeClient) -> None:
    with pytest.raises(UnknownSettingError):
        client.get_setting("no.such")
    with pytest.raises(InvalidSettingValueError):
        client.set_setting(KEY, layer="company", value="yes")
    with pytest.raises(SettingScopeError):
        client.set_setting("lake.sync.interval", layer="project:P1", value="1h")
    with pytest.raises(ReasonRequiredError):
        client.set_setting("webhooks.retry.max_hours", layer="company", value=48)
    with pytest.raises(RiskNotAcceptedError):
        client.set_setting("webhooks.egress.allowlist", layer="company", value=[], reason="r")
    with pytest.raises(SettingNotLockableError):
        client.lock_setting("lake.sync.interval", locked=True, reason="r")
    assert client.setting_history(KEY) == []


def test_a_lock_hides_project_values_and_refuses_new_ones(client: FakeClient) -> None:
    client.set_setting(KEY, layer="project:P1", value=False)
    locked = client.lock_setting(KEY, locked=True, reason="policy")
    assert locked.effective.locked
    assert client.get_setting(KEY, project="P1").effective.value is True
    with pytest.raises(SettingLockedError):
        client.set_setting(KEY, layer="project:P1", value=False)


def test_history_has_a_fixed_clock_and_revert_takes_back_only_the_latest(
    client: FakeClient,
) -> None:
    client.set_setting("feed.signal_tags", layer="company", value=["a"])
    client.set_setting("feed.signal_tags", layer="company", value=["b"])
    first, second = client.setting_history("feed.signal_tags")
    assert (first.seq, second.seq) == (1, 2) and first.recorded_at < second.recorded_at
    assert second.old_value == ["a"] and second.actor == "user:dev"
    with pytest.raises(SettingRevertNotLatestError):
        client.revert_setting("feed.signal_tags", layer="company", seq=1)
    with pytest.raises(SettingChangeNotFoundError):
        client.revert_setting("feed.signal_tags", layer="company", seq=9)
    back = client.revert_setting("feed.signal_tags", layer="company", seq=2)
    assert back.effective.value == ["a"]
    assert [c.seq for c in client.setting_history("feed.signal_tags")] == [1]
    client.revert_setting("feed.signal_tags", layer="company", seq=1)
    assert client.get_setting("feed.signal_tags").effective.origin == "default"
