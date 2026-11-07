"""The receipts log page, ``GET /web/p/{project}/receipts`` (P2-WEB1-T13, M4 twin of the log).

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
from tl_mod_materials import views
from tl_mod_materials.errors import ReceiptNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PROJECT = "P123"
PAGE = "/web/p/P123/receipts"
SCOPE = "project:P123"
COLUMNS = present.receipt_text.RECEIPT_COLUMNS
MTR_LINE = present.receipt_text.MTR_NOTE

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


def expected_page(fake: Any, labels: Any, number: str, *, technical: bool = False) -> Any:
    detail = fake.get_materials_receipt(PROJECT, number)
    return present.receipt_text.receipt_page(detail, labels, technical=technical)


@pytest.fixture
def fakes() -> Iterator[Any]:
    fake = load_fake()

    def list_materials_receipts(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_materials_receipts(project, **kwargs)

    def get_materials_receipt(self: WebReadClient, project: str, number: str) -> Any:
        return fake.get_materials_receipt(project, number)

    with (
        mock.patch.object(WebReadClient, "list_materials_receipts", list_materials_receipts),
        mock.patch.object(WebReadClient, "get_materials_receipt", get_materials_receipt),
    ):
        yield fake


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.receipts as receipts

    assert any(r is receipts.router for r in routers.page_routers())
    assert LOGS["receipts"].SLUG == "receipts"


def test_regions_headers_and_cells_equal_the_terminal_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table") == list(COLUMNS)
    labels = labels_for(world, "bob")
    rows = fakes.list_materials_receipts(PROJECT)
    full = [present.receipt_text.row_cells(r, COLUMNS, labels, technical=False) for r in rows]
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), COLUMNS, full)


def test_the_panel_lines_are_the_receipt_page(world: Any, htmlkit: Any, fakes: Any) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/RCV-0001")
    assert panel.status_code == 200
    want = expected_page(fakes, labels_for(world, "bob"), "RCV-0001")
    assert htmlkit.parse(panel.text).pre() == ""  # no terminal text: the page is HTML
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, want) == []


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.status() == present.receipt_text.summary_line(3, 3, text="")


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "RCV-0002"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["RCV-0002"]
    one, two = bob.get(f"{PAGE}/panel/RCV-9999"), bob.get(f"{PAGE}/panel/RCV-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_finds_no_receipt_is_the_same_404(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    unknown = bob.get(f"{PAGE}/panel/RCV-9999")

    def get_missing(self: WebReadClient, project: str, number: str) -> Any:
        if number == "RCV-0002":
            raise ReceiptNotFoundError(number)
        return fakes.get_materials_receipt(project, number)

    with mock.patch.object(WebReadClient, "get_materials_receipt", get_missing):
        hidden = bob.get(f"{PAGE}/panel/RCV-0002")
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
        htmlkit.missing_facts(plain.by_id("log-panel"), expected_page(fakes, labels, "RCV-0001"))
        == []
    )

    boss = htmlkit.parse(world.web("boss").client.get(PAGE, params={"mode": "technical"}).text)
    assert boss.status() != present.REFUSAL
    tech = expected_page(fakes, labels, "RCV-0001", technical=True)
    assert htmlkit.missing_facts(boss.by_id("log-panel"), tech) == []
    assert htmlkit.page_facts(tech) != htmlkit.page_facts(expected_page(fakes, labels, "RCV-0001"))
    assert "RCV-1" in htmlkit.visible(boss.by_id("log-panel"))


def test_open_only_drops_the_accepted_receipt(world: Any, htmlkit: Any, fakes: Any) -> None:
    found = htmlkit.parse(world.web("bob").client.get(PAGE, params={"open": "1"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["RCV-0002", "RCV-0003"]
    assert found.status() == present.receipt_text.summary_line(2, 2, open_only=True)


def test_missing_mtr_keeps_the_receipt_and_its_panel_has_the_mtr_line(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"mtr": "missing"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["RCV-0003"]
    panel = htmlkit.parse(bob.get(f"{PAGE}/panel/RCV-0003").text)
    assert MTR_LINE in htmlkit.visible(panel.root)


def test_a_rejected_receipt_panel_has_the_rejection_reason(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    reason = "Heat E7018-26C not on the MTR"
    rejected = fakes.get_materials_receipt(PROJECT, "RCV-0002").model_copy(
        update={
            "number": "RCV-0004",
            "id": "RCV-4",
            "title": "Electrodes, rejected lot",
            "state": "Rejected",
            "decided_by": "user:ana",
            "decided_on": "2026-10-30",
            "rejection_reason": reason,
        }
    )
    as_row = views.ReceiptView(**rejected.model_dump(include=set(views.ReceiptView.model_fields)))

    def list_with(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return [*fakes.list_materials_receipts(project, **kwargs), as_row]

    def get_with(self: WebReadClient, project: str, number: str) -> Any:
        if number == "RCV-0004":
            return rejected
        return fakes.get_materials_receipt(project, number)

    with (
        mock.patch.object(WebReadClient, "list_materials_receipts", list_with),
        mock.patch.object(WebReadClient, "get_materials_receipt", get_with),
    ):
        panel = world.web("bob").client.get(f"{PAGE}/panel/RCV-0004")
    assert panel.status_code == 200
    want = present.receipt_text.receipt_page(rejected, labels_for(world, "bob"), technical=False)
    got = htmlkit.parse(panel.text)
    assert htmlkit.missing_facts(got.root, want) == []
    assert "Rejection reason" in htmlkit.visible(got.root)
    assert reason in htmlkit.visible(got.root)


def test_an_unknown_open_value_is_ignored(world: Any, htmlkit: Any, fakes: Any) -> None:
    found = htmlkit.parse(world.web("bob").client.get(PAGE, params={"open": "zzz"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["RCV-0001", "RCV-0002", "RCV-0003"]
    assert found.status() == present.receipt_text.summary_line(3, 3, text="")


def test_the_real_world_answers_with_an_empty_table_and_404_panels(
    world: Any, htmlkit: Any
) -> None:
    bob = world.web("bob").client
    page = bob.get(PAGE)
    assert page.status_code == 200
    assert htmlkit.parse(page.text).rows("log-table") == []
    unknown = bob.get(f"{PAGE}/panel/RCV-9999")
    assert unknown.status_code == 404
    assert bob.get(f"{PAGE}/panel/RCV-0001").content == unknown.content


def test_the_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, "T13-receipts.png")
    assert path.exists()
