"""`tl awp` write verbs for CWPs and packages (T04c, D37)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_cli_awp import Cli, seed_copy

SUPER = "user:sue"
PLAIN = "user:uma"


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


def create(cli: Cli) -> str:
    made = cli.write(
        "cwp", "create", "--discipline", "PIP", "--title", "T04c test", "--cwa", "A2",
        "--planned-start", "2026-11-02", "--planned-finish", "2027-01-29",
        "--budget-hours", "250", "--contractor", "Acme Fab",
        "--qty", "piping:480:m", "--qty", "concrete:12.5:m3",
    )  # fmt: skip
    found = re.search(r"^created CWP (\S+)$", made.stdout, re.M)
    assert made.exit_code == 0, made.output
    assert found is not None
    return found.group(1)


def shown(cli: Cli, number: str) -> str:
    return "\n".join(cli.ok("cwp", "show", number))


def test_create_numbers_the_package_and_the_reads_show_it(cli: Cli) -> None:
    number = create(cli)
    assert number == "P123-CWP-PIP-0005"
    body = shown(cli, number)
    assert "title T04c test" in body
    assert "state Planned" in body
    assert "budget 250.0" in body
    assert "contractor Acme Fab" in body
    assert number in "\n".join(cli.ok("cwp", "ls"))


def test_revise_changes_the_title_and_only_the_title(cli: Cli) -> None:
    number = create(cli)
    result = cli.write("cwp", "revise", number, "--title", "T04c renamed")
    assert result.exit_code == 0
    assert result.stdout.startswith(f"revise {number}  version ")
    body = shown(cli, number)
    assert "title T04c renamed" in body
    assert "budget 250.0" in body


def test_allocate_needs_leaf_nodes_and_sums_to_100(cli: Cli) -> None:
    """D37: 1.1 and 1.2 are parents in the seed; the handler refuses them, the leaves work."""
    number = create(cli)
    parent = cli.write("cwp", "allocate", number, "--wbs", "1.1:60", "--wbs", "1.2:40")
    assert parent.exit_code == 1
    assert "error: only a leaf WBS node takes a package allocation" in parent.stderr
    done = cli.write("cwp", "allocate", number, "--wbs", "1.1.1:60", "--wbs", "1.2.1:40")
    assert done.exit_code == 0, done.output
    body = shown(cli, number)
    assert "allocations 2" in body
    assert "  1.1.1  60.00" in body
    assert "  1.2.1  40.00" in body
    short = cli.write("cwp", "allocate", number, "--wbs", "1.1.1:60", "--wbs", "1.2.1:39.99")
    assert short.exit_code == 1
    assert "error:" in short.stderr


def test_move_runs_the_workflow_with_its_word(cli: Cli) -> None:
    number = create(cli)
    moved = cli.write("cwp", "move", number, "start-development")
    assert moved.exit_code == 0
    assert moved.stdout.startswith(f"move {number}  version ")
    assert "state In development" in shown(cli, number)


def test_a_forbidden_release_exits_1_and_changes_nothing(cli: Cli) -> None:
    number = create(cli)
    cli.write("cwp", "move", number, "start-development")
    result = cli.write("cwp", "move", number, "release", who=PLAIN)
    assert result.exit_code == 1
    assert "error: forbidden" in result.stderr
    assert "state In development" in shown(cli, number)


def test_an_unknown_cwp_exits_1_with_the_project(cli: Cli) -> None:
    result = cli.write("cwp", "move", "P123-CWP-PIP-9999", "start-development")
    assert result.exit_code == 1
    assert "error: no CWP 'P123-CWP-PIP-9999' in project P123" in result.stderr


def test_a_malformed_allocation_is_a_parse_error_before_the_ledger(cli: Cli) -> None:
    number = create(cli)
    result = cli.write("cwp", "allocate", number, "--wbs", "1.1")
    assert result.exit_code == 1
    assert "error: --wbs 1.1: expected CODE:PERCENT" in result.stderr


def test_return_needs_a_reason_and_a_reasonless_action_takes_none(cli: Cli) -> None:
    number = create(cli)
    needs = cli.write("cwp", "move", number, "return")
    assert needs.exit_code == 1
    assert "error: return needs --reason" in needs.stderr
    extra = cli.write("cwp", "move", number, "start-development", "--reason", "why")
    assert extra.exit_code == 1
    assert "takes no --reason" in extra.stderr
    assert "state Planned" in shown(cli, number)


def test_void_hides_the_package_from_the_reads_and_needs_a_reason(cli: Cli) -> None:
    number = create(cli)
    missing = cli.write("cwp", "void", number)
    assert missing.exit_code == 2  # a Typer usage error
    voided = cli.write("cwp", "void", number, "--reason", "T04c clean-up")
    assert voided.exit_code == 0
    assert voided.stdout.startswith(f"void {number}  version ")
    assert cli.project("cwp", "show", number).exit_code == 1


def test_packages_are_recorded_updated_and_voided(cli: Cli) -> None:
    number = "EWP-T04C-1"
    rec = cli.write(
        "package", "record", "--type", "ewp", "--number", number, "--title", "T04c EWP",
        "--constraint-source", "--status", "Issued", "--forecast", "2027-01-15",
    )  # fmt: skip
    assert rec.exit_code == 0
    assert rec.stdout.startswith(f"record {number}  version ")
    listed = cli.ok("package", "ls")
    assert any(r.startswith(f"{number}  EWP  Issued") and r.endswith("  yes") for r in listed)
    upd = cli.write("package", "update", number, "--status", "IFC", "--no-constraint-source")
    assert upd.exit_code == 0
    assert upd.stdout.startswith(f"update {number}  version ")
    assert any(
        r.startswith(f"{number}  EWP  IFC") and r.endswith("  no") for r in cli.ok("package", "ls")
    )
    gone = cli.write("package", "void", number, "--reason", "T04c")
    assert gone.exit_code == 0
    assert gone.stdout.startswith(f"void {number}  version ")
    assert cli.ok("package", "ls") == ["packages: 0"]


def test_a_bad_package_type_is_a_usage_error_and_an_unknown_package_an_error(cli: Cli) -> None:
    bad = cli.write("package", "record", "--type", "xwp", "--number", "X-1", "--title", "T")
    assert bad.exit_code == 2
    unknown = cli.write("package", "update", "NOPE-1", "--status", "x")
    assert unknown.exit_code == 1
    assert "error: no package 'NOPE-1' in project P123" in unknown.stderr
