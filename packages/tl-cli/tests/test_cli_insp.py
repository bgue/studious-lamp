"""`tl insp` (P2-INSP-T04): the write verbs, the reads and the export.

The ledger is made by ``insp_world.InspWorld`` (loaded by path, on top of ``punch_world``, as
``test_cli_punch.py`` loads its world). Writes run with ``--actor`` on a dev ledger file. Reads run
signed in as the person they name, so the viewer is that person's.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from auth_support import sign_in
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli import insp_write
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_mod_quality import insp_views
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
PASSWORD = "correct horse battery"
IWP = "P123-IWP-0001"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
KEY = re.compile(r"P\d+-INS-\d{4}")


def _module(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_insp_world() -> ModuleType:
    """The ``insp_world`` helper of the quality module tests (``punch_world`` is loaded first)."""
    quality = ROOT / "packages" / "tl-modules" / "quality" / "tests"
    _module("punch_world", quality / "punch_world.py")
    return _module("insp_world", quality / "insp_world.py")


class Cli:
    """``tl --db DB insp ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: Path, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str, env: dict[str, str] | None = None) -> Result:
        result = CliRunner().invoke(app, ["--db", str(self.db), "insp", *argv], env=env or self.env)
        assert result.exception is None or isinstance(result.exception, SystemExit), result.output
        assert "Traceback" not in result.output
        assert not HEX32.search(result.output), result.output
        return result

    def as_person(self, name: str) -> dict[str, str]:
        env = {
            "TL_ENV": "dev",
            "TL_DB": str(self.db),
            "TL_SESSION_FILE": str(self.tmp / f"session-{name}.json"),
        }
        sign_in(env, name, PASSWORD)
        return env

    def read(self, name: str, *argv: str) -> Result:
        """A read as ``name``: signed in, and ``--actor`` names that same person."""
        return self.run(*argv, "--actor", f"user:{name}", env=self.as_person(name))

    def write(self, verb: str, *argv: str, who: str) -> Result:
        return self.run(verb, *argv, "--actor", f"user:{who}")

    def key_of(self, record: str) -> str:
        return str(self.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))

    def state_of(self, key: str) -> str:
        """The state line of ``show`` (read as the planner, who sees every inspection they made)."""
        shown = self.read("uma", "show", key, "--project", PROJECT)
        assert shown.exit_code == 0, shown.output
        return shown.output.splitlines()[1]

    def plan(self, who: str = "uma", **more: str) -> str:
        args = ["--project", PROJECT, "--subject", IWP, "--title", "Flange make-up"]
        args += ["--point", more.pop("point", "hold")]
        for name, value in more.items():
            args += [f"--{name.replace('_', '-')}", value]
        result = self.write("plan", *args, who=who)
        assert result.exit_code == 0, result.output
        return result.output.split()[1]

    def scheduled(self, who: str = "uma", **more: str) -> str:
        key = self.plan(who, **more)
        checklist = self.key_of(self.world.checklist())
        result = self.write(
            "schedule",
            key,
            "--project",
            PROJECT,
            "--checklist",
            checklist,
            "--on",
            "2026-12-01",
            "--inspector",
            "M. Okafor",
            who=who,
        )
        assert result.exit_code == 0, result.output
        return key


@pytest.fixture
def cli(tmp_path: Path) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_insp_world().InspWorld(target)
    world.people()
    world.record("awp.IWP", IWP)
    yield Cli(path, tmp_path, world)


ANSWERS_PASS = ["--answer", "q1=yes", "--answer", "q2=yes", "--answer", "q3=5"]


# 1. plan, schedule, record, verify ------------------------------------------------------------


