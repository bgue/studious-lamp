"""The path of construction page: ``GET /web/p/{project}/path`` (P2-WEB1-T16, TWINS recipe).

The reads of the page are the tl-tui fake of the awp reads, loaded by path and patched over the
four path and list mirrors it uses: ``get_path``, ``list_path_versions``, ``list_cwas`` and
``list_cwps``. The fake holds one path of two versions: version 1 has one step (A1 at 1), version 2
(current) has two (A1 at 1, A2 at 2; A2 is retired). Case (f) of the recipe does not apply: the
panel reads nothing of its own (it is the page's ``load_rows``, run again by the panel route), so
there is no panel read that can fail on a listed row. Case (i) has no technical-only row on this
page, so only the REFUSAL part applies (``bob``). The real world is read once, unpatched, at the
end: no path, so the table is empty, the panel is a 404, and ``?version=1`` is a 404.
"""

from __future__ import annotations

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
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

PAGE = "/web/p/P123/path"
COMPARE_PAGE = f"{PAGE}?compare=1"
PROJECT = "P123"
PATH_COLUMNS = present.path_text.PATH_COLUMNS
COMPARE_COLUMNS = present.path_text.COMPARE_COLUMNS
REPO = Path(__file__).resolve().parents[3]

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
    # 3 CWPs, 2 CWAs (A2 retired), WBS 1 / 1.1 / 1.2, path v1 v2, one EWP, one PWP; project P123
    spec = importlib.util.spec_from_file_location(
        "tl_web_tests_fakes_awp", REPO / "packages/tl-tui/tests/fakes_awp.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fake = mod.FakeAwpSupport()
    fake._init_awp()
    mod.seed_awp(fake, PROJECT)
    return fake


@pytest.fixture
def fakes() -> Iterator[Any]:
    fake = load_fake()

    def get_path(self: WebReadClient, project: str, version: int | None = None) -> Any:
        return fake.get_path(project, version)

    def list_path_versions(self: WebReadClient, project: str) -> Any:
        return fake.list_path_versions(project)

    def list_cwas(self: WebReadClient, project: str) -> Any:
        return fake.list_cwas(project)

    def list_cwps(self: WebReadClient, project: str, **filters: Any) -> Any:
        return fake.list_cwps(project, **filters)

    with (
        mock.patch.object(WebReadClient, "get_path", get_path),
        mock.patch.object(WebReadClient, "list_path_versions", list_path_versions),
        mock.patch.object(WebReadClient, "list_cwas", list_cwas),
        mock.patch.object(WebReadClient, "list_cwps", list_cwps),
    ):
        yield fake


def lines_of(fake: Any, version: int) -> list[present.path_text.PathLine]:
    return present.path_text.path_lines(
        fake.get_path(PROJECT, version), fake.list_cwas(PROJECT), fake.list_cwps(PROJECT)
    )


def step_of(fake: Any, version: int, code: str) -> present.path_text.PathLine:
    return next(line for line in lines_of(fake, version) if line.step.cwa == code)


def panel_page(
    fake: Any,
    version: int,
    line: present.path_text.PathLine | None,
    previous: int | None = None,
) -> present.Page:
    view = fake.get_path(PROJECT, version)
    earlier = None if previous is None else fake.get_path(PROJECT, previous)
    return present.path_text.path_page(
        view, fake.list_path_versions(PROJECT), line, previous=earlier, panel=True
    )


def row_panel(client: Any, doc: Any, number: str) -> list[str]:
    """The panel the page's row ``number`` loads (its ``hx-get`` link, followed as htmx would)."""
    row = next(r for r in doc.log_rows() if r.get("data-number") == number)
    return client.get(row.get("hx-get")).text


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.path as path

    assert any(r is path.router for r in routers.page_routers())
    assert LOGS["path"].SLUG == "path"


def test_seven_regions_and_the_cells_equal_the_text_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    headers = doc.headers("log-table")
    assert headers[:2] == ["Number", "Subject"]
    assert headers == [h for h in PATH_COLUMNS if h in headers]
    full = [list(present.path_text.path_cells(line)) for line in lines_of(fakes, 2)]
    assert doc.rows("log-table") == htmlkit.project_cells(headers, PATH_COLUMNS, full)
    assert [r.get("data-number") for r in doc.log_rows()] == ["1", "2"]


def test_the_panel_of_a_step_is_the_terminal_page_of_the_version(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    panel = htmlkit.parse(row_panel(bob, doc, "2"))
    want = panel_page(fakes, 2, step_of(fakes, 2, "A2"), previous=1)
    assert htmlkit.missing_facts(panel.root, want) == []


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.status() == present.layout.join_facts("2 steps", "version 2")


def test_the_filter_keeps_the_matching_row_and_an_unknown_number_is_a_404(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "Area A2"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["2"]
    one, two = bob.get(f"{PAGE}/panel/9"), bob.get(f"{PAGE}/panel/8")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: Any) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_only_the_open_link(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is not None
    assert "data-command" not in bar.text()


def test_plain_viewer_asking_for_technical_gets_the_refusal_and_the_plain_panel(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"mode": "technical"}).text)
    assert doc.status() == present.REFUSAL
    want = panel_page(fakes, 2, step_of(fakes, 2, "A1"), previous=1)
    assert htmlkit.missing_facts(doc.by_id("log-panel"), want) == []


def test_version_1_rows_and_status_are_the_text_module_of_version_1(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE, params={"version": "1"}).text)
    assert doc.headers("log-table") == list(PATH_COLUMNS)
    full = [list(present.path_text.path_cells(line)) for line in lines_of(fakes, 1)]
    assert doc.rows("log-table") == full
    assert doc.status() == present.layout.join_facts("1 step", "version 1")
    # the panel of the row is of version 1 too: its link carries the version, and its lines are
    # version 1's page (no earlier version, so no changed steps)
    assert "version=1" in row_panel_link(doc, "1")
    panel = htmlkit.parse(row_panel(bob, doc, "1"))
    assert htmlkit.missing_facts(panel.root, panel_page(fakes, 1, step_of(fakes, 1, "A1"))) == []
    other = panel_page(fakes, 2, step_of(fakes, 2, "A1"), previous=1)
    assert htmlkit.missing_facts(panel.root, other) != []  # version 2's page is not version 1's


