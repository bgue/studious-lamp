"""`tl agent stop`, `resume` and `stopped` against a temporary SQLite ledger (P2-X2-T02).

Modelled on test_cli_admin_roles.py: the admin `root` is signed in, `alice` is a plain user, and
`triage` is an agent account that has filed one proposal. A plain user and a session-less caller
are refused by all three commands, and nothing is written for a refused command.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from auth_support import GOOD, bootstrap, new_ledger, rows, separate_session, sign_in
from auth_support import run as tl
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
from tl_core.services.links import AddLink
from tl_core.services.records import handle_create_record
from tl_core.util import new_ulid

AGENT = "agent:triage"
TABLE = "agent_stop_cli_class"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A ledger with `root` signed in, a plain user `alice`, and the agent `triage` filing once."""
    values = new_ledger(tmp_path)
    assert bootstrap(values).exit_code == 0
    sign_in(values)
    assert (
        tl(values, "admin", "user", "add", "alice", "--password-stdin", stdin=GOOD).exit_code == 0
    )
    assert tl(values, "admin", "user", "add", "triage", "--kind", "agent").exit_code == 0
    file_link(values, new_ulid(), new_ulid())
    return values


def file_link(env: dict[str, str], from_id: str, to_id: str) -> str:
    """The agent files one link proposal; returns its id."""
    command = AddLink(
        actor=AGENT, source="mcp:triage", scope="project:P1", from_id=from_id, to_id=to_id
    )
    with open_uow(env["TL_DB"]) as uow:
        view = proposals.propose(
            uow, tool="link_records", agent=AGENT, command=command, summary="Link two records"
        )
    return str(view.proposal_id)


def event_count(env: dict[str, str]) -> int:
    return int(rows(env, "SELECT COUNT(*) FROM events")[0][0])


def stopped_lines(env: dict[str, str]) -> list[str]:
    return tl(env, "agent", "stopped").stdout.splitlines()


def test_stop_prints_the_line_and_a_second_stop_says_already_stopped(env: dict[str, str]) -> None:
    first = tl(env, "agent", "stop", "triage", "--reason", "runaway filing")
    assert first.exit_code == 0, first.output
    assert first.stdout.strip() == "stopped agent:triage"
    again = tl(env, "agent", "stop", "triage")
    assert again.exit_code == 0 and again.stdout.strip() == "already stopped: agent:triage"


def test_the_agent_prefix_is_accepted(env: dict[str, str]) -> None:
    result = tl(env, "agent", "stop", "agent:triage")
    assert result.exit_code == 0 and result.stdout.strip() == "stopped agent:triage"


def test_resume_prints_the_line_and_a_second_resume_says_not_stopped(env: dict[str, str]) -> None:
    assert tl(env, "agent", "stop", "triage").exit_code == 0
    first = tl(env, "agent", "resume", "triage")
    assert first.exit_code == 0, first.output
    assert first.stdout.strip() == "resumed agent:triage"
    again = tl(env, "agent", "resume", "triage")
    assert again.exit_code == 0 and again.stdout.strip() == "not stopped: agent:triage"


def test_stopped_lists_the_agent_with_its_held_count_and_json_matches(env: dict[str, str]) -> None:
    assert tl(env, "agent", "stop", "triage", "--reason", "checking").exit_code == 0
    lines = stopped_lines(env)
    assert len(lines) == 1
    assert lines[0].startswith("agent:triage  since ")
    assert "  by user:root  held 1  checking" in lines[0]
    listed = json.loads(tl(env, "agent", "stopped", "--json").stdout)
    assert [(a["agent"], a["stopped_by"], a["held"], a["reason"]) for a in listed] == [
        ("agent:triage", "user:root", 1, "checking")
    ]
    assert lines[0].startswith(f"{listed[0]['agent']}  since {listed[0]['stopped_at']}  ")


def test_stopped_says_none_when_no_agent_is_stopped(env: dict[str, str]) -> None:
    assert stopped_lines(env) == ["none stopped"]
    assert json.loads(tl(env, "agent", "stopped", "--json").stdout) == []


