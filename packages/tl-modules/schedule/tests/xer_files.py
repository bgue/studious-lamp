"""XER files of the schedule tests (the name is unique on purpose: L-P1-I0A-1)."""

from __future__ import annotations

from tl_xer.synth import make_xer, week_pair


def first_xer() -> bytes:
    return make_xer(week_pair()[0])


def second_xer() -> bytes:
    return make_xer(week_pair()[1])


def bad_xer(missing_table: str) -> bytes:
    """The first file without a table (a file that fails the XER document schema)."""
    lines = first_xer().decode("cp1252").split("\r\n")
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("%T\t"):
            skipping = line == f"%T\t{missing_table}"
        if line == "%E":
            skipping = False
        if not skipping:
            out.append(line)
    return "\r\n".join(out).encode("cp1252")


def multi_project_xer() -> bytes:
    """The first file with a second project, so one has to be named."""
    text = first_xer().decode("cp1252")
    row = "%R\t2\tOTHER\t1\t2026-10-05 08:00\t\t\t"
    return text.replace("\r\n%T\tCALENDAR", f"\r\n{row}\r\n%T\tCALENDAR", 1).encode("cp1252")
