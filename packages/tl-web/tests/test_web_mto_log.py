"""The take-off lines page on the web: ``GET /web/p/{project}/mto`` (P2-WEB1-T13b, M4 twin).

The reads of the page are the materials mirrors of ``WebReadClient``, patched with the materials
fake of the terminal tests (``fakes_materials.py``) seeded by ``seed_materials`` (T17): three
take-off lines on ``ISO-1234@A``. ``MTO_1`` and ``MTO_2`` are short, ``MTO_3`` is covered. A
take-off line has no record page, so the page offers no Open link (D41). The real world is read
once, unpatched, at the end.
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
from tl_mod_materials.errors import MtoLineNotFoundError
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

REPO = Path(__file__).resolve().parents[3]
PAGE = "/web/p/P123/mto"
SCOPE = "project:P123"
ISO = "ISO-1234@A"
MTO_1, MTO_2, MTO_3 = f"{ISO}/MTO-1", f"{ISO}/MTO-2", f"{ISO}/MTO-3"
COLUMNS = present.mto_text.MTO_COLUMNS
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


def _load(name: str, path: Path) -> ModuleType:
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
    seed_mod.seed_materials(fake, "P123")
    return fake


@pytest.fixture
def fakes() -> Iterator[Any]:
    fake = load_fake()

    def list_mto(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_materials_mto_lines(project, **kwargs)

    def get_mto(self: WebReadClient, project: str, key: str) -> Any:
        return fake.get_materials_mto_line(project, key)

    with (
        mock.patch.object(WebReadClient, "list_materials_mto_lines", list_mto),
        mock.patch.object(WebReadClient, "get_materials_mto_line", get_mto),
    ):
        yield fake


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(present.as_client(w.reads(name)), SCOPE, ("core.Record",))


def numbers(doc: Any) -> list[str]:
    return [r.get("data-number") for r in doc.log_rows()]


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


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.mto as mto

    assert any(r is mto.router for r in routers.page_routers())
    assert LOGS["mto"].SLUG == "mto"


def test_the_regions_and_the_cells_equal_the_text_module(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:2] == ["Number", "Subject"]
    views = fakes.list_materials_mto_lines("P123", limit=500)
    full = [present.mto_text.row_cells(view, COLUMNS, technical=False) for view in views]
    assert len(doc.rows("log-table")) == 3
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), COLUMNS, full)


def test_the_panel_of_a_key_with_a_slash_and_an_at_sign_is_the_text_page(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    panel = bob.get(f"{PAGE}/panel/{MTO_1}")
    assert panel.status_code == 200
    detail = fakes.get_materials_mto_line("P123", MTO_1)
    page = present.mto_text.mto_page(detail, labels_for(world, "bob"), technical=False)
    lines = htmlkit.parse(panel.text).pre().split("\n")
    assert lines == present.plain_lines(page)
    assert lines[0] == f"{MTO_1} · Carbon steel pipe 6 in Sch 40"


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    want = present.mto_text.summary_line(3, 3, short_only=False, work_package=None, text="")
    assert htmlkit.parse(world.web("bob").client.get(PAGE).text).status() == want


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "MTO-2"}).text)
    assert numbers(found) == [MTO_2]
    one = bob.get(f"{PAGE}/panel/ISO-9999@A/MTO-9")
    two = bob.get(f"{PAGE}/panel/ISO-9998@A/MTO-9")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_a_read_that_raises_not_found_is_the_same_404(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    unknown = bob.get(f"{PAGE}/panel/ISO-9999@A/MTO-9")

    def gone(self: WebReadClient, project: str, key: str) -> Any:
        raise MtoLineNotFoundError(key)

    with mock.patch.object(WebReadClient, "get_materials_mto_line", gone):
        hidden = bob.get(f"{PAGE}/panel/{MTO_2}")
    assert hidden.status_code == 404 and hidden.content == unknown.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: Any) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_no_buttons_and_no_open_link(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    assert doc.by_id("log-open") is None
    assert all(r.get("data-open") == "" for r in doc.log_rows())


def test_short_keeps_the_short_lines(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    short = htmlkit.parse(bob.get(PAGE, params={"short": "1"}).text)
    assert numbers(short) == [MTO_1, MTO_2]
    want = present.mto_text.summary_line(2, 2, short_only=True, work_package=None, text="")
    assert short.status() == want
    assert numbers(htmlkit.parse(bob.get(PAGE, params={"short": "0"}).text)) == [
        MTO_1,
        MTO_2,
        MTO_3,
    ]


def test_wp_keeps_one_work_package(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"wp": "WP-102"}).text)
    assert numbers(doc) == [MTO_2]
    want = present.mto_text.summary_line(1, 1, short_only=False, work_package="WP-102", text="")
    assert doc.status() == want


def test_a_covered_line_reads_covered_and_a_short_one_reads_short(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    covered = htmlkit.parse(bob.get(f"{PAGE}/panel/{MTO_3}").text).pre().split("\n")
    short = htmlkit.parse(bob.get(f"{PAGE}/panel/{MTO_1}").text).pre().split("\n")
    assert covered[1] == "Covered"
    assert short[1] == "Short 3.25 M"


def test_reservations_and_open_receipts_tables(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    lines = htmlkit.parse(bob.get(f"{PAGE}/panel/{MTO_1}").text).pre().split("\n")
    assert "Reservations" in lines and "Open receipts" in lines
    assert "Lot      Location  Qty" in lines and "PL-4471  WH-A      4.25" in lines
    assert "RCV-0003  Received  2026-11-02   6" in lines
    none = htmlkit.parse(bob.get(f"{PAGE}/panel/{MTO_2}").text).pre().split("\n")
    assert "No reservations" in none and "No open receipts" in none


def test_plain_versus_technical(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    refused = htmlkit.parse(bob.get(PAGE, params={"mode": "technical"}).text)
    assert refused.status() == present.REFUSAL
    plain = htmlkit.parse(bob.get(f"{PAGE}/panel/{MTO_1}").text).pre()
    bob_tech = htmlkit.parse(bob.get(f"{PAGE}/panel/{MTO_1}", params={"mode": "technical"}).text)
    assert bob_tech.pre() == plain
    boss = world.web("boss").client
    tech = htmlkit.parse(boss.get(f"{PAGE}/panel/{MTO_1}", params={"mode": "technical"}).text)
    detail = fakes.get_materials_mto_line("P123", MTO_1)
    want = present.mto_text.mto_page(detail, labels_for(world, "boss"), technical=True)
    assert tech.pre().split("\n") == present.plain_lines(want)
    assert "Id        MTL-1" in tech.pre().split("\n")
    assert "MTL-1" not in plain


def test_the_real_world_has_an_empty_table_and_404_panels(world: Any, htmlkit: Any) -> None:
    bob = world.web("bob").client
    page = bob.get(PAGE)
    assert page.status_code == 200
    assert htmlkit.parse(page.text).rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/{MTO_1}").status_code == 404


def test_the_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, "T13b-mto.png")
    assert path.exists()
