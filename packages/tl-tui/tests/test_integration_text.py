"""The plain text of the integration screens (P1-I7): cells, detail lines, state marks."""

from __future__ import annotations

import pytest
import rows_integration as rows
from tl_tui.integration_text import (
    COLUMNS,
    KINDS,
    cells,
    detail_lines,
    moment,
    on_off,
    record_name,
    run_state,
    shown_value,
)

SAMPLES = {
    "apps": rows.app,
    "endpoints": rows.endpoint,
    "rules": rows.rule,
    "actions": rows.action,
    "enrichers": rows.enricher,
    "invocations": rows.invocation,
    "deliveries": rows.delivery,
    "enrichments": rows.enrichment,
}


def test_every_kind_has_columns_a_sample_and_cells_that_line_up() -> None:
    assert set(KINDS) == set(COLUMNS) == set(SAMPLES)
    for kind, make in SAMPLES.items():
        assert len(cells(kind, make())) == len(COLUMNS[kind]), kind
        assert detail_lines(kind, make()), kind


def test_state_is_never_colour_alone() -> None:
    assert on_off({"enabled": True}) == "✓ on"
    assert on_off({"enabled": 0}) == "✗ off"
    assert on_off({"enabled": True, "retired": True}) == "✗ retired"
    assert run_state("completed") == "✓ completed"
    assert run_state("failed") == "! failed"
    assert run_state("queued") == "… queued"


def test_a_time_reads_as_minutes_and_nothing_as_a_dash() -> None:
    assert moment("2026-10-11T12:15:00.123456Z") == "2026-10-11 12:15"
    assert moment(None) == "-" and moment("") == "-"


def test_a_long_value_is_cut_and_a_record_shows_its_key() -> None:
    assert shown_value("DRW") == '"DRW"'
    cut = shown_value("x" * 100)
    assert len(cut) == 30 and cut.endswith("…")
    assert record_name({"id": "r1", "key": "DOC-1"}) == "DOC-1"
    assert record_name({"id": "r1", "key": None}) == "r1"
    assert record_name(None) == "?"


def test_rows_read_the_way_an_admin_expects() -> None:
    assert cells("endpoints", rows.endpoint()) == (
        "acme-nde/results", "✓ on", "live", "hmac", "user", "v2",
    )  # fmt: skip
    assert cells("endpoints", rows.endpoint(dry_run=True))[2] == "dry-run"
    assert cells("rules", rows.rule())[:3] == ("hse-notify", "✗ off", "propose")
    assert cells("actions", rows.action())[4] == "yes"
    assert cells("enrichers", rows.enricher())[-1] == "doc_type,discipline"
    assert cells("invocations", rows.invocation())[0] == "NAAAAAA1"
    assert cells("enrichments", rows.enrichment()) == (
        "AAAAAAA1", "… proposed", "DOC-0001", "enrich.doc_classifier.doc_type",
        '"DRW"', "0.80",
    )  # fmt: skip


def test_the_error_queue_names_the_endpoint_from_the_map() -> None:
    names = {"ep-1": "acme-nde/results"}
    assert cells("deliveries", rows.delivery(), names)[2] == "acme-nde/results"
    assert cells("deliveries", rows.delivery(), None)[2] == "?"
    assert cells("deliveries", rows.delivery(error_code=None))[-1] == "-"
    lines = detail_lines("deliveries", rows.delivery(), names)
    assert any(line.startswith("Endpoint") and "acme-nde/results v2" in line for line in lines)
    assert any("mapping_failed: no weld in the payload" in line for line in lines)


def test_the_detail_lines_pad_the_label_and_show_what_matters() -> None:
    lines = detail_lines("endpoints", rows.endpoint(dry_run=True))
    assert lines[0] == "Path        /in/acme-nde/results"
    assert any("dry-run (nothing is applied)" in line for line in lines)
    assert any("svc:inbound-acme-nde.results" in line for line in lines)
    rule = detail_lines("rules", rows.rule(condition="amount > 3"))
    assert any(line.startswith("Steps") and "PostToFeed" in line for line in rule)
    assert any(line.startswith("If") and "amount > 3" in line for line in rule)
    value = detail_lines("enrichments", rows.enrichment(reason="wrong sheet"))
    assert any(line.startswith("Reason") and "wrong sheet" in line for line in value)
    enricher = detail_lines("enrichers", rows.enricher())
    assert any("doc_type" in line and "propose" in line and "0.9" in line for line in enricher)


def test_an_unknown_kind_is_an_error() -> None:
    with pytest.raises(ValueError):
        cells("nonsense", {})
    with pytest.raises(ValueError):
        detail_lines("nonsense", {})
