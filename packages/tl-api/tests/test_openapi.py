"""The committed OpenAPI document and its drift check."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_api import openapi


def test_the_committed_document_is_current() -> None:
    committed = (openapi.repo_root() / openapi.OPENAPI_PATH).read_text(encoding="utf-8")
    assert committed == openapi.render(), "run `uv run python -m tl_api.openapi` and commit"
    assert openapi.main(["--check"]) == 0


def test_the_check_fails_on_a_stale_or_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(openapi, "repo_root", lambda: tmp_path)
    assert openapi.main(["--check"]) == 1  # missing
    assert openapi.main([]) == 0  # write
    assert openapi.main(["--check"]) == 0
    (tmp_path / openapi.OPENAPI_PATH).write_text("{}\n")
    assert openapi.main(["--check"]) == 1  # stale
    assert "out of date" in capsys.readouterr().err
    assert openapi.main(["--nonsense"]) == 2


def test_generation_is_deterministic() -> None:
    assert openapi.render() == openapi.render()


def test_the_document_describes_a_usable_api() -> None:
    doc = openapi.build_openapi()
    assert doc["openapi"].startswith("3.1")
    ids = [op["operationId"] for item in doc["paths"].values() for op in item.values()]
    assert len(ids) == len(set(ids)), "operation ids must be unique"
    for path, item in doc["paths"].items():
        for method, op in item.items():
            if path != "/health":
                assert op.get("security"), f"{method} {path} does not declare the bearer scheme"
            assert {"401", "404", "409", "422"} <= set(op["responses"]) or path == "/health", path
    assert "ErrorBody" in doc["components"]["schemas"]
    assert "HTTPBearer" in doc["components"]["securitySchemes"]
