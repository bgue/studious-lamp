"""The committed OpenAPI document and its drift check (`just check`).

    uv run python -m tl_api.openapi            # write docs/reference/openapi.json
    uv run python -m tl_api.openapi --check    # exit 1 when the committed file is out of date

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

from tl_api.app import create_app

#: Repository-relative location of the committed document.
OPENAPI_PATH = Path("docs/reference/openapi.json")


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


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "justfile").exists():
            return parent
    raise RuntimeError("cannot find the repository root (no justfile above this file)")


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
    if args:
        print("usage: python -m tl_api.openapi [--check]", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fresh, encoding="utf-8")
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
