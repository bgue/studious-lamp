"""The stock page: ``GET /web/p/{project}/stock`` (P2-WEB1-T12, the recipe of ``TWINS.md`` and
``M4-TWINS.md``).

The reads of the page are the tl-tui materials fake, seeded by ``seed_materials`` (T17) and loaded
by path, patched over the mirrors the page reads (``list_materials_stock``, ``get_materials_lot``,
``get_materials_receipt``). The seed has four stock rows over three lots: ``PL-4471`` in two
locations (receipt RCV-0001, MTR file ``MTR-H4471.pdf``), ``BL/26-07`` with no heat in the bin
``WH-A-1`` (receipt RCV-0001 as well), and ``WE-2601`` in ``WH-B`` with no receipt. The real world
is read once, unpatched, at the end.
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
from tl_mod_materials.errors import ReceiptNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

PAGE = "/web/p/P123/stock"
PROJECT = "P123"
COLUMNS = present.materials_text.STOCK_COLUMNS
REPO = Path(__file__).resolve().parents[3]
SHOT = "T12-stock.png"
MTR = "MTR-H4471.pdf"  # the MTR file of receipt RCV-0001 (slot mtr)

PIPE_A = "PL-4471@WH-A"
PIPE_B = "PL-4471@WH-B"
BOLT = "BL/26-07@WH-A-1"
WELD = "WE-2601@WH-B"
ALL_KEYS = [PIPE_A, PIPE_B, BOLT, WELD]

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

    def list_materials_stock(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_materials_stock(project, **kwargs)

    def get_materials_lot(self: WebReadClient, project: str, key: str) -> Any:
        return fake.get_materials_lot(project, key)

    def get_materials_receipt(self: WebReadClient, project: str, number: str) -> Any:
        return fake.get_materials_receipt(project, number)

    with (
        mock.patch.object(WebReadClient, "list_materials_stock", list_materials_stock),
        mock.patch.object(WebReadClient, "get_materials_lot", get_materials_lot),
        mock.patch.object(WebReadClient, "get_materials_receipt", get_materials_receipt),
    ):
        yield fake


def stock_of(fake: Any, **filters: Any) -> list[Any]:
    return fake.list_materials_stock(PROJECT, limit=500, **filters)


def row_of(fake: Any, key: str) -> Any:
    return next(r for r in stock_of(fake) if f"{r.lot}@{r.location}" == key)


def expected_panel(fake: Any, key: str, mtr: str | None) -> present.Page:
    row = row_of(fake, key)
    detail = fake.get_materials_lot(PROJECT, row.lot)
    return present.materials_text.lot_page(detail, row, present.Labels(), mtr=mtr, technical=False)


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.stock as stock

    assert any(r is stock.router for r in routers.page_routers())
    assert LOGS["stock"].SLUG == "stock"


def test_regions_headers_and_cells_equal_the_text_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    headers = doc.headers("log-table")
    assert headers == list(COLUMNS)
    full = [present.materials_text.stock_cells(row, COLUMNS) for row in stock_of(fakes)]
    assert doc.rows("log-table") == htmlkit.project_cells(headers, COLUMNS, full)
    assert [r.get("data-number") for r in doc.log_rows()] == ALL_KEYS


def test_the_panel_of_the_first_row_is_the_terminal_lot_page(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{PIPE_A}")
    assert panel.status_code == 200
    assert (
        htmlkit.missing_facts(htmlkit.parse(panel.text).root, expected_panel(fakes, PIPE_A, MTR))
        == []
    )


def test_on_the_web_location_never_drops_and_uom_may(world: Any, htmlkit: Any, fakes: Any) -> None:
    """Two lots of one heat in two bays stay told apart: only UOM may be hidden on the web."""
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    heads = {th.text(): th.get("class").split() for th in doc.by_id("log-table").find_all("th")}
    assert "tl-drop" not in heads["Location"]
    assert "tl-drop" in heads["UOM"]


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.status() == "Showing 4 of 4 stock rows"


def test_the_filter_keeps_the_matching_row_and_an_unknown_number_is_a_404(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "Hex bolt"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == [BOLT]
    one = bob.get(f"{PAGE}/panel/NOPE-0000@WH-A")
    two = bob.get(f"{PAGE}/panel/NOPE-0001@WH-A")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_is_not_found_is_the_same_404_as_an_unknown_number(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    def hidden(self: WebReadClient, project: str, key: str) -> Any:
        if key == "PL-4471":
            raise RecordNotFoundError("hidden")
        return fakes.get_materials_lot(project, key)

    with mock.patch.object(WebReadClient, "get_materials_lot", hidden):
        bob = world.web("bob").client
        gone = bob.get(f"{PAGE}/panel/{PIPE_A}")
        unknown = bob.get(f"{PAGE}/panel/NOPE-0000@WH-A")
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
    assert htmlkit.missing_facts(doc.by_id("log-panel"), expected_panel(fakes, PIPE_A, MTR)) == []


def test_admin_asking_for_technical_gets_the_lot_id_the_plain_panel_lacks(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    """The lot panel has a technical-only row (the lot id under Traceability): case (i) applies."""
    doc = htmlkit.parse(world.web("boss").client.get(PAGE, params={"mode": "technical"}).text)
    shown = doc.by_id("log-panel")
    row = row_of(fakes, PIPE_A)
    detail = fakes.get_materials_lot(PROJECT, row.lot)
    technical = present.materials_text.lot_page(
        detail, row, present.Labels(), mtr=MTR, technical=True
    )
    assert htmlkit.missing_facts(shown, technical) == []
    plain = expected_panel(fakes, PIPE_A, MTR)
    assert htmlkit.page_facts(technical) != htmlkit.page_facts(plain)
    assert detail.id in htmlkit.visible(shown)


def test_each_filter_keeps_the_matching_rows(world: Any, htmlkit: Any, fakes: Any) -> None:
    cases: list[tuple[dict[str, str], list[str]]] = [
        ({"item": "PIPE-6S"}, [PIPE_A, PIPE_B]),
        ({"lot": "WE-2601"}, [WELD]),
        ({"heat": "E7018-26B"}, [WELD]),
        ({"location": "WH-B"}, [PIPE_B, WELD]),
        ({"location": "WH", "subtree": "1"}, ALL_KEYS),
        ({"location": "WH"}, []),
        ({"location": "NOPE"}, []),
    ]
    bob = world.web("bob").client
    for params, keys in cases:
        doc = htmlkit.parse(bob.get(PAGE, params=params).text)
        assert [r.get("data-number") for r in doc.log_rows()] == keys, params
        want = stock_of(fakes, **_fake_filters(params))
        assert [f"{r.lot}@{r.location}" for r in want] == keys, params


def _fake_filters(params: dict[str, str]) -> dict[str, Any]:
    location = params.get("location")
    return {
        "lot": params.get("lot"),
        "item": params.get("item"),
        "heat": params.get("heat"),
        "location": location,
        "subtree": location is not None and params.get("subtree") == "1",
    }


def test_the_summary_names_the_filters(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE, params={"location": "WH", "subtree": "1"}).text)
    assert doc.status() == "Showing 4 of 4 stock rows · location WH and below"
    doc = htmlkit.parse(bob.get(PAGE, params={"lot": "WE-2601", "heat": "E7018-26B"}).text)
    assert doc.status() == "Showing 1 of 1 stock rows · heat E7018-26B · lot WE-2601"


def test_subtree_without_a_location_is_ignored(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    plain = htmlkit.parse(bob.get(PAGE).text)
    cut = htmlkit.parse(bob.get(PAGE, params={"subtree": "1"}).text)
    assert cut.rows("log-table") == plain.rows("log-table")
    assert cut.status() == "Showing 4 of 4 stock rows"


def test_an_overlong_text_filter_is_as_if_absent(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    cut = htmlkit.parse(bob.get(PAGE, params={"lot": "X" * 201}).text)
    assert cut.status() == "Showing 4 of 4 stock rows"
    assert [r.get("data-number") for r in cut.log_rows()] == ALL_KEYS


def test_a_lot_with_no_heat_shows_its_lot_key_and_its_panel(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    headers = doc.headers("log-table")
    lot_cell = [row for row in doc.rows("log-table") if row[headers.index("Lot")] == "BL/26-07"]
    assert len(lot_cell) == 1
    panel = bob.get(f"{PAGE}/panel/{BOLT}")
    assert panel.status_code == 200
    assert (
        htmlkit.missing_facts(htmlkit.parse(panel.text).root, expected_panel(fakes, BOLT, MTR))
        == []
    )


def test_the_panel_of_a_lot_whose_receipt_is_not_found_shows_no_mtr(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    def gone(self: WebReadClient, project: str, number: str) -> Any:
        raise ReceiptNotFoundError(number)

    with mock.patch.object(WebReadClient, "get_materials_receipt", gone):
        panel = world.web("bob").client.get(f"{PAGE}/panel/{PIPE_A}")
    assert panel.status_code == 200
    assert MTR not in panel.text
    assert (
        htmlkit.missing_facts(htmlkit.parse(panel.text).root, expected_panel(fakes, PIPE_A, None))
        == []
    )


def test_the_panel_of_a_lot_with_a_slash_in_its_key(world: Any, htmlkit: Any, fakes: Any) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/{BOLT}")
    assert panel.status_code == 200
    assert (
        htmlkit.missing_facts(htmlkit.parse(panel.text).root, expected_panel(fakes, BOLT, MTR))
        == []
    )


def test_the_real_world_has_no_stock_and_no_panel(world: Any, htmlkit: Any) -> None:
    """No patch: the world carries no stock for P123 in this harness, so the table is empty."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    assert doc.status() == "Showing 0 of 0 stock rows"
    assert doc.rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/{PIPE_A}").status_code == 404


def test_the_stock_page_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, SHOT)
    assert path.exists()


def test_the_lot_line_is_the_panel_summary_and_not_a_badge(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    """P2-WEB1-T23: the web shows "Lot … · receipt …" in the summary; no grey badge carries it."""
    doc = htmlkit.parse(world.web("bob").client.get(f"{PAGE}/panel/{PIPE_A}").text)
    badges = [n.text() for n in doc.all() if "tl-badge" in n.get("class").split()]
    summaries = [n.text() for n in doc.all() if "tl-summary" in n.get("class").split()]
    assert not any(b.startswith("Lot ") for b in badges)
    assert any(s.startswith("Lot PL-4471 · receipt RCV-0001") for s in summaries)
