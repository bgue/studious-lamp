"""The Details registry: one renderer per record type, generic rows otherwise (P1-UX-S2)."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from tl_tui import details
from tl_tui.details import DetailRow, details_for
from tl_tui.details.generic import generic_rows
from tl_tui.display import DisplayMode, Labels

PLAIN = DisplayMode()
TECHNICAL = DisplayMode()
TECHNICAL.technical = True


def a_record(record_type: str = "x.Unknown") -> dict[str, Any]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    return {**record, "type": record_type}


def test_an_unknown_type_uses_the_generic_rows() -> None:
    record = a_record("x.Unknown")
    rows = details_for(FakeClient(), "P123", record, Labels(), PLAIN)
    assert rows == [r for r in generic_rows(record, Labels()) if not r.technical]
    assert [r.label for r in rows][:2] == ["Type", "Title"]
    assert rows[0].value == "Unknown"  # a type without a title is humanized, never the raw name
    assert all(not r.technical for r in rows)


def test_the_generic_rows_use_the_type_title_and_hold_the_technical_rows_back() -> None:
    record = a_record("documents.Document")
    labels = Labels(type_titles={"documents.Document": "Document"})
    plain = details_for(FakeClient(), "P123", record, labels, PLAIN)
    full = details_for(FakeClient(), "P123", record, labels, TECHNICAL)
    assert plain[0] == DetailRow("Type", "Document")
    assert [r.label for r in full if r.technical] == ["Key", "Version", "Scope", "Schema hash"]
    assert [r for r in full if not r.technical] == plain


def test_a_renderer_error_shows_the_generic_rows_and_one_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(client: Any, project: str, record: dict[str, Any], labels: Labels) -> list[DetailRow]:
        raise RuntimeError("secret internals 01J000000000000000000000")

    monkeypatch.setitem(details._RENDERERS, "test.Boom", boom)  # noqa: SLF001
    record = a_record("test.Boom")
    rows = details_for(FakeClient(), "P123", record, Labels(), PLAIN)
    assert rows[:-1] == [r for r in generic_rows(record, Labels()) if not r.technical]
    assert rows[-1] == DetailRow(details.NOTE_LABEL, details.NOTE_TEXT)
    assert "secret" not in " ".join(r.value for r in rows)  # the error text is not shown


def test_a_registered_renderer_is_picked_by_type(monkeypatch: pytest.MonkeyPatch) -> None:
    def mine(client: Any, project: str, record: dict[str, Any], labels: Labels) -> list[DetailRow]:
        return [DetailRow("Mine", project), DetailRow("Hidden", "x", technical=True)]

    monkeypatch.setitem(details._RENDERERS, "test.Mine", mine)  # noqa: SLF001
    assert details_for(FakeClient(), "P9", a_record("test.Mine"), Labels(), PLAIN) == [
        DetailRow("Mine", "P9")
    ]
    assert details_for(FakeClient(), "P9", a_record("test.Mine"), Labels(), TECHNICAL)[-1].technical


def test_every_renderer_module_is_imported_once(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []
    real = importlib.import_module

    def spy(name: str, package: str | None = None) -> Any:
        imported.append(name)
        return real(name, package)

    monkeypatch.setattr(details, "_loaded", False)
    monkeypatch.setattr(importlib, "import_module", spy)
    record = a_record()
    for _ in range(3):
        details_for(FakeClient(), "P123", record, Labels(), PLAIN)
    names = sorted(f"{details.__name__}.{m.name}" for m in pkgutil.iter_modules(details.__path__))
    assert sorted(n for n in imported if n.startswith(details.__name__ + ".")) == names
    assert {"tl_tui.details.generic", "tl_tui.details.documents"} <= set(names)


def test_the_document_renderer_reads_get_document_by_the_key() -> None:
    client = FakeClient()
    client.seed_documents("P123")
    record = {**a_record("documents.Document"), "key": "ISO-1234"}
    rows = {r.label: r.value for r in details_for(client, "P123", record, Labels(), PLAIN)}
    assert rows["Number"] == "ISO-1234" and rows["Current revision"] == "B (IFC)"
    assert rows["Type"] == "Document" and rows["State"] == "Issued"
    missing = {**record, "key": "NO-SUCH"}
    fallback = details_for(client, "P123", missing, Labels(), PLAIN)
    assert fallback[-1] == DetailRow(details.NOTE_LABEL, details.NOTE_TEXT)
