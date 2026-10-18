"""ApiClient about:config methods against a real app (P0-I8-T08). Provided; do not edit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.client import ApiClient
from tl_api.errors import ApiError
from tl_api.tokens import add_token
from tl_core.services.errors import (
    InvalidSettingValueError,
    ReasonRequiredError,
    RiskNotAcceptedError,
    SettingChangeNotFoundError,
    SettingLockedError,
    SettingOutOfBoundsError,
    SettingRevertNotLatestError,
    SettingsDocumentError,
    UnknownSettingError,
)
from tl_core.settings.types import SettingChange, SettingDiff
from tl_core.settings.views import SettingView

KEY = "feed.reactions.enabled"
TAGS = "feed.signal_tags"


def test_list_and_get_return_the_models_the_routes_serve(harness: Harness) -> None:
    api = harness.api()
    rows = api.list_settings()
    keys = [row.effective.key for row in rows]
    assert keys == sorted(keys) and len(keys) == 15
    assert all(isinstance(row, SettingView) for row in rows)
    one = api.get_setting(KEY)
    assert one.definition.type == "bool" and one.effective.value is True
    assert one.effective.origin == "default" and not one.effective.modified_here
    assert [r.effective.key for r in api.list_settings(prefix="feed.")] == [KEY, TAGS]
    with pytest.raises(UnknownSettingError):
        api.get_setting("no.such")


def test_a_project_value_is_seen_by_the_project_and_listed_as_modified(harness: Harness) -> None:
    api = harness.api()
    done = api.set_setting(KEY, layer="project:P1", value=False)
    assert isinstance(done, SettingView)
    assert done.effective.value is False and done.effective.origin == "project"
    assert done.effective.modified_here
    assert api.get_setting(KEY).effective.value is True
    assert api.get_setting(KEY, project="P1").effective.value is False
    mine = api.list_settings(project="P1", modified_only=True)
    assert [r.effective.key for r in mine] == [KEY]
    assert api.list_settings(project="P2", modified_only=True) == []


def test_reset_gives_the_value_back_and_history_keeps_both_changes(harness: Harness) -> None:
    api = harness.api()
    api.set_setting(KEY, layer="project:P1", value=False)
    back = api.reset_setting(KEY, layer="project:P1")
    assert back.effective.value is True and back.effective.origin == "default"
    rows = api.setting_history(KEY)
    assert all(isinstance(row, SettingChange) for row in rows)
    assert [(r.layer, r.new_value, r.reset, r.actor) for r in rows] == [
        ("project:P1", False, False, "user:alice"),
        ("project:P1", None, True, "user:alice"),
    ]
    assert api.setting_history(KEY, layer="company") == []


def test_a_scheduled_change_is_listed_and_not_yet_in_force(harness: Harness) -> None:
    api = harness.api()
    later = datetime.now(UTC) + timedelta(days=30)
    done = api.set_setting(KEY, layer="company", value=False, applies_at=later)
    assert done.effective.value is True
    assert [s.new_value for s in done.effective.scheduled] == [False]


def test_refusals_come_back_as_the_embedded_exceptions(harness: Harness) -> None:
    api = harness.api()
    with pytest.raises(InvalidSettingValueError):
        api.set_setting(KEY, layer="project:P1", value="yes")
    with pytest.raises(UnknownSettingError):
        api.set_setting("no.such", layer="company", value=1)
    with pytest.raises(ReasonRequiredError):
        api.set_setting("webhooks.retry.max_hours", layer="company", value=48)
    with pytest.raises(RiskNotAcceptedError):
        api.set_setting(
            "webhooks.egress.allowlist", layer="company", value=["a.example.com"], reason="r"
        )
    ok = api.set_setting(
        "webhooks.egress.allowlist",
        layer="company",
        value=["a.example.com"],
        reason="partner hub",
        accept_risk=True,
    )
    assert ok.effective.value == ["a.example.com"]


def test_a_lock_with_bounds_refuses_projects_and_can_be_lifted(harness: Harness) -> None:
    api = harness.api()
    locked = api.lock_setting(KEY, locked=True, reason="policy")
    assert locked.effective.locked
    with pytest.raises(SettingLockedError):
        api.set_setting(KEY, layer="project:P1", value=False)
    api.lock_setting(KEY, locked=False, reason="done")
    assert api.set_setting(KEY, layer="project:P1", value=False).effective.value is False
    api.lock_setting("project.mode", locked=False, bounds={"choices": ["live"]}, reason="policy")
    with pytest.raises(SettingOutOfBoundsError):
        api.set_setting("project.mode", layer="project:P1", value="sandbox", reason="r")
    live = api.set_setting("project.mode", layer="project:P1", value="live", reason="r")
    assert live.effective.value == "live"


def test_only_the_latest_change_is_reverted(harness: Harness) -> None:
    api = harness.api()
    api.set_setting(TAGS, layer="project:P1", value=["a"])
    api.set_setting(TAGS, layer="project:P1", value=["b"])
    with pytest.raises(SettingRevertNotLatestError):
        api.revert_setting(TAGS, layer="project:P1", seq=1)
    with pytest.raises(SettingChangeNotFoundError):
        api.revert_setting(TAGS, layer="project:P1", seq=99)
    undone = api.revert_setting(TAGS, layer="project:P1", seq=2)
    assert undone.effective.value == ["a"]


def test_diff_export_and_import_round_trip(harness: Harness) -> None:
    api = harness.api()
    api.set_setting(KEY, layer="company", value=False)
    rows = api.diff_settings("default", "company")
    assert all(isinstance(row, SettingDiff) for row in rows)
    assert [(r.key, r.left.value, r.right.value) for r in rows] == [(KEY, True, False)]
    api.set_setting(KEY, layer="project:P1", value=True)
    text = api.export_settings("project:P1")
    assert yaml.safe_load(text)["settings"] == {KEY: True}
    assert api.import_settings(text, layer="project:P2") == [KEY]
    assert api.get_setting(KEY, project="P2").effective.value is True
    with pytest.raises(SettingsDocumentError):
        api.import_settings("x: [", layer="company")


def test_an_agent_token_reads_but_every_write_is_refused(harness: Harness) -> None:
    token = add_token(harness.settings.tokens_path, "agent:triage")
    http = TestClient(harness.app, raise_server_exceptions=False)
    api = ApiClient("http://testserver", token, http=http)
    assert len(api.list_settings()) == 15
    attempts = [
        lambda: api.set_setting(KEY, layer="company", value=False),
        lambda: api.reset_setting(KEY, layer="company"),
        lambda: api.lock_setting(KEY, locked=True, reason="r"),
        lambda: api.revert_setting(KEY, layer="company", seq=1),
        lambda: api.import_settings("settings: {}", layer="company"),
    ]
    for attempt in attempts:
        with pytest.raises(ApiError) as caught:
            attempt()
        assert (caught.value.status, caught.value.error) == (403, "agent_must_propose")
    assert harness.api().get_setting(KEY).effective.value is True


def test_a_dot_segment_is_refused_before_it_is_sent(harness: Harness) -> None:
    api = harness.api()
    with pytest.raises(ValueError, match="cannot be used"):
        api.get_setting("..")
