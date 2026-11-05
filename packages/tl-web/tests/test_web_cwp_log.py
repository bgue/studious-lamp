"""The CWP register page: ``GET /web/p/{project}/cwps`` (P2-WEB1-T09, the recipe of TWINS.md).

The reads of the page are patched with ``mock.patch.object(WebReadClient, ...)`` and the tl-tui fake
of the awp reads (3 CWPs, 2 CWAs, WBS, path, one EWP, one PWP; project P123). The real, unpatched
world is read once at the end. The screenshot step copies ``shoot`` from the provided recipe.
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

REPO = Path(__file__).resolve().parents[3]
PAGE = "/web/p/P123/cwps"
SCOPE = "project:P123"
SHOTS = Path("/home/user/wt/p2-web1/.accept/shots")  # one place for every worktree


def load_fake() -> Any:  # 3 CWPs, 2 CWAs (A2 retired), WBS 1 / 1.1 / 1.2, path v1 v2, EWP, PWP
    spec = importlib.util.spec_from_file_location(
        "tl_web_tests_fakes_awp", REPO / "packages/tl-tui/tests/fakes_awp.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fake = mod.FakeAwpSupport()
    fake._init_awp()
    mod.seed_awp(fake, "P123")
    return fake


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(present.as_client(w.reads(name)), SCOPE, ("awp.CWP",))


@pytest.fixture(scope="module")
def fake() -> Any:
    return load_fake()


@pytest.fixture
def fakes(fake: Any) -> Iterator[None]:
    def list_cwps(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_cwps(project, **kwargs)

    def get_cwp(self: WebReadClient, project: str, number: str) -> Any:
        return fake.get_cwp(project, number)

    with (
        mock.patch.object(WebReadClient, "list_cwps", list_cwps),
        mock.patch.object(WebReadClient, "get_cwp", get_cwp),
    ):
        yield


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.cwps as cwps

    assert any(r is cwps.router for r in routers.page_routers())
    assert LOGS["cwps"].SLUG == "cwps"


def test_seven_regions_and_the_cells_equal_the_text_module(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == ["Number", "Subject", "State"]
    labels = labels_for(world, "bob")
    rows = fake.list_cwps("P123")
    full = [present.awp_text.cwp_cells(row, labels) for row in rows]
    assert len(rows) == 3
    assert doc.rows("log-table") == htmlkit.project_cells(
        doc.headers("log-table"), present.awp_text.CWP_COLUMNS, full
    )


def test_the_panel_of_one_cwp_is_the_cwp_page_as_plain_lines(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    number = fake.list_cwps("P123")[0].number
    panel = world.web("bob").client.get(f"{PAGE}/panel/{number}")
    assert panel.status_code == 200
    want = present.awp_text.cwp_page(
        fake.get_cwp("P123", number), labels_for(world, "bob"), technical=False, panel=True
    )
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, want) == []


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: None) -> None:
    assert htmlkit.parse(world.web("bob").client.get(PAGE).text).status() == "3 CWPs"


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fake: Any, fakes: None) -> None:
    bob = world.web("bob").client
    number = fake.list_cwps("P123")[1].number
    found = htmlkit.parse(bob.get(PAGE, params={"q": number}).text)
    assert [r.get("data-number") for r in found.log_rows()] == [number]
    one = bob.get(f"{PAGE}/panel/P123-CWP-9999")
    two = bob.get(f"{PAGE}/panel/P123-CWP-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_says_not_found_is_the_same_404(
    world: Any, htmlkit: Any, fake: Any, fakes: None
) -> None:
    listed = fake.list_cwps("P123")[2].number

    def get_cwp(self: WebReadClient, project: str, number: str) -> Any:
        if number == listed:
            raise RecordNotFoundError(f"no CWP {number!r}")
        return fake.get_cwp(project, number)

    bob = world.web("bob").client
    with mock.patch.object(WebReadClient, "get_cwp", get_cwp):
        hidden = bob.get(f"{PAGE}/panel/{listed}")
    unknown = bob.get(f"{PAGE}/panel/P123-CWP-9999")
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.content == unknown.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_only_the_open_link(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is not None
    assert "data-command" not in bar.text()


def test_the_real_world_has_an_empty_register(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no CWPs, so the table is empty and any panel is a 404."""
    bob = world.web("bob").client
    page = htmlkit.parse(bob.get(PAGE).text)
    assert page.log_rows() == []
    missing = bob.get(f"{PAGE}/panel/P123-CWP-0001")
    assert missing.status_code == 404
    assert missing.content == bob.get(f"{PAGE}/panel/P123-CWP-9999").content


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


def test_the_screenshot_of_the_register(world: Any, fakes: None) -> None:
    out = shoot(world.app, world.web("bob").token, PAGE, "T09-cwps.png")
    assert out.exists()
