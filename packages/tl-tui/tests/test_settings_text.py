"""The about:config texts: rows, detail lines, hints and the layer a change goes to (P0-I8-S19)."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from tl_core.settings import get_definition
from tl_core.settings.types import ScheduledChange
from tl_tui.display import Labels
from tl_tui.settings_text import (
    detail_lines,
    hint_for,
    history_cells,
    layer_label,
    row_cells,
    target_layer,
    user_of,
)


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


def test_user_of_names_a_person_only() -> None:
    assert user_of("user:kim") == "kim"
    assert user_of("agent:triage") is None
    assert user_of("kim") is None


def test_the_target_layer_follows_the_key_and_the_preference() -> None:
    reactions = get_definition("feed.reactions.enabled")  # platform, company, project
    interval = get_definition("lake.sync.interval")  # platform, company
    keymap = get_definition("ui.tui.keymap")  # platform, user
    mode = get_definition("project.mode")  # platform, project
    assert target_layer(reactions, "project", "P1", "kim") == "project:P1"
    assert target_layer(reactions, "company", "P1", "kim") == "company"
    assert target_layer(reactions, "project", None, "kim") == "company"
    assert target_layer(interval, "project", "P1", "kim") == "company"
    assert target_layer(keymap, "project", "P1", "kim") == "user:kim"
    assert target_layer(keymap, "project", "P1", None) is None
    assert target_layer(mode, "company", "P1", "kim") == "project:P1"
    assert target_layer(mode, "company", None, "kim") is None


def test_a_row_shows_key_value_type_origin_and_lock(client: FakeClient) -> None:
    client.seed_setting("feed.reactions.enabled", "project:P1", False)
    client.lock_setting("feed.signal_tags", locked=True, reason="policy")
    reactions = client.get_setting("feed.reactions.enabled", project="P1")
    tags = client.get_setting("feed.signal_tags", project="P1")
    assert row_cells(reactions) == ("feed.reactions.enabled", "false", "bool", "project ●", "")
    assert row_cells(tags) == (
        "feed.signal_tags",
        "[safety, hold, decision, +2]",
        "list",
        "default",
        "locked",
    )


def test_the_detail_lists_what_matters_and_leaves_out_what_does_not(client: FakeClient) -> None:
    plain = detail_lines(client.get_setting("feed.reactions.enabled"), "project:P1")
    assert plain[0] == "key feed.reactions.enabled"
    assert "type bool (true or false)" in plain
    assert "change goes to Project P1" in plain
    assert not any(line.startswith(("risk", "effect", "locked", "bounds")) for line in plain)
    danger = detail_lines(client.get_setting("webhooks.egress.allowlist"), None)
    assert "risk dangerous: a reason is required; you must accept the risk" in danger
    assert "change goes to nowhere: platform default only" in danger
    client.lock_setting("feed.reactions.enabled", locked=True, reason="p")
    locked = detail_lines(client.get_setting("feed.reactions.enabled"), "company")
    assert "locked yes: projects cannot override it" in locked


def test_hints_say_how_to_type_a_value() -> None:
    assert hint_for(get_definition("lake.sync.interval")) == (
        "duration such as 90s, 5m, 24h, 10 to 86400"
    )
    assert hint_for(get_definition("project.mode")).startswith("one of ")
    assert hint_for(get_definition("feed.signal_tags")).startswith("words separated")


def test_a_history_row_shows_the_move_and_the_reason(client: FakeClient) -> None:
    client.set_setting("feed.signal_tags", layer="company", value=["a"], reason=None)
    client.set_setting("feed.signal_tags", layer="company", value=["b"])
    client.reset_setting("feed.signal_tags", layer="company")
    first, _, last = client.setting_history("feed.signal_tags")
    assert history_cells(first) == (
        "Company",
        "2026-10-09 09:01",
        "dev",
        "null -> [a]",
        "",
    )
    assert history_cells(first, technical=True) == (
        "1",
        "company",
        "2026-10-09 09:01",
        "user:dev",
        "null -> [a]",
        "",
    )
    assert history_cells(last)[3] == "reset"
    assert history_cells(first, technical=True)[1] == "company"


def test_the_layer_reads_in_plain_words_and_by_its_key_only_when_technical() -> None:
    assert layer_label("company") == "Company"
    assert layer_label("project:P123") == "Project P123"
    assert layer_label("user:kim") == "User"


def test_a_service_actor_reads_as_a_service_and_its_id_is_technical_only(
    client: FakeClient,
) -> None:
    client.setting_actor = "svc:enricher"
    client.set_setting("feed.signal_tags", layer="company", value=["a"])
    (change,) = client.setting_history("feed.signal_tags")
    assert history_cells(change)[2] == "a service"
    assert history_cells(change, Labels(services={"svc:enricher": "Enricher"}))[2] == "Enricher"
    assert history_cells(change, technical=True)[3] == "svc:enricher"


def test_a_scheduled_change_ends_with_its_sequence_number_only_when_technical(
    client: FakeClient,
) -> None:
    view = client.get_setting("feed.signal_tags")
    later = ScheduledChange(applies_at="2026-11-01T00:00:00Z", new_value=["b"], seq=7)
    effective = view.effective.model_copy(update={"scheduled": [later]})
    scheduled = view.model_copy(update={"effective": effective})
    assert "scheduled 2026-11-01T00:00:00Z [b]" in detail_lines(scheduled, None)
    assert "scheduled 2026-11-01T00:00:00Z [b] (seq 7)" in detail_lines(
        scheduled, None, technical=True
    )
