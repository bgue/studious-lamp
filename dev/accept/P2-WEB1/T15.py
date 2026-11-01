"""Acceptance script for P2-WEB1 T15: the RFI log page (``tl_web.pages.rfis``).

Reuses the helpers and the seeded ledger of ``S4.py`` (loaded as a module, not copied). The S4
demo page is switched off first: its slug ``rfis`` is owned by the real page now. Prints one
``PASS <letter>: ...`` per check, exits 0 when all pass and 1 on the first failure.
"""

from __future__ import annotations

import html
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
S4.PAGE_SOURCE = (
    "from fastapi import APIRouter\n"
    "router = APIRouter(prefix='/web', include_in_schema=False)\n"  # S4's own demo page off
)

from tl_web import present, routers  # noqa: E402
from tl_web.log import LOGS  # noqa: E402

expect, passed, Doc, PROJECT = S4.expect, S4.passed, S4.Doc, S4.PROJECT
RFI_COLUMNS = present.rfi_text.RFI_COLUMNS
HIDDEN = ("P123-RFI-0004", "P123-RFI-0005")
PAGE = f"/web/p/{PROJECT}/rfis"


def status_text(doc: Any) -> str:
    return html.unescape(doc.texts.get("log-status", "")).strip()


def check_registration() -> None:
    import tl_web.pages.rfis as rfis

    expect(any(r is rfis.router for r in routers.page_routers()), "pages.rfis is not mounted")
    expect(LOGS["rfis"].SLUG == "rfis", f"SLUG {LOGS['rfis'].SLUG!r}")
    passed("a: routers.page_routers() mounts tl_web.pages.rfis; LOGS['rfis'].SLUG == 'rfis'")


def check_page(world: Any) -> None:
    alice, _ = world.web("alice")
    page = alice.get(PAGE)
    expect(page.status_code == 200, f"page {page.status_code}")
    doc = Doc(page.text)
    seen = [i for i in doc.ids if i in S4.REGIONS]
    expect(seen == S4.REGIONS, f"regions {seen}")
    expect(doc.headers[:3] == ["Number", "Subject", "State"], f"columns {doc.headers}")
    full = S4.expected_rows(world, "alice", technical=False)
    positions = [RFI_COLUMNS.index(h) for h in doc.headers]
    expect(len(doc.rows) == len(full) == 4, f"{len(doc.rows)} rows")
    for row, cells in zip(doc.rows, full, strict=True):
        expect(row["cells"] == [cells[i] for i in positions], f"cells {row['cells']} != {cells}")
    passed("b: seven regions in order; columns start Number, Subject, State; cells == rfi_cells")


def check_panel(world: Any) -> None:
    alice, _ = world.web("alice")
    labels = S4.labels_for(world, "alice")
    reader = world.reads("alice")
    view = reader.get_rfi(PROJECT, "P123-RFI-0001")
    lines = present.plain_lines(
        present.rfi_text.rfi_page(
            view, labels, technical=False, client=present.as_client(reader), project=PROJECT
        )
    )
    panel = alice.get(f"{PAGE}/panel/P123-RFI-0001")
    expect(panel.status_code == 200, f"panel {panel.status_code}")
    got = Doc(panel.text)
    expect(got.texts.get("pre", "").split("\n") == lines, "the panel is not the terminal's lines")
    passed("c: the panel of P123-RFI-0001 is the terminal's plain_lines(rfi_page(...))")


def check_summary(world: Any) -> None:
    alice, _ = world.web("alice")
    summary = present.rfi_text.rfi_summary(world.reads("alice").list_rfis(PROJECT))
    got = status_text(Doc(alice.get(PAGE).text))
    expect(got == summary, f"status {got!r} != summary {summary!r}")
    passed(f"d: #log-status is rfi_summary: {summary}")


def check_hidden(world: Any) -> None:
    alice, _ = world.web("alice")
    start = len(world.answers)
    reference = alice.get(f"{PAGE}/panel/P123-RFI-9999")
    expect(reference.status_code == 404, f"unknown panel {reference.status_code}")
    for number in HIDDEN:
        hidden = alice.get(f"{PAGE}/panel/{number}")
        expect(hidden.status_code == 404, f"{number}: panel {hidden.status_code}")
        expect(hidden.content == reference.content, f"{number}: not the 404 page of 9999")
    # a hidden number asked as the selection: the page still answers, the hidden row is absent
    selected = alice.get(f"{PAGE}?sel={HIDDEN[0]}")
    expect(selected.status_code == 200, f"page with a hidden sel: {selected.status_code}")
    secrets = ("PRIVSECRET", "RESTSECRET", *HIDDEN, world.ids["secret"], world.ids["restricted"])
    for response in world.answers[start:]:  # every answer alice got in this check
        for secret in secrets:
            expect(secret.encode() not in response.content, f"{secret} in an answer for alice")
    passed("e: hidden RFIs 0004/0005 answer the same 404 bytes as P123-RFI-9999; no secret text")


def check_mode(world: Any) -> None:
    alice, _ = world.web("alice")
    root, _ = world.web("root")
    for path in (f"{PAGE}?mode=technical", f"{PAGE}/panel/P123-RFI-0001?mode=technical"):
        doc = Doc(alice.get(path).text)
        expect(status_text(doc) == present.REFUSAL, f"{path}: status {status_text(doc)!r}")
    plain = Doc(alice.get(f"{PAGE}?mode=technical").text)
    labels = S4.labels_for(world, "alice")
    lines = world.reads("alice").list_rfis(PROJECT).lines
    positions = [RFI_COLUMNS.index(h) for h in plain.headers]
    for row, line in zip(plain.rows, lines, strict=True):
        cells = present.rfi_text.rfi_cells(line, labels, technical=False)
        expect(row["cells"] == [cells[i] for i in positions], "a non-admin got technical cells")
    technical = Doc(root.get(f"{PAGE}?mode=technical").text)
    expect(status_text(technical) != present.REFUSAL, "an admin was refused")
    root_labels = S4.labels_for(world, "root")
    root_lines = world.reads("root").list_rfis(PROJECT).lines
    positions = [RFI_COLUMNS.index(h) for h in technical.headers]
    for row, line in zip(technical.rows, root_lines, strict=True):
        cells = present.rfi_text.rfi_cells(line, root_labels, technical=True)
        expect(row["cells"] == [cells[i] for i in positions], "the admin did not get raw cells")
    passed("f: ?mode=technical: alice keeps plain cells and REFUSAL; root gets raw state cells")


def check_sign_in(world: Any) -> None:
    anonymous = world.client()
    response = anonymous.get(PAGE)
    expect(response.status_code == 303, f"no cookie: {response.status_code}")
    location = response.headers.get("location", "")
    expect(location.startswith("/web/sign-in"), f"redirect to {location!r}")
    passed("g: no cookie: 303 to /web/sign-in")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        world = S4.World(Path(tmp))
        try:
            check_registration()
            check_page(world)
            check_panel(world)
            check_summary(world)
            check_hidden(world)
            check_mode(world)
            check_sign_in(world)
        finally:
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
