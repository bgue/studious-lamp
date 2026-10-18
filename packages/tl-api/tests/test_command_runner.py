"""The command runner entry points hand to the integration engines (FANOUT D14)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import create_schema, open_uow
from tl_api.commands import COMMANDS, TableCommandRunner, command_runner
from tl_core.auth import accounts
from tl_core.integration.contract import AUTOMATION_COMMANDS, CommandRunner
from tl_core.services.commands import CreateRecord
from tl_core.services.feed import PostToFeed

SCOPE = "project:P123"


def test_the_runner_is_a_command_runner() -> None:
    assert isinstance(command_runner(), CommandRunner)


def test_it_knows_every_command_of_the_table_and_nothing_else() -> None:
    runner = command_runner()
    for spec in COMMANDS:
        assert runner.model_of(spec.name) is spec.model
    assert runner.model_of("NoSuchCommand") is None
    assert runner.model_of("") is None
    assert runner.access_of("NoSuchCommand") is None


def test_the_access_of_a_command_comes_from_its_declaration() -> None:
    runner = command_runner()
    assert runner.access_of("CreateRecord") == "user"
    assert runner.access_of("AdminRetractLink") == "admin"
    assert runner.access_of("IssueRevision") == "controller"


def test_a_company_command_counts_as_admin_so_automation_never_runs_it() -> None:
    runner = command_runner()
    company = [s for s in COMMANDS if s.access == "company"]
    assert company, "the table has a company command"
    for spec in company:
        assert runner.access_of(spec.name) == "admin"


def test_every_automation_command_that_exists_is_a_user_command() -> None:
    """Automation is declared ``user`` or ``controller``: an admin command never qualifies."""
    runner = command_runner()
    present = {name for name in AUTOMATION_COMMANDS if runner.model_of(name) is not None}
    assert {"CreateRecord", "UpdateRecord", "SetPsetValues", "AddLink", "SuggestLink"} <= present
    for name in present:
        assert runner.access_of(name) in ("user", "controller"), name


def test_a_table_of_its_own_limits_what_the_runner_knows() -> None:
    only = TableCommandRunner(tuple(s for s in COMMANDS if s.name == "PostToFeed"))
    assert only.model_of("PostToFeed") is PostToFeed
    assert only.model_of("CreateRecord") is None


def test_run_calls_the_handler_of_the_commands_type(new_db: Callable[[], str | Path]) -> None:
    db = new_db()
    create_schema(db)
    command = CreateRecord(
        actor="user:u", source="test", scope=SCOPE, record_type="core.Record", title="T", key="K-1"
    )
    with open_uow(db) as uow:
        accounts.create_account(
            uow,
            username="u",
            display_name="U",
            kind="person",
            roles=["user"],
            password=None,
            by="user:root",
        )
    with open_uow(db) as uow:
        made = command_runner().run(uow, command)
    assert made.key == "K-1"


def test_run_refuses_a_command_the_table_does_not_list() -> None:
    only = TableCommandRunner(tuple(s for s in COMMANDS if s.name == "PostToFeed"))
    command = CreateRecord(
        actor="user:u", source="test", scope=SCOPE, record_type="core.Record", title="T"
    )
    with pytest.raises(KeyError):
        only.run(None, command)  # type: ignore[arg-type]
