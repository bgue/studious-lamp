"""V3-F1b walk: the forms log and record screen of the terminal app, as five kinds of reader.

Readers: the author (``uma``), another user (``rob``), the document controller (``dora``), an
administrator (``ada``) and a plain user (``vera``). The terminal app reads through the embedded
client under the person's viewer; an agent token is not a terminal reader (the `forms.read` route
word is closed to agents and the walk of the routes, ``test_forms_walk``, proves it). A draft and a
submission of a privileged template are the author's alone: for every other reader the log does not
list them and their key opens the screen a key that never existed opens, character for character.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.forms_log import FormRunnerScreen, FormsLogScreen, FormSubmissionScreen

_ROOT = Path(__file__).resolve().parents[2] / "packages"
for _tests in (_ROOT / "tl-modules/forms/tests", _ROOT / "tl-tui/tests"):
    if str(_tests) not in sys.path:
        sys.path.insert(0, str(_tests))

from forms_world import SCOPE, World, two_fields  # noqa: E402
from helpers import settle, static_of  # noqa: E402

PROJECT = "P123"
MISSING_KEY = "P123-FRM-9999"
FAKE_ULID = "01J000000000000000000000"
READERS = ("uma", "rob", "dora", "ada", "vera")
OTHERS = ("rob", "dora", "ada", "vera")
SIZE = (170, 44)


class Rig:
    def __init__(self, h: Harness, world: World) -> None:
        self.h = h
        self.world = world
        self.ids: dict[str, str] = {}
        self.keys: dict[str, str] = {}


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("forms-tui-walk"))
    world = World(h.target or h.db)
    world.people()
    r = Rig(h, world)
    plain = world.template(fields=two_fields())
    secret = world.template(fields=two_fields(), answer_class="privileged")
    r.ids["plain"] = plain
    r.ids["secret"] = secret
    r.keys["open"] = str(world.submit("uma", plain).key)
    r.keys["secret"] = str(world.submit("uma", secret).key)
    r.ids["draft"] = str(world.save("uma", plain).stream_id)
    yield r
    h.close()


def client_for(rig: Rig, who: str) -> EmbeddedClient:
    return EmbeddedClient(rig.h.backend, actor=f"user:{who}")


def observe(rig: Rig, who: str, refs: tuple[str, ...]) -> dict[str, Any]:
    """What ``who`` sees: the log's submission rows (numbers and ids), and for each ``ref`` the
    record screen's status line and page."""
    out: dict[str, Any] = {"screens": {}}
    client = client_for(rig, who)
    app = TlApp(client, scope=SCOPE, actor=f"user:{who}")

    async def go() -> None:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            await _walk(pilot, app, refs, out)

    asyncio.run(go())
    return out


async def _walk(pilot: Pilot[Any], app: TlApp, refs: tuple[str, ...], out: dict[str, Any]) -> None:
    app.action_forms()
    await settle(pilot)
    log = app.screen
    assert isinstance(log, FormsLogScreen)
    out["rows"] = {(r.key or r.id) for r in log.shown}
    out["panel_text"] = " ".join(str(log.panel_text(r)) for r in log.shown)
    out["summary"] = static_of(log, "#log-status")
    await pilot.press("2")
    await settle(pilot)
    out["templates"] = {r.id for r in log.shown}
    await pilot.press("1")
    await settle(pilot)
    for ref in refs:
        app.push_screen(FormSubmissionScreen(app.client, PROJECT, ref))
        await settle(pilot)
        out["screens"][ref] = (
            static_of(app.screen, "#fs-status"),
            static_of(app.screen, "#fs-page"),
        )
        await pilot.press("escape")
        await settle(pilot)


@pytest.fixture(scope="module")
def seen(rig: Rig) -> dict[str, dict[str, Any]]:
    refs = (rig.keys["open"], rig.keys["secret"], rig.ids["draft"], MISSING_KEY, FAKE_ULID)
    return {who: observe(rig, who, refs) for who in READERS}


