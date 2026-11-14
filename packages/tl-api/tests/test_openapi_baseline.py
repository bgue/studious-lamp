"""The OpenAPI release baseline: `--compat` fails on a breaking change, `--baseline` refuses one.

Every test that writes or compares a scratch baseline calls `main` on a copy in `tmp_path`; none
writes the repository's baseline file.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from tl_api import openapi
from tl_api.errors import ERROR_TABLE, ErrorSpec


def _committed() -> dict[str, Any]:
    text = (openapi.repo_root() / openapi.BASELINE_PATH).read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def _scratch_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> Path:
    monkeypatch.setattr(openapi, "repo_root", lambda: tmp_path)
    target = tmp_path / openapi.BASELINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(openapi.render_baseline(baseline), encoding="utf-8")
    return target


def _current_document(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    monkeypatch.setattr(openapi, "build_openapi", lambda: copy.deepcopy(document))


def test_the_committed_baseline_passes_compat(capsys: pytest.CaptureFixture[str]) -> None:
    assert openapi.main(["--compat"]) == 0, capsys.readouterr().err


def test_the_committed_baseline_lists_the_s1_error_codes() -> None:
    errors = _committed()["errors"]
    assert errors["invalid_idempotency_key"] == 422
    assert errors["idempotency_mismatch"] == 409
    assert errors["idempotency_in_progress"] == 409


def test_the_committed_baseline_has_no_prose() -> None:
    committed = _committed()
    assert openapi.strip_prose(committed) == committed


def test_a_property_named_like_prose_is_kept() -> None:
    node = {
        "properties": {"title": {"type": "string", "title": "Title"}},
        "description": "gone",
    }
    assert openapi.strip_prose(node) == {"properties": {"title": {"type": "string"}}}


def test_a_field_the_current_document_lacks_fails_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scratch = _committed()
    name, schema = next(
        (n, s) for n, s in scratch["openapi"]["components"]["schemas"].items() if "properties" in s
    )
    schema["properties"]["retired_field"] = {"type": "string"}
    _scratch_repo(tmp_path, monkeypatch, scratch)
    assert openapi.main(["--compat"]) == 1
    err = capsys.readouterr().err
    assert name in err
    assert "retired_field" in err
    assert openapi.RULE in err


def test_an_added_optional_field_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = copy.deepcopy(_committed()["openapi"])
    schema = next(s for s in doc["components"]["schemas"].values() if "properties" in s)
    schema["properties"]["added_note"] = {"type": "string"}
    _current_document(monkeypatch, doc)
    assert openapi.main(["--compat"]) == 0, capsys.readouterr().err


def test_a_removed_route_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = copy.deepcopy(_committed()["openapi"])
    path = sorted(doc["paths"])[0]
    del doc["paths"][path]
    _current_document(monkeypatch, doc)
    assert openapi.main(["--compat"]) == 1
    assert "operation removed" in capsys.readouterr().err


def test_a_removed_error_code_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = tuple(spec for spec in ERROR_TABLE if spec.error != "idempotency_mismatch")
    monkeypatch.setattr(openapi, "ERROR_TABLE", table)
    assert openapi.main(["--compat"]) == 1
    assert "error idempotency_mismatch: removed" in capsys.readouterr().err


def test_a_changed_error_status_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = tuple(
        dataclasses.replace(spec, status=422) if spec.error == "idempotency_mismatch" else spec
        for spec in ERROR_TABLE
    )
    monkeypatch.setattr(openapi, "ERROR_TABLE", table)
    assert openapi.main(["--compat"]) == 1
    assert "error idempotency_mismatch: status 409 -> 422" in capsys.readouterr().err


def test_a_new_error_code_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    extra = ErrorSpec(exc=ValueError, error="brand_new_code", status=418)
    monkeypatch.setattr(openapi, "ERROR_TABLE", (*ERROR_TABLE, extra))
    assert openapi.main(["--compat"]) == 0, capsys.readouterr().err


def test_a_missing_baseline_fails_in_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(openapi, "repo_root", lambda: tmp_path)
    assert openapi.main(["--compat"]) == 1
    err = capsys.readouterr().err.strip()
    assert err.count("\n") == 0
    assert "missing" in err


def test_baseline_refuses_a_breaking_change_and_leaves_the_file_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _scratch_repo(tmp_path, monkeypatch, _committed())
    before = target.read_bytes()
    table = tuple(spec for spec in ERROR_TABLE if spec.error != "idempotency_mismatch")
    monkeypatch.setattr(openapi, "ERROR_TABLE", table)
    assert openapi.main(["--baseline"]) == 1
    assert "error idempotency_mismatch: removed" in capsys.readouterr().err
    assert target.read_bytes() == before


def test_baseline_writes_an_additive_change_in_the_stated_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _scratch_repo(tmp_path, monkeypatch, _committed())
    extra = ErrorSpec(exc=ValueError, error="brand_new_code", status=418)
    monkeypatch.setattr(openapi, "ERROR_TABLE", (*ERROR_TABLE, extra))
    assert openapi.main(["--baseline"]) == 0
    text = target.read_text(encoding="utf-8")
    assert text == openapi.render_baseline(json.loads(text))
    assert text.endswith("}\n")
    assert json.loads(text)["errors"]["brand_new_code"] == 418
