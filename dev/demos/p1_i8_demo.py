"""Driver for dev/demos/P1-I8.sh: the parts of the demo that are not a `tl` command.

Modes (first argument; DIR is the demo's work directory):

* ``prepare DIR``: write the two package versions the script drafts, made from the company fixture
  ``schema/fixtures/co.acme.engineering@3.2.0.yaml``:
  ``pkg-3.3.0.yaml`` (version 3.3.0 with one more optional property in ``valve_data``, an additive
  change) and ``pkg-4.0.0.yaml`` (version 4.0.0 with ``size_in`` retyped to ``range: int``, a
  breaking change).

Every edit is checked to match exactly once; a fixture that drifts fails the demo loudly.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "schema" / "fixtures" / "co.acme.engineering@3.2.0.yaml"

ADDED_PROPERTY = """      actuator_make:
        label: Actuator make
        description: Make of the actuator fitted to the valve.
        range: string
        enforcement: advisory"""


def replace_once(text: str, old: str, new: str) -> str:
    found = text.count(old)
    if found != 1:
        raise SystemExit(f"prepare: expected one match for {old!r} in the fixture, found {found}")
    return text.replace(old, new)


def prepare(directory: Path) -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    directory.mkdir(parents=True, exist_ok=True)

    additive = replace_once(text, "version: 3.2.0\n", "version: 3.3.0\n")
    additive = replace_once(
        additive, "\n\n  safety_data:", "\n" + ADDED_PROPERTY + "\n\n  safety_data:"
    )
    (directory / "pkg-3.3.0.yaml").write_text(additive, encoding="utf-8")

    retyped = replace_once(text, "version: 3.2.0\n", "version: 4.0.0\n")
    retyped = replace_once(retyped, "        range: decimal\n", "        range: int\n")
    (directory / "pkg-4.0.0.yaml").write_text(retyped, encoding="utf-8")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prepare" and len(sys.argv) == 3:
        prepare(Path(sys.argv[2]))
    else:
        raise SystemExit("usage: p1_i8_demo.py prepare DIR")


if __name__ == "__main__":
    main()
