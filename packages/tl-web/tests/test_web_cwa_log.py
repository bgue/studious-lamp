"""The CWA register page: ``GET /web/p/{project}/cwas`` (P2-WEB1-T09b, twin of ``tl_tui.cwa_text``).

The reads of the page (``list_cwas``, ``get_path``, ``list_cwps``) are patched over the mirrors of
``WebReadClient`` with the tl-tui fake of the awp reads (3 CWPs, 2 CWAs with A2 retired, path
versions 1 and 2, 2 current). Positions come from path version 2. Case (f) of the recipe does not
apply: the panel reads nothing, it is the page's ``load_rows`` that reads, so a read that fails
on a listed row is not a case of this page; an unlisted code is the unknown-number 404 of (e).
"""

from __future__ import annotations

import contextlib
import dataclasses
import importlib.util
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import uvicorn
from tl_core.services.errors import RecordNotFoundError
from tl_tui import cwa_text
from tl_tui.text import EMPTY
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PAGE = "/web/p/P123/cwas"
PROJECT = "P123"
COLUMNS = cwa_text.CWA_COLUMNS
SHOTS = Path("/home/user/wt/p2-web1/.accept/shots")  # one place for every worktree
_JS = """
const { chromium } = require('playwright');
(async () => {
  const [base, path, token, out] = process.argv.slice(1);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addCookies([{ name: 'tl_session', value: token, url: base }]);
  const page = await context.newPage();
  await page.goto(base + path);
  await page.screenshot({ path: out });
  await browser.close();
})();
"""


def shoot(app: Any, token: str, path: str, name: str) -> Path:
    """Save `path` (e.g. ``/web/p/P123/cwps``) as seen by the signed-in `token` to `SHOTS/name`."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        assert server.started, "the app did not start"
        base = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
        env = {
            **os.environ,
            "NODE_PATH": os.environ.get("NODE_PATH") or "/opt/node-tools/node_modules",
        }
        subprocess.run(
            ["node", "-e", _JS, base, path, token, str(out)], check=True, env=env, timeout=90
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert out.stat().st_size > 1000, out
    return out


def load_fake() -> Any:
    """3 CWPs, 2 CWAs (A2 retired), WBS 1 / 1.1 / 1.2, path v1 v2 (v2 current), one EWP, one PWP."""
    path = REPO / "packages/tl-tui/tests/fakes_awp.py"
    spec = importlib.util.spec_from_file_location("tl_web_tests_fakes_awp", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fake = mod.FakeAwpSupport()
    fake._init_awp()
    mod.seed_awp(fake, PROJECT)
    return fake


@contextlib.contextmanager
def patched(fake: Any, *, no_path: bool = False) -> Iterator[None]:
    """The three reads of the page answered by ``fake``; ``no_path`` makes ``get_path`` raise the
    fake's ``RecordNotFoundError`` (a project with no path yet)."""

    def get_path(self: WebReadClient, project: str, version: int | None = None) -> Any:
        if no_path:
            raise RecordNotFoundError(f"no path {project!r}")
        return fake.get_path(project, version)

    def list_cwas(self: WebReadClient, project: str) -> Any:
        return fake.list_cwas(project)

    def list_cwps(self: WebReadClient, project: str, **filters: Any) -> Any:
        return fake.list_cwps(project, **filters)

    with (
        mock.patch.object(WebReadClient, "list_cwas", list_cwas),
        mock.patch.object(WebReadClient, "get_path", get_path),
        mock.patch.object(WebReadClient, "list_cwps", list_cwps),
    ):
        yield


@pytest.fixture
def fakes() -> Iterator[None]:
    with patched(load_fake()):
        yield


def lines_of(fake: Any) -> list[cwa_text.CwaLine]:
    return cwa_text.cwa_lines(
        fake.list_cwas(PROJECT), fake.get_path(PROJECT), fake.list_cwps(PROJECT)
    )


def expected_panel(line: cwa_text.CwaLine, technical: bool = False) -> present.Page:
    return cwa_text.cwa_page(line, panel=True, technical=technical)


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.cwas as cwas

    assert any(r is cwas.router for r in routers.page_routers())
    assert LOGS["cwas"].SLUG == "cwas"


