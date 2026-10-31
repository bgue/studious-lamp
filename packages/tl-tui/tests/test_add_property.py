"""The Add property form on the one read the API offers too (P1-UX3 round 4).

Pure functions first (offers, adoption, custom names), then the form as a screen: a person who may
adopt a set is offered to, anybody else sees the line greyed with the words the read gives, a custom
field's name is checked with the service's rule, and the ad-hoc fields a record holds show in the
set's custom section labelled ``custom``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import FakeClient
from helpers import run_pilot
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, OptionList, Static
from tl_core.addable import AddableProperties, AddableProperty, AdoptableSet, CustomRule
from tl_core.services.errors import RecordNotFoundError
from tl_tui.add_property import (
    CustomTarget,
    adopt_command,
    adopt_label,
    custom_key,
    custom_problem,
    custom_targets,
    offer_command,
    owners,
    standard_offers,
)
from tl_tui.widgets.add_property_form import (
    AddData,
    AddOutcome,
    AddPropertyScreen,
    _typed,  # pyright: ignore[reportPrivateUsage]
    load_add_property,
)
from tl_tui.widgets.psets_tab import adhoc_lines, psets_text

RECORD: dict[str, Any] = {
    "id": "01REC",
    "key": "P123-V-1",
    "scope": "project:P123",
    "type": "core.Record",
    "version": 3,
    "psets": {"valve_data": {"x": {"inspector_note": "ok", "size_class": 2}}},
}


def prop(
    pset: str = "valve_data", name: str = "size_in", label: str = "Nominal size", **more: Any
) -> AddableProperty:
    fields: dict[str, Any] = {
        "pset": pset,
        "set_label": pset.replace("_", " ").capitalize(),
        "package": "co.acme.engineering",
        "layer": "standard",
        "property": name,
        "path": f"psets.{pset}.{name}",
        "label": label,
        "description": "d",
        "type": "decimal",
        "unit": "[in_i]",
    }
    return AddableProperty(**{**fields, **more})


def sheet(*, can_adopt: bool) -> AdoptableSet:
    return AdoptableSet(
        pset="inspection_data",
        set_label="Inspection data",
        package="co.acme.engineering",
        version="3.3.0",
        project="P123",
        can_adopt=can_adopt,
        needs=None if can_adopt else "Needs a superuser to adopt this set for P123",
        properties=[
            prop("inspection_data", "inspected_on", "Inspected on", type="date", unit=None)
        ],
    )


def addable(*, can_adopt: bool = False, can_write: bool = True) -> AddableProperties:
    return AddableProperties(
        record_id="01REC",
        key="P123-V-1",
        type="core.Record",
        scope="project:P123",
        can_write=can_write,
        write_refusal=None if can_write else "the record is voided",
        standard=[prop()],
        adoptable=[sheet(can_adopt=can_adopt)],
        custom=[
            CustomRule(
                pset="valve_data",
                set_label="Valve data",
                package="co.acme.engineering",
                allowed=True,
                max_properties=2,
                used=1,
            ),
            CustomRule(
                pset="safety_data",
                set_label="Safety data",
                package="co.acme.engineering",
                allowed=False,
                used=0,
            ),
        ],
    )


# --- pure ------------------------------------------------------------------------------------


def test_offers_are_the_standard_ones_then_those_of_a_set_to_adopt() -> None:
    offers = standard_offers(addable(), RECORD)
    assert [(o.pset, o.prop.property, o.adopted) for o in offers] == [
        ("valve_data", "size_in", True),
        ("inspection_data", "inspected_on", False),
    ]
    assert offers[0].unit  # a UCUM code reads as its label
    assert "set not adopted" not in offers[0].line


def test_a_plain_user_gets_a_blocked_offer_and_a_superuser_one_to_adopt() -> None:
    plain = standard_offers(addable(can_adopt=False), RECORD)[1]
    assert plain.blocked == "Needs a superuser to adopt this set for P123"
    assert plain.line.endswith("(Needs a superuser to adopt this set for P123)")
    boss = standard_offers(addable(can_adopt=True), RECORD)[1]
    assert boss.blocked is None and boss.adopt is not None
    assert adopt_label(boss.adopt) == "Adopt Inspection data for P123"


def test_the_adoption_is_the_schema_registrys_command_for_the_set_in_the_projects_scope() -> None:
    command = adopt_command(sheet(can_adopt=True), actor="user:boss")
    assert type(command).__name__ == "AdoptSchemaSet"
    assert (command.project, command.package, command.version, command.pset) == (
        "P123",
        "co.acme.engineering",
        "3.3.0",
        "inspection_data",
    )
    assert command.scope == "project:P123" and command.source == "tui"


def test_a_property_of_a_set_to_adopt_is_written_with_its_own_layer_and_key() -> None:
    offer = standard_offers(addable(can_adopt=True), RECORD)[1]
    cmd = offer_command(RECORD, offer, "2026-10-30", actor="user:boss", scope="project:P123")
    assert (cmd.pset, cmd.layer, cmd.values) == (
        "inspection_data",
        "standard",
        {"inspected_on": "2026-10-30"},
    )
    assert cmd.expected_version == 3 and cmd.stream_id == "01REC"


def test_a_currency_placeholder_unit_reads_from_the_record() -> None:
    money = prop("cost_data", "amount", unit="{currency}")
    record = {**RECORD, "psets": {"cost_data": {"currency": "USD"}}}
    found = AddableProperties(**{**addable().model_dump(), "standard": [money]})
    assert standard_offers(found, record)[0].unit == "USD"
    assert standard_offers(found, {**RECORD, "psets": {}})[0].unit == ""


def test_custom_targets_are_the_sets_that_allow_one_and_know_when_they_are_full() -> None:
    targets = custom_targets(addable())
    assert [(t.pset, t.used, t.limit, t.full) for t in targets] == [("valve_data", 1, 2, False)]
    assert targets[0].line == "Valve data  ·  1 of 2 used"
    assert CustomTarget("v", "V", 2, 2, "p", "custom").full
    assert not CustomTarget("v", "V", 99, None, "p", "custom").full


@pytest.mark.parametrize(
    ("typed", "key"),
    [("Fat witness by", "fat_witness_by"), ("  Lead time (days) ", "lead_time_days"), ("???", "")],
)
def test_a_typed_name_becomes_a_key(typed: str, key: str) -> None:
    assert custom_key(typed) == key


def test_the_name_is_checked_with_the_services_rule_before_the_command_goes() -> None:
    target = custom_targets(addable())[0]
    assert custom_problem("Fat witness by", target) is None
    assert custom_problem("???", target) == "Enter a name."
    assert "starting with a letter" in (custom_problem("1st check", target) or "")
    assert "reserved" in (custom_problem("prj_note", target) or "")
    full = CustomTarget("valve_data", "Valve data", 2, 2, "p", "custom")
    assert "at most 2" in (custom_problem("fine", full) or "")


def test_a_number_typed_stays_a_number_only_when_it_reads_back_the_same() -> None:
    assert _typed("14") == 14 and isinstance(_typed("14"), int)
    assert _typed("2.5") == 2.5
    assert (
        _typed("007") == "007" and _typed("1e3") == "1e3" and _typed("2026-10-30") == "2026-10-30"
    )
    assert _typed("nan") == "nan" and _typed("inf") == "inf" and _typed("hello") == "hello"


def test_owners_name_each_package_once() -> None:
    assert owners(addable()) == [("co.acme.engineering", "Valve data")]


# --- the tab -------------------------------------------------------------------------------------


def test_the_tab_shows_a_held_ad_hoc_field_in_the_custom_section_labelled_custom() -> None:
    client = FakeClient()
    meta = client.metadata
    group = next(g for g in meta.psets if g.name == "valve_data")
    group = group.model_copy(update={"custom_allowed": True})
    lines = adhoc_lines(group, RECORD["psets"])
    assert [line.split()[:2] for line in lines] == [["Inspector", "note"], ["Size", "class"]]
    assert all("custom" in line for line in lines)
    assert "ok" in lines[0] and "2" in lines[1]
    # a set that takes no custom section shows none, and a declared field is not shown twice
    assert adhoc_lines(group.model_copy(update={"custom_allowed": False}), RECORD["psets"]) == []
    meta = meta.model_copy(update={"psets": [group, *[g for g in meta.psets if g is not group]]})
    client.add_stored_record("x", "P123-V-1", "core.Record", "Valve")
    text = psets_text(
        meta, {**RECORD, "psets": RECORD["psets"]}, client.conformance("x"), technical=False
    )
    assert "Inspector note" in text and text.count("Inspector note") == 1


# --- the screen ----------------------------------------------------------------------------------


class FormApp(App[None]):
    def __init__(self, screen: AddPropertyScreen) -> None:
        super().__init__()
        self.form = screen
        self.outcome: AddOutcome | None = None
        self.closed = False

    def on_mount(self) -> None:
        self.push_screen(self.form, self.got)

    def got(self, outcome: AddOutcome | None) -> None:
        self.outcome, self.closed = outcome, True


def drive(
    data: AddData,
    steps: Callable[[Pilot[Any], FormApp, AddPropertyScreen], Awaitable[None]],
    **options: Any,
) -> FormApp:
    screen = AddPropertyScreen(data, actor="user:boss", scope="project:P123", **options)
    app = FormApp(screen)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await steps(pilot, app, screen)

    run_pilot(app, go, size=(110, 36))
    return app


def status(screen: AddPropertyScreen) -> str:
    return str(screen.query_one("#ap-status", Static).render())


def test_the_form_reads_the_record_and_what_can_be_added_and_a_hidden_record_is_missing() -> None:
    client = FakeClient()
    client.add_stored_record("01REC", "P123-V-1", "core.Record", "Valve")
    client.set_addable("01REC", addable())
    data = load_add_property(client, "01REC")
    assert data.record["id"] == "01REC" and data.addable.standard[0].property == "size_in"
    client.hide_record("01REC")
    with pytest.raises(RecordNotFoundError):
        client.addable_properties("01REC")
    with pytest.raises(RecordNotFoundError):
        load_add_property(client, "01NONE")


def test_a_plain_user_sees_the_set_to_adopt_greyed_and_cannot_pick_it() -> None:
    data = AddData(RECORD, addable(can_adopt=False))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: AddPropertyScreen) -> None:
        await pilot.press("1")  # From the standard
        await pilot.pause()
        listing = screen.query_one("#ap-offers", OptionList)
        assert listing.get_option_at_index(1).disabled
        assert not listing.get_option_at_index(0).disabled
        assert "Needs a superuser to adopt this set for P123" in str(
            listing.get_option_at_index(1).prompt
        )
        assert screen.step == "standard" and not app.closed

    drive(data, steps)


def test_a_superuser_adopts_then_the_form_hands_back_the_set_and_the_property() -> None:
    data = AddData(RECORD, addable(can_adopt=True))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: AddPropertyScreen) -> None:
        await pilot.press("1")
        await pilot.pause()
        listing = screen.query_one("#ap-offers", OptionList)
        assert not listing.get_option_at_index(1).disabled
        listing.highlighted = 1
        listing.action_select()
        await pilot.pause()
        assert screen.step == "adopt"
        options = screen.query_one("#ap-adopt-list", OptionList)
        assert str(options.get_option_at_index(0).prompt) == "Adopt Inspection data for P123"
        options.highlighted = 0
        options.action_select()
        await pilot.pause()

    app = drive(data, steps, is_admin=True)
    assert app.outcome is not None and app.outcome.adopt is not None and app.outcome.command is None
    assert app.outcome.adopt.project == "P123" and app.outcome.adopt.version == "3.3.0"
    assert app.outcome.then == ("inspection_data", "inspected_on")


def test_after_adoption_the_form_opens_on_the_property_to_enter_its_value() -> None:
    adopted = addable(can_adopt=True)
    after = AddableProperties(
        **{
            **adopted.model_dump(),
            "standard": [*adopted.standard, *adopted.adoptable[0].properties],
            "adoptable": [],
        }
    )

    async def steps(pilot: Pilot[Any], app: FormApp, screen: AddPropertyScreen) -> None:
        await pilot.pause()
        assert screen.step == "value" and screen.offer is not None
        assert screen.offer.prop.property == "inspected_on"

    drive(AddData(RECORD, after), steps, preselect=("inspection_data", "inspected_on"))


def test_a_bad_custom_name_is_said_before_anything_is_sent() -> None:
    data = AddData(RECORD, addable())

    async def steps(pilot: Pilot[Any], app: FormApp, screen: AddPropertyScreen) -> None:
        await pilot.press("2")  # Custom field
        await pilot.pause()
        screen.query_one("#ap-cname", Input).value = "prj_note"
        screen.query_one("#ap-cvalue", Input).value = "v"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "reserved" in status(screen) and not app.closed

    drive(data, steps)


def test_a_good_custom_field_goes_out_as_one_command_with_a_number_kept_as_a_number() -> None:
    data = AddData(RECORD, addable())

    async def steps(pilot: Pilot[Any], app: FormApp, screen: AddPropertyScreen) -> None:
        await pilot.press("2")
        await pilot.pause()
        screen.query_one("#ap-cname", Input).value = "Lead time days"
        screen.query_one("#ap-cvalue", Input).value = "14"
        await pilot.press("ctrl+s")
        await pilot.pause()

    app = drive(data, steps)
    assert app.outcome is not None and app.outcome.command is not None
    cmd = app.outcome.command
    assert (cmd.pset, cmd.layer, cmd.values) == ("valve_data", "custom", {"x.lead_time_days": 14})


def test_a_record_that_cannot_be_written_says_why_and_sends_nothing() -> None:
    data = AddData(RECORD, addable(can_write=False))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: AddPropertyScreen) -> None:
        assert "the record is voided" in status(screen)
        await pilot.press("2")
        await pilot.pause()
        screen.query_one("#ap-cname", Input).value = "fine"
        screen.query_one("#ap-cvalue", Input).value = "v"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "voided" in status(screen) and not app.closed

    drive(data, steps)
