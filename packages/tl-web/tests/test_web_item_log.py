"""The item library page, ``GET /web/p/{project}/items`` (P2-WEB1-T14, M4 twin of the library).

The materials reads of the page are patched with ``mock.patch.object(WebReadClient, ...)`` and
answered by the tl-tui materials fake seeded by ``seed_materials`` (P2-WEB1-T17), both loaded by
path. The screenshot is taken with the fake on (``shoot``, copied from
``docs/tickets/P2-WEB1/provided/shot_recipe.py``).
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
from types import ModuleType
from typing import Any
from unittest import mock

import pytest
import uvicorn
from tl_mod_materials.errors import ItemNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PROJECT = "P123"
PAGE = "/web/p/P123/items"
SCOPE = "project:P123"
COLUMNS = present.item_text.ITEM_COLUMNS
PIPE, VALVE = "PIPE-6S", "VLV-GATE-4"

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


def _load(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_fake() -> Any:
    base = "packages/tl-tui/tests"
    fake_mod = _load("tl_web_tests_fakes_materials", f"{base}/fakes_materials.py")
    seed_mod = _load("tl_web_tests_fakes_materials_seed", f"{base}/fakes_materials_seed.py")
    fake = fake_mod.FakeMaterialsSupport()
    fake._init_materials()
    seed_mod.seed_materials(fake, PROJECT)
    return fake


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(present.as_client(w.reads(name)), SCOPE, ("core.Record",))


def expected_panel(fake: Any, labels: Any, code: str, *, technical: bool = False) -> present.Page:
    item = next(v for v in fake.list_materials_items(project=PROJECT) if v.code == code)
    projects = fake.list_materials_item_projects(code)
    return present.item_text.item_page(item, projects, labels, technical=technical)


@pytest.fixture
def fakes() -> Iterator[Any]:
    fake = load_fake()

    def list_materials_items(self: WebReadClient, **kwargs: Any) -> Any:
        return fake.list_materials_items(**kwargs)

    def list_materials_item_projects(self: WebReadClient, code: str) -> Any:
        return fake.list_materials_item_projects(code)

    with (
        mock.patch.object(WebReadClient, "list_materials_items", list_materials_items),
        mock.patch.object(
            WebReadClient, "list_materials_item_projects", list_materials_item_projects
        ),
    ):
        yield fake


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.items as items

    assert any(r is items.router for r in routers.page_routers())
    assert LOGS["items"].SLUG == "items"


def test_regions_headers_and_cells_equal_the_terminal_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table") == list(COLUMNS)
    labels = labels_for(world, "bob")
    rows = fakes.list_materials_items(project=PROJECT)
    full = [present.item_text.row_cells(r, COLUMNS, labels, technical=False) for r in rows]
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), COLUMNS, full)
    # the terminal's rows pass no labels: the category cell is the same either way
    bare = [present.item_text.row_cells(r, COLUMNS, technical=False) for r in rows]
    assert full == bare


def test_the_panel_lines_are_the_item_page(world: Any, htmlkit: Any, fakes: Any) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{PIPE}")
    assert panel.status_code == 200
    want = expected_panel(fakes, labels_for(world, "bob"), PIPE)
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, want) == []


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    want = present.item_text.summary_line(4, 4, state=None, project=PROJECT, text="")
    assert doc.status() == want


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "BOLT-M20"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["BOLT-M20"]
    one, two = bob.get(f"{PAGE}/panel/ITEM-9999"), bob.get(f"{PAGE}/panel/ITEM-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_finds_no_item_is_the_same_404(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    unknown = bob.get(f"{PAGE}/panel/ITEM-9999")

    def projects_missing(self: WebReadClient, code: str) -> Any:
        if code == "BOLT-M20":
            raise ItemNotFoundError(code)
        return fakes.list_materials_item_projects(code)

    with mock.patch.object(WebReadClient, "list_materials_item_projects", projects_missing):
        hidden = bob.get(f"{PAGE}/panel/BOLT-M20")
    assert hidden.status_code == 404 and hidden.content == unknown.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: Any) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_no_buttons_and_no_open_link(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is None
    assert all(r.get("data-open") == "" for r in doc.log_rows())


def test_plain_versus_technical(world: Any, htmlkit: Any, fakes: Any) -> None:
    labels = labels_for(world, "bob")
    plain = htmlkit.parse(world.web("bob").client.get(PAGE, params={"mode": "technical"}).text)
    assert plain.status() == present.REFUSAL
    assert (
        htmlkit.missing_facts(plain.by_id("log-panel"), expected_panel(fakes, labels, PIPE)) == []
    )

    boss = htmlkit.parse(world.web("boss").client.get(PAGE, params={"mode": "technical"}).text)
    assert boss.status() != present.REFUSAL
    shown = boss.by_id("log-panel")
    assert htmlkit.missing_facts(shown, expected_panel(fakes, labels, PIPE, technical=True)) == []
    plain_page = expected_panel(fakes, labels, PIPE)
    assert htmlkit.page_facts(expected_panel(fakes, labels, PIPE, technical=True)) != (
        htmlkit.page_facts(plain_page)
    )
    assert "ITM-1" in htmlkit.visible(shown)


def test_retired_keeps_the_retired_item_and_an_unknown_state_is_ignored(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    retired = htmlkit.parse(bob.get(PAGE, params={"state": "Retired"}).text)
    assert [r.get("data-number") for r in retired.log_rows()] == [VALVE]
    assert retired.status() == present.item_text.summary_line(
        1, 4, state="Retired", project=PROJECT, text=""
    )
    anything = htmlkit.parse(bob.get(PAGE, params={"state": "zzz"}).text)
    assert len(anything.log_rows()) == 4


def test_the_panel_lists_the_projects_with_their_quantities(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    panel = htmlkit.parse(bob.get(f"{PAGE}/panel/{PIPE}").text).root
    page = expected_panel(fakes, labels_for(world, "bob"), PIPE)
    assert htmlkit.missing_facts(panel, page) == []
    assert any("Project" in fact for fact in htmlkit.page_facts(page))
    # quantities are the module's qty_text (no trailing zeros): 15.500 shows as 15.5
    rows = [[td.text() for td in tr.find_all("td")] for tr in panel.find_all("tr")]
    assert [PROJECT, "15.5", "4.25", "11.25"] in rows
    assert ["P456", "30", "0", "30"] in rows
    assert "Not used in any project" not in htmlkit.visible(panel)


def test_an_item_used_in_no_project_says_so(world: Any, htmlkit: Any, fakes: Any) -> None:
    panel = htmlkit.parse(world.web("bob").client.get(f"{PAGE}/panel/{VALVE}").text).root
    page = expected_panel(fakes, labels_for(world, "bob"), VALVE)
    assert "Not used in any project" in htmlkit.page_facts(page)
    assert htmlkit.missing_facts(panel, page) == []


def test_the_real_world_answers_with_an_empty_table_and_404_panels(
    world: Any, htmlkit: Any
) -> None:
    bob = world.web("bob").client
    page = bob.get(PAGE)
    assert page.status_code == 200
    assert htmlkit.parse(page.text).rows("log-table") == []
    unknown = bob.get(f"{PAGE}/panel/ITEM-9999")
    assert unknown.status_code == 404
    assert bob.get(f"{PAGE}/panel/{PIPE}").content == unknown.content


def test_the_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, "T14-items.png")
    assert path.exists()
