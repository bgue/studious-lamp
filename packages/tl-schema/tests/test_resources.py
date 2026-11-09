"""``schema_root``: checkout, packaged fallback and the built wheel (P2-REL-S1)."""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from tl_schema import resources

REPO = Path(__file__).resolve().parents[3]


def test_checkout_resolves_repository_schema() -> None:
    assert resources.schema_root() == REPO / "schema"


def test_packaged_path_when_repo_probe_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resources, "_repo_schema", lambda: None)
    root = resources.schema_root()
    assert root != REPO / "schema"
    assert root.parts[-3:] == ("tl_schema", "_data", "schema")


@pytest.mark.slow
def test_built_wheel_carries_schema_data(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    subprocess.run(
        [
            uv,
            "build",
            "--wheel",
            "--offline",
            "--out-dir",
            str(tmp_path),
            str(REPO / "packages" / "tl-schema"),
        ],
        check=True,
        capture_output=True,
    )
    (wheel,) = tmp_path.glob("tl_schema-*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert "tl_schema/_data/schema/core/core.yaml" in names
    assert "tl_schema/_data/schema/settings/access-words.yaml" in names
    assert not [n for n in names if n.endswith((".db", ".sqlite", "tokens.json"))]
