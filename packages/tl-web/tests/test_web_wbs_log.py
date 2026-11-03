"""The WBS tree page: ``GET /web/p/{project}/wbs`` (P2-WEB1-T10, the recipe of ``TWINS.md``).

The reads of the page are the tl-tui fake of the awp reads, loaded by path and patched over the two
WBS mirrors. The fake holds three nodes, 1 / 1.1 / 1.2: node 1 is a parent, 1.1 a leaf with a cost
code, 1.2 a leaf with none (the one unallocated leaf). Case (i) has no technical-only row on this
page, so only the REFUSAL part applies; the admin's technical view is not tested. The real world is
read once, unpatched, at the end.
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
from tl_core.services.errors import RecordNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

PAGE = "/web/p/P123/wbs"
PROJECT = "P123"
COLUMNS = present.wbs_text.WBS_COLUMNS
REPO = Path(__file__).resolve().parents[3]
SHOT = "T10-wbs.png"

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

    def wbs_tree(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.wbs_tree(project, **kwargs)

    def get_wbs_node(self: WebReadClient, project: str, code: str) -> Any:
        return fake.get_wbs_node(project, code)

    with (
        mock.patch.object(WebReadClient, "wbs_tree", wbs_tree),
        mock.patch.object(WebReadClient, "get_wbs_node", get_wbs_node),
    ):
        yield fake


def tree_of(fake: Any) -> list[Any]:
    return fake.wbs_tree(PROJECT)


def expected_panel(fake: Any, code: str) -> list[str]:
    tree = tree_of(fake)
    node = fake.get_wbs_node(PROJECT, code)
    return present.plain_lines(present.wbs_text.wbs_page(node, tree, panel=True, technical=False))


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.wbs as wbs

    assert any(r is wbs.router for r in routers.page_routers())
    assert LOGS["wbs"].SLUG == "wbs"


def test_seven_regions_and_the_cells_equal_the_text_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    headers = doc.headers("log-table")
    assert headers[:2] == ["Number", "Subject"]
    full = [present.wbs_text.wbs_cells(row, tree_of(fakes)) for row in tree_of(fakes)]
    assert doc.rows("log-table") == htmlkit.project_cells(headers, COLUMNS, full)


def test_the_panel_of_a_dotted_code_is_the_terminal_page(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/1.1")
    assert panel.status_code == 200
    assert htmlkit.parse(panel.text).pre().split("\n") == expected_panel(fakes, "1.1")


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.status() == "3 of 3 nodes"


def test_the_filter_keeps_the_matching_row_and_an_unknown_number_is_a_404(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "Piping"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["1.1"]
    one, two = bob.get(f"{PAGE}/panel/9.9"), bob.get(f"{PAGE}/panel/9.8")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_is_not_found_is_the_same_404_as_an_unknown_number(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    def hidden(self: WebReadClient, project: str, code: str) -> Any:
        if code == "1.1":
            raise RecordNotFoundError("hidden")
        return fakes.get_wbs_node(project, code)

    with mock.patch.object(WebReadClient, "get_wbs_node", hidden):
        bob = world.web("bob").client
        gone = bob.get(f"{PAGE}/panel/1.1")
        unknown = bob.get(f"{PAGE}/panel/9.9")
    assert gone.status_code == unknown.status_code == 404
    assert gone.content == unknown.content


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
    assert doc.pre("log-panel").split("\n") == expected_panel(fakes, "1")


def test_depth_one_leaves_one_row_and_the_status_says_depth(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"depth": "1"}).text)
    assert [r.get("data-number") for r in doc.log_rows()] == ["1"]
    assert doc.status() == "1 of 3 nodes · depth 1"


def test_unallocated_equals_the_text_module_unallocated_leaves(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"unallocated": "1"}).text)
    want = present.wbs_text.unallocated_leaves(tree_of(fakes))
    assert [r.get("data-number") for r in doc.log_rows()] == [node.code for node in want]
    assert [node.code for node in want] == ["1.2"]
    assert doc.status() == "1 of 3 nodes · unallocated leaves"


@pytest.mark.parametrize("value", ["abc", "99", "9" * 5000])
def test_a_bad_depth_is_as_if_absent(world: Any, htmlkit: Any, fakes: Any, value: str) -> None:
    bob = world.web("bob").client
    plain = htmlkit.parse(bob.get(PAGE).text)
    response = bob.get(PAGE, params={"depth": value})
    assert response.status_code == 200
    cut = htmlkit.parse(response.text)
    assert cut.rows("log-table") == plain.rows("log-table")
    assert len(cut.log_rows()) == 3
    assert cut.status() == "3 of 3 nodes"


def test_the_real_world_has_an_empty_tree_and_no_panel(world: Any, htmlkit: Any) -> None:
    """No patch: the world carries no WBS for P123 in this harness, so the table is empty."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    assert doc.status() == "0 of 0 nodes"
    assert doc.rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/1").status_code == 404


def test_the_tree_page_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, SHOT)
    assert path.exists()
