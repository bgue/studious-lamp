"""Driver for dev/demos/P1-I8.sh: the parts of the demo that are not a `tl` command.

Modes (first argument; DIR is the demo's work directory):

* ``prepare DIR``: write the two package versions the script drafts, made from the company fixture
  ``schema/fixtures/co.acme.engineering@3.2.0.yaml``:
  ``pkg-3.3.0.yaml`` (version 3.3.0 with one more optional property in ``valve_data``, an additive
  change) and ``pkg-4.0.0.yaml`` (version 4.0.0 with ``size_in`` retyped to ``range: int``, a
  breaking change).
* ``registers DIR``: clause 5's legacy registers, in the columns of the ``dms-register`` loader and
  with the legacy values its mapping turns into document types and disciplines (``ISOMETRIC``
  becomes ``ISO``, ``PIPING`` becomes ``PIP``): ``register.csv`` (three documents of P123) and
  ``restricted.csv`` (one restricted document).

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

REGISTER_HEADER = (
    "DOC NO,TITLE,DOC TYPE,DISCIPLINE,ORIGINATOR,REV,STATUS,REV DATE,FILE PATH,CHECKED BY,REMARKS"
)
REGISTER_ROWS = (
    "ISO-0101,Isometric drawing unit 47,ISOMETRIC,PIPING,ACME,C,IFC,2026-03-02,"
    "ISO-0101_C.pdf,R. Singh,",
    "ISO-0102,Isometric drawing unit 48,ISOMETRIC,PIPING,ACME,B,AFC,2026-03-04,"
    "ISO-0102_B.pdf,R. Singh,",
    "PID-0201,P&ID unit 47,P&ID,PROCESS,ACME,A,IFC,2026-03-05,PID-0201_A.pdf,R. Singh,",
)
RESTRICTED_ROWS = (
    "SEC-0001,Security plan unit 47,PROCEDURE,CIVIL,ACME,A,IFC,2026-03-06,SEC-0001_A.pdf,R. Singh,",
)


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


def registers(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    body = "\n".join((REGISTER_HEADER, *REGISTER_ROWS)) + "\n"
    (directory / "register.csv").write_text(body, encoding="utf-8")
    restricted = "\n".join((REGISTER_HEADER, *RESTRICTED_ROWS)) + "\n"
    (directory / "restricted.csv").write_text(restricted, encoding="utf-8")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prepare" and len(sys.argv) == 3:
        prepare(Path(sys.argv[2]))
    elif mode == "registers" and len(sys.argv) == 3:
        registers(Path(sys.argv[2]))
    else:
        raise SystemExit("usage: p1_i8_demo.py prepare|registers DIR")


if __name__ == "__main__":
    main()
