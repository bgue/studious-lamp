"""The external packages page: ``GET /web/p/{project}/packages`` (P2-WEB1-T11, the twin recipe).

The awp reads of the page are the fake of ``tl-tui`` (``fakes_awp.py``, loaded by path), patched
over the one mirror the page calls, ``list_packages``. The fake's seed holds one EWP (``EWP-001``,
not a constraint source) and one PWP (``PWP-001``, a constraint source). The real world of the
fixture is read once, unpatched, at the end.

Case (f) of the recipe does not apply: the panel reads nothing of its own (it shows the row the
page already read), so there is no read to make raise ``RecordNotFoundError``.
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
from tl_tui import package_text
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PAGE = "/web/p/P123/packages"
COLUMNS = package_text.PACKAGE_COLUMNS
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


def load_fake() -> Any:
    """The tl-tui fake of the awp reads, seeded with one EWP and one PWP for project P123."""
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


def seeded_rows() -> list[Any]:
    """The fake's packages, as the page's one read gets them (sorted by number)."""
    return list(load_fake().list_packages("P123"))


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


@pytest.fixture
def fakes() -> Iterator[None]:
    fake = load_fake()
    with mock.patch.object(
        WebReadClient, "list_packages", lambda self, *a, **kw: fake.list_packages(*a, **kw)
    ):
        yield


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.packages as packages

    assert any(r is packages.router for r in routers.page_routers())
    assert LOGS["packages"].SLUG == "packages"


def test_seven_regions_and_the_cells_equal_row_cells(world: Any, htmlkit: Any, fakes: None) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    # Actual and CWPs hold one value in both rows, so visible_columns leaves them out.
    want_headers = ["Number", "Subject", "Type", "Status", "Forecast", "Constraint source"]
    assert doc.headers("log-table") == want_headers
    full = [package_text.package_cells(row) for row in seeded_rows()]
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), COLUMNS, full)


def test_the_panel_is_the_package_page_as_plain_lines(
    world: Any, htmlkit: Any, fakes: None
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/EWP-001")
    assert panel.status_code == 200
    ewp = next(row for row in seeded_rows() if row.package_no == "EWP-001")
    page = package_text.package_page(ewp, panel=True, technical=False)
    assert htmlkit.missing_facts(htmlkit.parse(panel.text).root, page) == []


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: None) -> None:
    want = package_text.summary_line(2, 2, kind=None, constraints_only=False, text="")
    assert want == "2 packages"
    assert htmlkit.parse(world.web("bob").client.get(PAGE).text).status() == want


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fakes: None) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "PWP-001"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["PWP-001"]
    one, two = bob.get(f"{PAGE}/panel/EWP-9999"), bob.get(f"{PAGE}/panel/EWP-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_only_the_open_link(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is not None
    assert "data-command" not in bar.text()


def test_plain_and_technical_modes(world: Any, htmlkit: Any, fakes: None) -> None:
    """A plain user asking for technical mode gets the refusal and the plain panel. An admin gets
    no refusal, and the same panel: ``package_page`` marks the record id as not for the panel
    (``panel=False``), so ``rows_page`` leaves it out in technical mode too (see the report)."""
    bob = world.web("bob").client
    assert htmlkit.parse(bob.get(f"{PAGE}?mode=technical").text).status() == present.REFUSAL
    plain = htmlkit.parse(bob.get(f"{PAGE}/panel/EWP-001").text).root
    ewp = next(row for row in seeded_rows() if row.package_no == "EWP-001")
    plain_page = package_text.package_page(ewp, panel=True, technical=False)
    assert htmlkit.missing_facts(plain, plain_page) == []
    tech = htmlkit.parse(bob.get(f"{PAGE}/panel/EWP-001?mode=technical").text).root
    assert htmlkit.missing_facts(tech, plain_page) == []
    boss = world.web("boss").client
    summary = package_text.summary_line(2, 2, kind=None, constraints_only=False, text="")
    assert htmlkit.parse(boss.get(f"{PAGE}?mode=technical").text).status() == summary
    boss_tech = htmlkit.parse(boss.get(f"{PAGE}/panel/EWP-001?mode=technical").text).root
    assert htmlkit.missing_facts(boss_tech, plain_page) == []
    assert "EWP-1" not in htmlkit.visible(plain)


def test_the_kind_filter_keeps_the_pwp_and_names_it(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"kind": "PWP"}).text)
    assert [r.get("data-number") for r in doc.log_rows()] == ["PWP-001"]
    want = package_text.summary_line(1, 2, kind="PWP", constraints_only=False, text="")
    assert doc.status() == want


def test_an_unknown_kind_is_ignored(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"kind": "xyz"}).text)
    assert [r.get("data-number") for r in doc.log_rows()] == ["EWP-001", "PWP-001"]
    want = package_text.summary_line(2, 2, kind=None, constraints_only=False, text="")
    assert doc.status() == want


def test_the_constraints_filter_is_the_constraint_sources_only(
    world: Any, htmlkit: Any, fakes: None
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"constraints": "1"}).text)
    constraint_sources = [p.package_no for p in seeded_rows() if p.constraint_source]
    assert constraint_sources == ["PWP-001"]
    assert [r.get("data-number") for r in doc.log_rows()] == constraint_sources
    want = package_text.summary_line(1, 2, kind=None, constraints_only=True, text="")
    assert doc.status() == want


def test_the_screenshot_of_the_packages_page(world: Any, fakes: None) -> None:
    out = shoot(world.app, world.web("bob").token, PAGE, "T11-packages.png")
    assert out.exists()


def test_the_real_world_answers_the_page_and_no_panel(world: Any, htmlkit: Any) -> None:
    """No patch: the seeded world holds no packages, so the table is empty and any panel is the
    one 404 page."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    want = package_text.summary_line(0, 0, kind=None, constraints_only=False, text="")
    assert doc.status() == want
    assert doc.rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/EWP-001").status_code == 404
    assert bob.get(f"{PAGE}/panel/EWP-001").content == bob.get(f"{PAGE}/panel/EWP-002").content
