"""Rules of the extension record form beyond the provided tests (P0-I8, supervisor)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Select, Switch
from tl_core.extypes.forms import TypeForm, TypeFormField
from tl_core.services.commands import CommandResult
from tl_tui.widgets.extension_form import ExtensionRecordForm

SIZE = (110, 110)


class Recording(FakeClient):
    """A fake that remembers what the form asked ``create_instance`` for."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict[str, Any]] = []

    def create_instance(self, type_name: str, **kwargs: Any) -> CommandResult:  # type: ignore[override]
        self.sent.append({"type_name": type_name, **kwargs})
        return super().create_instance(type_name, **kwargs)


class Host(App[None]):
    def __init__(self, client: FakeClient, form: TypeForm) -> None:
        super().__init__()
        self.client = client
        self.form = form
        self.results: list[str | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        self.push_screen(ExtensionRecordForm(self.client, SCOPE, self.form), self.results.append)


def _form(client: FakeClient, ref: str) -> TypeForm:
    detail = client.get_type(ref)
    assert detail.form is not None
    return detail.form


def _with_flag(form: TypeForm, *, required: bool) -> TypeForm:
    flag = TypeFormField(
        name="witnessed",
        path=f"psets.{form.pset}.witnessed",
        label="Witnessed",
        description="Seen by a second person",
        kind="bool",
        required=required,
        widget="checkbox",
        order=99,
    )
    group = form.groups[0].model_copy(update={"fields": [*form.groups[0].fields, flag]})
    return form.model_copy(update={"groups": [group, *form.groups[1:]]})


def _fill_observation(form: ExtensionRecordForm) -> None:
    for name, text in {
        "new_key": "SO-1",
        "new_title": "Spill",
        "ext_observed_on": "2026-10-02",
        "ext_location": "Unit 3",
    }.items():
        form.query_one(f"#{name} Input", Input).value = text
    form.query_one("#ext_category Select", Select).value = "near_miss"
    form.query_one("#ext_severity Select", Select).value = "high"


@pytest.fixture
def fake() -> Recording:
    client = Recording()
    client.add_example_type("co.acme.LiftPlan")
    client.add_example_type("co.acme.SafetyObservation")
    return client


def _created_values(client: Recording) -> dict[str, Any]:
    (call,) = client.sent
    return call["psets"]["co_acme_safety_observation"]


def test_an_untouched_optional_switch_is_left_unset(fake: Recording) -> None:
    form = _with_flag(_form(fake, "co.acme.SafetyObservation@1.0.0"), required=False)
    app = Host(fake, form)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.screen, ExtensionRecordForm)
        _fill_observation(app.screen)
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "witnessed" not in _created_values(fake)

    run_pilot(app, scenario, size=SIZE)


def test_a_switch_the_user_turned_on_is_sent(fake: Recording) -> None:
    form = _with_flag(_form(fake, "co.acme.SafetyObservation@1.0.0"), required=False)
    app = Host(fake, form)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.screen, ExtensionRecordForm)
        _fill_observation(app.screen)
        app.screen.query_one("#ext_witnessed Switch", Switch).value = True
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert _created_values(fake)["witnessed"] is True

    run_pilot(app, scenario, size=SIZE)


def test_a_required_switch_is_sent_as_shown(fake: Recording) -> None:
    form = _with_flag(_form(fake, "co.acme.SafetyObservation@1.0.0"), required=True)
    app = Host(fake, form)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.screen, ExtensionRecordForm)
        _fill_observation(app.screen)
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert _created_values(fake)["witnessed"] is False

    run_pilot(app, scenario, size=SIZE)


def test_an_object_backed_type_is_created_without_psets(fake: Recording) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, ExtensionRecordForm)
        for name, text in {
            "new_key": "LP-1",
            "new_title": "Lift",
            "ext_lift_date": "2026-11-03",
            "ext_crane": "CR-12",
            "ext_load_tonnes": "4.5",
        }.items():
            form.query_one(f"#{name} Input", Input).value = text
        form.query_one("#ext_risk_class Select", Select).value = "medium"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        (call,) = fake.sent
        assert call["psets"] is None and call["body"]["crane"] == "CR-12"

    run_pilot(app, scenario, size=SIZE)


def test_choosing_a_value_clears_the_required_mark_of_a_choice_field(fake: Recording) -> None:
    app = Host(fake, _form(fake, "co.acme.LiftPlan@1.0.0"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, ExtensionRecordForm)
        await pilot.press("ctrl+s")  # nothing filled in
        await pilot.pause()
        risk = form.query_one("#ext_risk_class")
        assert "Required" in "".join(str(s.render()) for s in risk.query(".field-error"))
        form.query_one("#ext_risk_class Select", Select).value = "medium"
        await pilot.pause()
        assert "Required" not in "".join(str(s.render()) for s in risk.query(".field-error"))
        assert "Fix the marked fields" in screen_text(app)

    run_pilot(app, scenario, size=SIZE)