def test_the_lifecycle_prints_each_line_and_moves_the_state(cli: Cli) -> None:
    planned = cli.write(
        "plan",
        "--project",
        PROJECT,
        "--subject",
        IWP,
        "--title",
        "Flange make-up",
        "--point",
        "hold",
        who="uma",
    )
    assert planned.exit_code == 0, planned.output
    key = planned.output.split()[1]
    assert re.fullmatch(rf"planned {KEY.pattern}  version \d+\n", planned.output)
    assert cli.state_of(key) == "Planned"

    checklist = cli.key_of(cli.world.checklist())
    scheduled = cli.write(
        "schedule",
        key,
        "--project",
        PROJECT,
        "--checklist",
        checklist,
        "--on",
        "2026-12-01",
        "--inspector",
        "M. Okafor",
        who="uma",
    )
    assert re.fullmatch(rf"scheduled {key}  version \d+\n", scheduled.output), scheduled.output
    assert cli.state_of(key) == "Scheduled"

    recorded = cli.write("record", key, "--project", PROJECT, *ANSWERS_PASS, who="rob")
    assert recorded.exit_code == 0, recorded.output
    lines = recorded.output.splitlines()
    assert re.fullmatch(rf"recorded {key}  version \d+", lines[0]), lines
    assert lines[1:] == ["result accept", "punch 0"], lines

    verified = cli.write("verify", key, "--project", PROJECT, who="sue")
    assert re.fullmatch(rf"verified {key}  version \d+\n", verified.output), verified.output
    assert cli.state_of(key) == "Verified"


def test_a_failed_answer_prints_the_punch_count(cli: Cli) -> None:
    key = cli.scheduled()
    failed = cli.write(
        "record",
        key,
        "--project",
        PROJECT,
        "--answer",
        "q1=no",
        "--answer",
        "q2=yes",
        "--answer",
        "q3=5",
        "--note",
        "Gauge missing",
        who="rob",
    )
    assert failed.exit_code == 0, failed.output
    assert "result reject" in failed.output.splitlines()
    assert "punch 1" in failed.output.splitlines()


def test_answers_from_a_file_are_recorded_as_given(cli: Cli, tmp_path: Path) -> None:
    key = cli.scheduled()
    answers = tmp_path / "answers.json"
    answers.write_text(
        '[{"q": "q1", "value": "yes"}, {"q": "q2", "value": "no"}, {"q": "q3", "value": 5}]'
    )
    result = cli.write(
        "record", key, "--project", PROJECT, "--answers-file", str(answers), who="rob"
    )
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[1] == "result conditional"
    assert cli.state_of(key) == "Done"


def test_answers_and_an_answers_file_are_a_usage_error(cli: Cli, tmp_path: Path) -> None:
    key = cli.scheduled()
    answers = tmp_path / "answers.json"
    answers.write_text("[]")
    result = cli.write(
        "record",
        key,
        "--project",
        PROJECT,
        "--answer",
        "q1=yes",
        "--answers-file",
        str(answers),
        who="rob",
    )
    assert result.exit_code == 2, result.output


# 2. the guards are the handlers' ----------------------------------------------------------------


def test_the_recorder_cannot_verify_and_an_actor_without_the_word_is_refused(cli: Cli) -> None:
    key = cli.scheduled()
    cli.write("record", key, "--project", PROJECT, *ANSWERS_PASS, who="rob")
    refused = cli.write("verify", key, "--project", PROJECT, who="rob")
    assert refused.exit_code == 1, refused.output
    assert refused.output.startswith("error: "), refused.output
    assert cli.state_of(key) == "Done"

    no_word = cli.write("verify", key, "--project", PROJECT, who="uma")
    assert no_word.exit_code == 1, no_word.output
    assert "error: forbidden" in no_word.output
    assert cli.state_of(key) == "Done"


def test_reinspect_and_cancel_paths(cli: Cli) -> None:
    key = cli.scheduled()
    cli.write(
        "record",
        key,
        "--project",
        PROJECT,
        "--answer",
        "q1=no",
        "--answer",
        "q2=yes",
        "--answer",
        "q3=5",
        who="rob",
    )
    again = cli.write(
        "reinspect", key, "--project", PROJECT, "--planned-on", "2026-12-05", who="uma"
    )
    assert again.exit_code == 0, again.output
    new_key = again.output.split()[1]
    assert re.fullmatch(rf"reinspected {KEY.pattern}  version \d+\n", again.output)
    assert new_key != key
    assert cli.state_of(key) == "Done"

    planned = cli.plan(point="witness")
    cancelled = cli.write(
        "cancel", planned, "--project", PROJECT, "--reason", "Work moved", who="sue"
    )
    assert cancelled.exit_code == 0, cancelled.output
    assert re.fullmatch(rf"cancelled {KEY.pattern}  version \d+\n", cancelled.output)
    assert cli.state_of(planned) == "Cancelled"


# 3. reads ----------------------------------------------------------------------------------------


