"""The ``Offline class`` row of the record screen (OC-T2): technical mode only, three wordings."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeClient
from tl_core.offline import record_type_rows
from tl_tui import details
from tl_tui.details import TECHNICAL_SECTION, DetailRow, details_for, rows_page
from tl_tui.details.generic import offline_rows
from tl_tui.display import DisplayMode, Labels, offline_words
from tl_tui.layout import plain_lines

PROJECT = "P1"
LABEL = "Offline class"
# The wording of offline-classes spec 5.6, written out here.
WORDS = {
    "full": "Full: created and edited offline",
    "draft_only": "Draft only: drafted offline, issued online",
    "none": "None: online only",
}


def mode(*, technical: bool) -> DisplayMode:
    value = DisplayMode()  # takes no arguments
    value.technical = technical
    return value


def record_of(record_type: str) -> dict[str, Any]:
    return {"id": "01OC2TESTRECORD", "type": record_type, "key": "OC2-1", "status": "Draft"}


def label_rows(rows: list[DetailRow]) -> list[DetailRow]:
    return [row for row in rows if row.label == LABEL]


def types_without_a_renderer() -> dict[str, str]:
    """One record type without a renderer for each class (its rows are the generic ones)."""
    details._load_renderers()  # noqa: SLF001
    chosen: dict[str, str] = {}
    for row in record_type_rows():
        if row.record_type not in details._RENDERERS:  # noqa: SLF001
            chosen.setdefault(row.offline, row.record_type)
    return chosen


CHOSEN = types_without_a_renderer()


class RaisingTypes(FakeClient):
    def record_types(self) -> Any:
        raise RuntimeError("record types unavailable")


def test_the_three_wordings_are_the_spec_wordings() -> None:
    assert {k: offline_words(k) for k in WORDS} == WORDS
    assert offline_words("something_else") == "something_else"


def test_there_is_a_type_without_a_renderer_for_every_class() -> None:
    assert set(CHOSEN) == {"full", "draft_only", "none"}


@pytest.mark.parametrize("offline", ["full", "draft_only", "none"])
def test_technical_mode_shows_the_row_once_with_the_wording(offline: str) -> None:
    rows = details_for(
        FakeClient(), PROJECT, record_of(CHOSEN[offline]), Labels(), mode(technical=True)
    )
    found = label_rows(rows)
    assert len(found) == 1
    assert found[0].value == WORDS[offline]
    assert found[0].section == TECHNICAL_SECTION
    assert found[0].technical is True and found[0].panel is False


def test_the_row_comes_after_the_other_technical_rows() -> None:
    rows = details_for(
        FakeClient(), PROJECT, record_of(CHOSEN["none"]), Labels(), mode(technical=True)
    )
    technical = [r.label for r in rows if r.technical]
    assert technical[-1] == LABEL and technical[:4] == ["Key", "Version", "Scope", "Schema hash"]


def test_a_renderer_type_shows_the_row_too() -> None:
    # documents.Document has its own renderer and is draft_only: the row is added after it.
    rows = details_for(
        FakeClient(), PROJECT, record_of("documents.Document"), Labels(), mode(technical=True)
    )
    assert [r.value for r in label_rows(rows)] == [WORDS["draft_only"]]


def test_the_row_for_a_type_the_client_does_not_list_is_absent() -> None:
    rows = details_for(
        FakeClient(), PROJECT, record_of("x.Unknown"), Labels(), mode(technical=True)
    )
    assert label_rows(rows) == []
    assert offline_rows(FakeClient(), "x.Unknown") == []


@pytest.mark.parametrize("offline", ["full", "draft_only", "none"])
def test_plain_mode_shows_no_row(offline: str) -> None:
    rows = details_for(
        FakeClient(), PROJECT, record_of(CHOSEN[offline]), Labels(), mode(technical=False)
    )
    assert label_rows(rows) == []
    assert all(not r.technical for r in rows)


def test_plain_mode_makes_no_record_types_read() -> None:
    client = FakeClient()
    for record_type in CHOSEN.values():
        details_for(client, PROJECT, record_of(record_type), Labels(), mode(technical=False))
    assert "record_types" not in client.calls  # type: ignore[attr-defined]


def test_technical_mode_makes_exactly_one_record_types_read_per_call() -> None:
    client = FakeClient()
    details_for(client, PROJECT, record_of(CHOSEN["full"]), Labels(), mode(technical=True))
    assert client.calls.count("record_types") == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("offline", ["full", "draft_only", "none"])
def test_a_client_whose_record_types_raises_leaves_the_rows_unchanged(offline: str) -> None:
    record = record_of(CHOSEN[offline])
    technical = mode(technical=True)
    good = details_for(FakeClient(), PROJECT, record, Labels(), technical)
    bad = details_for(RaisingTypes(), PROJECT, record, Labels(), technical)
    assert label_rows(bad) == []
    assert bad == [row for row in good if row.label != LABEL]
    assert offline_rows(RaisingTypes(), CHOSEN[offline]) == []


@pytest.mark.parametrize("offline", ["full", "draft_only", "none"])
def test_the_plain_walk_shows_no_offline_word(offline: str) -> None:
    rows = details_for(
        FakeClient(), PROJECT, record_of(CHOSEN[offline]), Labels(), mode(technical=False)
    )
    text = "\n".join(plain_lines(rows_page(rows, technical=False), identity=False))
    assert "offline" not in text.lower()
    # the same rows in technical mode show it (a positive control for the walk)
    tech = details_for(
        FakeClient(), PROJECT, record_of(CHOSEN[offline]), Labels(), mode(technical=True)
    )
    shown = "\n".join(plain_lines(rows_page(tech, technical=True, panel=False), identity=False))
    assert LABEL in shown and WORDS[offline] in shown


def test_the_row_is_on_the_record_screen_and_not_in_the_technical_panel() -> None:
    rows = details_for(
        FakeClient(), PROJECT, record_of(CHOSEN["draft_only"]), Labels(), mode(technical=True)
    )
    panel = "\n".join(plain_lines(rows_page(rows, technical=True, panel=True), identity=False))
    assert LABEL not in panel
