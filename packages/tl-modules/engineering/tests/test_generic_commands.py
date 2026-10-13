"""The generic record commands refuse the registry records and allow a tag only what it lists.

ADR-0010 addendum: a module record's envelope and typed fields change through the module's own
commands. Without this check, any person could `UpdateRecord` a tag class or a code list (a title,
a description) and the event would sit on the registry record's stream with the wrong stream type.
"""

from __future__ import annotations

from typing import Any

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import UpdateRecord, VoidRecord
from tl_core.services.errors import UnsupportedRecordTypeError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_update_record, handle_void_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_engineering.handlers.tags import CreateTag, handle_create_tag
from tl_mod_engineering.testing import seed_registry

pytestmark = pytest.mark.usefixtures("fixture_schemas")

COMPANY: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "company"}
PROJECT: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "project:P123"}
# stream ids seed_registry gives its registry records
REGISTRY = {
    "engineering.CodeList": "S-Area",
    "engineering.CodeValue": "V-47",
    "engineering.Mnemonic": "S-FV",
    "engineering.NumberingPattern": "S-tag",
    "engineering.TagClass": "C-ControlValve",
}


@pytest.fixture
def ledger(db: DbTarget) -> DbTarget:
    seed_registry(db)
    return db


@pytest.mark.parametrize(("record_type", "stream_id"), sorted(REGISTRY.items()))
def test_no_generic_command_changes_a_registry_record(
    ledger: DbTarget, record_type: str, stream_id: str
) -> None:
    runs: list[Any] = [
        lambda uow: handle_update_record(
            uow,
            UpdateRecord(
                **COMPANY, stream_id=stream_id, expected_version=2, changes={"title": "hijacked"}
            ),
        ),
        lambda uow: handle_void_record(
            uow, VoidRecord(**COMPANY, stream_id=stream_id, expected_version=2, reason="r")
        ),
        lambda uow: handle_set_pset_values(
            uow,
            SetPsetValues(
                **COMPANY,
                stream_id=stream_id,
                expected_version=2,
                pset="valve_data",
                layer="standard",
                values={"manufacturer": "Acme"},
            ),
        ),
        lambda uow: handle_transition_workflow(
            uow,
            TransitionWorkflow(
                **COMPANY, stream_id=stream_id, expected_version=2, transition="submit"
            ),
        ),
        lambda uow: handle_add_link(uow, AddLink(**COMPANY, from_id=stream_id, to_id="S-tag")),
    ]
    for run in runs:
        with pytest.raises(UnsupportedRecordTypeError, match=record_type):
            with open_uow(ledger) as uow:
                run(uow)
    with open_uow(ledger, readonly=True) as uow:
        title = (
            uow.conn()
            .exec_driver_sql(f"SELECT title FROM cur_core_record WHERE id = '{stream_id}'")
            .scalar_one()
        )
    assert title != "hijacked"


def test_a_tag_allows_the_generic_commands_its_module_lists(ledger: DbTarget) -> None:
    with open_uow(ledger) as uow:
        made = handle_create_tag(
            uow, CreateTag(**PROJECT, number="47-FV-1001", class_code="ControlValve")
        )
    with open_uow(ledger) as uow:
        updated = handle_update_record(
            uow,
            UpdateRecord(
                **PROJECT,
                stream_id=made.stream_id,
                expected_version=made.version,
                changes={"title": "Feed gas"},
            ),
        )
    with open_uow(ledger) as uow:
        handle_set_pset_values(
            uow,
            SetPsetValues(
                **PROJECT,
                stream_id=made.stream_id,
                expected_version=updated.version,
                pset="valve_data",
                layer="standard",
                values={"manufacturer": "Acme"},
            ),
        )
    with pytest.raises(UnsupportedRecordTypeError, match="VoidRecord"):
        with open_uow(ledger) as uow:
            handle_void_record(
                uow,
                VoidRecord(**PROJECT, stream_id=made.stream_id, expected_version=4, reason="r"),
            )


def proposal(stream_id: str) -> SetPsetValues:
    return SetPsetValues(
        actor="agent:triage",
        source="mcp:triage",
        **{"scope": "company"},
        stream_id=stream_id,
        expected_version=2,
        pset="valve_data",
        layer="standard",
        values={"manufacturer": "Acme"},
    )


def test_a_proposal_that_targets_a_registry_record_is_refused_when_proposed_and_when_accepted(
    ledger: DbTarget,
) -> None:
    from collections.abc import Callable

    from tl_core.services import proposals

    def factory(readonly: bool = False) -> Any:
        return open_uow(ledger, readonly=readonly)

    submit: Callable[..., Any] = proposals.submit
    with pytest.raises(UnsupportedRecordTypeError, match="engineering.TagClass"):
        submit(
            factory,
            tool="update_psets",
            agent="agent:triage",
            command=proposal("C-ControlValve"),
            summary="set a pset",
        )
    # a proposal stored without the pre-check (an older one, or a bypass) fails at accept
    with open_uow(ledger) as uow:
        made = proposals.propose(
            uow,
            tool="update_psets",
            agent="agent:triage",
            command=proposal("C-ControlValve"),
            summary="set a pset",
        )
    decided = proposals.accept_or_fail(factory, proposal_id=made.proposal_id, by="user:kim")
    assert decided.status == "failed"
    assert "UnsupportedRecordTypeError" in (decided.reason or "")
    with open_uow(ledger, readonly=True) as uow:
        assert (
            uow.conn()
            .exec_driver_sql(
                "SELECT COUNT(*) FROM events WHERE event_type = 'Pset.ValuesSet' "
                "AND stream_id = 'C-ControlValve'"
            )
            .scalar_one()
            == 0
        )
