"""The integration registry in plain words (P1-UX-T09a): no ids, versions or code versions.

Services are named by their label, and the technical view keeps what it showed before the change.
"""

from __future__ import annotations

import re
from typing import Any

import rows_integration as rows
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.display import Labels, find_technical
from tl_tui.integration_text import cells, columns, detail_lines
from tl_tui.widgets.integration_screen import IntegrationScreen

NAMES = {"ep-1": "acme-nde/results"}
MAKERS = {
    "apps": rows.app,
    "endpoints": rows.endpoint,
    "rules": rows.rule,
    "actions": rows.action,
    "enrichers": rows.enricher,
    "invocations": rows.invocation,
    "deliveries": rows.delivery,
    "enrichments": rows.enrichment,
}
SERVICE_LABELS = Labels(services={"svc:inbound-acme-nde.results": "Acme NDE inbound"})


def value_of(lines: list[str], label: str) -> str:
    """The value of the line whose label is ``label`` (labels are padded to 12 columns)."""
    return next(line[12:] for line in lines if line[:12].strip() == label)


def test_plain_columns_and_cells_drop_ids_versions_and_code_versions() -> None:
    for kind in ("endpoints", "rules", "actions", "enrichers", "invocations", "deliveries"):
        assert not {"Ver", "Code", "Id"} & set(columns(kind, technical=False)), kind
    assert columns("endpoints", technical=False) == ("Path", "State", "Mode", "Auth", "Access")
    assert cells("endpoints", rows.endpoint(), technical=False) == (
        "acme-nde/results", "✓ on", "live", "hmac", "user",
    )  # fmt: skip
    assert cells("rules", rows.rule(), technical=False) == (
        "hse-notify", "✗ off", "propose", "user", "Notify HSE",
    )  # fmt: skip
    assert cells("actions", rows.action(), technical=False) == (
        "send_to_nde", "✓ on", "webhook", "user", "yes", "Send to NDE",
    )  # fmt: skip
    assert cells("enrichers", rows.enricher(), technical=False) == (
        "doc_classifier", "✓ on", "user", "doc_type,discipline",
    )  # fmt: skip
    assert cells("invocations", rows.invocation(), technical=False) == (
        "✓ Completed", "send_to_nde", "bob", "2026-10-11 12:15",
    )  # fmt: skip
    assert columns("deliveries", technical=False) == ("State", "Endpoint", "Received", "Error")
    assert cells("deliveries", rows.delivery(), NAMES, technical=False) == (
        "! Failed", "acme-nde/results", "2026-10-11 12:15", "Mapping failed",
    )  # fmt: skip
    assert cells("deliveries", rows.delivery(error_code=None), technical=False)[-1] == "-"


def test_plain_detail_lines_name_services_and_hide_ids() -> None:
    endpoint = detail_lines("endpoints", rows.endpoint(), labels=SERVICE_LABELS, technical=False)
    assert value_of(endpoint, "Acts as") == "Acme NDE inbound"
    assert value_of(endpoint, "Owner") == "boss"
    assert value_of(endpoint, "Allowed") == "Set pset values, Add link"
    unknown = detail_lines("rules", rows.rule(), technical=False)
    assert value_of(unknown, "Acts as") == "a service"
    assert value_of(unknown, "Steps") == "Post to feed"
    action = detail_lines("actions", rows.action(), labels=SERVICE_LABELS, technical=False)
    assert value_of(action, "Owner") == "boss"
    invocation = detail_lines("invocations", rows.invocation(), technical=False)
    assert value_of(invocation, "Action") == "send_to_nde"
    assert value_of(invocation, "By") == "bob"
    delivery = detail_lines("deliveries", rows.delivery(), NAMES, technical=False)
    assert value_of(delivery, "Endpoint") == "acme-nde/results"
    assert value_of(delivery, "Error") == "Mapping failed: no weld in the payload"
    assert not any(line.startswith(("Invocation", "Delivery", "Code")) for line in delivery)


def test_plain_panels_show_no_technical_tokens() -> None:
    for kind, make in MAKERS.items():
        text = "\n".join(detail_lines(kind, make(), NAMES, technical=False))
        assert find_technical(text) == [], kind
        assert not re.search(r"\bv\d", text), kind
        assert "svc:" not in text and "user:" not in text, kind


