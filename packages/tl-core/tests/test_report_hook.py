"""The ``reports`` module hook and the writer (V3-P0)."""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest
from tl_core import confidentiality
from tl_core.modules import (
    ModuleLoadError,
    ModuleSpec,
    Report,
    module_reports,
    resolve_hook,
    use_modules,
)
from tl_core.report_out import csv_cell, render


def _rows(conn, scope, viewer) -> Iterator[dict[str, object]]:  # type: ignore[no-untyped-def]
    yield {"a": date(2026, 1, 2), "b": None, "c": "=SUM(1)", "d": Decimal("1.50"), "x": "hidden"}
    yield {"a": datetime(2026, 1, 2, 3, 4, 5), "b": True, "c": "plain", "d": 3}


def _spec(name: str, ref: str) -> ModuleSpec:
    return ModuleSpec(name=name, record_types=frozenset(), projectors=list, reports=(ref,))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = types.ModuleType("tl_mod_fakerep")
    mod.REPORTS = (Report("fake-one", "One", ("a", "b", "c", "d"), _rows),)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tl_mod_fakerep", mod)


def test_a_module_names_its_own_reports(fake: None) -> None:
    spec = _spec("fakerep", "tl_mod_fakerep:REPORTS")
    assert resolve_hook(spec, "reports")[0][0].name == "fake-one"  # type: ignore[index]
    with use_modules([spec]):
        assert list(module_reports()) == ["fake-one"]


def test_a_report_ref_outside_the_places_it_may_load_from_is_refused() -> None:
    with pytest.raises(ModuleLoadError, match="may not load from"):
        _spec("fakerep", "os:REPORTS")
    with pytest.raises(ModuleLoadError, match="may not load from"):
        _spec("fakerep", "tl_cli.report_awp:REPORTS")  # only an in-tree module may name tl_cli


def test_a_broken_hook_is_skipped_and_a_duplicate_name_stops(
    fake: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    good, broken = (
        _spec("fakerep", "tl_mod_fakerep:REPORTS"),
        _spec("fakerep2", "tl_mod_fakerep2:X"),
    )
    with use_modules([good, broken]):
        assert list(module_reports()) == ["fake-one"]
    mod = types.ModuleType("tl_mod_fakerep2")
    mod.REPORTS = (Report("fake-one", "Again", ("a",), _rows),)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tl_mod_fakerep2", mod)
    with use_modules([good, _spec("fakerep2", "tl_mod_fakerep2:REPORTS")]):
        with pytest.raises(ModuleLoadError, match="declared twice"):
            module_reports()


def test_csv_and_jsonl_write_the_columns_only() -> None:
    report = Report("r", "R", ("a", "b", "c", "d"), _rows)
    lines = list(render(report, None, "s", confidentiality.LOWEST))  # type: ignore[arg-type]
    assert lines == [
        "a,b,c,d\n",
        "2026-01-02,,'=SUM(1),1.50\n",
        "2026-01-02T03:04:05,true,plain,3\n",
    ]
    rows = [json.loads(x) for x in render(report, None, "s", confidentiality.LOWEST, "jsonl")]  # type: ignore[arg-type]
    assert rows[0] == {"a": "2026-01-02", "b": None, "c": "=SUM(1)", "d": "1.50"}
    assert rows[1]["b"] is True and rows[1]["d"] == 3


def test_a_bad_format_and_the_cell_rule() -> None:
    with pytest.raises(ValueError, match="csv, jsonl"):
        list(render(Report("r", "R", ("a",), _rows), None, "s", confidentiality.LOWEST, "xml"))  # type: ignore[arg-type]
    assert csv_cell("@x") == "'@x" and csv_cell("-1") == "'-1" and csv_cell(None) == ""
    assert csv_cell(-5) == "-5" and csv_cell(Decimal("-1.5")) == "-1.5"  # numbers are not text