@pytest.mark.parametrize("who", OTHERS)
def test_the_log_leaves_out_the_draft_and_the_privileged_submission(
    rig: Rig, seen: dict[str, dict[str, Any]], who: str
) -> None:
    got = seen[who]
    assert rig.keys["secret"] not in got["rows"] and rig.ids["draft"] not in got["rows"]
    assert rig.keys["open"] in got["rows"]
    assert rig.keys["secret"] not in got["panel_text"] and rig.ids["draft"] not in got["panel_text"]
    assert "(draft)" not in got["panel_text"]
    assert "2 form submission" in got["summary"] or "1 form submission" in got["summary"]


@pytest.mark.parametrize("who", OTHERS)
def test_a_hidden_key_opens_the_screen_a_missing_key_opens(
    rig: Rig, seen: dict[str, dict[str, Any]], who: str
) -> None:
    screens = seen[who]["screens"]
    missing = screens[MISSING_KEY]
    assert missing[0].startswith("! ") and "This form could not be read." in missing[1]
    assert screens[rig.keys["secret"]] == missing
    assert screens[FAKE_ULID] == missing
    assert screens[rig.ids["draft"]] == missing  # another person's draft, by its id
    assert rig.keys["secret"] not in missing[0] + missing[1]
    assert screens[rig.keys["open"]][0] == ""  # an ordinary submission is readable


def test_the_author_lists_and_opens_the_draft_and_the_privileged_submission(
    rig: Rig, seen: dict[str, dict[str, Any]]
) -> None:
    got = seen["uma"]
    assert {rig.keys["secret"], rig.keys["open"], rig.ids["draft"]} <= got["rows"]
    for ref in (rig.keys["secret"], rig.keys["open"], rig.ids["draft"]):
        status, page = got["screens"][ref]
        assert status == "" and "Answers" in page, ref
    assert got["screens"][MISSING_KEY][0] == "! no such submission"


def test_every_reader_reads_the_published_templates_but_the_log_has_no_other_door(
    rig: Rig, seen: dict[str, dict[str, Any]]
) -> None:
    for who in READERS:
        assert {rig.ids["plain"], rig.ids["secret"]} <= seen[who]["templates"]


def test_the_runner_submits_as_the_person_and_the_number_shows_in_their_log(rig: Rig) -> None:
    """Filled through the runner screen as rob; the new number is in rob's log and, being an
    ordinary template, in uma's; the privileged one stays rob's alone."""
    client = client_for(rig, "rob")
    app = TlApp(client, scope=SCOPE, actor="user:rob")
    seen: dict[str, Any] = {}

    async def go() -> None:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            app.action_forms()
            await settle(pilot)
            log = app.screen
            assert isinstance(log, FormsLogScreen)
            await pilot.press("2")
            await settle(pilot)
            row = next(r for r in log.shown if r.id == rig.ids["secret"])
            log.open_row(row)
            await settle(pilot)
            screen = app.screen
            assert isinstance(screen, FormRunnerScreen)
            for line in ("Ladders", ""):  # an empty line skips the optional count
                for ch in line:
                    await pilot.press("space" if ch == " " else ch)
                await pilot.press("enter")
                await settle(pilot)
            await pilot.press("enter")  # review: send
            await settle(pilot)
            seen["numbers"] = {r.key for r in log.shown}
            seen["status"] = static_of(log, "#log-status")

    asyncio.run(go())
    new = next(iter(seen["numbers"] - {rig.keys["open"], rig.keys["secret"], None}), None)
    assert new is not None and seen["status"].startswith(f"Submitted {new}")
    for who, expect in (("rob", True), ("uma", False), ("ada", False), ("dora", False)):
        page = client_for(rig, who).list_form_submissions(PROJECT)
        assert (new in {r.key for r in page.rows}) is expect, who
