"""The committed OpenAPI document, its drift check, and the release baseline (`just check`).

    uv run python -m tl_api.openapi            # write docs/reference/openapi.json
    uv run python -m tl_api.openapi --check    # exit 1 when the committed file is out of date
    uv run python -m tl_api.openapi --compat   # exit 1 on a breaking change against the baseline
    uv run python -m tl_api.openapi --baseline # refresh the baseline (release step; refuses breaks)

The baseline (`docs/reference/openapi.baseline.json`) holds the document and the error codes with
their statuses. It is refreshed only as a release step: a breaking change between releases needs
an `APPROVALS.md` line naming what breaks and a note in `api-compat.md`, and removals are
deprecated for at least one release first. Additive changes pass without a refresh.

The document is built from the routes alone: the app is created over a backend that fails if it
is ever used, so generation needs no database, no token file and no environment.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, NoReturn

from tl_core.bus import Bus
from tl_core.ledger import Ledger
from tl_core.uow import UnitOfWork
from tl_schema.compat import diff_openapi

from tl_api.app import create_app
from tl_api.errors import ERROR_TABLE

#: Repository-relative location of the committed document.
OPENAPI_PATH = Path("docs/reference/openapi.json")

#: Repository-relative location of the release baseline (document plus error codes).
BASELINE_PATH = Path("docs/reference/openapi.baseline.json")

#: The rule every breaking-change refusal ends with (one sentence).
RULE = (
    "The baseline is refreshed only as a release step: a breaking change between releases needs "
    "an APPROVALS.md line naming what breaks and a note in api-compat.md, and removals are "
    "deprecated for at least one release first."
)


class _UnusedBackend:
    """A backend for building the route table only."""

    @property
    def ledger(self) -> Ledger:
        self._fail()

    @property
    def bus(self) -> Bus:
        self._fail()

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        self._fail()

    def close(self) -> None:
        return None

    @staticmethod
    def _fail() -> NoReturn:
        raise RuntimeError("the OpenAPI generator never opens a backend")


def build_openapi() -> dict[str, Any]:
    """The OpenAPI document of ``create_app``, as plain data."""
    return create_app(_UnusedBackend()).openapi()


def render() -> str:
    """The document as committed: sorted keys, two-space indent, trailing newline."""
    return json.dumps(build_openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def baseline_document() -> dict[str, Any]:
    """The current document and error codes, in the baseline's shape."""
    return {
        "openapi": build_openapi(),
        "errors": {spec.error: spec.status for spec in ERROR_TABLE},
    }


def render_baseline(document: dict[str, Any]) -> str:
    """A baseline as committed: sorted keys, two-space indent, trailing newline."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def breaking_changes(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """One line per breaking change: API diff, then removed or re-statused error codes."""
    lines = diff_openapi(baseline.get("openapi", {}), current["openapi"])
    old_codes: dict[str, int] = baseline.get("errors", {})
    new_codes: dict[str, int] = current["errors"]
    for code in sorted(old_codes):
        if code not in new_codes:
            lines.append(f"error {code}: removed")
        elif new_codes[code] != old_codes[code]:
            lines.append(f"error {code}: status {old_codes[code]} -> {new_codes[code]}")
    return lines


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "justfile").exists():
            return parent
    raise RuntimeError("cannot find the repository root (no justfile above this file)")


def _baseline_file() -> Path:
    # An absolute BASELINE_PATH replaces the repository root, which the tests rely on.
    return repo_root() / BASELINE_PATH


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _report_breaks(problems: list[str]) -> None:
    for line in problems:
        print(line, file=sys.stderr)
    print(RULE, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    target = repo_root() / OPENAPI_PATH
    fresh = render()
    if args == ["--check"]:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != fresh:
            print(
                f"{OPENAPI_PATH} is out of date; run `uv run python -m tl_api.openapi` "
                "and commit the result",
                file=sys.stderr,
            )
            return 1
        return 0
    if args == ["--compat"]:
        baseline_file = _baseline_file()
        if not baseline_file.exists():
            print(
                f"{BASELINE_PATH} is missing; the baseline is written only as a release step "
                "(`just openapi-baseline`)",
                file=sys.stderr,
            )
            return 1
        problems = breaking_changes(_load(baseline_file), baseline_document())
        if problems:
            _report_breaks(problems)
            return 1
        return 0
    if args == ["--baseline"]:
        baseline_file = _baseline_file()
        current_document = baseline_document()
        if baseline_file.exists():
            problems = breaking_changes(_load(baseline_file), current_document)
            if problems:
                _report_breaks(problems)
                return 1
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text(render_baseline(current_document), encoding="utf-8")
        print(f"wrote {BASELINE_PATH}")
        return 0
    if args:
        print("usage: python -m tl_api.openapi [--check | --compat | --baseline]", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fresh, encoding="utf-8")
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