def row_panel_link(doc: Any, number: str) -> str:
    return next(r for r in doc.log_rows() if r.get("data-number") == number).get("hx-get")


def test_compare_rows_are_the_compare_cells_of_the_two_versions(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE, params={"compare": "1"}).text)
    assert doc.headers("log-table") == list(COMPARE_COLUMNS)
    old, new = fakes.get_path(PROJECT, 1), fakes.get_path(PROJECT, 2)
    moved = present.path_text.compare_versions(old, new)
    assert doc.rows("log-table") == [list(present.path_text.compare_cells(m)) for m in moved]
    assert doc.status() == present.layout.join_facts("2 rows", "against version 1")
    # the panel of the A2 row: version 2 in comparison mode, with its CWP list and changed steps
    link = row_panel_link(doc, "A2")
    assert "version=2" in link and "compare=1" in link
    panel = htmlkit.parse(row_panel(bob, doc, "A2"))
    want = panel_page(fakes, 2, step_of(fakes, 2, "A2"), previous=1)
    assert htmlkit.missing_facts(panel.root, want) == []


def test_version_1_with_compare_shows_the_steps_and_no_earlier_version(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(
        world.web("bob").client.get(PAGE, params={"version": "1", "compare": "1"}).text
    )
    assert doc.headers("log-table") == list(PATH_COLUMNS)
    assert doc.rows("log-table") == [
        list(present.path_text.path_cells(line)) for line in lines_of(fakes, 1)
    ]
    assert doc.status() == "No earlier version"


@pytest.mark.parametrize("raw", ["0", "abc", "-1", "", "9" * 5000, "0" * 5000])
def test_a_bad_version_is_the_current_version(
    world: Any, htmlkit: Any, fakes: Any, raw: str
) -> None:
    bob = world.web("bob").client
    response = bob.get(PAGE, params={"version": raw})
    assert response.status_code == 200
    asked = htmlkit.parse(response.text)
    current = htmlkit.parse(bob.get(PAGE).text)
    assert asked.status() == current.status() == present.layout.join_facts("2 steps", "version 2")
    assert asked.rows("log-table") == current.rows("log-table")


def test_an_unheld_version_is_the_one_404(world: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    response = bob.get(PAGE, params={"version": "99"})
    assert response.status_code == 404


def test_the_panel_of_the_compare_row_is_the_version_it_compares(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    """The compare page's panel holds version 2 and the comparison flag, as the page does."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(COMPARE_PAGE).text)
    link = row_panel_link(doc, "A1")
    assert "version=2" in link and "compare=1" in link
    want = panel_page(fakes, 2, step_of(fakes, 2, "A1"), previous=1)
    assert htmlkit.missing_facts(htmlkit.parse(row_panel(bob, doc, "A1")).root, want) == []


def test_a_real_world_without_a_path_is_an_empty_register(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no path, so the table and the summary are empty, any panel is a 404,
    and an asked version is a 404 (it is not held)."""
    bob = world.web("bob").client
    page = bob.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.rows("log-table") == []
    assert doc.status() == ""
    assert bob.get(f"{PAGE}/panel/1").status_code == 404
    assert bob.get(PAGE, params={"version": "1"}).status_code == 404


def test_the_screenshot_of_the_steps_is_saved(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, "T16-path.png")
    assert path.exists()


def test_the_screenshot_of_the_comparison_is_saved(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, COMPARE_PAGE, "T16-path-compare.png")
    assert path.exists()
