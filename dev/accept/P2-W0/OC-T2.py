"""Acceptance script for P2-W0 OC-T2: the Offline class row of the record screen (technical mode).

Runs on the TUI fake client (packages/tl-tui/tests); no ledger, no network. Prints one
``PASS <check>`` line per check and exits 0 when every check passes, 1 on the first failure. The
record types and their classes come from the generated offline table
(``tl_core.offline.record_type_rows``); the wording is the offline-classes spec (5.6), written out
here, not read back from the code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("TL_ENV", "test")  # the same test environment as the other acceptance runs

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the fake client and its helpers

from fakes import FakeClient  # noqa: E402
from tl_core.offline import record_type_rows  # noqa: E402
from tl_tui import details  # noqa: E402
from tl_tui.details import TECHNICAL_SECTION, DetailRow, details_for, rows_page  # noqa: E402
from tl_tui.details.generic import offline_rows  # noqa: E402
from tl_tui.display import DisplayMode, Labels  # noqa: E402
from tl_tui.layout import plain_lines  # noqa: E402

PROJECT = "P1"
LABEL = "Offline class"
WORDS = {
    "full": "Full: created and edited offline",
    "draft_only": "Draft only: drafted offline, issued online",
    "none": "None: online only",
}


def passed(check: str) -> None:
    print(f"PASS {check}")


def mode(*, technical: bool) -> DisplayMode:
    """A display mode with its flag set (``DisplayMode`` takes no constructor arguments)."""
    value = DisplayMode()
    value.technical = technical
    return value


def record_of(record_type: str) -> dict[str, Any]:
    """A minimal record of one type; it carries no renderer's data."""
    return {"id": "01OC2TESTRECORD", "type": record_type, "key": "OC2-1", "status": "Draft"}


def label_rows(rows: list[DetailRow]) -> list[DetailRow]:
    return [row for row in rows if row.label == LABEL]


class RaisingTypes(FakeClient):
    """A client that cannot list its record types."""

    def record_types(self) -> Any:
        raise RuntimeError("record types unavailable")


def main() -> None:
    details._load_renderers()  # the renderer table fills on the first call (as details_for does)
    chosen: dict[str, str] = {}
    for row in record_type_rows():
        if row.record_type not in details._RENDERERS:
            chosen.setdefault(row.offline, row.record_type)
    for offline in ("full", "draft_only", "none"):
        assert offline in chosen, f"no record type without a renderer is {offline}"
        print(f"CHOSEN {offline} {chosen[offline]}")

    labels = Labels()
    client = FakeClient()
    technical = mode(technical=True)
    plain = mode(technical=False)
    by_class: dict[str, list[DetailRow]] = {}

    for offline, record_type in chosen.items():
        rows = details_for(client, PROJECT, record_of(record_type), labels, technical)
        by_class[offline] = rows
        found = label_rows(rows)
        assert len(found) == 1, f"{record_type}: {len(found)} Offline class rows"
        assert found[0].value == WORDS[offline], (record_type, found[0].value)
        assert found[0].section == TECHNICAL_SECTION, found[0].section
        assert found[0].technical is True and found[0].panel is False, found[0]
    passed("(a) each class without a renderer shows its wording in Technical details, once")

    for record_type in chosen.values():
        rows = details_for(client, PROJECT, record_of(record_type), labels, plain)
        assert not label_rows(rows), f"{record_type}: plain mode shows {LABEL}"
    passed("(b) plain mode shows no Offline class row for any of the three types")

    for offline, rows in by_class.items():
        text = "\n".join(plain_lines(rows_page(rows, technical=False), identity=False))
        assert "offline" not in text.lower(), (offline, text)
    passed("(c) rows_page(rows, technical=False) text holds no offline word")

    raising = RaisingTypes()
    for offline, record_type in chosen.items():
        ok_rows = by_class[offline]
        bad_rows = details_for(raising, PROJECT, record_of(record_type), labels, technical)
        assert not label_rows(bad_rows), f"{record_type}: row shown when types cannot be read"
        expected = [row for row in ok_rows if row.label != LABEL]
        assert bad_rows == expected, f"{record_type}: other rows changed when types failed"
        assert offline_rows(raising, record_type) == [], record_type
    passed("(d) a client whose record_types raises leaves the other rows unchanged, no error")

    for offline, rows in by_class.items():
        shown = "\n".join(plain_lines(rows_page(rows, technical=True, panel=False), identity=False))
        assert LABEL in shown, (offline, "positive control: the record screen shows the row")
        panel = "\n".join(plain_lines(rows_page(rows, technical=True, panel=True), identity=False))
        assert LABEL not in panel, (offline, panel)
    passed("(e) the row is on the record screen, not in a technical panel")

    print("ALL PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL {exc!r}")
        raise SystemExit(1) from exc
