"""Tests for the codegen driver: determinism, output shape, and the --check drift gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tl_schema import generate

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_KEYS = {
    "__init__.py",
    "ddl/postgres/cur_core_record.sql",
    "ddl/postgres/cur_feed_items.sql",
    "ddl/postgres/cur_feed_tags.sql",
    "ddl/postgres/cur_link_counts.sql",
    "ddl/postgres/cur_links.sql",
    "ddl/postgres/cur_numbering.sql",
    "ddl/postgres/cur_pset_values.sql",
    "ddl/postgres/cur_workflow_state.sql",
    "ddl/sqlite/cur_core_record.sql",
    "ddl/sqlite/cur_feed_items.sql",
    "ddl/sqlite/cur_feed_tags.sql",
    "ddl/sqlite/cur_link_counts.sql",
    "ddl/sqlite/cur_links.sql",
    "ddl/sqlite/cur_numbering.sql",
    "ddl/sqlite/cur_pset_values.sql",
    "ddl/sqlite/cur_workflow_state.sql",
    "json_schema/core.schema.json",
    "models.py",
}


def test_outputs_has_expected_keys_and_is_deterministic() -> None:
    first = generate.outputs()
    second = generate.outputs()
    assert set(first) == EXPECTED_KEYS
    assert list(first) == sorted(first)
    assert first == second


def test_outputs_contain_no_machine_paths() -> None:
    files = generate.outputs()
    for path, text in files.items():
        assert str(generate.SCHEMA_DIR) not in text, path
        assert str(generate.GENERATED_DIR) not in text, path
        assert str(REPO_ROOT) not in text, path
        assert text.endswith("\n") and not text.endswith("\n\n"), path


def test_models_define_record_and_event() -> None:
    models = generate.outputs()["models.py"]
    assert "class Record(" in models
    assert "class Event(" in models


def test_json_schema_defines_record_and_event() -> None:
    schema = json.loads(generate.outputs()["json_schema/core.schema.json"])
    assert "Record" in schema["$defs"]
    assert "Event" in schema["$defs"]


def test_main_writes_then_checks_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    assert generate.existing(tmp_path) == EXPECTED_KEYS
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0
    assert f"generated files are up to date ({len(EXPECTED_KEYS)} files)" in capsys.readouterr().out


def test_check_reports_differs_missing_stale_and_repair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    capsys.readouterr()

    # Edit a file: the check must name it as differing.
    models = tmp_path / "models.py"
    models.write_text(models.read_text(encoding="utf-8") + "# x\n", encoding="utf-8")
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "differs: models.py" in err
    assert "codegen drift: run `just gen` and commit the result" in err

    # Delete a file: the check must name it as missing.
    (tmp_path / "json_schema" / "core.schema.json").unlink()
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "missing: json_schema/core.schema.json" in err

    # Add a file the generators do not produce: the check must name it as stale.
    (tmp_path / "extra.py").write_text("# extra\n", encoding="utf-8")
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "stale: extra.py" in err

    # Re-running the writer repairs all three problems.
    assert generate.main(["--out", str(tmp_path)]) == 0
    capsys.readouterr()
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0
    assert "generated files are up to date" in capsys.readouterr().out


def test_ignores_pycache_directory(tmp_path: Path) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "models.cpython-312.pyc").write_bytes(b"\x00")
    assert generate.existing(tmp_path) == EXPECTED_KEYS
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0


def test_committed_generated_directory_is_in_sync() -> None:
    assert generate.main(["--check"]) == 0
