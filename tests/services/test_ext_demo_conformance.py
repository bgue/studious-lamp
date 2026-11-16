"""The S4 rules and the module hooks serve `ext_demo`, a module no platform file names (P2-X4 S5).

`ext_demo` is the fixture under `tests/ext_demo/`: never installed, never an entry point. It is
added with `use_modules`; the rule functions of `test_module_conformance.py` are called, not
copied. The CLI group is checked here too (the root test environment holds `tl_cli`).
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from tl_adapters.db import as_target, create_schema
from tl_cli.main import _add_module_groups  # pyright: ignore[reportPrivateUsage]
from tl_core.modules import (
    IN_TREE_SURFACES,
    ModuleSpec,
    hook_failures,
    load_modules,
    module_commands,
    use_modules,
)
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "ext_demo"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from load import ext_demo_spec  # noqa: E402  # pyright: ignore[reportMissingImports]
from test_module_conformance import (  # noqa: E402
    Marks,
    load_exclusions,
    load_undecided,
    mark_problems,
    money_problems,
    proposable_rows,
    ratchet_problems,
    word_problems,
)

NAME = "ExtDemoAddNote"
NOT_FOUND = "error: no such note"


@pytest.fixture
def spec() -> Iterator[ModuleSpec]:
    added = ext_demo_spec()
    with use_modules([*load_modules(), added]):
        yield added


def test_the_row_is_in_module_commands_and_no_hook_failed(spec: ModuleSpec) -> None:
    rows = [row for row in module_commands() if row.module == "ext_demo"]
    assert [row.name for row in rows] == [NAME]
    assert (rows[0].access, rows[0].meta) == ("user", {"delegation": "excluded:reserved"})
    assert hook_failures() == {}
    assert spec.name == "ext_demo" and spec.name not in IN_TREE_SURFACES


def test_the_word_and_money_rules_find_nothing(spec: ModuleSpec) -> None:
    rows = [row for row in module_commands() if row.module == "ext_demo"]
    assert word_problems(rows, load_modules()) == []
    assert word_problems(module_commands(), load_modules()) == []
    assert money_problems(rows, Marks({}, {})) == []


def test_the_one_mark_is_in_row_meta_and_a_copy_without_meta_fails(spec: ModuleSpec) -> None:
    rows = [row for row in module_commands() if row.module == "ext_demo"]
    kw = {"agent_rows": proposable_rows(load_modules(), agent_only=True), "exclusions": set()}
    assert mark_problems(rows, Marks({}, {}), **kw) == []
    bare = [dataclasses.replace(row, meta={}) for row in rows]
    found = mark_problems(bare, Marks({}, {}), **kw)
    assert any("exactly one" in p for p in found)
    # a mark kept in the file instead of the row meta is refused for a module outside the tree
    in_file = mark_problems(bare, Marks({}, {NAME: "reserved"}), **kw)
    assert any("row meta" in p for p in in_file)


def test_the_command_is_decided_and_the_ratchet_does_not_grow(spec: ModuleSpec) -> None:
    decided = proposable_rows(load_modules(), agent_only=False) | load_exclusions()
    assert NAME in decided
    assert NAME not in proposable_rows(load_modules(), agent_only=True)  # no agent tool
    rows = [row for row in module_commands() if row.module == "ext_demo"]
    assert ratchet_problems(rows, decided, []) == []
    assert ratchet_problems(module_commands(), decided, load_undecided()) == []
    # without the proposable row the command would be undecided, and a new module may not be
    assert any("must be decided" in p for p in ratchet_problems(rows, set(), []))


def test_every_hook_ref_names_the_modules_own_package(spec: ModuleSpec) -> None:
    refs = [spec.commands, *spec.read_routers, *spec.tools, *spec.cli_groups]
    assert len(refs) == 4
    assert all(ref is not None and ref.startswith("tl_mod_ext_demo.") for ref in refs)


def test_no_platform_source_file_names_the_module() -> None:
    sources = [*ROOT.glob("packages/*/src"), *ROOT.glob("packages/tl-modules/*/src")]
    named = [
        str(path.relative_to(ROOT))
        for src in sources
        for path in src.rglob("*.py")
        if "ext_demo" in path.read_text(encoding="utf-8")
    ]
    assert named == []
    assert ext_demo_spec().name not in {s.name for s in load_modules()}


# --- the CLI group --------------------------------------------------------------------------


def run(db: Path, tmp_path: Path, env: str, *argv: str) -> tuple[int, str]:
    root = typer.Typer()
    _add_module_groups(root, load_modules())
    environ = {"TL_ENV": env, "TL_SESSION_FILE": str(tmp_path / "session.json")}
    result = CliRunner().invoke(root, list(argv), obj=as_target(str(db)), env=environ)
    return result.exit_code, result.output


@pytest.fixture
def cli_db(spec: ModuleSpec, tmp_path: Path) -> Path:
    db = tmp_path / "tl.db"
    create_schema(as_target(str(db)))
    return db


def test_the_group_appears_under_add_module_groups(spec: ModuleSpec) -> None:
    root = typer.Typer()
    _add_module_groups(root, load_modules())
    assert "ext_demo" in [group.name for group in root.registered_groups]
    group = next(g for g in root.registered_groups if g.name == "ext_demo")
    commands = group.typer_instance.registered_commands  # type: ignore[union-attr]
    names = [c.name or getattr(c.callback, "__name__", "") for c in commands]
    assert sorted(names) == ["add", "get"]


def test_a_missing_key_and_a_hidden_key_print_one_text_and_exit_non_zero(
    cli_db: Path, tmp_path: Path
) -> None:
    code, out = run(cli_db, tmp_path, "test", "ext_demo", "add", "N-1", "--project", "P123",
                    "--title", "Open", "--body", "plain words")  # fmt: skip
    assert (code, out.strip()) == (0, "added N-1")
    code, out = run(cli_db, tmp_path, "test", "ext_demo", "add", "N-2", "--project", "P123",
                    "--title", "Hush", "--body", "secret words", "--restricted")  # fmt: skip
    assert (code, out.strip()) == (0, "added N-2")
    # the file's owner (a dev ledger, no session) reads restricted notes
    code, out = run(cli_db, tmp_path, "test", "ext_demo", "get", "N-2", "--project", "P123")
    assert code == 0 and "secret words" in out
    # with no session and no dev setup the reader is the lowest clearance
    seen = [
        run(cli_db, tmp_path, "prod", "ext_demo", "get", key, "--project", "P123")
        for key in ("N-2", "N-404")
    ]
    assert [code for code, _ in seen] == [1, 1]
    assert {out.strip() for _, out in seen} == {NOT_FOUND}
    code, out = run(cli_db, tmp_path, "prod", "ext_demo", "get", "N-1", "--project", "P123")
    assert code == 0 and "plain words" in out
    assert all("restricted" not in out and "secret" not in out for _, out in seen)
