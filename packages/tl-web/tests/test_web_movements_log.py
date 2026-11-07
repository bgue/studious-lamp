"""The movements log page: ``GET /web/p/{project}/movements`` (P2-WEB1-T12b, the recipe of
``TWINS.md`` with the materials differences of ``M4-TWINS.md``).

The one read of the page, ``list_materials_movements``, is patched with the tl-tui materials fake
seeded by T17 (``seed_materials``), loaded by path. The seed has six movements, one of each kind,
seq 1 to 6. Case (f) of the recipe does not apply: the page makes no per-row read (the panel is
built from the row itself), so there is no read to fail. Case (i) is not among this ticket's
cases. The real world is read once, unpatched, at the end.
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
from urllib.parse import quote

import pytest
import uvicorn
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

PAGE = "/web/p/P123/movements"
PROJECT = "P123"
SCOPE = "project:P123"
COLUMNS = present.materials_text.MOVEMENT_COLUMNS
KEEP = COLUMNS[:2]  # Date and Kind always show, as in the terminal
REPO = Path(__file__).resolve().parents[3]
SHOT = "T12b-movements.png"

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


def _load(name: str, rel: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_fake() -> Any:
    base = Path("packages/tl-tui/tests")
    fake_mod = _load("tl_web_tests_fakes_materials", base / "fakes_materials.py")
    seed_mod = _load("tl_web_tests_fakes_materials_seed", base / "fakes_materials_seed.py")
    fake = fake_mod.FakeMaterialsSupport()
    fake._init_materials()
    seed_mod.seed_materials(fake, PROJECT)
    return fake


def number_of(seq: int) -> str:
    """The panel URL's part for movement ``#seq``: the ``#`` is quoted."""
    return quote(f"#{seq}", safe="/")


def labels_for(world: Any) -> Any:
    return present.load_labels(present.as_client(world.reads("bob")), SCOPE, ("core.Record",))


def shown_positions(full: list[tuple[str, ...]]) -> list[int]:
    """The columns the page shows: the log drops a column that is the same in every row."""
    return present.visible_columns(list(COLUMNS), full, KEEP)


def expected_panel(row: Any, labels: Any) -> present.Page:
    cells = present.materials_text.movement_cells(row, COLUMNS, labels)
    props = [present.layout.prop(name, cell) for name, cell in zip(COLUMNS, cells, strict=True)]
    props.append(present.layout.prop("Reason", row.reason))
    props.append(present.layout.prop("Person", row.person))
    kind = present.materials_text.movement_cells(row, ("Kind",))[0]
    page = present.layout.Page(
        identity=present.layout.identity_line(f"#{row.seq}", kind),
        sections=(present.layout.Section("", tuple(props)),),
    )
    return page


@pytest.fixture
def fakes() -> Iterator[Any]:
    fake = load_fake()

    def list_materials_movements(self: WebReadClient, project: str, **kwargs: Any) -> Any:
        return fake.list_materials_movements(project, **kwargs)

    with mock.patch.object(WebReadClient, "list_materials_movements", list_materials_movements):
        yield fake


def all_rows(fake: Any) -> list[Any]:
    return fake.list_materials_movements(PROJECT, limit=500)


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.movements as movements

    assert any(r is movements.router for r in routers.page_routers())
    assert LOGS["movements"].SLUG == "movements"


