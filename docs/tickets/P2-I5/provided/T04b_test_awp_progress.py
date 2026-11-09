"""P2-I5-T04b: `tl awp iwp` progress verbs (start-work, item-move, step, progress)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_awp import Cli, load_world, seed_copy
from tl_adapters.db import as_target

NUMBER_SQL = "SELECT key FROM cur_core_record WHERE id = :i"


class Built:
    def __init__(self, cli: Cli) -> None:
        self.cli = cli
        self.w = load_world().World(as_target(str(cli.db)))
        self.iwp = str(self.w.iwp("Rack", planned_start="2026-12-01", foreman="user:uma"))
        ids = [str(i) for i in self.w.items(["10.0", "30.0"])]
        self.w.call("uma", "AddIwpScope", iwp=self.iwp, items=ids)
        self.number = str(self.w.scalar(NUMBER_SQL, i=self.iwp))
        self.small, self.large = (str(self.w.scalar(NUMBER_SQL, i=i)) for i in ids)

    def issue(self) -> None:
        """Issued as the projection holds it (the sign-off path is not under test here)."""
        self.w.set_status(self.iwp, "Issued")

    def earned(self) -> str:
        return self.cli.ok("iwp", "progress", self.number)[1]

    def state(self) -> str:
        return "\n".join(self.cli.ok("iwp", "show", self.number))


@pytest.fixture
def built(tmp_path: Path) -> Built:
    return Built(Cli(seed_copy(tmp_path), tmp_path))


def test_start_work_and_complete_field_move_an_issued_iwp(built: Built) -> None:
    built.issue()
    started = built.cli.write("iwp", "start-work", built.number, "--date", "2026-11-02")
    assert started.exit_code == 0, started.output
    assert started.stdout.startswith(f"start-work {built.number}  version ")
    assert "state In progress" in built.state()
    done = built.cli.write("iwp", "complete-field", built.number)
    assert done.exit_code == 0, done.output
    assert done.stdout.startswith(f"complete-field {built.number}  version ")
    assert "state Field complete" in built.state()


def test_start_work_on_a_draft_is_refused_and_a_stale_version_too(built: Built) -> None:
    draft = built.cli.write("iwp", "start-work", built.number)
    assert draft.exit_code == 1
    assert "error:" in draft.stderr
    assert "start-work" not in draft.stdout
    built.issue()
    stale = built.cli.write("iwp", "start-work", built.number, "--expected-version", "99")
    assert stale.exit_code == 1
    assert "error:" in stale.stderr
    assert "state Issued" in built.state()


def test_item_moves_change_the_earned_figure(built: Built) -> None:
    installed = built.cli.write("iwp", "item-move", built.small, "install")
    assert installed.exit_code == 0, installed.output
    assert installed.stdout.startswith(f"install {built.small}  version ")
    assert built.earned() == "earned 15.0  edition co.acme.awp@1.1.0"
    assert built.cli.write("iwp", "item-move", built.small, "verify").exit_code == 0
    assert built.earned().startswith("earned 17.5  ")
    again = built.cli.write("iwp", "item-move", built.small, "install")
    assert again.exit_code == 1
    assert "error:" in again.stderr


def test_return_puts_an_installed_item_back_and_a_bad_action_is_a_usage_error(
    built: Built,
) -> None:
    built.cli.write("iwp", "item-move", built.small, "install")
    back = built.cli.write("iwp", "item-move", built.small, "return")
    assert back.exit_code == 0, back.output
    assert built.earned().startswith("earned 0.0  ")
    bad = built.cli.write("iwp", "item-move", built.small, "teleport")
    assert bad.exit_code == 2
    stale = built.cli.write("iwp", "item-move", built.small, "install", "--expected-version", "99")
    assert stale.exit_code == 1


def test_a_manual_step_is_marked_and_unmarked(built: Built) -> None:
    done = built.cli.write("iwp", "step", built.number, built.large, "Material received")
    assert done.exit_code == 0, done.output
    assert done.stdout.startswith(f"step {built.number}  version ")
    assert built.earned().startswith("earned 22.5  ")
    undone = built.cli.write(
        "iwp", "step", built.number, built.large, "Material received", "--undo"
    )
    assert undone.exit_code == 0, undone.output
    assert built.earned().startswith("earned 0.0  ")
    unknown = built.cli.write("iwp", "step", built.number, built.large, "Nonsense step")
    assert unknown.exit_code == 1
    assert "error:" in unknown.stderr


def test_progress_lists_the_items_and_says_no_for_an_unknown_iwp(built: Built) -> None:
    built.cli.write("iwp", "item-move", built.small, "install")
    lines = built.cli.ok("iwp", "progress", built.number)
    assert lines[0] == f"iwp {built.number}"
    assert lines[2] == "items: 2"
    assert any(x.startswith(f"{built.small}  60.0  ") for x in lines)
    assert any(x.startswith(f"{built.large}  0.0  ") for x in lines)
    missing = built.cli.project("iwp", "progress", "NOPE")
    assert missing.exit_code == 1
    assert "error: no IWP NOPE" in missing.stderr


def test_a_viewer_cannot_record_progress(built: Built) -> None:
    refused = built.cli.write("iwp", "item-move", built.small, "install", who="user:vera")
    assert refused.exit_code == 1
    assert "error:" in refused.stderr
    assert built.earned().startswith("earned 0.0  ")
