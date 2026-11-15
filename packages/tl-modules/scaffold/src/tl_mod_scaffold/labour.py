"""The readiness check ``labour_requested`` (P2-I4B T05b fills the body; the interface is fixed).

It replaces the ``n_a`` placeholder of the same name in ``tl_mod_awp.checks_na`` (T05b moves the
entry point). Found through the entry point ``throughline.readiness_checks``.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from sqlalchemy import Connection
from tl_core.readiness import CheckResult, IwpFacts, ReadinessCheck
from tl_mod_requisitions.names import LABOR

NAME: Final = "labour_requested"
VERSION: Final = "1"
NO_ESTIMATE: Final = "this work package has no labour estimate yet"
NO_REQUISITION: Final = "no labour requisition for this work package"
NOT_APPROVED: Final = "a labour requisition is requested and not yet approved"
NOT_COVERED: Final = "no approved labour requisition covers the planned window"
COVERED: Final = "an approved labour requisition covers the planned window"
UNKNOWN: Final = "the labour requisitions of this work package could not be read"


class LabourRequested:
    """An approved labour requisition serves the IWP and covers its planned window."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({LABOR})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        raise NotImplementedError("T05b fills this body")


def labour_requested() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return LabourRequested()