def test_ls_filters_the_total_and_hides_what_the_reader_cannot_see(cli: Cli) -> None:
    hold = cli.plan(point="hold")
    review = cli.plan(point="review")
    hidden_subject = cli.world.hidden_record()
    secret = cli.world.plan(subject=hidden_subject, who="dora", title="Secret walk")
    secret_key = cli.key_of(secret)

    everything = cli.read("uma", "ls", "--project", PROJECT)
    assert everything.exit_code == 0, everything.output
    lines = everything.output.splitlines()
    assert lines[-1] == "2 of 2", lines
    assert secret_key not in everything.output

    holds = cli.read("uma", "ls", "--project", PROJECT, "--point", "hold")
    assert holds.output.splitlines() == [
        f"{hold}  Flange make-up  Planned  hold  {IWP}  {IWP}  -  -  -",
        "1 of 1",
    ]
    planned = cli.read("uma", "ls", "--project", PROJECT, "--state", "Planned", "--limit", "1")
    assert planned.output.splitlines()[-1] == "1 of 2"
    assert review in cli.read("uma", "ls", "--project", PROJECT).output

    shown_to_dora = cli.read("dora", "ls", "--project", PROJECT)
    assert secret_key in shown_to_dora.output


def test_show_has_no_id_and_missing_keys_print_the_same_text(cli: Cli) -> None:
    key = cli.plan()
    shown = cli.read("uma", "show", key, "--project", PROJECT)
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    assert lines[0] == f"{key} · Flange make-up"
    assert lines[1] == "Planned"
    assert f"{'Point':<16}hold" in lines
    assert "Answers" in lines and "No answers" in lines
    assert f"{'Punch items':<16}—" in lines

    unknown = cli.read("uma", "show", "P123-INS-9999", "--project", PROJECT)
    assert unknown.exit_code == 1
    assert unknown.output == "error: no inspection P123-INS-9999\n"

    hidden_key = cli.key_of(cli.world.plan(subject=cli.world.hidden_record(), who="dora"))
    hidden = cli.read("uma", "show", hidden_key, "--project", PROJECT)
    assert hidden.output == f"error: no inspection {hidden_key}\n"

    other_project = cli.read("uma", "show", key, "--project", "P456")
    assert other_project.output == f"error: no inspection {key}\n"


# 4. export and the format ------------------------------------------------------------------------


def test_export_equals_the_view_rows_in_csv_and_jsonl(cli: Cli) -> None:
    cli.plan(point="hold")
    cli.plan(point="witness")
    with open_uow(cli.world.db, readonly=True) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:uma")
        rows = insp_views.inspection_list(uow.conn(), SCOPE, viewer=viewer).rows
    for fmt in ("csv", "jsonl"):
        out = cli.read("uma", "export", "--project", PROJECT, "--format", fmt)
        assert out.exit_code == 0, out.output
        assert out.output == insp_views.export_rows(rows, fmt)


def test_a_bad_format_is_a_usage_error(cli: Cli) -> None:
    result = cli.read("uma", "export", "--project", PROJECT, "--format", "xml")
    assert result.exit_code == 2, result.output


def test_an_oversized_answers_file_is_refused(cli: Cli, tmp_path: Path) -> None:
    key = cli.scheduled()
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (256 * 1024 + 1))
    result = cli.write("record", key, "--project", PROJECT, "--answers-file", str(big), who="rob")
    assert result.exit_code == 1, result.output
    assert result.output == "error: answers file is too large\n"


def test_an_inspection_write_runs_its_handler_as_the_acting_person(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No refusal names a record here, so the test spies on the viewer the handler runs under: it
    # must be the actor's, not the process's (LOWEST on a dev ledger).
    seen: list[cf.Viewer] = []
    original = insp_write._handler

    def spy(model: Any) -> Any:
        handler = original(model)

        def run(uow: Any, command: Any) -> Any:
            seen.append(cf.current_viewer())
            return handler(uow, command)

        return run

    monkeypatch.setattr(insp_write, "_handler", spy)
    cli.plan("uma")
    with open_uow(cli.world.db, readonly=True) as uow:
        expected = cf.viewer_for_actor(uow.conn(), "user:uma")
    assert seen == [expected]
    assert expected != cf.LOWEST


# 5. the group is registered ------------------------------------------------------------------


def test_tl_help_lists_insp() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert re.search(r"\binsp\s{2,}\S", result.output), result.output