def test_a_plain_user_is_refused_all_three_and_nothing_is_written(
    env: dict[str, str], tmp_path: Path
) -> None:
    assert tl(env, "agent", "stop", "triage").exit_code == 0
    mine = separate_session(env, tmp_path, "alice")
    sign_in(mine, "alice")
    before = event_count(env)
    for args in (("stop", "triage"), ("resume", "triage"), ("stopped",)):
        result = tl(mine, "agent", *args)
        assert result.exit_code == 1 and "forbidden" in result.output, (args, result.output)
    assert event_count(env) == before
    assert "held 1" in stopped_lines(env)[0]  # still stopped, as the admin sees it


def test_with_no_session_the_commands_are_refused(env: dict[str, str], tmp_path: Path) -> None:
    nobody = separate_session(env, tmp_path, "nobody")
    before = event_count(env)
    for args in (("stop", "triage"), ("resume", "triage"), ("stopped",)):
        result = tl(nobody, "agent", *args)
        assert result.exit_code == 1 and "error:" in result.output, (args, result.output)
    assert event_count(env) == before


def test_an_unknown_name_and_a_never_filed_agent_give_the_same_error(
    env: dict[str, str],
) -> None:
    assert tl(env, "admin", "user", "add", "idle", "--kind", "agent").exit_code == 0
    unknown = tl(env, "agent", "stop", "ghost")
    never = tl(env, "agent", "stop", "idle")
    assert unknown.exit_code == 1 and never.exit_code == 1
    assert unknown.stderr.strip() == never.stderr.strip() == "error: no such agent"
    assert tl(env, "agent", "resume", "ghost").stderr.strip() == "error: no such agent"


@pytest.fixture
def classed(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> Iterator[dict[str, str]]:
    """Confidential records come from a class table in the ledger, with clearance rows beside it."""
    with sqlite3.connect(env["TL_DB"]) as conn:
        conn.execute(f"CREATE TABLE {TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)")
        conn.execute(f"CREATE TABLE {TABLE}_clear (record_id TEXT, account TEXT)")
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}), table=TABLE, id_column="id", class_column="cls",
        clearance_table=f"{TABLE}_clear",
    )  # fmt: skip
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    yield env


def classify(env: dict[str, str], record_id: str, cls: str) -> None:
    """Set the class of a record (an unclassified record is hidden from every reader).

    Only ``user:amy`` holds a clearance for it, so ``privileged`` is hidden from the admin (an
    admin is a controller who reads ``restricted``, but not clearance).
    """
    with sqlite3.connect(env["TL_DB"]) as conn:
        conn.execute(f"DELETE FROM {TABLE} WHERE id = ?", (record_id,))
        conn.execute(f"INSERT INTO {TABLE} (id, cls) VALUES (?, ?)", (record_id, cls))
        conn.execute(f"DELETE FROM {TABLE}_clear WHERE record_id = ?", (record_id,))
        conn.execute(
            f"INSERT INTO {TABLE}_clear (record_id, account) VALUES (?, 'user:amy')", (record_id,)
        )


def create_record(env: dict[str, str], key: str) -> str:
    """A real record in the ledger (the viewer filter only sees records that exist)."""
    command = CreateRecord(
        actor="user:root", source="test", scope="project:P1", record_type="core.Record",
        title=key, key=key,
    )  # fmt: skip
    with open_uow(env["TL_DB"]) as uow:
        return str(handle_create_record(uow, command).stream_id)


def test_a_pending_proposal_with_a_hidden_record_is_not_counted(classed: dict[str, str]) -> None:
    env = classed
    hidden = create_record(env, "H-1")
    classify(env, hidden, "internal")  # readable while filed: the filer reads its own result
    file_link(env, new_ulid(), hidden)
    classify(env, hidden, "privileged")
    assert tl(env, "agent", "stop", "triage").exit_code == 0
    listed = json.loads(tl(env, "agent", "stopped", "--json").stdout)
    assert [a["held"] for a in listed] == [1]  # the visible proposal only
    assert hidden not in tl(env, "agent", "stopped").stdout
    assert "held 1" in stopped_lines(env)[0]


def test_stop_and_resume_are_recorded_on_the_account_stream(env: dict[str, str]) -> None:
    assert tl(env, "agent", "stop", "triage", "--reason", "why").exit_code == 0
    assert tl(env, "agent", "resume", "triage").exit_code == 0
    types = [
        r[0]
        for r in rows(
            env, "SELECT event_type FROM events WHERE event_type LIKE 'Agent.%' ORDER BY seq"
        )
    ]
    assert types == ["Agent.Stopped", "Agent.Resumed"]
