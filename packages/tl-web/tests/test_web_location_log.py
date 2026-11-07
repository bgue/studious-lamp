"""The locations page: ``GET /web/p/{project}/locations`` (P2-WEB1-T14b, the recipe of ``TWINS.md``
and ``M4-TWINS.md``).

The reads of the page are the tl-tui materials fake, seeded by ``seed_materials`` (T17) and loaded
by path, patched over the two mirrors the page reads (``list_materials_locations`` and
``list_materials_stock``). The seed has four locations in a tree: the store ``WH`` (no stock of its
own), the bays ``WH-A`` (pipe stock) and ``WH-B`` (pipe and weld stock), and the bin ``WH-A-1``
under ``WH-A`` (bolt stock). The seed has no leaf without stock, so the empty note of a leaf is
tested with the stock read of ``WH-B`` narrowed to nothing. The real world is read once, unpatched,
at the end.
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

PAGE = "/web/p/P123/locations"
PROJECT = "P123"
COLUMNS = present.location_text.LOCATION_COLUMNS
REPO = Path(__file__).resolve().parents[3]
SHOT = "T14b-locations.png"
ROOT, BAY_A, BIN, BAY_B = "WH", "WH-A", "WH-A-1", "WH-B"
LIMIT = 500

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


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_fake() -> Any:
    base = REPO / "packages/tl-tui/tests"
    fake_mod = _load("tl_web_tests_fakes_materials", base / "fakes_materials.py")
    seed_mod = _load("tl_web_tests_fakes_materials_seed", base / "fakes_materials_seed.py")
    fake = fake_mod.FakeMaterialsSupport()
    fake._init_materials()
    seed_mod.seed_materials(fake, PROJECT)
    return fake


@pytest.fixture
def fakes() -> Iterator[Any]:
    fake = load_fake()

    def list_materials_locations(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_materials_locations(project, **kwargs)

    def list_materials_stock(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_materials_stock(project, **kwargs)

    with (
        mock.patch.object(WebReadClient, "list_materials_locations", list_materials_locations),
        mock.patch.object(WebReadClient, "list_materials_stock", list_materials_stock),
    ):
        yield fake


def locations_of(fake: Any) -> list[Any]:
    return fake.list_materials_locations(PROJECT, limit=LIMIT)


def cells_of(fake: Any, code: str) -> tuple[str, ...]:
    row = next(loc for loc in locations_of(fake) if loc.code == code)
    return present.location_text.row_cells(row, COLUMNS)


def expected_panel(fake: Any, code: str) -> present.Page:
    locations = locations_of(fake)
    row = next(loc for loc in locations if loc.code == code)
    stock = fake.list_materials_stock(PROJECT, location=code, limit=LIMIT)
    page = present.location_text.location_page(
        row, locations, stock, present.Labels(), technical=False
    )
    return page


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.locations as locations

    assert any(r is locations.router for r in routers.page_routers())
    assert LOGS["locations"].SLUG == "locations"


def test_regions_headers_and_cells_equal_the_text_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    headers = doc.headers("log-table")
    assert headers == list(COLUMNS)
    full = [present.location_text.row_cells(row, COLUMNS) for row in locations_of(fakes)]
    assert doc.rows("log-table") == htmlkit.project_cells(headers, COLUMNS, full)
    assert [r.get("data-number") for r in doc.log_rows()] == [
        loc.code for loc in locations_of(fakes)
    ]


def test_a_child_location_carries_its_depth_as_indent_in_the_subject(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    """The cells are the module's: the Subject of a depth-2 bin starts with four spaces (two per
    depth). The browser collapses them; the text does not, so the page keeps the module's words."""
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    subject = doc.headers("log-table").index("Subject")
    by_code = {row[0]: row for row in doc.rows("log-table")}
    assert by_code[BIN][subject] == cells_of(fakes, BIN)[subject] == "    Bin A-1"
    assert by_code[ROOT][subject] == cells_of(fakes, ROOT)[subject] == "Site store"


def test_the_panel_of_a_bay_is_the_terminal_location_page(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{BAY_A}")
    assert panel.status_code == 200
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, expected_panel(fakes, BAY_A)) == []


