"""Display-text helpers."""

from __future__ import annotations

from tl_tui.text import conformance_mark, format_value, short_hash, timestamp, unit_label


def test_short_hash() -> None:
    assert short_hash("a91f" + "0" * 56 + "3c") == "#a91f…3c"
    assert short_hash(None) == "—"
    assert short_hash("") == "—"


def test_timestamp() -> None:
    assert timestamp("2026-10-09T09:05:30+00:00") == "2026-10-09 09:05"
    assert timestamp(None) == "—"


def test_conformance_mark() -> None:
    assert conformance_mark("ok") == "✓ ok"
    assert conformance_mark("warning") == "! warning"
    assert conformance_mark("nonconformant") == "✗ nonconformant"
    assert conformance_mark("waived") == "waived"


def test_format_value() -> None:
    assert format_value(None) == "—"
    assert format_value("") == "—"
    assert format_value(True) == "yes"
    assert format_value(6.0) == "6"
    assert format_value(2.5) == "2.5"
    assert format_value({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'
    assert format_value("x") == "x"


def test_conformance_mark_of_nothing_is_a_dash() -> None:
    assert conformance_mark(None) == "—"


def test_unit_label() -> None:
    assert unit_label("[in_i]") == "in"
    assert unit_label("furlong") == "furlong"
    assert unit_label(None) == ""
