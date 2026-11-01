"""Acceptance script for P2-WEB1-T01: the correspondence register page on the web.

Reuses the helpers and the world of ``S4.py`` (loaded as a module, not run). The RFI page of S4 is
switched off (``PAGE_SOURCE`` is an empty router), so the real RFI page cannot clash with it.
SQLite temp ledger, ``TL_ENV=test``, ``TestClient`` at ``http://127.0.0.1``. Prints one
``PASS <letter>`` per check, exits 0 when all pass and 1 on the first failure.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("accept_s4", ROOT / "dev/accept/P2-WEB1/S4.py")
assert spec is not None and spec.loader is not None
S4 = importlib.util.module_from_spec(spec)
sys.modules["accept_s4"] = S4
spec.loader.exec_module(S4)
# S4's demo RFI page off: the real RFI page (T15) would collide with it
S4.PAGE_SOURCE = (
    "from fastapi import APIRouter\nrouter = APIRouter(prefix='/web', include_in_schema=False)\n"
)

from tl_web import present  # noqa: E402
from tl_web.log import LOGS  # noqa: E402

PROJECT = S4.PROJECT
LETTER = "P123-COR-0001"
SECOND = "P123-COR-0002"
RESTRICTED = "P123-COR-0003"
SECRET_WORD = "RESTSECRET"
BASE = f"/web/p/{PROJECT}/correspondence"
NAMES = present.correspondence_text.REGISTER_COLUMNS
KEPT = ("Number", "Subject", "State")


def expect(condition: bool, what: Any) -> None:
    S4.expect(condition, what)


def labels_for(world: Any, name: str) -> Any:
    """The labels the page uses: the project scope and the correspondence label types."""
    return present.load_labels(
        present.as_client(world.reads(name)),
        f"project:{PROJECT}",
        ("correspondence.Correspondence",),
    )


def setup(world: Any) -> None:
    """Two more letters: one visible to a plain user, one restricted (hidden from a plain user).

    ``forge_item`` has no ``scope`` argument: it writes the scope of the base envelope, as the
    first letter does.
    """
    world.ids["second"] = world.corr.forge_item(SECOND, subject="Second letter", state="Received")
    world.ids["restricted"] = world.corr.forge_item(
        RESTRICTED, subject=f"{SECRET_WORD} letter", state="Received", confidentiality="restricted"
    )


def check_mounted(world: Any, alice: Any) -> None:
    log = LOGS.get("correspondence")
    expect(log is not None and log.SLUG == "correspondence", f"LOGS: {sorted(LOGS)}")
    page = alice.get(BASE)
    expect(page.status_code == 200, f"the page answers {page.status_code}")
    S4.passed("a: the log is registered as correspondence and the page route is mounted")


def check_rows(world: Any, alice: Any) -> None:
    page = alice.get(BASE)
    doc = S4.Doc(page.text)
    seen = [i for i in doc.ids if i in S4.REGIONS]
    expect(seen == S4.REGIONS, f"regions {seen}")
    expect(doc.headers[:3] == list(KEPT), f"columns {doc.headers}")
    reader = world.reads("alice")
    lines = reader.list_correspondence(PROJECT)
    labels = labels_for(world, "alice")
    full = [present.correspondence_text.register_cells(line, labels) for line in lines]
    expect(
        len(doc.rows) == len(full) and len(full) >= 2, f"{len(doc.rows)} rows, {len(full)} lines"
    )
    positions = [NAMES.index(h) for h in doc.headers]
    for row, cells in zip(doc.rows, full, strict=True):
        expect(row["cells"] == [cells[i] for i in positions], f"cells {row['cells']} != {cells}")
    for index, name in enumerate(NAMES):
        values = {cells[index] for cells in full}
        if index in positions and name not in KEPT:
            expect(len(values) > 1, f"constant column {name} is shown")
        if index not in positions:
            expect(len(values) == 1, f"varying column {name} is dropped")
    S4.passed("b: seven regions in order, the register columns, cells equal register_cells")


def check_panel(world: Any, alice: Any) -> None:
    reader = world.reads("alice")
    labels = labels_for(world, "alice")
    item = reader.get_correspondence(PROJECT, LETTER)
    lines = present.plain_lines(
        present.correspondence_text.item_page(
            item, None, labels, technical=False, client=present.as_client(reader), project=PROJECT
        )
    )
    panel = alice.get(f"{BASE}/panel/{LETTER}")
    expect(panel.status_code == 200, f"panel {panel.status_code}")
    got = S4.Doc(panel.text)
    expect(got.texts.get("pre", "").split("\n") == lines, "the panel is not the terminal's lines")
    S4.passed(f"c: the panel of {LETTER} is plain_lines(item_page(...))")


def check_status(world: Any, alice: Any) -> None:
    page = S4.Doc(alice.get(BASE).text)
    shown = len(world.reads("alice").list_correspondence(PROJECT))
    want = present.correspondence_text.summary_line("register", shown)
    status = page.texts.get("log-status", "").strip()
    expect(status == want, f"status {status!r}")
    S4.passed(f"d: the status line is summary_line('register', {shown}): {want}")


def check_hidden(world: Any, alice: Any) -> None:
    hidden = alice.get(f"{BASE}/panel/{RESTRICTED}")
    unknown = alice.get(f"{BASE}/panel/P123-COR-9999")
    expect(hidden.status_code == 404, f"hidden panel {hidden.status_code}")
    expect(hidden.content == unknown.content, "the hidden and unknown 404 pages differ")
    answers = [
        hidden,
        unknown,
        alice.get(BASE),
        alice.get(f"{BASE}?q={SECRET_WORD.lower()}"),
        alice.get(f"{BASE}?sel={RESTRICTED}"),
        alice.get(f"{BASE}?mode=technical"),
        alice.get(f"{BASE}/panel/{LETTER}?mode=technical"),
    ]
    for answer in answers:
        expect(SECRET_WORD not in answer.text, f"{SECRET_WORD} in an answer")
        expect(world.ids["restricted"] not in answer.text, "the restricted id in an answer")
    found = S4.Doc(alice.get(f"{BASE}?q={SECRET_WORD.lower()}").text)
    expect(found.rows == [], f"the secret filter found {len(found.rows)} rows")
    S4.passed(f"e: {RESTRICTED} and {SECRET_WORD} are in no answer for alice; it is the 404 page")


def check_mode(world: Any, alice: Any, root: Any) -> None:
    plain = alice.get(f"{BASE}?mode=technical")
    expect(plain.status_code == 200, f"technical page for alice {plain.status_code}")
    status = S4.Doc(plain.text).texts.get("log-status", "")
    expect(present.REFUSAL in status, f"no refusal for alice: {status!r}")
    expect(world.ids["letter"] not in S4.Doc(plain.text).text, "a record id is visible to alice")
    reader = world.reads("root")
    labels = labels_for(world, "root")
    item = reader.get_correspondence(PROJECT, LETTER)
    lines = present.plain_lines(
        present.correspondence_text.item_page(
            item, None, labels, technical=True, client=present.as_client(reader), project=PROJECT
        )
    )
    expect(world.ids["letter"] in "\n".join(lines), "the technical panel lacks the record id")
    panel = root.get(f"{BASE}/panel/{LETTER}?mode=technical")
    expect(panel.status_code == 200, f"root panel {panel.status_code}")
    expect(S4.Doc(panel.text).texts.get("pre", "").split("\n") == lines, "root panel lines differ")
    admin_status = S4.Doc(root.get(f"{BASE}?mode=technical").text).texts.get("log-status", "")
    expect(present.REFUSAL not in admin_status, "the admin is refused")
    S4.passed("f: technical is refused for alice (plain, REFUSAL) and shows the ids for root")


def check_filter(alice: Any) -> None:
    found = S4.Doc(alice.get(f"{BASE}?q=second+letter").text)
    expect([r["cells"][0] for r in found.rows] == [SECOND], f"the filter: {found.rows}")
    S4.passed(f"g: the filter q narrows the rows to {SECOND}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        world = S4.World(Path(tmp))
        try:
            setup(world)
            alice, _ = world.web("alice")
            root, _ = world.web("root")
            check_mounted(world, alice)
            check_rows(world, alice)
            check_panel(world, alice)
            check_status(world, alice)
            check_hidden(world, alice)
            check_mode(world, alice, root)
            check_filter(alice)
        finally:
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
