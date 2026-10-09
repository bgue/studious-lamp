"""Run every schema generator and write the outputs under ``generated/``.

This is a placeholder until P0-I1-T03 replaces it. ``--check`` must exit non-zero when the committed
generated files differ from what the generators would write; it never modifies files.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    mode = "check" if "--check" in args else "gen"
    print(f"tl_schema.generate {mode}: no generators yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
