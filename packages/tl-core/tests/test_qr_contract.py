"""The scan-card contract and registry (P2-QR S1)."""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection
from tl_core.confidentiality import Viewer
from tl_core.qr import registry, types
from tl_core.qr.registry import ScanCardLoadError, load_scan_cards
from tl_core.qr.types import (
    MAX_BANNER_CHARS,
    MAX_LABEL_CHARS,
    MAX_LINES,
    MAX_PROVIDERS,
    MAX_TITLE_CHARS,
    MAX_VALUE_CHARS,
    SCAN_NEXT_PATTERN,
    ScanCard,
    ScanCardProvider,
    ScanLine,
    is_scan_next,
)

NOW = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
CODE = "ABCDEFGHJK234567"


def card_args(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "record_type": "quality.PunchItem",
        "key": "P123-PUN-0001",
        "title": "Guard missing",
        "banner": "OPEN",
        "tone": "caution",
        "as_of": NOW,
        "lines": [{"label": "Area", "value": "A1"}],
        "open_path": "/web/records/x",
    }
    base.update(over)
    return base


def test_a_good_card_is_accepted_and_bounds_are_the_frozen_numbers() -> None:
    c = ScanCard(**card_args())
    assert c.open_path == "/web/records/x" and c.valid_until is None
    assert (MAX_LINES, MAX_LABEL_CHARS, MAX_VALUE_CHARS) == (8, 24, 80)
    assert (MAX_BANNER_CHARS, MAX_TITLE_CHARS, MAX_PROVIDERS) == (40, 120, 32)
    assert ScanCard(**card_args(open_path=None)).open_path is None


def test_a_card_at_the_bounds_is_accepted() -> None:
    lines = [{"label": "l" * MAX_LABEL_CHARS, "value": "v" * MAX_VALUE_CHARS}] * MAX_LINES
    ScanCard(**card_args(lines=lines, banner="b" * MAX_BANNER_CHARS, title="t" * MAX_TITLE_CHARS))


@pytest.mark.parametrize(
    "over",
    [
        {"lines": [{"label": "a", "value": "b"}] * (MAX_LINES + 1)},
        {"lines": [{"label": "l" * (MAX_LABEL_CHARS + 1), "value": "v"}]},
        {"lines": [{"label": "l", "value": "v" * (MAX_VALUE_CHARS + 1)}]},
        {"banner": "b" * (MAX_BANNER_CHARS + 1)},
        {"title": "t" * (MAX_TITLE_CHARS + 1)},
        {"as_of": datetime(2026, 12, 1, 9, 0)},
        {"tone": "purple"},
        {"extra_field": 1},
        {"open_path": "/other/x"},
        {"open_path": "web/x"},
        {"open_path": "/web//x"},
        {"open_path": "/web/../x"},
        {"open_path": "https://evil.example/web/x"},
    ],
)
def test_a_card_refuses(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ScanCard(**card_args(**over))


def test_a_line_refuses_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ScanLine(label="a", value="b", extra=1)  # type: ignore[call-arg]


def test_the_scan_next_pattern_matches_a_scan_path_only() -> None:
    assert SCAN_NEXT_PATTERN == r"^/web/q/[A-Z0-9]{16}$"
    assert is_scan_next(f"/web/q/{CODE}")
    for bad in (
        f"//web/q/{CODE}",
        f"/web/q//{CODE}",
        "/web/q/../AAAAAAAAAAAAAAAA",
        f"/web/other/{CODE}",
        f"/web/q/{CODE[:15]}",
        f"/web/q/{CODE}A",
        f"/web/q/{CODE.lower()}",
        f"https://evil.example/web/q/{CODE}",
        f"evil.example/web/q/{CODE}",
        f"/web/q/{CODE}\n",
        f"/web/q/{CODE}?x=1",
        "",
    ):
        assert not is_scan_next(bad), bad


class Provider:
    view_word = "qr.view"

    def __init__(self, record_type: str) -> None:
        self.record_type = record_type

    def card(
        self, conn: Connection, record_id: str, viewer: Viewer, now: datetime
    ) -> ScanCard | None:
        return None


class Entry:
    def __init__(self, name: str, factory: Callable[[], Any]) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> Callable[[], Any]:
        return self._factory


def entry(name: str, record_type: str) -> Entry:
    return Entry(name, lambda: Provider(record_type))


def load(*entries: Entry) -> dict[str, ScanCardProvider]:
    return load_scan_cards(entries)  # type: ignore[arg-type]


def test_an_empty_group_loads_as_empty() -> None:
    assert load() == {}


def test_providers_are_keyed_by_record_type() -> None:
    found = load(entry("b", "x.B"), entry("a", "x.A"))
    assert list(found) == ["x.A", "x.B"]
    assert isinstance(found["x.A"], ScanCardProvider)


def test_two_providers_for_one_record_type_are_refused() -> None:
    with pytest.raises(ScanCardLoadError, match="twice"):
        load(entry("a", "x.A"), entry("b", "x.A"))


def test_a_provider_that_does_not_satisfy_the_protocol_is_refused() -> None:
    with pytest.raises(ScanCardLoadError, match="ScanCardProvider"):
        load(Entry("a", lambda: object()))


def test_a_plugin_that_fails_to_load_is_an_error_with_the_type_only() -> None:
    def boom() -> Any:
        raise RuntimeError("secret detail")

    with pytest.raises(ScanCardLoadError) as info:
        load(Entry("a", boom))
    assert "RuntimeError" in str(info.value) and "secret" not in str(info.value)


def test_more_than_the_maximum_providers_is_refused() -> None:
    many = [entry(f"p{i:02}", f"x.T{i}") for i in range(MAX_PROVIDERS)]
    assert len(load(*many)) == MAX_PROVIDERS
    with pytest.raises(ScanCardLoadError, match="more than"):
        load(*many, entry("zz", "x.Extra"))


def test_the_default_group_is_read_from_the_entry_points() -> None:
    assert isinstance(load_scan_cards(), dict)


def test_tl_core_qr_imports_no_web_cli_mcp_or_module_code() -> None:
    forbidden = ("tl_web", "tl_cli", "tl_mcp", "tl_api", "tl_tui", "tl_mod_")
    for mod in (types, registry):
        tree = ast.parse(Path(str(mod.__file__)).read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(forbidden), (mod.__name__, name)
