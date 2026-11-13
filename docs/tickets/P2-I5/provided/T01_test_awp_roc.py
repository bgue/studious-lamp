"""P2-I5-T01: `tl awp roc ls|show|set` over the rules of credit of the adopted package."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_awp import Cli, seed_copy

DEFAULT = "co.acme.awp@1.1.0"
ADMIN = "user:ada"


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


def test_show_prints_the_default_edition_and_its_steps(cli: Cli) -> None:
    assert cli.ok("roc", "show") == [
        f"edition {DEFAULT}",
        "source default",
        "commodities: 3",
        "piping  scope_item  Material received 30, Installed 60, Verified 10",
        "weld  weld  Fit-up 20, Welded 60, NDE accepted 20",
        "bolted_joint  bolted_joint  Placed 50, Torqued 50",
    ]


def test_ls_names_the_edition_in_force(cli: Cli) -> None:
    assert cli.ok("roc", "ls") == ["editions: 1", f"{DEFAULT}  3  in force"]


def test_show_takes_an_edition_and_says_it_was_asked_for(cli: Cli) -> None:
    lines = cli.ok("roc", "show", "--edition", DEFAULT)
    assert lines[:3] == [f"edition {DEFAULT}", "source argument", "commodities: 3"]


def test_set_adopts_an_edition_for_the_project_and_show_says_so(cli: Cli) -> None:
    done = cli.write("roc", "set", DEFAULT, "--reason", "company standard", who=ADMIN)
    assert done.exit_code == 0, done.output
    assert done.stdout.startswith("set awp.rules_of_credit.set project:P123 ")
    assert cli.ok("roc", "show")[:2] == [f"edition {DEFAULT}", "source setting"]
    assert cli.ok("roc", "ls") == ["editions: 1", f"{DEFAULT}  3  in force"]


@pytest.mark.parametrize("value", ["co.acme.awp@9.9.9", "no.such.package@1.0.0"])
def test_set_refuses_an_edition_that_is_not_adopted_and_changes_nothing(
    cli: Cli, value: str
) -> None:
    refused = cli.write("roc", "set", value, who=ADMIN)
    assert refused.exit_code == 1
    assert "error: the edition of the rules of credit is not adopted" in refused.stderr
    assert value not in refused.output
    assert cli.ok("roc", "show")[1] == "source default"


@pytest.mark.parametrize("value", ["nonsense", "co.acme.awp", "co.acme.awp@1.1", "@1.1.0"])
def test_set_refuses_a_value_that_is_not_package_at_version(cli: Cli, value: str) -> None:
    refused = cli.write("roc", "set", value, who=ADMIN)
    assert refused.exit_code == 1
    assert "error: edition: expected package@version" in refused.stderr
    assert cli.ok("roc", "show")[1] == "source default"


def test_an_agent_cannot_set_the_edition(cli: Cli) -> None:
    refused = cli.write("roc", "set", DEFAULT, who="agent:bot")
    assert refused.exit_code == 1
    assert "agent_must_propose" in refused.stderr
    assert cli.ok("roc", "show")[1] == "source default"


def test_show_of_an_unknown_edition_is_the_same_refusal(cli: Cli) -> None:
    refused = cli.project("roc", "show", "--edition", "co.acme.awp@9.9.9")
    assert refused.exit_code == 1
    assert "error: the edition of the rules of credit is not adopted" in refused.stderr
