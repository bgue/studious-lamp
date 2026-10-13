"""Comparing a read file with the project's register: the import plan (brief 9 M1; P1-I2-T12c).

``plan_import`` checks every row the way ``RegisterDocument`` will (the number against the registry
pattern, the type and discipline against their code lists) and against the register, and says what
would happen: register it, skip it because the project already has the number, or refuse it with
the reasons. It reads and writes nothing.

STUB (P1-I2-T12c): the bodies of plan_import raise NotImplementedError; their signatures, options,
docstrings and the helpers are final. Each body has a STEPS comment. Implement them, then delete
this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

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
    # STEPS
    # 1. plan = ImportPlan(); first_line: dict[str, int] = {} (number to the line it first appeared
    #    on, for every row with a non-blank number).
    # 2. For each row, in order: problems = list(row.problems). If row.number is non-blank and in
    #    first_line, append f"the number appears again; first on line {first_line[row.number]}";
    #    otherwise (and when non-blank) first_line[row.number] = row.line. If row.title is None,
    #    append "the title is blank". When problems is still empty and the number is non-blank,
    #    extend it with register_problems(conn, scope, row.number, row.doc_type, row.discipline).
    # 3. With problems: plan.invalid.append(replace(row, problems=problems)). Else if
    #    registry.find_document(conn, scope, row.number) is not None: plan.exists.append(row.number)
    #    (no repeats: the second occurrence of a number was already refused above). Else
    #    plan.new.append(row).
    # 4. Return plan.
    raise NotImplementedError
