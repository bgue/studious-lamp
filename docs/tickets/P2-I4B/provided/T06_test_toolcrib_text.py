"""T06: the toolcrib line, its tool lookup and its command, as pure functions.

Copied byte-identical to packages/tl-tui/tests/test_toolcrib_text.py. No Textual, no client.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest
from tl_mod_materials.handlers.movements import IssueStock, ReturnStock
from tl_tui import toolcrib_text as t


def row(lot: str, item: str, on_hand: str = "1", uom: str = "ea") -> SimpleNamespace:
    return SimpleNamespace(lot=lot, item_code=item, on_hand=Decimal(on_hand), uom=uom)


def test_a_line_is_tool_then_person_then_an_optional_count() -> None:
    p = t.parse_line("L-0042 Ana Ruiz x2")
    assert (p.tool, p.person, p.qty) == ("L-0042", "Ana Ruiz", "2")
    p = t.parse_line("  drill-01   Ben  ")
    assert (p.tool, p.person, p.qty) == ("drill-01", "Ben", "1")
    p = t.parse_line("L-0042")
    assert (p.tool, p.person, p.qty) == ("L-0042", "", "1")


def test_line_checks_say_what_to_type() -> None:
    assert t.check_line("issue", t.parse_line("")) == [("line", t.NEED_TOOL)]
    assert t.check_line("issue", t.parse_line("L-1")) == [("person", t.NEED_PERSON)]
    assert t.check_line("return", t.parse_line("L-1")) == []
    assert t.check_line("issue", t.parse_line("L-1 Ana")) == []
    for bad in ("L-1 Ana x0", "L-1 Ana x-2", "L-1 Ana x1.2345"):
        assert t.check_line("issue", t.parse_line(bad)) == [("qty", t.BAD_QTY)]
    assert t.check_line("lend", t.parse_line("L-1 Ana")) == [("mode", t.BAD_MODE)]


def test_a_tool_is_found_by_lot_key_first_then_by_item_code() -> None:
    rows = [row("L-1", "DRILL"), row("L-2", "DRILL"), row("L-3", "SAW")]
    assert t.resolve_tool("l-1", rows).lot == "L-1"  # lot key, any case
    assert t.resolve_tool("SAW", rows).lot == "L-3"  # one lot of the item
    with pytest.raises(t.ToolcribError) as many:
        t.resolve_tool("DRILL", rows)
    assert str(many.value) == t.several_lots("DRILL", 2)
    with pytest.raises(t.ToolcribError) as none:
        t.resolve_tool("LADDER", rows)
    assert str(none.value) == t.no_such_tool("LADDER")


def test_the_command_is_one_movement_from_or_to_the_crib() -> None:
    issue = t.build_command(
        "issue",
        lot="L-1",
        uom="ea",
        qty="2",
        person="Ana Ruiz",
        crib="TC1",
        actor="user:crib",
        project="P123",
    )
    assert isinstance(issue, IssueStock)
    assert issue.scope == "project:P123" and issue.source == "tui" and issue.actor == "user:crib"
    (m,) = issue.movements
    assert (m.lot_key, m.qty, m.uom, m.from_location, m.to_location, m.person) == (
        "L-1",
        "2",
        "ea",
        "TC1",
        None,
        "Ana Ruiz",
    )
    back = t.build_command(
        "return",
        lot="L-1",
        uom="ea",
        qty="1",
        person="",
        crib="TC1",
        actor="user:crib",
        project="P123",
    )
    assert isinstance(back, ReturnStock)
    (m,) = back.movements
    assert (m.from_location, m.to_location, m.person) == (None, "TC1", None)


def test_done_texts_are_words() -> None:
    assert t.done_text("issue", "2", "ea", "L-1", "Ana Ruiz") == "Issued 2 ea of L-1 to Ana Ruiz."
    assert t.done_text("return", "1", "ea", "L-1", "") == "Took back 1 ea of L-1."
    assert (
        t.done_text("return", "1", "ea", "L-1", "Ana Ruiz")
        == "Took back 1 ea of L-1 from Ana Ruiz."
    )


def test_the_module_leaves_textual_out() -> None:
    code = "import sys, tl_tui.toolcrib_text; sys.exit('textual' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
