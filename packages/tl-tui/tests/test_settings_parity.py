"""`FakeClient` settings answer like the embedded client, errors and messages included (S19).

The fake is a model of the service, so a script of changes is run on both and the results are
compared: the key as seen at the layer, the history rows (without their numbers and times), and
for a refused call the exception class and its message. A message that changes in the service
fails here, not in a screen test that happens to quote it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.sqlite.uow import create_schema
from tl_core.settings.types import SettingChange
from tl_core.settings.views import SettingView
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

KEY = "feed.reactions.enabled"
TAGS = "feed.signal_tags"
DANGER = "webhooks.egress.allowlist"

Step = Callable[[ClientInterface], Any]


def latest(client: ClientInterface, key: str, layer: str) -> int:
    return [c for c in client.setting_history(key) if c.layer == layer][-1].seq


def first(client: ClientInterface, key: str, layer: str) -> int:
    return [c for c in client.setting_history(key) if c.layer == layer][0].seq


SCRIPT: list[tuple[str, Step]] = [
    ("set a project value", lambda c: c.set_setting(KEY, layer="project:P1", value=False)),
    ("set the same value again", lambda c: c.set_setting(KEY, layer="project:P1", value=False)),
    ("a wrong type", lambda c: c.set_setting(KEY, layer="project:P1", value="yes")),
    ("an unknown key", lambda c: c.set_setting("no.such", layer="company", value=1)),
    ("a layer the key does not have", lambda c: c.set_setting(TAGS, layer="user:kim", value=["a"])),
    ("a platform-only layer", lambda c: c.set_setting(KEY, layer="elsewhere", value=True)),
    (
        "advanced without a reason",
        lambda c: c.set_setting("ai.agents.daily_proposals", layer="company", value=5),
    ),
    (
        "dangerous without a reason",
        lambda c: c.set_setting(DANGER, layer="company", value=["a.example.com"]),
    ),
    (
        "dangerous without the risk",
        lambda c: c.set_setting(DANGER, layer="company", value=["a.example.com"], reason="r"),
    ),
    (
        "dangerous with both",
        lambda c: c.set_setting(
            DANGER, layer="company", value=["a.example.com"], reason=" partner ", accept_risk=True
        ),
    ),
    (
        "undo a dangerous change without the risk",
        lambda c: c.revert_setting(
            DANGER, layer="company", seq=latest(c, DANGER, "company"), reason="r"
        ),
    ),
    (
        "undo a dangerous change",
        lambda c: c.revert_setting(
            DANGER, layer="company", seq=latest(c, DANGER, "company"), reason="r", accept_risk=True
        ),
    ),
    ("lock without a reason", lambda c: c.lock_setting(KEY, locked=True, reason=" ")),
    (
        "lock a key that cannot be locked",
        lambda c: c.lock_setting("lake.sync.interval", locked=True, reason="r"),
    ),
    ("lock", lambda c: c.lock_setting(KEY, locked=True, reason="policy")),
    (
        "a project is refused by the lock",
        lambda c: c.set_setting(KEY, layer="project:P2", value=False),
    ),
    ("the project value is inert", lambda c: c.get_setting(KEY, project="P1")),
    ("unlock", lambda c: c.lock_setting(KEY, locked=False, reason="policy changed")),
    (
        "bounds",
        lambda c: c.lock_setting(
            "project.mode", locked=False, bounds={"choices": ["live"]}, reason="p"
        ),
    ),
    (
        "outside the bounds",
        lambda c: c.set_setting("project.mode", layer="project:P1", value="sandbox", reason="r"),
    ),
    (
        "inside the bounds",
        lambda c: c.set_setting("project.mode", layer="project:P1", value="live", reason="r"),
    ),
    (
        "two changes",
        lambda c: (
            c.set_setting(TAGS, layer="company", value=["a"]),
            c.set_setting(TAGS, layer="company", value=["b"]),
        )[1],
    ),
    (
        "undo an older change",
        lambda c: c.revert_setting(TAGS, layer="company", seq=first(c, TAGS, "company")),
    ),
    (
        "undo a change that is not there",
        lambda c: c.revert_setting(TAGS, layer="company", seq=9999),
    ),
    (
        "undo the latest",
        lambda c: c.revert_setting(TAGS, layer="company", seq=latest(c, TAGS, "company")),
    ),
    (
        "undo the undo",
        lambda c: c.revert_setting(TAGS, layer="company", seq=latest(c, TAGS, "company")),
    ),
    ("reset", lambda c: c.reset_setting(TAGS, layer="company")),
    ("reset where nothing is set", lambda c: c.reset_setting(TAGS, layer="company")),
    (
        "undo the reset",
        lambda c: c.revert_setting(TAGS, layer="company", seq=latest(c, TAGS, "company")),
    ),
    ("a user value", lambda c: c.set_setting("ui.tui.keymap", layer="user:kim", value="vim")),
    ("seen by that user", lambda c: c.get_setting("ui.tui.keymap", user="kim")),
]


def shape(view: SettingView) -> tuple[Any, ...]:
    e = view.effective
    return (e.key, e.value, e.origin, e.modified_here, e.locked, e.bounds)


def outcome(step: Step, client: ClientInterface) -> tuple[Any, ...]:
    try:
        result = step(client)
    except Exception as exc:  # compared, not swallowed: the class and the text must match
        # change numbers are event seqs in the ledger and a counter in the fake: not compared
        text = re.sub(r"\b(change|seq) \d+", r"\1 N", str(exc))
        return ("refused", type(exc).__name__, text)
    assert isinstance(result, SettingView)
    return ("ok", shape(result))


def rows(client: ClientInterface, key: str) -> list[tuple[Any, ...]]:
    found: list[SettingChange] = client.setting_history(key)
    return [(c.layer, c.old_value, c.new_value, c.reset, c.reason, c.actor) for c in found]


@pytest.fixture
def embedded(tmp_path: Path) -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    return EmbeddedClient.for_sqlite(db)


def test_every_step_of_the_script_has_the_same_outcome_on_both(embedded: EmbeddedClient) -> None:
    fake = FakeClient()
    for name, step in SCRIPT:
        assert outcome(step, fake) == outcome(step, embedded), name


def test_the_histories_have_the_same_rows_on_both(embedded: EmbeddedClient) -> None:
    fake = FakeClient()
    for _, step in SCRIPT:
        outcome(step, fake)
        outcome(step, embedded)
    for key in (KEY, TAGS, DANGER, "project.mode", "ui.tui.keymap"):
        assert rows(fake, key) == rows(embedded, key), key
    assert (
        len(rows(fake, TAGS)) == 6
    )  # two sets, an undo, a reset, a second undo ... as the service has
    assert [(v.effective.key, v.effective.value) for v in fake.list_settings(project="P1")] == [
        (v.effective.key, v.effective.value) for v in embedded.list_settings(project="P1")
    ]
