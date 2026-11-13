"""`tl awp rollup` and `tl awp worker` (T04e, D25: on a copy of the seed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_awp import Cli, seed_copy


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


def test_rollup_queues_once_and_is_idempotent(cli: Cli) -> None:
    first = cli.write("rollup")
    second = cli.write("rollup")
    assert first.exit_code == second.exit_code == 0
    assert first.stdout.startswith("rollup requested  job ")
    assert second.stdout == first.stdout
    assert cli.scalar("SELECT COUNT(*) FROM job_queue WHERE kind = 'awp.rollup'") == 1


def test_worker_once_runs_the_queued_rollup_then_has_nothing_to_run(cli: Cli) -> None:
    cli.write("rollup")
    once = cli.run("worker", "--once", "--actor", "user:ada")
    lines = once.stdout.splitlines()
    ran = [r for r in lines if r.startswith("ran ")]
    assert once.exit_code == 0
    assert len(ran) == 1
    assert " awp.rollup " in ran[0]
    assert lines[-1] == "worker done: ran=1"
    tree = cli.ok("wbs", "tree")
    assert any(not line.rstrip().endswith("-") for line in tree[1:])  # a total appears
    node = cli.ok("wbs", "show", "1.1.1")
    assert "total 4,200.0" in node or any(
        line.startswith("total ") and line != "total -" for line in node
    )
    idle = cli.run("worker", "--once", "--actor", "user:ada")
    assert idle.exit_code == 0
    assert idle.stdout.splitlines() == ["worker done: ran=0"]


def test_worker_once_requeue_prints_requeued_0_first_then_runs_the_queued_job(cli: Cli) -> None:
    """T04e: after a ``rollup`` request nothing is lost, so 0 are requeued; the job still runs."""
    cli.write("rollup")
    result = cli.run("worker", "--once", "--requeue", "--actor", "user:ada")
    lines = result.stdout.splitlines()
    assert result.exit_code == 0
    assert lines[0] == "requeued 0"
    assert any(r.startswith("ran ") and " awp.rollup " in r for r in lines)
    assert lines[-1] == "worker done: ran=1"


def test_requeue_finds_a_project_whose_queue_row_was_lost(cli: Cli) -> None:
    """The restore case: the queue is empty but the ledger moved past the last run."""
    from sqlalchemy import text
    from tl_adapters.db import as_target, open_uow

    with open_uow(as_target(str(cli.db))) as uow:
        uow.conn().execute(text("DELETE FROM job_queue WHERE kind = 'awp.rollup'"))
    result = cli.run("worker", "--once", "--requeue", "--actor", "user:ada")
    lines = result.stdout.splitlines()
    assert lines[0] == "requeued 1"
    assert lines[-1] == "worker done: ran=1"


def test_a_user_without_the_rollup_word_is_refused(cli: Cli) -> None:
    # awp.rollup is a user word: a viewer is the one refused
    result = cli.write("rollup", who="user:vera")
    assert result.exit_code == 1
    assert "error: forbidden" in result.stderr


MSG_WORKER_WORD = "error: forbidden: tl awp worker needs the awp.worker.run access word"


@pytest.mark.parametrize("who", ["user:sue", "user:uma", "user:vera", "user:dev", "agent:bot"])
def test_worker_without_the_word_is_refused_with_the_fixed_text(cli: Cli, who: str) -> None:
    """P2-I5-S4b: a project superuser, a user, a viewer, the dev actor and an agent hold no
    company-scope ``awp.worker.run`` (a controller word); nothing runs, the queue is untouched."""
    cli.write("rollup")
    result = cli.run("worker", "--once", "--actor", who)
    assert result.exit_code == 1
    assert result.stderr.strip() == MSG_WORKER_WORD
    assert result.stdout == ""
    assert cli.scalar("SELECT COUNT(*) FROM job_queue WHERE kind = 'awp.rollup'") == 1
    assert cli.scalar("SELECT COUNT(*) FROM rule_cursor WHERE name = 'awp.hold'") == 0


def test_worker_with_the_word_runs_both_followers(cli: Cli) -> None:
    assert cli.run("worker", "--once", "--actor", "user:ada").exit_code == 0
    assert cli.scalar("SELECT COUNT(*) FROM rule_cursor WHERE name = 'awp.hold'") == 1
    assert cli.scalar("SELECT COUNT(*) FROM rule_cursor WHERE name = 'awp.readiness'") == 1
