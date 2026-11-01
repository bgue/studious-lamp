"""Acceptance script for P2-WEB1 T06: the licence check reads the vendored-files manifest.

Every manifest is written in a temp directory, never in the repository. Prints one ``PASS <check>``
line per check; exits 0 when every check passes, 1 on the first failure.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
CHECK_PATH = ROOT / "dev" / "tools" / "check_licences.py"


def load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licences", CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licences"] = module
    spec.loader.exec_module(module)
    return module


CHECK = load_check()
VENDOR_DIR = Path("packages") / "tl-web" / "src" / "tl_web" / "static" / "vendor"
BODY = b"/* vendored test body */\n"


def passed(check: str) -> None:
    print(f"PASS {check}")


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


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp)
        vendor = tree / VENDOR_DIR
        (vendor / "htmx").mkdir(parents=True)
        (vendor / "htmx" / "htmx.min.js").write_bytes(BODY)
        good_sha = sha(BODY)

        good = write_manifest(tree, entry(sha256=good_sha))
        assert CHECK.vendored_problems(good) == [], CHECK.vendored_problems(good)
        passed("(a) a good manifest with a matching sha256 and BSD-2-Clause gives []")

        bad = write_manifest(tree, entry(sha256="0" * 64))
        lines = CHECK.vendored_problems(bad)
        assert len(lines) == 1, lines
        assert lines[0] == "vendored htmx: sha256 mismatch (htmx/htmx.min.js)", lines
        passed("(b) a wrong sha256 gives exactly one sha256 mismatch line")

        gone = write_manifest(tree, entry(path="htmx/absent.js", sha256=good_sha))
        lines = CHECK.vendored_problems(gone)
        assert lines == ["vendored htmx: file not found (htmx/absent.js)"], lines
        passed("(c) a missing file gives file not found")

        for licence in ("Apache-2.0", "0BSD", "MIT"):
            ok = write_manifest(tree, entry(licence=licence, sha256=good_sha))
            assert CHECK.vendored_problems(ok) == [], (licence, CHECK.vendored_problems(ok))
        gpl = write_manifest(tree, entry(licence="GPL-3.0-only", sha256=good_sha))
        lines = CHECK.vendored_problems(gpl)
        assert lines == ["vendored htmx: licence not allowed (GPL-3.0-only)"], lines
        passed("(d) GPL-3.0-only is refused; Apache-2.0, 0BSD and MIT pass")

        no_hash = write_manifest(tree, entry(sha256=None))
        lines = CHECK.vendored_problems(no_hash)
        assert lines == ["vendored htmx: missing field sha256"], lines
        passed("(e) an entry without sha256 gives missing field sha256 and nothing else")

        broken = write_manifest(tree, '[[file]\npath = "x"\n')
        lines = CHECK.vendored_problems(broken)
        assert lines == ["vendored src/tl_web/static/vendor/VENDORED.toml: unreadable manifest"], (
            lines
        )
        passed("(f) invalid TOML gives unreadable manifest")

        found_tree = Path(tmp) / "with"
        found_tree.mkdir()
        expected = write_manifest(found_tree, entry(sha256=good_sha))
        assert CHECK.find_manifests(found_tree) == [expected], CHECK.find_manifests(found_tree)
        empty_tree = Path(tmp) / "without"
        empty_tree.mkdir()
        assert CHECK.find_manifests(empty_tree) == [], CHECK.find_manifests(empty_tree)
        passed("(g) find_manifests finds the manifest in the glob layout and none without one")

    result = subprocess.run(
        ["uv", "run", "python", str(CHECK_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stdout.strip().splitlines()[-1] == "licences ok", result.stdout
    passed("(h) check_licences.py on the real repository exits 0 and prints licences ok")

    print("ALL PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL {exc!r}")
        raise SystemExit(1) from exc