#: The technical text as it was before P1-UX-T09a (captured from the HEAD parent), one row per kind.
TECHNICAL_CELLS: dict[str, tuple[str, ...]] = {
    "apps": ("acme-nde", "✓ on", "user:boss", "Acme NDE"),
    "endpoints": ("acme-nde/results", "✓ on", "live", "hmac", "user", "v2"),
    "rules": ("hse-notify", "✗ off", "propose", "user", "v1", "Notify HSE"),
    "actions": ("send_to_nde", "✓ on", "webhook", "user", "yes", "v1", "Send to NDE"),
    "enrichers": ("doc_classifier", "✓ on", "user", "v1", "1.0.0", "doc_type,discipline"),
    "invocations": ("NAAAAAA1", "✓ completed", "send_to_nde", "user:bob", "2026-10-11 12:15"),
    "deliveries": (
        "AAAAAAA1",
        "! failed",
        "acme-nde/results",
        "2026-10-11 12:15",
        "mapping_failed",
    ),  # fmt: skip
    "enrichments": (
        "AAAAAAA1",
        "… proposed",
        "DOC-0001",
        "enrich.doc_classifier.doc_type",
        '"DRW"',
        "0.80",
    ),  # fmt: skip
}
TECHNICAL_DETAIL: dict[str, list[str]] = {
    "apps": [
        "App         acme-nde",
        "State       ✓ on",
        "Owner       user:boss",
        "Label       Acme NDE",
        "About       Weld inspection results",
    ],  # fmt: skip
    "endpoints": [
        "Path        /in/acme-nde/results",
        "State       ✓ on",
        "Mode        live",
        "Auth        hmac",
        "Access      user",
        "Acts as     svc:inbound-acme-nde.results",
        "Owner       user:boss",
        "Allowed     SetPsetValues, AddLink",
        "Body cap    65536 bytes",
        "Rate        60 per minute",
    ],  # fmt: skip
    "rules": [
        "Rule        hse-notify",
        "Title       Notify HSE",
        "State       ✗ off",
        "Mode        propose",
        "Access      user",
        "Acts as     svc:rule-hse-notify",
        "Owner       user:boss",
        "Steps       PostToFeed",
    ],  # fmt: skip
    "actions": [
        "Action      send_to_nde",
        "Label       Send to NDE",
        "State       ✓ on",
        "Executor    webhook",
        "Access      user",
        "Approval    needs another person",
        "Effect      external",
        "Owner       user:boss",
        "Parameters  weld, note",
    ],  # fmt: skip
    "enrichers": [
        "Enricher    doc_classifier",
        "State       ✓ on",
        "Access      user",
        "Code        1.0.0",
        "Owner       user:boss",
        "  doc_type  text, propose (threshold 0.9)",
        "  disciplinetext, auto (threshold 0.8)",
    ],  # fmt: skip
    "invocations": [
        "Invocation  01JINVOCATIONAAAAAA1",
        "Action      send_to_nde v1",
        "Status      ✓ completed",
        "By          user:bob",
        "Requested   2026-10-11 12:15",
        "Finished    2026-10-11 12:15",
        "Targets     1",
    ],  # fmt: skip
    "deliveries": [
        "Delivery    01JDELIVERYAAAAAAA1",
        "Endpoint    acme-nde/results v2",
        "State       ! failed",
        "Received    2026-10-11 12:15",
        "Size        412 bytes",
        "Attempts    3",
        "Error       mapping_failed: no weld in the payload",
    ],  # fmt: skip
    "enrichments": [
        "Value       01JVALUEAAAAAAAAAA1",
        "State       … proposed",
        "Record      DOC-0001",
        "Property    enrich.doc_classifier.doc_type",
        'Proposed    "DRW"',
        "Confidence  0.80",
        "Enricher    doc_classifier@1",
        "Produced    2026-10-11 12:15",
    ],  # fmt: skip
}


def test_technical_detail_lines_and_cells_are_unchanged() -> None:
    assert set(TECHNICAL_CELLS) == set(TECHNICAL_DETAIL) == set(MAKERS)
    for kind, make in MAKERS.items():
        assert cells(kind, make(), NAMES) == TECHNICAL_CELLS[kind], kind
        assert cells(kind, make(), NAMES, technical=True) == TECHNICAL_CELLS[kind], kind
        assert detail_lines(kind, make(), NAMES) == TECHNICAL_DETAIL[kind], kind


def test_screen_redraws_columns_on_the_mode_switch() -> None:
    client = FakeClient()
    client.seed_integration("endpoints", **rows.endpoint())
    app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=True)

    def headings(screen: IntegrationScreen) -> tuple[str, ...]:
        table = screen.query_one("#integration-table", DataTable)
        return tuple(str(column.label) for column in table.columns.values())

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+e")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, IntegrationScreen)
        assert headings(screen) == ("Path", "State", "Mode", "Auth", "Access")
        assert "acme-nde/results" in screen_text(app) and "v2" not in screen_text(app)
        await pilot.press("ctrl+d")  # technical details on: the version column is back
        await pilot.pause()
        assert headings(screen) == ("Path", "State", "Mode", "Auth", "Access", "Ver")
        assert "v2" in screen_text(app)
        await pilot.press("ctrl+d")  # and off again
        await pilot.pause()
        assert headings(screen) == ("Path", "State", "Mode", "Auth", "Access")
        assert "v2" not in screen_text(app)

    run_pilot(app, go)
