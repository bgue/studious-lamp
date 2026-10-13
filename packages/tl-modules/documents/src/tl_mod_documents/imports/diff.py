"""Comparing a read file with the project's register: the import plan (brief 9 M1; P1-I2-T12c).

``plan_import`` checks every row the way ``RegisterDocument`` will (the number against the registry
pattern, the type and discipline against their code lists) and against the register, and says what
would happen: register it, skip it because the project already has the number, or refuse it with
the reasons. It reads and writes nothing.
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import Connection

from tl_mod_documents import registry
from tl_mod_documents.handlers.documents import register_problems
from tl_mod_documents.imports.model import ImportPlan, ImportRow


def plan_import(conn: Connection, scope: str, rows: list[ImportRow]) -> ImportPlan:
    """What importing ``rows`` into ``scope`` would do, row by row, in file order.

    A row is **invalid** when it carries problems from the mapping, has no title, repeats a number
    an earlier row of the file has, or breaks a rule of ``RegisterDocument``
    (``register_problems``); its reasons are added to its ``problems``. A valid row whose number the
    scope already holds is **exists** (listed by number, once); the others are **new**.
    """
    plan = ImportPlan()
    first_line: dict[str, int] = {}  # number to the line it first appeared on
    for row in rows:
        problems = list(row.problems)
        if row.number and row.number in first_line:
            problems.append(f"the number appears again; first on line {first_line[row.number]}")
        elif row.number:
            first_line[row.number] = row.line
        if not row.number and "the document number is blank" not in problems:
            problems.append("the document number is blank")  # a hand-built row; read_rows says it
        if row.title is None:
            problems.append("the title is blank")
        if not problems:
            problems.extend(
                register_problems(conn, scope, row.number, row.doc_type, row.discipline)
            )
        if problems:
            plan.invalid.append(replace(row, problems=problems))
        elif registry.find_document(conn, scope, row.number) is not None:
            plan.exists.append(row.number)
        else:
            plan.new.append(row)
    return plan
