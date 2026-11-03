"""`tl awp` verbs for the WBS, the CWAs and the path (T04d, D47)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_awp import Cli, seed_copy

PLAIN = "user:uma"


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


def version_of(stdout: str) -> int:
    head, sep, tail = stdout.strip().rpartition("  version ")
    assert sep
    return int(tail)


def record_version(cli: Cli, key: str) -> int:
    return int(cli.scalar("SELECT version FROM cur_core_record WHERE key = :k", k=key))


def test_wbs_define_revise_map_clear_retire(cli: Cli) -> None:
    root = cli.write("wbs", "define", "9", "--title", "Spare")
    leaf = cli.write("wbs", "define", "9.1", "--parent", "9", "--title", "Spare leaf")
    assert root.stdout == "defined WBS 9\n"
    assert leaf.stdout == "defined WBS 9.1\n"
    assert "parent 9" in cli.ok("wbs", "show", "9.1")
    mapped = cli.write("wbs", "map", "9.1", "--cost-code", "4210-PIP-WLD:100")
    assert mapped.exit_code == 0
    assert mapped.stdout.startswith("map 9.1  version ")
    cleared = cli.write("wbs", "map", "9.1", "--clear")
    assert version_of(cleared.stdout) > version_of(mapped.stdout)
    rev = cli.write("wbs", "revise", "9.1", "--title", "Spare leaf renamed")
    assert rev.stdout.startswith("revise 9.1  version ")
    shown = cli.ok("wbs", "show", "9.1")
    assert "title Spare leaf renamed" in shown
    assert "parent 9" in shown
    gone = cli.write("wbs", "retire", "9.1", "--reason", "T04d")
    assert gone.stdout.startswith("retire 9.1  version ")
    assert "retired yes" in cli.ok("wbs", "show", "9.1")


def test_the_printed_version_is_the_record_version_not_the_path_version(cli: Cli) -> None:
    moved = cli.write("path", "move", "A2", "--to", "1", "--reason", "Access")
    assert moved.exit_code == 0
    assert moved.stdout.startswith("move A2  version ")
    printed = version_of(moved.stdout)
    assert printed == record_version(cli, "P123-POC")
    assert cli.scalar("SELECT current_version FROM cur_awp_path") == 2
    assert printed == 3  # Record.Created, Defined, Resequenced: not the path's version 2


def test_wbs_map_is_checked_by_exit_status_and_the_printed_version(cli: Cli) -> None:
    before = record_version(cli, "awp.wbs@1.1.1")
    mapped = cli.write(
        "wbs", "map", "1.1.1", "--cost-code", "4210-PIP-WLD:60", "--cost-code", "4210-PIP-ERC:40"
    )
    assert mapped.exit_code == 0
    assert version_of(mapped.stdout) == before + 1 == record_version(cli, "awp.wbs@1.1.1")


def test_cwa_define_revise_and_retire(cli: Cli) -> None:
    made = cli.write("cwa", "define", "SP", "--title", "Spare area")
    assert made.stdout == "defined CWA SP\n"
    located = cli.write("cwa", "revise", "SP", "--location", "Bay 4")
    assert located.stdout.startswith("revise SP  version ")
    retired = cli.write("cwa", "retire", "SP", "--reason", "T04d")
    assert retired.stdout.startswith("retire SP  version ")
    line = next(r for r in cli.ok("cwa", "ls") if r.startswith("SP"))
    assert line == "SP  Spare area  Bay 4  retired"


def test_the_option_pairs_that_exclude_each_other_exit_1_before_the_ledger_opens(cli: Cli) -> None:
    before = cli.scalar("SELECT COUNT(*) FROM events")
    cases = [
        (("wbs", "revise", "1.1", "--parent", "1", "--root"), "give --parent or --root, not both"),
        (("cwa", "revise", "A1", "--location", "x", "--clear-location"), "not both"),
        (("wbs", "map", "1.1.1", "--cost-code", "4210-PIP-WLD:100", "--clear"), "not both"),
        (("wbs", "map", "1.1.1"), "give --cost-code or --clear"),
    ]
    for argv, text in cases:
        result = cli.write(*argv)
        assert result.exit_code == 1, argv
        assert text in result.stderr, argv
    assert cli.scalar("SELECT COUNT(*) FROM events") == before


def test_path_define_without_a_step_refuses(cli: Cli) -> None:
    result = cli.write("path", "define")
    assert result.exit_code == 1
    assert "error: give at least one --step CWA[:REASON]" in result.stderr


def test_a_second_path_is_refused(cli: Cli) -> None:
    result = cli.write("path", "define", "--step", "A1", "--step", "A2:Access")
    assert result.exit_code == 1
    assert "error: the project already has a path of construction" in result.stderr


def test_path_define_on_a_project_without_a_path_prints_version_1(tmp_path: Path) -> None:
    """The success line the acceptance run could not show: the seed already had a path.

    The spec expected ``defined path  version 1``; as built the line shows the record version."""
    cli = Cli(seed_copy(tmp_path), tmp_path)
    # a second project in the same ledger: its own areas, no path
    for code in ("B1", "B2"):
        made = cli.run(
            "cwa", "define", code, "--title", code, "--project", "P321", "--actor", "user:ada"
        )
        assert made.exit_code == 0, made.output
    result = cli.run(
        "path",
        "define",
        "--step",
        "B1",
        "--step",
        "B2:Access",
        "--project",
        "P321",
        "--actor",
        "user:ada",
    )
    assert result.exit_code == 0, result.output
    # the line prints the record's version (Created, then Defined: 2), not the path's version 1
    assert result.stdout.strip() == "defined path  version 2"
    assert cli.scalar("SELECT current_version FROM cur_awp_path WHERE scope = 'project:P321'") == 1
    assert record_version(cli, "P321-POC") == 2


def test_a_user_may_not_define_a_node_or_move_an_area(cli: Cli) -> None:
    denied = cli.write("wbs", "define", "9.9", "--title", "x", who=PLAIN)
    assert denied.exit_code == 1
    assert "error: forbidden" in denied.stderr
    moved = cli.write("path", "move", "A2", "--to", "1", "--reason", "Access", who=PLAIN)
    assert moved.exit_code == 1
    assert "error: forbidden" in moved.stderr


def test_unknown_codes_and_parse_errors_say_what_and_where(cli: Cli) -> None:
    unknown = cli.write("wbs", "revise", "9.9", "--title", "x")
    assert unknown.exit_code == 1
    assert "error: no WBS node '9.9' in project P123" in unknown.stderr
    bad_area = cli.write("cwa", "revise", "ZZ", "--title", "x")
    assert bad_area.exit_code == 1
    assert "error: no CWA 'ZZ' in project P123" in bad_area.stderr
    parse = cli.write("wbs", "map", "1.1.1", "--cost-code", "100")
    assert parse.exit_code == 1
    assert "error: --cost-code 100: expected CODE:PERCENT" in parse.stderr


def test_an_empty_revise_is_pinned_as_the_handler_decides(cli: Cli) -> None:
    """T04d open question: ``wbs revise CODE`` and ``cwa revise CODE`` with no option are not
    refused by the CLI; the handler finds nothing to change and refuses (``NoChangesError``)."""
    for argv in (("wbs", "revise", "1.1.1"), ("cwa", "revise", "A1")):
        before = cli.scalar("SELECT COUNT(*) FROM events")
        result = cli.write(*argv)
        assert result.exit_code == 1, argv
        assert result.stderr.startswith("error:"), argv
        assert cli.scalar("SELECT COUNT(*) FROM events") == before, argv
