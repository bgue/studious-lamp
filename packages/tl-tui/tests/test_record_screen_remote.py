"""The record screen over `RemoteClient` on loopback: a hidden record reads like a missing one.

P1-UX-T11b (carry-over of the S2 review F1). The API serves the harness ledger over a real socket;
the viewer is the one the plain token names (`user:alice` is not a document controller). Reads of
restricted records run under ``use_viewer(LOWEST)``, as in `test_record_screen.py` (ADR-0016).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import ALICE, Harness
from helpers import run_pilot, screen_text
from remote_support import LIVE_TIMEOUT_S, SCOPE
from textual.app import App
from textual.pilot import Pilot
from tl_core.confidentiality import LOWEST, use_viewer
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world
from tl_tui.client import ClientInterface
from tl_tui.display import DisplayMode
from tl_tui.remote import RemoteClient
from tl_tui.widgets.record_screen import RecordScreen

PROJECT = "P123"
ACTOR = "user:alice"
FAKE_ID = "01J000000000000000000000"


class Host(App[None]):
    """A bare app that can host one record screen."""

    def __init__(self, client: ClientInterface, record_id: str) -> None:
        super().__init__()
        self.client = client
        self.record_id = record_id
        self.actor = ACTOR
        self.display_mode = DisplayMode()

    def on_mount(self) -> None:
        self.push_screen(RecordScreen(self.client, SCOPE, PROJECT, self.record_id, ACTOR))


def _text_over_remote(base_url: str, token: str, record_id: str, tmp: Path) -> str:
    """The text of the record screen for ``record_id``, read through a remote client."""
    remote = RemoteClient.connect(base_url, token, timeout=LIVE_TIMEOUT_S).as_client()
    app = Host(remote, record_id)
    seen: list[str] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        seen.append(screen_text(app))

    with use_viewer(LOWEST):
        run_pilot(app, scenario, size=(100, 30))
    return seen[0]


@pytest.fixture
def hidden_world(harness: Harness) -> Hidden:
    """The hidden world seeded on the harness ledger that the live server serves."""
    return seed_hidden_world(harness.db, harness.service, harness.root)


def test_remote_hidden_record_reads_like_a_missing_one(
    harness: Harness, hidden_world: Hidden
) -> None:
    with harness.live(ALICE) as server:
        for kind in ("restricted", "privileged", "bogus"):
            record_id = hidden_world.ids[kind]
            as_hidden = _text_over_remote(server.base_url, server.token, record_id, harness.root)
            as_missing = _text_over_remote(server.base_url, server.token, FAKE_ID, harness.root)
            assert "No record" in as_hidden, kind
            assert as_hidden == as_missing, kind
            assert record_id not in as_hidden and hidden_world.numbers[kind] not in as_hidden, kind


def test_remote_readable_record_opens(harness: Harness, hidden_world: Hidden) -> None:
    with harness.live(ALICE) as server:
        readable = _text_over_remote(
            server.base_url, server.token, hidden_world.ids["open"], harness.root
        )
    assert "No record" not in readable
    assert hidden_world.numbers["open"] in readable
