"""Check a directory of release wheels (P2-REL-T03, Sec-6). Stdlib only.

Usage: python dev/release/check_wheels.py DIR [--repo ROOT]
  DIR     a directory of *.whl files, e.g. dist/release-0.1.0
  --repo  the repository whose [tool.uv.workspace] members give the expected wheel count
          (default: the checkout this script is in)
Prints `OK <n> wheels` and exits 0, or one line per problem and exits 1. Exits 2 on bad usage.

Rules (each problem line names the wheel and, where there is one, the member):
  - a member whose basename matches a secret-like pattern
    (tokens.json, *.db, *.sqlite*, *.pem, *.key, .env*)
  - a member whose path contains /dev/data/ or .gate/
  - tl-schema without tl_schema/_data/schema/core/core.yaml, or tl-cli without tl_cli/main.py
  - two wheels that disagree on the METADATA version
  - a wheel count that is not the workspace member count
  - a text member under 200 kB with a line that has `demo` followed later by `password` (any case)
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import tomllib
import zipfile
from pathlib import Path

SECRET_NAMES = ("tokens.json", "*.db", "*.sqlite*", "*.pem", "*.key", ".env*")
FORBIDDEN_PARTS = ("/dev/data/", ".gate/")
REQUIRED: dict[str, tuple[str, ...]] = {
    "tl_schema": ("tl_schema/_data/schema/core/core.yaml",),
    "tl_cli": ("tl_cli/main.py",),
}
TEXT_LIMIT = 200_000  # bytes; text members at or above this size are not scanned
DEMO_PASSWORD = re.compile(r"demo.*password", re.IGNORECASE)
VERSION_LINE = re.compile(r"^Version: *(\S+)\s*$", re.MULTILINE)


def workspace_members(repo: Path) -> list[Path]:
    """Directories named by [tool.uv.workspace] members (globs) that have a pyproject.toml."""
    data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    workspace = data.get("tool", {}).get("uv", {}).get("workspace", {})
    found: set[Path] = set()
    for pattern in workspace.get("members", []):
        for path in repo.glob(pattern):
            if (path / "pyproject.toml").is_file():
                found.add(path)
    excludes = workspace.get("exclude", [])
    kept = [
        path
        for path in found
        if not any(fnmatch.fnmatch(path.relative_to(repo).as_posix(), ex) for ex in excludes)
    ]
    return sorted(kept)


def _member_problems(wheel: str, zf: zipfile.ZipFile, names: list[str]) -> list[str]:
    problems: list[str] = []
    for info in zf.infolist():
        name = info.filename
        if name.endswith("/"):
            continue
        base = name.rsplit("/", 1)[-1].lower()
        if any(fnmatch.fnmatch(base, pattern) for pattern in SECRET_NAMES):
            problems.append(f"{wheel}: {name}: secret-like file name")
        if any(part in "/" + name for part in FORBIDDEN_PARTS):
            problems.append(f"{wheel}: {name}: path under dev/data/ or .gate/")
        if info.file_size < TEXT_LIMIT:
            data = zf.read(info)
            if b"\0" not in data:
                text = data.decode("utf-8", errors="replace")
                if any(DEMO_PASSWORD.search(line) for line in text.splitlines()):
                    problems.append(f"{wheel}: {name}: line mentions demo and password")
    for required in REQUIRED.get(wheel.split("-")[0], ()):
        if required not in names:
            problems.append(f"{wheel}: missing {required}")
    return problems


def _wheel_version(
    wheel: str, zf: zipfile.ZipFile, names: list[str]
) -> tuple[str | None, list[str]]:
    metadata = [n for n in names if n.count("/") == 1 and n.endswith(".dist-info/METADATA")]
    if len(metadata) != 1:
        return None, [f"{wheel}: expected one dist-info METADATA, found {len(metadata)}"]
    match = VERSION_LINE.search(zf.read(metadata[0]).decode("utf-8", errors="replace"))
    if match is None:
        return None, [f"{wheel}: no Version line in METADATA"]
    return match.group(1), []


def check(wheel_dir: Path, repo: Path) -> tuple[int, list[str]]:
    """Return (number of wheels, problem lines). An empty list means the directory passes."""
    problems: list[str] = []
    wheels = sorted(wheel_dir.glob("*.whl"))
    versions: dict[str, str] = {}
    present: set[str] = set()
    for path in wheels:
        wheel = path.name
        present.add(wheel.split("-")[0])
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            problems.extend(_member_problems(wheel, zf, names))
            version, version_problems = _wheel_version(wheel, zf, names)
        problems.extend(version_problems)
        if version is not None:
            versions[wheel] = version
    for dist in REQUIRED:
        if dist not in present:
            problems.append(f"{dist}: no wheel in {wheel_dir.name}")
    if len(set(versions.values())) > 1:
        pairs = ", ".join(f"{wheel} is {version}" for wheel, version in sorted(versions.items()))
        problems.append(f"version mismatch: {pairs}")
    expected = len(workspace_members(repo))
    if len(wheels) != expected:
        problems.append(f"wheel count: {len(wheels)} wheels, workspace has {expected} members")
    return len(wheels), problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a directory of release wheels.")
    parser.add_argument("wheel_dir", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    if not args.wheel_dir.is_dir():
        print(f"check_wheels: not a directory: {args.wheel_dir}", file=sys.stderr)
        return 2
    count, problems = check(args.wheel_dir, args.repo)
    if problems:
        for line in problems:
            print(line)
        return 1
    print(f"OK {count} wheels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