def test_the_panel_of_the_root_lists_its_children(world: Any, htmlkit: Any, fakes: Any) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{ROOT}")
    assert panel.status_code == 200
    root = htmlkit.parse(panel.text).root
    page = expected_panel(fakes, ROOT)
    assert htmlkit.missing_facts(root, page) == []
    assert "Children" in htmlkit.page_facts(page)
    shown = htmlkit.visible(root)
    assert BAY_A in shown and "Bay A" in shown
    assert BAY_B in shown and "Bay B" in shown
    assert "No stock here" in htmlkit.page_facts(page)


def test_the_panel_of_a_leaf_with_stock_lists_its_contents(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{BAY_B}")
    assert panel.status_code == 200
    root = htmlkit.parse(panel.text).root
    assert htmlkit.missing_facts(root, expected_panel(fakes, BAY_B)) == []
    shown = htmlkit.visible(root)
    assert "Lot" in shown and "Item" in shown and "On hand" in shown
    assert "H4471" in shown and "PIPE-6S" in shown
    assert "E7018-26B" in shown and "WELD-E7018" in shown
    assert "No child locations" in shown


def test_the_panel_of_a_leaf_with_no_stock_shows_the_empty_note(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    def no_stock(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return []

    with mock.patch.object(WebReadClient, "list_materials_stock", no_stock):
        panel = world.web("bob").client.get(f"{PAGE}/panel/{BAY_B}")
    assert panel.status_code == 200
    root = htmlkit.parse(panel.text).root
    assert "No stock here" in htmlkit.visible(root)
    assert "Lot" not in [th.text() for th in root.find_all("th")]


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.status() == present.location_text.summary_line(4, 4, text="")
    assert doc.status() == "Showing 4 of 4 locations"


def test_the_filter_keeps_the_matching_row_and_an_unknown_number_is_a_404(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "Bin A-1"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == [BIN]
    one, two = bob.get(f"{PAGE}/panel/NOPE-0000"), bob.get(f"{PAGE}/panel/NOPE-0001")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_is_not_found_is_the_same_404_as_an_unknown_number(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    def hidden(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        if kwargs.get("location") == BAY_A:
            raise RecordNotFoundError("hidden")
        return fakes.list_materials_stock(project, **kwargs)

    with mock.patch.object(WebReadClient, "list_materials_stock", hidden):
        bob = world.web("bob").client
        gone = bob.get(f"{PAGE}/panel/{BAY_A}")
        unknown = bob.get(f"{PAGE}/panel/NOPE-0000")
    assert gone.status_code == unknown.status_code == 404
    assert gone.content == unknown.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: Any) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_no_record_page_so_no_open_link_and_no_data_open(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is None
    assert all(r.get("data-open") == "" for r in doc.log_rows())


def test_plain_viewer_asking_for_technical_gets_the_refusal_and_the_plain_panel(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"mode": "technical"}).text)
    assert doc.status() == present.REFUSAL
    assert htmlkit.missing_facts(doc.by_id("log-panel"), expected_panel(fakes, ROOT)) == []


def test_admin_asking_for_technical_gets_the_location_id_the_plain_panel_lacks(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    """The location panel has a technical-only section (the location id, Location): case (i)
    applies."""
    doc = htmlkit.parse(world.web("boss").client.get(PAGE, params={"mode": "technical"}).text)
    shown = doc.by_id("log-panel")
    locations = locations_of(fakes)
    row = next(loc for loc in locations if loc.code == ROOT)
    stock = fakes.list_materials_stock(PROJECT, location=ROOT, limit=LIMIT)
    technical = present.location_text.location_page(
        row, locations, stock, present.Labels(), technical=True
    )
    assert htmlkit.missing_facts(shown, technical) == []
    plain = expected_panel(fakes, ROOT)
    assert htmlkit.page_facts(technical) != htmlkit.page_facts(plain)
    assert row.id in htmlkit.visible(shown)


def test_the_real_world_has_no_locations_and_no_panel(world: Any, htmlkit: Any) -> None:
    """No patch: the world carries no locations for P123 in this harness, so the table is empty."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    assert doc.status() == "Showing 0 of 0 locations"
    assert doc.rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/{ROOT}").status_code == 404


def test_the_locations_page_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, SHOT)
    assert path.exists()