def test_seven_regions_and_the_cells_equal_cwa_cells(world: Any, htmlkit: Any, fakes: None) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    headers = doc.headers("log-table")
    assert headers == list(COLUMNS)
    full = [cwa_text.cwa_cells(line) for line in lines_of(load_fake())]
    assert doc.rows("log-table") == htmlkit.project_cells(headers, COLUMNS, full)
    # path order, the retired area last
    assert [r.get("data-number") for r in doc.log_rows()] == ["A1", "A2"]


def test_the_areas_are_in_path_order_from_version_2(world: Any, htmlkit: Any, fakes: None) -> None:
    lines = lines_of(load_fake())
    assert [(line.row.code, line.position, line.steps) for line in lines] == [
        ("A1", 1, 2),
        ("A2", 2, 2),
    ]
    rows = htmlkit.parse(world.web("bob").client.get(PAGE).text).rows("log-table")
    assert [row[COLUMNS.index("Position")] for row in rows] == ["1", "2"]


@pytest.mark.parametrize("code", ["A1", "A2"])
def test_the_panel_is_the_terminal_panel_including_a_retired_area(
    world: Any, htmlkit: Any, fakes: None, code: str
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{code}")
    assert panel.status_code == 200
    line = next(line for line in lines_of(load_fake()) if line.row.code == code)
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, expected_panel(line)) == []
    retired = any("Retired" in fact for fact in htmlkit.page_facts(expected_panel(line)))
    assert retired == (code == "A2")


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: None) -> None:
    want = present.layout.join_facts("2 CWAs", "1 retired")
    assert htmlkit.parse(world.web("bob").client.get(PAGE).text).status() == want


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fakes: None) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "A2"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["A2"]
    one, two = bob.get(f"{PAGE}/panel/ZZ9"), bob.get(f"{PAGE}/panel/ZZ8")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_no_path_yet_gives_no_positions_and_the_page_answers(world: Any, htmlkit: Any) -> None:
    with patched(load_fake(), no_path=True):
        bob = world.web("bob").client
        page = bob.get(PAGE)
        assert page.status_code == 200
        doc = htmlkit.parse(page.text)
        headers = doc.headers("log-table")
        # every position is the same "—", so the log standard drops the column from the table
        assert "Position" not in headers
        fake = load_fake()
        none = cwa_text.cwa_lines(fake.list_cwas(PROJECT), None, fake.list_cwps(PROJECT))
        full = [cwa_text.cwa_cells(line) for line in none]
        assert all(cells[2] == EMPTY for cells in full)
        assert doc.rows("log-table") == htmlkit.project_cells(headers, COLUMNS, full)
        assert doc.status() == present.layout.join_facts("2 CWAs", "1 retired")
        panel = htmlkit.parse(bob.get(f"{PAGE}/panel/A1").text).root
        line = next(line for line in lines_of(load_fake()) if line.row.code == "A1")
        want = expected_panel(dataclasses.replace(line, position=None, steps=0))
        assert htmlkit.missing_facts(panel, want) == []


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_only_the_open_link(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is not None
    assert "data-command" not in bar.text()


def test_plain_and_technical_wording(world: Any, htmlkit: Any, fakes: None) -> None:
    line = next(line for line in lines_of(load_fake()) if line.row.code == "A1")
    bob = htmlkit.parse(world.web("bob").client.get(f"{PAGE}?mode=technical&sel=A1").text)
    assert bob.status() == present.REFUSAL
    assert htmlkit.missing_facts(bob.by_id("log-panel"), expected_panel(line)) == []
    boss = htmlkit.parse(world.web("boss").client.get(f"{PAGE}?mode=technical&sel=A1").text)
    boss_panel = boss.by_id("log-panel")
    assert htmlkit.missing_facts(boss_panel, expected_panel(line, technical=True)) == []
    assert "CWA-A1" in htmlkit.visible(boss_panel)
    assert not any("CWA-A1" in fact for fact in htmlkit.page_facts(expected_panel(line)))


def test_a_real_world_without_awp_data_is_an_empty_register(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no areas and no path, so the table is empty and no panel is found."""
    bob = world.web("bob").client
    page = bob.get(PAGE)
    assert page.status_code == 200
    assert htmlkit.parse(page.text).rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/A1").status_code == 404


def test_the_screenshot_is_saved(world: Any, fakes: None) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, "T09b-cwas.png")
    assert path.exists()
