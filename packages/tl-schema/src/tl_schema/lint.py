"""Lint rules over package documents (brief 27.6).

STUB: the body below is implemented by P0-I2-T08a. Signatures and docstrings are the contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tl_schema.packages import PackageDoc


@dataclass(frozen=True)
class LintIssue:
    severity: Literal["error", "warning"]
    rule: str  # "L001" ... "L007"
    package: str  # "name@version"
    path: str  # "psets.valve_data.properties.size_in", "code_lists.MaterialCode"
    message: str


def lint_documents(docs: Sequence[PackageDoc]) -> list[LintIssue]:
    """Apply every lint rule to ``docs`` (the whole set at once, so cross-package rules work).

    Sorted by ``(package, path, rule)``. The rule table is in the ticket.
    """
    raise NotImplementedError
