"""`tl derive diff` says when the module cut its lists (the T14c open question)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import (
    FACTORY,
    KEY,
    ROWS,
    as_admin,
    csv_file,
    derive_env,
    runtime,
    schema_file,
    seed,
)
from tl_adapters.db import DbTarget
from tl_mod_documents.derivation import diff as diff_module

P = ["--project", "P123"]
OTHER = [("47-PSV-3001", "Relief", "PSV", "1"), ("47-PSV-3002", "Relief", "PSV", "1")]
NOTICE = "the lists above are cut; the counts on the first line are complete"


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[dict[str, str]]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    made = seed(values, tmp_path)
    with runtime(made):
        as_admin(values)
        schema = str(schema_file(tmp_path))
        assert tl(values, "derive", "schema", "register", schema, "--company").exit_code == 0
        yield values


def derive(env: dict[str, str], *args: str) -> str:
    result = tl(env, "derive", *args)
    assert result.exit_code == 0, result.output
    return result.stdout


def two_passes(env: dict[str, str], tmp_path: Path) -> None:
    derive(env, "open", "ISD-001", "A", "--schema", "instrument-index", *P)
    for name, rows in (("one.csv", ROWS), ("two.csv", OTHER)):
        derive(env, "content", KEY, str(csv_file(tmp_path, rows, name)), *P)
        derive(env, "start", KEY, *P)
        derive(env, "worker", "--once", "--factory", FACTORY)


def test_a_diff_that_fits_has_no_notice(env: dict[str, str], tmp_path: Path) -> None:
    two_passes(env, tmp_path)
    out = derive(env, "diff", KEY, *P)
    assert out.splitlines()[0].startswith("added 2  removed 3")
    assert NOTICE not in out


def test_a_diff_whose_lists_were_cut_says_so_and_keeps_the_counts(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(diff_module, "MAX_LISTED", 1)
    two_passes(env, tmp_path)
    lines = derive(env, "diff", KEY, *P).splitlines()
    assert lines[0].startswith("added 2  removed 3")  # exact
    assert lines.count("+ 47-PSV-3001") + lines.count("+ 47-PSV-3002") == 1  # cut at one
    assert lines[-1] == f"... {NOTICE}"
