"""The licence check reads the vendored-files manifest (P2-WEB1-T06).

``VENDORED.toml`` lists the third-party files served by the web client (htmx, pdf.js) with a
licence and a SHA-256 each. A copyleft licence, a missing field, a missing file or a hash that does
not match fails the check; the committed manifest passes. Every manifest here is written under
``tmp_path``, never in the repository.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "dev" / "tools" / "check_licences.py"
VENDOR_DIR = Path("packages") / "tl-web" / "src" / "tl_web" / "static" / "vendor"
BODY = b"/* vendored test body */\n"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licences_vendored", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licences_vendored"] = module
    spec.loader.exec_module(module)
    return module


CHECK = load()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_manifest(tree: Path, text: str) -> Path:
    """Write ``VENDORED.toml`` in the glob layout under ``tree`` and return its path."""
    manifest = tree / VENDOR_DIR / "VENDORED.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(text, encoding="utf-8")
    return manifest


def entry(
    *,
    path: str = "htmx/htmx.min.js",
    name: str = "htmx",
    licence: str = "BSD-2-Clause",
    sha256: str | None = None,
) -> str:
    lines = ["[[file]]", f'path = "{path}"', f'name = "{name}"', 'version = "2.0.4"']
    lines.append(f'licence = "{licence}"')
    lines.append('url = "https://example.invalid/htmx.tgz"')
    if sha256 is not None:
        lines.append(f'sha256 = "{sha256}"')
    return "\n".join(lines) + "\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    vendor = tmp_path / VENDOR_DIR
    (vendor / "htmx").mkdir(parents=True)
    (vendor / "htmx" / "htmx.min.js").write_bytes(BODY)
    return tmp_path


def test_a_good_manifest_gives_no_problem(tree: Path) -> None:
    good = write_manifest(tree, entry(sha256=sha(BODY)))
    assert CHECK.vendored_problems(good) == []


def test_a_wrong_hash_is_exactly_one_mismatch_line(tree: Path) -> None:
    bad = write_manifest(tree, entry(sha256="0" * 64))
    assert CHECK.vendored_problems(bad) == ["vendored htmx: sha256 mismatch (htmx/htmx.min.js)"]


def test_an_upper_case_hash_still_matches(tree: Path) -> None:
    upper = write_manifest(tree, entry(sha256=sha(BODY).upper()))
    assert CHECK.vendored_problems(upper) == []


def test_a_missing_file_is_reported(tree: Path) -> None:
    gone = write_manifest(tree, entry(path="htmx/absent.js", sha256=sha(BODY)))
    assert CHECK.vendored_problems(gone) == ["vendored htmx: file not found (htmx/absent.js)"]


@pytest.mark.parametrize("licence", ["Apache-2.0", "0BSD", "MIT"])
def test_a_permissive_licence_passes(tree: Path, licence: str) -> None:
    ok = write_manifest(tree, entry(licence=licence, sha256=sha(BODY)))
    assert CHECK.vendored_problems(ok) == []


@pytest.mark.parametrize("licence", ["GPL-3.0-only", "AGPL-3.0-or-later", "LGPL-2.1-only"])
def test_a_copyleft_licence_fails(tree: Path, licence: str) -> None:
    bad = write_manifest(tree, entry(licence=licence, sha256=sha(BODY)))
    assert CHECK.vendored_problems(bad) == [f"vendored htmx: licence not allowed ({licence})"]


def test_an_entry_without_a_hash_gives_the_missing_field_and_nothing_else(tree: Path) -> None:
    no_hash = write_manifest(tree, entry(sha256=None))
    assert CHECK.vendored_problems(no_hash) == ["vendored htmx: missing field sha256"]


def test_invalid_toml_is_one_unreadable_manifest_line(tree: Path) -> None:
    broken = write_manifest(tree, '[[file]\npath = "x"\n')
    assert CHECK.vendored_problems(broken) == [
        "vendored src/tl_web/static/vendor/VENDORED.toml: unreadable manifest"
    ]


def test_find_manifests_finds_the_glob_layout_and_none_without_one(tmp_path: Path) -> None:
    with_one, without = tmp_path / "with", tmp_path / "without"
    with_one.mkdir()
    without.mkdir()
    expected = write_manifest(with_one, entry(sha256=sha(BODY)))
    assert CHECK.find_manifests(with_one) == [expected]
    assert CHECK.find_manifests(without) == []


def test_the_committed_manifest_is_found_and_passes() -> None:
    manifests = CHECK.find_manifests(ROOT)
    assert [m.name for m in manifests] == ["VENDORED.toml"]
    assert CHECK.vendored_problems(manifests[0]) == []
