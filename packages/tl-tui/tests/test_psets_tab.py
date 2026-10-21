"""Psets tab: layer-grouped rendering with enforcement markers (P0-I2-T15). Provided."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from tl_core.services.errors import ServiceError
from tl_schema.forms import FieldMeta
from tl_tui.messages import StatusMessage
from tl_tui.widgets.psets_tab import PsetsTab, psets_text, rule_text, value_text

FV_1001 = [
    "Property                    Value                   Layer       Rule",
    "▾ valve_data · required",
    "  size_in                   6 in                    standard    "
    "● required at Design or Installed  ✓",
    "  body_material             316L stainless          standard    ● required at Design  ✓",
    "  fail_action               Fail closed             standard    ■ locked  ✓",
    "  seat_leakage              IV                      standard    ○ advisory  ✓",
    "  x.fat_witness_by          @party:client-acme      custom      optional  ✓",
    "  x.tie_in_window           —                       custom      optional",
    "▾ prj.shutdown_tie_in · optional",
    "  window                    —                       project     optional",
    "  isolation                 —                       project     optional",
    "▾ enrich.ai_classifier · optional",
    "  valve_type                —                       enrichment  optional (read-only)",
    "",
    "● required  ○ advisory  ■ locked  ! warning  ✗ nonconformant  ✓ ok  x. project custom section",
    "Conformance: ✓ ok",
]


def _text(client: FakeClient, key: str, *, technical: bool = False) -> str:
    record = client.get_record(SCOPE, key)
    assert record is not None
    meta = client.form_metadata(SCOPE, "core.Record")
    return psets_text(meta, record, client.conformance(record["id"]), technical=technical)


def test_psets_text_for_a_conformant_record_matches_the_layout_exactly() -> None:
    assert _text(FakeClient.with_valve_example(), "FV-1001").splitlines() == FV_1001


def test_technical_mode_keeps_the_stored_codes() -> None:
    lines = _text(FakeClient.with_valve_example(), "FV-1001", technical=True).splitlines()
    assert lines[3].startswith("  body_material             SS316L ")
    assert lines[4].startswith("  fail_action               FC ")


def test_psets_text_marks_issues_with_symbols() -> None:
    lines = _text(FakeClient.with_valve_example(), "FV-1003").splitlines()
    assert lines[2].endswith("● required at Design or Installed  ✗")
    assert lines[5].endswith("○ advisory  !")
    assert lines[3].endswith("● required at Design")  # not required in state Installed, no issue
    assert lines[-1] == "Conformance: ✗ nonconformant"
    technical = _text(FakeClient.with_valve_example(), "FV-1003", technical=True)
    assert technical.splitlines()[-1] == "Conformance: ✗ nonconformant   Effective schema #a91f…3c"


def _field(**extra: Any) -> FieldMeta:
    base: dict[str, Any] = {
        "path": "psets.p.f",
        "label": "f",
        "description": "d",
        "kind": "string",
        "layer": "standard",
        "group": "p",
        "order": 1,
    }
    base.update(extra)
    return FieldMeta.model_validate(base)


def test_rule_text_variants() -> None:
    assert rule_text(_field()) == "optional"
    assert rule_text(_field(enforcement="advisory")) == "○ advisory"
    assert rule_text(_field(enforcement="locked")) == "■ locked"
    assert rule_text(_field(enforcement="required", required_in_states=["A", "B"])) == (
        "● required at A or B"
    )
    assert rule_text(_field(required_in_states=["A"])) == "optional at A"
    assert rule_text(_field(readonly=True, layer="enrichment")) == "optional (read-only)"


def test_value_text_units_and_missing_values() -> None:
    psets = {"p": {"f": 6.0, "g": "x", "h": ""}}
    assert value_text(_field(unit="[in_i]"), psets) == "6 in"
    assert value_text(_field(unit="furlong"), psets) == "6 furlong"
    assert value_text(_field(), psets) == "6"
    assert value_text(_field(path="psets.p.g"), psets) == "x"
    assert value_text(_field(path="psets.p.h"), psets) == "—"
    assert value_text(_field(path="psets.p.none"), psets) == "—"
    flat = {"p": {"x.f": "v"}}
    assert value_text(_field(path="psets.p.x.f"), flat) == "v"


def _codes() -> dict[str, Any]:
    return {
        "enum_values": [
            {"code": "structural", "label": "Structural"},
            {"code": "USD", "label": "US dollar"},
            {"code": "XTS", "label": ""},
        ]
    }


def test_a_code_list_value_shows_its_label_and_technical_mode_the_stored_code() -> None:
    psets = {"p": {"f": "structural", "g": "XTS", "h": "unlisted"}}
    field = _field(**_codes())
    assert value_text(field, psets) == "Structural"
    assert value_text(field, psets, technical=True) == "structural"
    assert value_text(_field(path="psets.p.g", **_codes()), psets) == "XTS"  # no label: the code
    assert value_text(_field(path="psets.p.h", **_codes()), psets) == "unlisted"
    assert value_text(_field(path="psets.p.none", **_codes()), psets) == "—"


def test_a_currency_placeholder_is_the_sibling_currency_then_the_record_then_nothing() -> None:
    cost = _field(path="psets.p.cost_estimate", unit="{currency}", kind="decimal")
    cur = _field(path="psets.p.cost_currency", **_codes())
    psets = {"p": {"cost_estimate": 1200, "cost_currency": "USD"}}
    assert value_text(cost, psets, siblings=[cost, cur]) == "1200 USD"
    assert value_text(cost, psets, siblings=[cost, cur], technical=True) == "1200 USD"
    assert value_text(cur, psets, siblings=[cost, cur]) == "US dollar"
    assert value_text(cur, psets, siblings=[cost, cur], technical=True) == "USD"
    no_sibling = {"p": {"cost_estimate": 1200}}
    assert value_text(cost, no_sibling, siblings=[cost, cur], record={"currency": "EUR"}) == (
        "1200 EUR"
    )
    assert value_text(cost, no_sibling, siblings=[cost, cur]) == "1200"
    assert value_text(cost, no_sibling) == "1200"
    other = _field(path="psets.p.x", unit="{count}")
    assert value_text(other, {"p": {"x": 3}}) == "3"  # a placeholder with no value never shows


def test_the_tab_shows_labels_and_resolved_units_in_plain_mode_only() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    meta = client.form_metadata(SCOPE, "core.Record")
    group = meta.psets[0]
    group.fields.append(
        _field(
            path=f"psets.{group.name}.cost_estimate",
            label="Cost estimate",
            unit="{currency}",
            kind="decimal",
        )
    )
    group.fields.append(
        _field(path=f"psets.{group.name}.cost_currency", label="Cost currency", **_codes())
    )
    record["psets"].setdefault(group.name, {}).update({"cost_estimate": 90, "cost_currency": "USD"})
    report = client.conformance(record["id"])
    plain = psets_text(meta, record, report)
    technical = psets_text(meta, record, report, technical=True)
    assert "Cost estimate             90 USD" in plain
    assert "Cost currency             US dollar" in plain
    assert "Cost currency             USD" in technical
    assert "{" not in plain


class Host(App[None]):
    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield PsetsTab(self.client, SCOPE, id="psets")

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)


def test_tab_renders_the_text_literally_and_follows_show_record() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(PsetsTab)
        first = client.get_record(SCOPE, "FV-1001")
        assert first is not None
        tab.show_record(first)
        await pilot.pause()
        text = screen_text(app)
        assert tab.text.splitlines() == FV_1001
        assert "size_in" in text and "6 in" in text and "● required at Design or Installed" in text
        second = client.get_record(SCOPE, "FV-1003")
        assert second is not None
        tab.show_record(second)
        await pilot.pause()
        assert tab.record is not None and tab.record["key"] == "FV-1003"
        assert "✗ nonconformant" in screen_text(app)

    run_pilot(app, scenario, size=(120, 30))


def test_tab_reports_missing_services_and_client_errors() -> None:
    class NoServices(FakeClient):
        def form_metadata(self, scope: str, record_type: str, record_id: str | None = None):  # noqa: ANN202
            raise NotImplementedError

    class Broken(FakeClient):
        def conformance(self, record_id: str):  # noqa: ANN202
            raise ServiceError("schema unavailable")

    for client_type, expected in (
        (NoServices, "Properties unavailable: the property services are not installed yet"),
        (Broken, "Properties unavailable: schema unavailable"),
    ):
        client = client_type.with_valve_example()
        app = Host(client)

        async def scenario(
            pilot: Pilot[Any],
            app: Host = app,
            client: FakeClient = client,
            expected: str = expected,
        ) -> None:
            await pilot.pause()
            record = client.get_record(SCOPE, "FV-1001")
            assert record is not None
            app.query_one(PsetsTab).show_record(record)
            await pilot.pause()
            assert expected in screen_text(app)

        run_pilot(app, scenario, size=(120, 30))
        if client_type is Broken:
            texts = [(m.text, m.severity) for m in app.seen if isinstance(m, StatusMessage)]
            assert texts == [("schema unavailable", "error")]


def test_record_view_fills_the_psets_tab_and_refreshes_on_change() -> None:
    from tl_core.services.psets import SetPsetValues
    from tl_tui.messages import RecordChanged
    from tl_tui.widgets.record_view import RecordView

    client = FakeClient.with_valve_example()

    class ViewHost(App[None]):
        def compose(self) -> ComposeResult:
            yield RecordView(client, SCOPE, "FV-1002", id="record")

    app = ViewHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(PsetsTab)
        assert "  x.fat_witness_by          —" in tab.text
        record = client.get_record(SCOPE, "FV-1002")
        assert record is not None
        client.set_pset_values(
            SetPsetValues(
                actor="user:t",
                source="tui",
                scope=SCOPE,
                stream_id=record["id"],
                expected_version=record["version"],
                pset="valve_data",
                layer="custom",
                values={"x.fat_witness_by": "@party:acme"},
            )
        )
        app.query_one(RecordView).post_message(RecordChanged(record["id"]))
        await pilot.pause()
        assert "x.fat_witness_by          @party:acme" in tab.text

    run_pilot(app, scenario, size=(120, 40))
