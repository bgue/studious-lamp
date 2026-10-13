"""Applying an import plan: register the new documents, all or nothing (brief 9 M1; P1-I2-T12d).

The caller opens one unit of work and passes it in; every document of the plan is registered in
it, so a failure on one rolls back the lot. The source of each event is ``import:<job>``, so the
history says where a document came from. The plan is trusted to have been made against the same
ledger a moment before: ``RegisterDocument`` checks everything again and a number that appeared
in between is refused as it would be for anyone.

STUB (P1-I2-T12d): the bodies of apply_plan raise NotImplementedError; their signatures, options,
docstrings and the helpers are final. Each body has a STEPS comment. Implement them, then delete
this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import re

from tl_core.services.commands import CommandResult
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork

from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document
from tl_mod_documents.imports.model import ImportPlan

JOB = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class ImportRefusedError(ServiceError):
    """The plan cannot be applied as it stands (rows that cannot be imported; a bad job name)."""


def apply_plan(
    uow: UnitOfWork,
    scope: str,
    plan: ImportPlan,
    *,
    actor: str,
    job: str,
    skip_invalid: bool = False,
) -> list[CommandResult]:
    """Register the plan's new documents; the results are in the order of ``plan.new``.

    Raises ``ImportRefusedError`` before anything is written when ``job`` is not a short name of
    letters, digits, ``_``, ``.`` and ``-``, or when the plan has invalid rows and ``skip_invalid``
    is false. Anything ``RegisterDocument`` raises stops the import and leaves nothing registered
    (the caller's unit of work rolls back).
    """
    # STEPS
    # 1. When JOB.fullmatch(job) is None raise ImportRefusedError(f"the job name {job!r} must be 1
    #    to 64 letters, digits, '_', '.' or '-'").
    # 2. When plan.invalid and not skip_invalid raise ImportRefusedError(f"{len(plan.invalid)}
    #    row(s) cannot be imported; fix the file or skip them").
    # 3. For each row of plan.new, in order, results.append(handle_register_document(uow,
    #    RegisterDocument(actor=actor, source=f"import:{job}", scope=scope, number=row.number,
    #    title=row.title, description=row.note, doc_type=row.doc_type, discipline=row.discipline,
    #    originator=row.originator))). Write `title=row.title or row.number`: a new row always has
    #    a title, and the fallback only satisfies the type checker.
    # 4. Return the results.
    raise NotImplementedError
