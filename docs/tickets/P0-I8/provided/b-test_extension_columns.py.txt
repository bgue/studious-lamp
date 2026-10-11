"""Grid columns of an extension type (P0-I8-T24)."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from tl_core.extypes.errors import UnknownTypeError
from tl_core.extypes.service import TypeSummary
from tl_tui.extension_columns import (
    columns_for_form,
    columns_for_type,
    form_for_type,
    newest_active,
)

LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
LIFT_PSET = "co_acme_lift_plan"


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.add_example_type(LIFT)
    client.add_example_type(OBSERVATION)
    return client


def test_the_columns_of_an_object_backed_type_are_its_index_fields(fake: FakeClient) -> None:
    form = fake.get_type("co.acme.LiftPlan@1.0.0").form
    assert form is not None
    columns = columns_for_form(form)
    assert [c.key for c in columns] == [
        "key",
        "title",
        f"psets.{LIFT_PSET}.lift_date",
        f"psets.{LIFT_PSET}.crane",
        f"psets.{LIFT_PSET}.load_tonnes",
        f"psets.{LIFT_PSET}.risk_class",
        "status",
        "version",
    ]
    assert [c.label for c in columns][2:6] == ["Lift date", "Crane", "Load (t)", "Risk class"]


def test_numbers_are_right_aligned_and_widths_are_bounded(fake: FakeClient) -> None:
    form = fake.get_type("co.acme.LiftPlan@1.0.0").form
    assert form is not None
    by_key = {c.key: c for c in columns_for_form(form)}
    assert by_key[f"psets.{LIFT_PSET}.load_tonnes"].align == "right"
    assert by_key[f"psets.{LIFT_PSET}.crane"].align == "left"
    for column in by_key.values():
        assert 3 <= column.width <= 24
    assert by_key[f"psets.{LIFT_PSET}.lift_date"].width >= 10


def test_slots_stored_only_in_the_body_and_unknown_names_get_no_column(fake: FakeClient) -> None:
    form = fake.get_type("co.acme.LiftPlan@1.0.0").form
    assert form is not None
    wider = form.model_copy(
        update={"grid_columns": ["crane", "method_statement", "no_such_slot", "crew"]}
    )
    assert [c.key for c in columns_for_form(wider)] == [
        "key",
        "title",
        f"psets.{LIFT_PSET}.crane",
        "status",
        "version",
    ]


def test_a_managed_type_shows_its_grid_columns(fake: FakeClient) -> None:
    columns = columns_for_type(fake, OBSERVATION)
    assert columns is not None
    assert [c.label for c in columns] == [
        "Key",
        "Title",
        "Observed on",
        "Category",
        "Severity",
        "Location",
        "Status",
        "Ver",
    ]


def test_core_records_and_unknown_types_keep_the_default_columns(fake: FakeClient) -> None:
    assert columns_for_type(fake, "core.Record") is None
    assert columns_for_type(fake, None) is None
    assert columns_for_type(fake, "co.acme.Nope") is None


def test_a_deprecated_type_keeps_the_default_columns() -> None:
    client = FakeClient()
    client.add_example_type(LIFT, status="deprecated")
    assert columns_for_type(client, LIFT) is None


def test_the_newest_active_version_wins() -> None:
    client = FakeClient()
    client.add_example_type(LIFT, version="1.2.0")
    client.add_example_type(LIFT, version="1.10.0")
    client.add_example_type(LIFT, version="2.0.0", status="deprecated")
    chosen = newest_active(client.list_types(), LIFT)
    assert isinstance(chosen, TypeSummary) and chosen.version == "1.10.0"
    assert newest_active(client.list_types(), "co.acme.Nope") is None
    assert newest_active([], LIFT) is None


def test_a_client_that_refuses_gives_the_default_columns(fake: FakeClient) -> None:
    def refuse(type_ref: str) -> object:
        raise UnknownTypeError(f"no registration {type_ref!r}")

    fake.get_type = refuse  # type: ignore[method-assign,assignment]
    assert columns_for_type(fake, LIFT) is None


def test_form_for_type_gives_the_form_of_the_newest_active_version(fake: FakeClient) -> None:
    form = form_for_type(fake, LIFT)
    assert form is not None and form.type_ref == "co.acme.LiftPlan@1.0.0"
    assert form_for_type(fake, "core.Record") is None
    assert form_for_type(fake, None) is None
    assert form_for_type(fake, "co.acme.Nope") is None