def test_seven_regions_and_the_cells_equal_the_text_cells(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    headers = doc.headers("log-table")
    assert headers[:2] == ["Date", "Kind"]
    labels = labels_for(world)
    full = [
        present.materials_text.movement_cells(row, COLUMNS, labels, technical=False)
        for row in all_rows(fakes)
    ]
    positions = shown_positions(full)
    assert headers == [COLUMNS[i] for i in positions]
    assert doc.rows("log-table") == [[cells[i] for i in positions] for cells in full]


def test_the_panel_of_each_movement_is_the_terminal_panel(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    labels = labels_for(world)
    for row in all_rows(fakes):
        panel = bob.get(f"{PAGE}/panel/{number_of(row.seq)}")
        assert panel.status_code == 200
        got = htmlkit.parse(panel.text)
        assert htmlkit.missing_facts(got.root, expected_panel(row, labels)) == []


def test_the_panel_has_reason_and_person(world: Any, htmlkit: Any, fakes: Any) -> None:
    rows = all_rows(fakes)
    bob = world.web("bob").client
    with_reason = next(m for m in rows if m.reason)
    with_person = next(m for m in rows if m.person)
    reason = htmlkit.parse(bob.get(f"{PAGE}/panel/{number_of(with_reason.seq)}").text)
    person = htmlkit.parse(bob.get(f"{PAGE}/panel/{number_of(with_person.seq)}").text)
    labels = labels_for(world)
    assert htmlkit.missing_facts(reason.root, expected_panel(with_reason, labels)) == []
    assert htmlkit.missing_facts(person.root, expected_panel(with_person, labels)) == []


def test_the_status_line_is_the_summary(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    want = present.materials_text.movement_summary(6, 6)
    assert doc.status() == want == "Showing 6 of 6 movements"


def test_the_filter_keeps_the_matching_row_and_an_unknown_number_is_a_404(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    bob = world.web("bob").client
    labels = labels_for(world)
    rows = all_rows(fakes)
    full = [present.materials_text.movement_cells(m, COLUMNS, labels) for m in rows]
    found = htmlkit.parse(bob.get(PAGE, params={"q": "WH-B"}).text)
    want = [m.seq for m, cells in zip(rows, full, strict=True) if "wh-b" in " ".join(cells).lower()]
    assert want
    assert [r.get("data-number") for r in found.log_rows()] == [f"#{s}" for s in want]
    one = bob.get(f"{PAGE}/panel/{number_of(999)}")
    two = bob.get(f"{PAGE}/panel/{number_of(998)}")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: Any) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_no_button_and_no_open_link(
    world: Any, htmlkit: Any, fakes: Any
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    assert doc.by_id("log-open") is None
    assert all(not row.get("data-open") for row in doc.log_rows())


def test_the_kind_filter_keeps_one_kind(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE, params={"kind": "issue"}).text)
    want = [m.seq for m in all_rows(fakes) if m.kind == "issue"]
    assert want
    assert [r.get("data-number") for r in doc.log_rows()] == [f"#{s}" for s in want]
    assert doc.status() == "Showing 1 of 6 movements · Issue"


def test_an_unknown_kind_is_as_if_absent(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    plain = htmlkit.parse(bob.get(PAGE).text)
    cut = htmlkit.parse(bob.get(PAGE, params={"kind": "bogus"}).text)
    assert cut.rows("log-table") == plain.rows("log-table")
    assert cut.status() == "Showing 6 of 6 movements"


def test_the_lot_filter_keeps_the_lot(world: Any, htmlkit: Any, fakes: Any) -> None:
    lot = all_rows(fakes)[0].lot
    doc = htmlkit.parse(world.web("bob").client.get(PAGE, params={"lot": lot}).text)
    want = [m.seq for m in fakes.list_materials_movements(PROJECT, lot=lot)]
    assert [r.get("data-number") for r in doc.log_rows()] == [f"#{s}" for s in want]
    assert doc.status().endswith(f"· lot {lot}")


def test_an_unknown_period_is_all(world: Any, htmlkit: Any, fakes: Any) -> None:
    bob = world.web("bob").client
    plain = htmlkit.parse(bob.get(PAGE).text)
    cut = htmlkit.parse(bob.get(PAGE, params={"period": "zzz"}).text)
    assert cut.rows("log-table") == plain.rows("log-table")
    assert cut.status() == "Showing 6 of 6 movements"


def test_the_quantity_is_signed(world: Any, htmlkit: Any, fakes: Any) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    qty = doc.headers("log-table").index("Qty")
    cells = {
        row.get("data-number"): text[qty]
        for row, text in zip(doc.log_rows(), doc.rows("log-table"), strict=True)
    }
    for m in all_rows(fakes):
        if m.kind == "receive":
            assert cells[f"#{m.seq}"].startswith("+")
        if m.kind == "issue":
            assert cells[f"#{m.seq}"].startswith("-")


def test_a_real_world_has_no_movements_and_no_panel(world: Any, htmlkit: Any) -> None:
    """No patch: the world has no movement for P123 in this harness, so the table is empty."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(PAGE).text)
    assert doc.status() == "Showing 0 of 0 movements"
    assert doc.rows("log-table") == []
    assert bob.get(f"{PAGE}/panel/{number_of(1)}").status_code == 404


def test_the_movements_page_screenshot(world: Any, fakes: Any) -> None:
    path = shoot(world.app, world.web("bob").token, PAGE, SHOT)
    assert path.exists()
