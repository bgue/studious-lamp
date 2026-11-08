"""Five readiness checks that answer ``n_a`` until the modules they wait for exist (P2-I2-T06b).

The names are reserved now so the readiness screen lists them. Each check watches ``awp.IWP``,
reads nothing, uses no connection and answers ``n_a`` with a fixed detail; ``n_a`` counts as
passing for readiness (README D9) and never blocks a release. Found through the entry-point group
``throughline.readiness_checks``; each entry point names one zero-argument function below that
returns its check.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Connection
from tl_core.readiness import CheckResult, IwpFacts

VERSION = "1"
WATCHES: frozenset[str] = frozenset({"awp.IWP"})


class NotApplicable:
    """A readiness check that answers ``n_a`` with one fixed detail for every IWP."""

    version: str = VERSION
    watches: frozenset[str] = WATCHES

    def __init__(self, name: str, detail: str) -> None:
        self.name = name
        self._detail = detail

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        return CheckResult(
            name=self.name,
            version=self.version,
            state="n_a",
            detail=self._detail,
        )


def permits_planned() -> NotApplicable:
    return NotApplicable(
        "permits_planned",
        "not applicable yet: permit records are built in Phase 3",
    )


def inspections_planned() -> NotApplicable:
    return NotApplicable(
        "inspections_planned",
        "not applicable yet: inspection and test plan records are built in Phase 3",
    )


def labour_requested() -> NotApplicable:
    return NotApplicable(
        "labour_requested",
        "not applicable yet: labour requisitions arrive with the requisitions module",
    )


def predecessors_handed_over() -> NotApplicable:
    return NotApplicable(
        "predecessors_handed_over",
        "not applicable yet: hand-over of predecessor work is not recorded",
    )


def model_slice_available() -> NotApplicable:
    return NotApplicable(
        "model_slice_available",
        "not applicable yet: model records are built in Phase 3",
    )
