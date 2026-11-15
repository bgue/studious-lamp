"""The readiness check ``scaffold_tagged`` (P2-I4B T05a fills the body; the interface is fixed).

Found through the entry point ``throughline.readiness_checks`` (T05a adds the line): the entry
point's callable takes no argument and returns the check.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from sqlalchemy import Connection
from tl_core.readiness import CheckResult, IwpFacts, ReadinessCheck

from tl_mod_scaffold.names import SCAFFOLD

NAME: Final = "scaffold_tagged"
VERSION: Final = "1"
NO_SCAFFOLD: Final = "this work package requires no scaffold"
UNKNOWN: Final = "the scaffolds of this work package could not be read"


class ScaffoldTagged:
    """Every scaffold the IWP ``requires`` stands, is tagged green and is not overdue."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({SCAFFOLD})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        raise NotImplementedError("T05a fills this body")


def scaffold_tagged() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return ScaffoldTagged()
