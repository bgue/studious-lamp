"""Edit modal for the body of an object-backed record (P0-I8-T27)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Select
from tl_tui.widgets.extension_edit_form import ExtensionEditForm

LIFT = "co.acme.LiftPlan"
SIZE = (110, 110)
BODY: dict[str, Any] = {
    "lift_date": "2026-11-03",
    "crane": "CR-12",
    "load_tonnes": 42.5,
    "risk_class": "medium",
    "crew": ["A. Okafor"],
}


class Host(App[None]):
    def __init__(self, client: FakeClient, record_id: str) -> None:
        super().__init__()
        self.client = client
        self.record_id = record_id
        self.results: list[bool | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        record = self.client.get_record_by_id(self.record_id)
        assert record is not None
        detail = self.client.get_type("co.acme.LiftPlan@1.0.0")
        assert detail.form is not None
        body = self.client.get_record_body(self.record_id).body
        self.push_screen(
            ExtensionEditForm(self.client, SCOPE, record, detail.form, body), self.results.append
        )


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.add_example_type(LIFT)
    return client


def _record(client: FakeClient) -> str:
    return client.create_instance(
        LIFT, scope=SCOPE, title="Skid lift", key="LP-1", body=BODY
    ).stream_id


def _form(app: Host) -> ExtensionEditForm:
    form = app.screen
    assert isinstance(form, ExtensionEditForm)
    return form


def _input(form: ExtensionEditForm, slot: str) -> Input:
    return form.query_one(f"#ext_{slot} Input", Input)


def test_the_form_is_filled_from_the_stored_body(fake: FakeClient) -> None:
    app = Host(fake, _record(fake))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _form(app)
        text = screen_text(app)
        assert "Edit LP-1" in text and "Lift plan" in text and "Method and crew" in text
        assert _input(form, "crane").value == "CR-12"
        assert _input(form, "load_tonnes").value == "42.5"
        assert _input(form, "crew").value == '["A. Okafor"]'
        assert form.query_one("#ext_risk_class Select", Select).value == "medium"

    run_pilot(app, scenario, size=SIZE)


def test_a_change_is_stored_as_a_new_body_and_the_rest_is_kept(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _input(_form(app), "crane").value = "CR-14"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [True]
        assert fake.get_record_body(record_id).body == {**BODY, "crane": "CR-14"}
        record = fake.get_record_by_id(record_id)
        assert record is not None and record["psets"]["co_acme_lift_plan"]["crane"] == "CR-14"

    run_pilot(app, scenario, size=SIZE)


def test_clearing_an_optional_slot_removes_it_from_the_body(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _input(_form(app), "crew").value = ""
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [True]
        assert "crew" not in fake.get_record_body(record_id).body

    run_pilot(app, scenario, size=SIZE)


def test_nothing_changed_is_said_and_nothing_is_stored(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and "No changes to save" in screen_text(app)
        assert "put_record_body" not in fake.calls

    run_pilot(app, scenario, size=SIZE)


def test_clearing_a_required_slot_is_refused_inline(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _input(_form(app), "crane").value = ""
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        text = screen_text(app)
        assert app.results == [] and "Required" in text and "Fix the marked fields" in text
        assert fake.get_record_body(record_id).body == BODY

    run_pilot(app, scenario, size=SIZE)


def test_text_that_does_not_parse_is_refused_inline(fake: FakeClient) -> None:
    app = Host(fake, _record(fake))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _input(_form(app), "load_tonnes").value = "heavy"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and "Enter a number" in screen_text(app)

    run_pilot(app, scenario, size=SIZE)


def test_a_body_the_server_refuses_stays_open_and_lists_the_issues(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _input(_form(app), "crew").value = "[1, 2]"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and isinstance(app.screen, ExtensionEditForm)
        text = screen_text(app)
        assert "Not saved" in text and "crew" in text
        assert fake.get_record_body(record_id).body == BODY

    run_pilot(app, scenario, size=SIZE)


def test_a_record_that_moved_on_blocks_the_save(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        fake.put_record_body(
            record_id, scope=SCOPE, body={**BODY, "crane": "CR-99"}
        )  # someone else
        _input(_form(app), "crane").value = "CR-14"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and "changed" in screen_text(app)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "cancel and open the form again" in screen_text(app)
        assert fake.get_record_body(record_id).body["crane"] == "CR-99"

    run_pilot(app, scenario, size=SIZE)


def test_escape_cancels(fake: FakeClient) -> None:
    record_id = _record(fake)
    app = Host(fake, record_id)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _input(_form(app), "crane").value = "CR-14"
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [False]
        assert fake.get_record_body(record_id).body == BODY

    run_pilot(app, scenario, size=SIZE)
