"""HTTP client: forms reads and the write door (V3-F1a). Each read equals the embedded client's
answer; a hidden or missing record is one ``RecordNotFoundError``; the intake reads are stubs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from harness import ALICE, Harness
from tl_core.forms.jsonschema import to_json_schema
from tl_core.services.errors import RecordNotFoundError
from tl_tui.embedded import EmbeddedClient

_FORMS_TESTS = str(Path(__file__).resolve().parents[2] / "tl-modules/forms/tests")
if _FORMS_TESTS not in sys.path:
    sys.path.insert(0, _FORMS_TESTS)

from forms_world import SCOPE, World, answer, two_fields  # noqa: E402

PROJECT = SCOPE.removeprefix("project:")


@pytest.fixture
def seeded(harness: Harness) -> tuple[Harness, World, str, str]:
    world = World(harness.target or harness.db)
    world.people()
    template = world.template(fields=two_fields())
    sent = world.submit("uma", template, answers=[answer("topic", "Ladders")])
    return harness, world, template, str(sent.key)


def test_template_and_submission_reads_equal_the_embedded_answers(
    seeded: tuple[Harness, World, str, str],
) -> None:
    h, _world, template, key = seeded
    api = h.api()
    embedded = EmbeddedClient(h.backend, actor=ALICE)
    page = api.list_form_templates()
    assert page == embedded.list_form_templates() and page.total == 1
    row = page.rows[0]
    assert row.id == template
    detail: Any = api.get_form_template(str(row.key), int(row.version or 1))
    assert detail == embedded.get_form_template(str(row.key), int(row.version or 1))
    fields = detail["fields"]
    schema = api.get_form_template(str(row.key), 1, projection="jsonschema")
    assert schema == to_json_schema(fields, 2)
    survey = api.get_form_template(str(row.key), 1, projection="surveyjs")
    assert survey == embedded.get_form_template(str(row.key), 1, projection="surveyjs")
    subs = api.list_form_submissions(PROJECT)
    assert subs == embedded.list_form_submissions(PROJECT) and subs.total == 1
    got = api.get_form_submission(PROJECT, key)
    assert got == embedded.get_form_submission(PROJECT, key)
    assert got.answers[0]["value"] == "Ladders"


def test_a_missing_record_is_one_not_found_on_both_clients(
    seeded: tuple[Harness, World, str, str],
) -> None:
    h, _world, _template, _key = seeded
    api = h.api()
    embedded = EmbeddedClient(h.backend, actor=ALICE)
    for client in (api, embedded):
        with pytest.raises(RecordNotFoundError):
            client.get_form_submission(PROJECT, "P123-FRM-9999")
        with pytest.raises(RecordNotFoundError):
            client.get_form_template("TPL-9999", 1)
        with pytest.raises(RecordNotFoundError):
            client.get_form_for(PROJECT, "NOPE-1")


def test_the_intake_reads_are_not_built_yet(seeded: tuple[Harness, World, str, str]) -> None:
    h, _world, _template, _key = seeded
    for client in (h.api(), EmbeddedClient(h.backend, actor=ALICE)):
        with pytest.raises(NotImplementedError):
            client.list_intake_items(PROJECT)
        with pytest.raises(NotImplementedError):
            client.get_intake_item(PROJECT, "x")
