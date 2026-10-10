"""`tl proposal ls|show|accept|reject` on a temporary ledger (P0-I6-T20). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.sqlite.uow import open_uow
from tl_cli.main import app
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.psets import SetPsetValues
from tl_core.services.queries import get_record
from tl_core.services.records import handle_update_record
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
P = "P123"
SCOPE = f"project:{P}"
AGENT = "agent:triage"
KEY = "P123-REC-0042"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.delenv("TL_AGENT_DAILY_PROPOSALS", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def factory(env: dict[str, str]) -> Any:
    def open_one(readonly: bool = False) -> Any:
        return open_uow(Path(env["TL_DB"]), readonly=readonly)

    return open_one


def propose_create(env: dict[str, str], key: str = KEY, scope: str = SCOPE) -> str:
    command = CreateRecord(
        actor=AGENT,
        source="mcp:triage",
        scope=scope,
        record_type="core.Record",
        title="Weld NCR",
        key=key,
    )
    view = proposals.submit(
        factory(env), tool="create_record", agent=AGENT, command=command, summary=f"Create {key}"
    )
    return view.proposal_id


def make_record(env: dict[str, str], title: str = "Spool") -> str:
    result = run(env, "record", "create", "--project", P, "--title", title)
    assert result.exit_code == 0, result.output
    key = next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))
    return key


def record_id(env: dict[str, str], key: str) -> str:
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        row = get_record(uow, SCOPE, key)
    assert row is not None
    return str(row["id"])


def test_the_proposal_group_is_in_the_help() -> None:
    assert "proposal" in runner.invoke(app, ["--help"]).stdout
    helped = runner.invoke(app, ["proposal", "--help"]).stdout
    for name in ("ls", "show", "accept", "reject"):
        assert name in helped


def test_ls_lists_pending_proposals_oldest_first_in_two_space_columns(
    env: dict[str, str],
) -> None:
    first = propose_create(env, "P123-REC-0001")
    second = propose_create(env, "P123-REC-0002")
    propose_create(env, "P999-REC-0001", scope="project:P999")
    result = run(env, "proposal", "ls", "--project", P)
    assert result.exit_code == 0 and result.exception is None, result.output
    rows = [line.split("  ") for line in result.stdout.splitlines()]
    assert rows == [
        [first, "pending", AGENT, "create_record", "Create P123-REC-0001"],
        [second, "pending", AGENT, "create_record", "Create P123-REC-0002"],
    ]


def test_ls_filters_by_status_and_agent_and_limits(env: dict[str, str]) -> None:
    first = propose_create(env, "P123-REC-0001")
    propose_create(env, "P123-REC-0002")
    assert run(env, "proposal", "reject", first, "--reason", "no").exit_code == 0
    assert len(run(env, "proposal", "ls", "--project", P).stdout.splitlines()) == 1
    rejected = run(env, "proposal", "ls", "--project", P, "--status", "rejected")
    assert [line.split("  ")[:2] for line in rejected.stdout.splitlines()] == [[first, "rejected"]]
    everything = run(env, "proposal", "ls", "--project", P, "--status", "all")
    assert len(everything.stdout.splitlines()) == 2
    assert run(env, "proposal", "ls", "--project", P, "--agent", "agent:other").stdout == ""
    one = run(env, "proposal", "ls", "--project", P, "--status", "all", "-n", "1")
    assert len(one.stdout.splitlines()) == 1


def test_ls_needs_exactly_one_scope_and_a_known_status(env: dict[str, str]) -> None:
    for args, message in (
        (["proposal", "ls"], "exactly one of --project and --company"),
        (["proposal", "ls", "--project", P, "--company"], "exactly one of --project and --company"),
        (["proposal", "ls", "--project", P, "--status", "later"], "--status must be"),
    ):
        result = run(env, *args)
        assert result.exit_code == 1 and result.exception is not None, args
        assert message in result.stderr, args
    assert run(env, "proposal", "ls", "--company").exit_code == 0


def test_show_prints_the_proposal_and_the_command_it_would_run(env: dict[str, str]) -> None:
    pid = propose_create(env)
    result = run(env, "proposal", "show", pid)
    assert result.exit_code == 0 and result.exception is None, result.output
    lines = result.stdout.splitlines()
    assert lines[:7] == [
        f"proposal {pid}",
        f"scope {SCOPE}",
        "status pending",
        f"agent {AGENT}",
        "tool create_record",
        f"summary Create {KEY}",
        "command CreateRecord",
    ]
    assert f'  key "{KEY}"' in lines and '  title "Weld NCR"' in lines
    assert '  record_type "core.Record"' in lines
    assert not any(line.startswith(("  actor", "  source", "  causation_id")) for line in lines)
    assert not any(line.startswith("  description") for line in lines)  # null fields are left out
    assert not any(line.startswith(("decided by", "reason", "result")) for line in lines)
    assert [line.split()[0] for line in lines[7:]] == sorted(line.split()[0] for line in lines[7:])


def test_show_of_a_decided_proposal_adds_who_why_and_what_resulted(env: dict[str, str]) -> None:
    accepted, rejected = propose_create(env, "P123-REC-0001"), propose_create(env, "P123-REC-0002")
    run(env, "proposal", "accept", accepted, "--actor", "user:alice")
    run(env, "proposal", "reject", rejected, "--reason", "Duplicate", "--actor", "user:bob")
    done = run(env, "proposal", "show", accepted).stdout.splitlines()
    assert "status accepted" in done and "decided by user:alice" in done
    assert any(line.startswith("result ") and len(line.split()[1]) == 26 for line in done)
    no = run(env, "proposal", "show", rejected).stdout.splitlines()
    assert "status rejected" in no and "decided by user:bob" in no and "reason Duplicate" in no


def test_accept_runs_the_command_as_the_person_with_the_agent_as_source(
    env: dict[str, str],
) -> None:
    pid = propose_create(env)
    result = run(env, "proposal", "accept", pid, "--actor", "user:alice")
    assert result.exit_code == 0 and result.exception is None, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == f"accepted {pid}" and lines[1].startswith("result ")
    new_id = lines[1].split()[1]
    assert new_id == record_id(env, KEY)
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        (made,) = uow.ledger.read_stream(new_id)
        decided = uow.ledger.read_stream(pid)[1]
    assert (made.actor, made.source) == ("user:alice", "mcp:triage")
    assert (decided.event_type, decided.actor, decided.source) == (
        "Proposal.Accepted",
        "user:alice",
        "cli",
    )
    assert run(env, "proposal", "ls", "--project", P).stdout == ""


def test_the_default_actor_is_user_dev(env: dict[str, str]) -> None:
    pid = propose_create(env)
    assert run(env, "proposal", "accept", pid).exit_code == 0
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        assert uow.ledger.read_stream(pid)[1].actor == "user:dev"


def test_accepting_twice_or_an_unknown_id_is_an_error(env: dict[str, str]) -> None:
    pid = propose_create(env)
    assert run(env, "proposal", "accept", pid).exit_code == 0
    again = run(env, "proposal", "accept", pid)
    assert again.exit_code == 1 and again.exception is not None
    assert again.stderr.startswith("error: ") and "already accepted" in again.stderr
    unknown = run(env, "proposal", "accept", "01NOSUCHPROPOSAL")
    assert unknown.exit_code == 1 and "no proposal" in unknown.stderr
    assert run(env, "proposal", "show", "01NOSUCHPROPOSAL").exit_code == 1


def test_an_agent_cannot_decide_from_the_command_line(env: dict[str, str]) -> None:
    pid = propose_create(env)
    for args in (
        ["proposal", "accept", pid, "--actor", AGENT],
        ["proposal", "reject", pid, "--reason", "mine", "--actor", AGENT],
    ):
        result = run(env, *args)
        assert result.exit_code == 1 and "only a person" in result.stderr, args
    assert f"{pid}  pending" in run(env, "proposal", "ls", "--project", P).stdout


def test_a_proposal_the_record_has_outgrown_fails_loudly_and_changes_nothing(
    env: dict[str, str],
) -> None:
    key = make_record(env)
    rid = record_id(env, key)
    command = SetPsetValues(
        actor=AGENT,
        source="mcp:triage",
        scope=SCOPE,
        stream_id=rid,
        expected_version=1,
        pset="valve_data",
        layer="standard",
        values={"manufacturer": "Acme"},
    )
    view = proposals.submit(
        factory(env), tool="update_psets", agent=AGENT, command=command, summary="Set maker"
    )
    with open_uow(Path(env["TL_DB"])) as uow:  # a person edits the record first
        handle_update_record(
            uow,
            UpdateRecord(
                actor="user:bob",
                source="cli",
                scope=SCOPE,
                stream_id=rid,
                expected_version=1,
                changes={"title": "Renamed"},
            ),
        )
    result = run(env, "proposal", "accept", view.proposal_id, "--actor", "user:alice")
    assert result.exit_code == 1 and result.exception is not None
    assert result.stdout.splitlines() == [f"failed {view.proposal_id}"]
    assert result.stderr.startswith("error: ") and "ConcurrencyError" in result.stderr
    shown = run(env, "proposal", "show", view.proposal_id).stdout.splitlines()
    assert "status failed" in shown and "decided by user:alice" in shown
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        types = [e.event_type for e in uow.ledger.read_stream(rid)]
    assert "Pset.ValuesSet" not in types


def test_role_options_reach_the_workflow_guard(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_core.services.workflow import TransitionWorkflow
    from tl_core.workflow.definition import WorkflowDefinition
    from tl_core.workflow.loader import WorkflowRegistry
    from tl_core.workflow.provider import use_workflows

    flow = {
        "id": "t.flow",
        "version": 1,
        "record_type": "core.Record",
        "initial_state": "Draft",
        "states": [{"name": "Draft"}, {"name": "Done"}],
        "transitions": [
            {
                "name": "finish",
                "from": ["Draft"],
                "to": "Done",
                "guards": [{"kind": "roles", "any_of": ["manager"]}],
            }
        ],
    }
    with use_workflows(WorkflowRegistry([WorkflowDefinition.model_validate(flow)])):
        rid = record_id(env, make_record(env))
        command = TransitionWorkflow(
            actor=AGENT,
            source="x",
            scope=SCOPE,
            stream_id=rid,
            expected_version=1,
            transition="finish",
        )

        def propose() -> str:
            made = proposals.submit(
                factory(env), tool="transition_workflow", agent=AGENT, command=command, summary="s"
            )
            return made.proposal_id

        without = run(env, "proposal", "accept", propose())
        assert without.exit_code == 1 and "GuardFailedError" in without.stderr
        with_role = run(env, "proposal", "accept", propose(), "--role", "manager")
        assert with_role.exit_code == 0, with_role.output
        assert with_role.stdout.startswith("accepted ")


def test_reject_records_the_reason_and_never_runs_the_command(env: dict[str, str]) -> None:
    pid = propose_create(env)
    result = run(env, "proposal", "reject", pid, "--reason", "Duplicate of NCR-0040")
    assert result.exit_code == 0 and result.exception is None, result.output
    assert result.stdout.splitlines() == [f"rejected {pid}"]
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        event = uow.ledger.read_stream(pid)[1]
    assert (event.event_type, event.actor, event.source) == ("Proposal.Rejected", "user:dev", "cli")
    assert event.payload["reason"] == "Duplicate of NCR-0040"
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        assert get_record(uow, SCOPE, KEY) is None


def test_reject_needs_a_reason(env: dict[str, str]) -> None:
    pid = propose_create(env)
    assert run(env, "proposal", "reject", pid).exit_code != 0  # the option is required
    blank = run(env, "proposal", "reject", pid, "--reason", "  ")
    assert blank.exit_code == 1 and blank.exception is not None and "reason" in blank.stderr
    late = run(env, "proposal", "reject", "01NOSUCH", "--reason", "x")
    assert late.exit_code == 1 and "no proposal" in late.stderr
