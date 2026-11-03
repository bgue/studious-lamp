"""Acceptance for P2-I1-T05a: the CWP text (``tl_tui.awp_text``) and its Details renderer
(``tl_tui.details.awp``), on the ``seed_awp`` fake. No database, no network, no pytest.

Run: ``uv run python dev/accept/P2-I1/T05a.py``. Prints ``PASS <check>`` per check, then
``T05a ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))

from fakes import FakeClient  # noqa: E402
from fakes_awp import PROJECT, seed_awp  # noqa: E402
from tl_api.routes.awp import CwpDetailView  # noqa: E402
from tl_mod_schedule.resolver import ActivityLink, Resolution  # noqa: E402
from tl_tui.awp_text import (  # noqa: E402
    cwp_cells,
    cwp_page,
    cwp_rows,
    cwp_summary,
    group_by_cwa,
    hours_text,
)
from tl_tui.details import details_for  # noqa: E402
from tl_tui.display import DisplayMode, Labels  # noqa: E402
from tl_tui.layout import plain_lines  # noqa: E402

SECTIONS = ("Scope", "Allocation", "References", "Schedule", "Timeline", "Files and links")
WIDTHS = (80, 170)


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def check_no_textual() -> None:
    code = (
        "import sys; sys.modules['textual'] = None\n"
        "import tl_tui.awp_text, tl_tui.details.awp\n"
        "print('imported')"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    need(done.returncode == 0 and "imported" in done.stdout, f"textual imported: {done.stderr}")
    passed("no textual")


def fixture() -> tuple[FakeClient, list, CwpDetailView]:
    client = FakeClient()
    seed_awp(client)
    rows = client.list_cwps(PROJECT)
    seed = client.get_cwp(PROJECT, rows[0].number)
    detail = CwpDetailView(
        **seed.model_dump(exclude={"link_count", "file_count", "timeline"}),
        link_count=0,
        file_count=0,
        timeline=[],
    )
    return client, rows, detail


def check_cells(rows: list) -> None:
    cells = cwp_cells(rows[0])
    need(len(cells) == 8, f"expected 8 cells, got {len(cells)}")
    need(cells[-1] in ("✓", "—"), f"Allocated cell is {cells[-1]!r}")
    allocated = cwp_cells(rows[0].model_copy(update={"allocated": True}))
    need(allocated[-1] == "✓", "an allocated row must read ✓")
    need(hours_text(Decimal("4200")) == "4 200", "4200 must read 4 200")
    need(hours_text(Decimal("12.50")) == "12.5", "12.50 must read 12.5")
    need(hours_text(None) == "—", "None must read —")
    passed("cells")


def check_group_by_cwa(client: FakeClient, rows: list) -> None:
    orphan = rows[0].model_copy(update={"cwa": None, "number": "P123-CWP-0009"})
    groups = group_by_cwa([orphan, *reversed(rows)])
    codes = [code for code, _ in groups]
    need(codes == ["A1", "A2", "—"], f"group order is {codes}")
    first = [row.number for row in groups[0][1]]
    need(first == sorted(first), f"rows of a group must keep number order: {first}")
    passed("group_by_cwa")


def check_page(detail: CwpDetailView) -> None:
    for width in WIDTHS:
        lines = plain_lines(cwp_page(detail, panel=True), width=width)
        print(f"-- width {width}")
        print("\n".join(lines))
        for heading in SECTIONS:
            need(heading in [line.strip() for line in lines], f"no heading {heading!r}")
        need(
            not any(a == "" and b == "" for a, b in zip(lines, lines[1:], strict=False)),
            "two blank lines in a row",
        )
        starts = [i for i, line in enumerate(lines) if line.strip() in SECTIONS]
        need(all(lines[i - 1] == "" for i in starts[1:]), "a heading without a blank line before")
    panel = cwp_page(detail, panel=True)
    need(panel.summary == cwp_summary(detail) and panel.summary != "", "panel has no summary")
    many = [
        ActivityLink(
            link_id=f"L{n}",
            status="active",
            pin=None,
            reason=None,
            ref_key=f"ACT-{n}",
            resolution=Resolution(
                state="current",
                schedule_code="SCH",
                activity_id=f"ACT-{n}",
                snapshot_id=None,
                snapshot_number=None,
                data_date=None,
                activity=None,
            ),
        )
        for n in range(6)
    ]
    busy = detail.model_copy(update={"activities": many})
    schedule_rows = [row for row in cwp_rows(busy) if row.section == "Schedule" and row.cells]
    need(len(schedule_rows) == 6, "the full Details keeps all six activity rows")
    panel_lines = plain_lines(cwp_page(busy, panel=True), width=80)
    shown = [line for line in panel_lines if line.strip().startswith("ACT-")]
    need(len(shown) <= 4, f"panel shows {len(shown)} schedule rows")
    passed("page")


def check_details(client: FakeClient, rows: list) -> None:
    number = rows[0].number
    record = {"type": "awp.CWP", "key": number}
    plain = details_for(client, PROJECT, record, Labels(), DisplayMode())
    sections = {row.section for row in plain}
    need(set(SECTIONS) <= sections, f"Details sections are {sorted(sections)}")
    admin_mode = DisplayMode()
    admin_mode.technical = True
    technical = details_for(client, PROJECT, record, Labels(), admin_mode)
    need(any(row.label == "Key" for row in technical), "technical mode shows the key")
    need(not any(row.label == "Key" for row in plain), "plain mode hides the key")
    passed("details")


def main() -> int:
    try:
        check_no_textual()
        client, rows, detail = fixture()
        check_cells(rows)
        check_group_by_cwa(client, rows)
        check_page(detail)
        check_details(client, rows)
    except Failed as exc:
        print(f"FAIL {exc}")
        return 1
    print("T05a ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
