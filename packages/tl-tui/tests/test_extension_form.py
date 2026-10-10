"""New-record modal of an extension type (P0-I8-T25)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Select
from tl_core.extypes.forms import TypeForm
from tl_tui.widgets.extension_form import ExtensionRecordForm

LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
SIZE = (110, 110)


class Host(App[None]):
    def __init__(self, client: FakeClient, form: TypeForm) -> None:
        super().__init__()
        self.client = client
        self.form = form
        self.results: list[str | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        self.push_screen(
            ExtensionRecordForm(self.client, SCOPE, self.form, actor="user:t"), self.results.append
        )


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.add_example_type(LIFT)
    client.add_example_type(OBSERVATION)
    return client


def _form(client: FakeClient, ref: str) -> TypeForm:
    detail = client.get_type(ref)
    assert detail.form is not None
    return detail.form


def _type(form: ExtensionRecordForm, name: str, text: str) -> None:
    form.query_one(f"#{name} Input", Input).value = text


def _fill_lift(form: ExtensionRecordForm, **overrides: str) -> None:
    values = {
        "new_key": "LP-1",
        "new_title": "Skid lift",
        "ext_lift_date": "2026-11-03",
        "ext_crane": "CR-12",
        "ext_load_tonnes": "42.5",
        **overrides,
    }
    for name, text in values.items():
        _type(form, name, text)
    form.query_one("#ext_risk_class Select", Select).value = "medium"


def _open(app: Host) -> ExtensionRecordForm:
    form = app.screen
    assert isinstance(form, ExtensionRecordForm)
    return form


def test_the_form_shows_the_groups_and_required_markers(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "New co.acme.LiftPlan" in text
        assert "Lift plan" in text and "Method and crew" in text
        assert "Crane ●" in text and "Lift date ●" in text and "Title ●" in text
        assert "Crew" in text and "Crew ●" not in text

    run_pilot(app, scenario, size=SIZE)


def test_an_object_backed_instance_is_created_with_its_body(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _fill_lift(form, ext_crew='["A. Okafor", "B. Lindqvist"]')
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == ["LP-1"]
        record = fake.get_record(SCOPE, "LP-1")
        assert record is not None and record["type"] == LIFT and record["title"] == "Skid lift"
        body = fake.get_record_body(record["id"]).body
        assert body == {
            "lift_date": "2026-11-03",
            "crane": "CR-12",
            "load_tonnes": 42.5,
            "risk_class": "medium",
            "crew": ["A. Okafor", "B. Lindqvist"],
        }

    run_pilot(app, scenario, size=SIZE)


def test_a_managed_instance_is_created_with_psets(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.SafetyObservation@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _type(form, "new_key", "SO-1")
        _type(form, "new_title", "Spill")
        _type(form, "ext_observed_on", "2026-10-02")
        _type(form, "ext_location", "Unit 3 pipe rack")
        form.query_one("#ext_category Select", Select).value = "near_miss"
        form.query_one("#ext_severity Select", Select).value = "high"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == ["SO-1"]
        record = fake.get_record(SCOPE, "SO-1")
        assert record is not None
        assert record["psets"]["co_acme_safety_observation"] == {
            "observed_on": "2026-10-02",
            "category": "near_miss",
            "severity": "high",
            "location": "Unit 3 pipe rack",
        }

    run_pilot(app, scenario, size=SIZE)


def test_a_missing_required_slot_is_refused_inline(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _fill_lift(form, ext_crane="")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and fake.get_record(SCOPE, "LP-1") is None
        text = screen_text(app)
        assert "Required" in text and "Fix the marked fields" in text

    run_pilot(app, scenario, size=SIZE)


def test_a_missing_title_is_refused_inline(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _fill_lift(form, new_title="")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and "Fix the marked fields" in screen_text(app)

    run_pilot(app, scenario, size=SIZE)


def test_text_that_does_not_parse_is_refused_inline(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _fill_lift(form, ext_load_tonnes="heavy", ext_crew="[oops")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == []
        text = screen_text(app)
        assert "Enter a number" in text and "Invalid JSON" in text

    run_pilot(app, scenario, size=SIZE)


def test_a_body_the_server_refuses_stays_open_and_lists_the_issues(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _fill_lift(form, ext_crew="[1, 2]")  # valid JSON, but not a list of text
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and isinstance(app.screen, ExtensionRecordForm)
        text = screen_text(app)
        assert "Not created" in text and "crew" in text

    run_pilot(app, scenario, size=SIZE)


def test_a_duplicate_key_stays_open_and_explains(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = _open(app)
        _fill_lift(form)
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == ["LP-1"]
        app.push_screen(
            ExtensionRecordForm(fake, SCOPE, app.form, actor="user:t"), app.results.append
        )
        await pilot.pause()
        _fill_lift(_open(app))
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == ["LP-1"] and isinstance(app.screen, ExtensionRecordForm)
        assert "Not created" in screen_text(app)

    run_pilot(app, scenario, size=SIZE)


def test_escape_cancels_and_creates_nothing(fake: FakeClient) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        _fill_lift(_open(app))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None] and fake.list_records(SCOPE) == []

    run_pilot(app, scenario, size=SIZE)
