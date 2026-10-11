"""`tl types sync|ls|show|validate|lock|deprecate|watch` on a temporary ledger (P0-I8-T20)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget
from tl_cli.main import app
from tl_core.extypes.lock import write_lock
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan@1.0.0"
OBSERVATION = "co.acme.SafetyObservation@1.0.0"


class Env:
    def __init__(self, root: Path, env: dict[str, str]) -> None:
        self.root = root
        self.env = env

    def run(self, *args: str) -> RunResult:
        return runner.invoke(app, list(args), env=self.env)

    def ok(self, *args: str) -> list[str]:
        result = self.run(*args)
        assert result.exit_code == 0, result.output
        assert result.exception is None
        return result.stdout.splitlines()

    def package(self, name: str = "LiftPlan") -> Path:
        return self.root / "co.acme" / name / "1.0.0"


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Env]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    root = tmp_path / "types"
    shutil.copytree(TYPES, root)
    values = {"TL_DB": str(new_db())}
    with use_provider(DirectorySchemaProvider()):
        assert runner.invoke(app, ["init"], env=values).exit_code == 0
        yield Env(root, values)


def break_lift(env: Env) -> None:
    (env.package() / "examples" / "bad.json").write_text("{}")
    write_lock(env.package())


def test_the_types_group_is_in_the_help() -> None:
    assert "types" in runner.invoke(app, ["--help"]).stdout
    helped = runner.invoke(app, ["types", "--help"]).stdout
    for name in ("sync", "ls", "show", "validate", "lock", "deprecate", "watch"):
        assert name in helped


# --- sync ------------------------------------------------------------------------------------


def test_sync_registers_every_package_and_says_so(env: Env) -> None:
    assert env.ok("types", "sync", str(env.root)) == [
        f"registered {LIFT}",
        f"registered {OBSERVATION}",
    ]


def test_sync_twice_reports_nothing_new(env: Env) -> None:
    env.ok("types", "sync", str(env.root))
    assert env.ok("types", "sync", str(env.root)) == ["up to date (2 packages)"]


def test_sync_quarantines_an_invalid_package_and_lists_its_issues(env: Env) -> None:
    break_lift(env)
    lines = env.ok("types", "sync", str(env.root))
    assert lines[0] == f"quarantined {LIFT}"
    assert lines[1].startswith("  example examples/bad.json: ")
    assert lines[-1] == f"registered {OBSERVATION}"
    assert env.ok("types", "sync", str(env.root)) == ["up to date (2 packages)"]


def test_sync_strict_exits_1_while_something_is_quarantined(env: Env) -> None:
    break_lift(env)
    result = env.run("types", "sync", str(env.root), "--strict")
    assert result.exit_code == 1
    assert "1 quarantined" in result.stderr
    clean = env.run("types", "sync", str(env.root))
    assert clean.exit_code == 0


def test_sync_of_a_missing_directory_fails(env: Env) -> None:
    result = env.run("types", "sync", str(env.root / "nowhere"))
    assert result.exit_code == 1 and "error: no such directory" in result.stderr


def test_sync_records_the_actor_given(env: Env) -> None:
    env.ok("types", "sync", str(env.root), "--actor", "user:alice")
    shown = env.ok("types", "show", LIFT)
    assert "owner user:alice" in shown


# --- ls and show -------------------------------------------------------------------------------


def test_ls_is_silent_when_nothing_is_registered(env: Env) -> None:
    assert env.ok("types", "ls") == []


def test_ls_lists_types_by_ref(env: Env) -> None:
    env.ok("types", "sync", str(env.root))
    assert env.ok("types", "ls") == [
        f"{LIFT}  active  object-backed  lift_date,crane,load_tonnes,risk_class",
        f"{OBSERVATION}  active  managed  observed_on,category,severity,location",
    ]


def test_ls_filters_by_status(env: Env) -> None:
    break_lift(env)
    env.ok("types", "sync", str(env.root))
    assert env.ok("types", "ls", "--status", "quarantined") == [f"{LIFT}  quarantined  -  -"]
    assert [line.split()[0] for line in env.ok("types", "ls", "--status", "active")] == [
        OBSERVATION
    ]
    assert env.ok("types", "ls", "--status", "deprecated") == []
    assert len(env.ok("types", "ls", "--status", "all")) == 2


def test_ls_refuses_an_unknown_status(env: Env) -> None:
    result = env.run("types", "ls", "--status", "gone")
    assert result.exit_code == 1
    assert "--status must be active, quarantined, deprecated or all, not 'gone'" in result.stderr


def test_show_prints_the_state_and_the_fields(env: Env) -> None:
    env.ok("types", "sync", str(env.root))
    lines = env.ok("types", "show", LIFT)
    assert lines[:3] == [f"type {LIFT}", "status active", "storage object-backed"]
    assert any(line.startswith("location file://") for line in lines)
    assert any(line.startswith("content_hash ") and len(line) == 13 + 64 for line in lines)
    assert any(line.startswith("schema_hash ") for line in lines)
    fields = lines[lines.index("fields") + 1 :]
    assert "  crane string required indexed" in fields
    assert "  load_tonnes decimal required indexed" in fields
    assert "  crew string multiple" in fields
    assert "  method_statement text" in fields
    assert "issues" not in lines


def test_show_of_a_quarantined_version_prints_its_issues(env: Env) -> None:
    break_lift(env)
    env.ok("types", "sync", str(env.root))
    lines = env.ok("types", "show", LIFT)
    assert lines[:2] == [f"type {LIFT}", "status quarantined"]
    assert "fields" not in lines and not any(line.startswith("storage") for line in lines)
    assert lines[lines.index("issues") + 1].startswith("  example examples/bad.json: ")


def test_show_of_an_unknown_type_fails(env: Env) -> None:
    result = env.run("types", "show", "co.acme.Nope@1.0.0")
    assert result.exit_code == 1 and "error: no registration 'co.acme.Nope@1.0.0'" in result.stderr


# --- validate and lock --------------------------------------------------------------------------


def test_validate_says_ok_for_a_valid_package(env: Env) -> None:
    assert env.ok("types", "validate", str(env.package()), "--root", str(env.root)) == [
        f"ok {LIFT} object-backed 4 index fields"
    ]


def test_validate_prints_every_issue_and_exits_1(env: Env) -> None:
    break_lift(env)
    result = env.run("types", "validate", str(env.package()), "--root", str(env.root))
    assert result.exit_code == 1
    assert result.stdout.startswith("  example examples/bad.json: ")


def test_validate_registers_nothing(env: Env) -> None:
    env.ok("types", "validate", str(env.package()), "--root", str(env.root))
    assert env.ok("types", "ls") == []


def test_lock_writes_type_lock_and_prints_the_content_hash(env: Env) -> None:
    (env.package() / "README.md").write_text("changed\n")
    result = env.run("types", "validate", str(env.package()), "--root", str(env.root))
    assert result.exit_code == 1 and "lock README.md: hash differs" in result.stdout
    (line,) = env.ok("types", "lock", str(env.package()))
    assert line.startswith("content_hash ") and len(line) == 13 + 64
    assert env.ok("types", "validate", str(env.package()), "--root", str(env.root)) == [
        f"ok {LIFT} object-backed 4 index fields"
    ]


# --- deprecate ---------------------------------------------------------------------------------


def test_deprecate_retires_a_version(env: Env) -> None:
    env.ok("types", "sync", str(env.root))
    assert env.ok("types", "deprecate", LIFT, "--reason", "superseded") == [f"deprecated {LIFT}"]
    assert env.ok("types", "ls", "--status", "deprecated")[0].startswith(LIFT)
    assert env.ok("types", "sync", str(env.root)) == ["up to date (2 packages)"]


def test_deprecate_needs_a_reason_and_a_known_active_version(env: Env) -> None:
    env.ok("types", "sync", str(env.root))
    assert env.run("types", "deprecate", LIFT).exit_code == 2  # --reason is required
    unknown = env.run("types", "deprecate", "co.acme.Nope@1.0.0", "--reason", "x")
    assert unknown.exit_code == 1 and "error: no registration" in unknown.stderr
    env.ok("types", "deprecate", LIFT, "--reason", "old")
    again = env.run("types", "deprecate", LIFT, "--reason", "again")
    assert again.exit_code == 1 and "only an active version" in again.stderr


# --- watch -------------------------------------------------------------------------------------


def test_watch_syncs_what_it_finds_on_the_first_poll(env: Env) -> None:
    lines = env.ok("types", "watch", str(env.root), "--interval", "0", "--max-cycles", "2")
    assert lines == [
        "changed co.acme/LiftPlan/1.0.0 (added)",
        "changed co.acme/SafetyObservation/1.0.0 (added)",
        f"registered {LIFT}",
        f"registered {OBSERVATION}",
    ]
    assert env.ok("types", "ls", "--status", "active")  # they are registered


def test_watch_on_an_already_synced_root_only_confirms(env: Env) -> None:
    env.ok("types", "sync", str(env.root))
    lines = env.ok("types", "watch", str(env.root), "--interval", "0", "--max-cycles", "1")
    assert lines[-1] == "up to date (2 packages)"


def test_watch_of_a_missing_directory_fails(env: Env) -> None:
    result = env.run("types", "watch", str(env.root / "nowhere"), "--max-cycles", "1")
    assert result.exit_code == 1 and "error: no such directory" in result.stderr
