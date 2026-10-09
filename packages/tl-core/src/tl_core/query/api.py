"""Query language entry points (P0-I4 contract; workstream A replaces the bodies).

Rules every implementation keeps:
- SQL is built only from allow-listed envelope columns and bound parameters; no caller text is
  spliced into SQL.
- Pset paths compile to EXISTS sub-queries over ``cur_pset_values`` (the long-form typed index,
  brief 5.4), so filters stay dialect-neutral.
- Linked / CountLinked / MissingLink compile over ``cur_links`` (both directions, retracted links
  excluded).
- Results are the same envelope dicts as ``tl_core.services.queries.list_records``.
- ``path(a>b>c)`` from brief 7.5 is out of scope for P0-I4 and raises QuerySyntaxError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from tl_core.query.ast import Expr
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork


class QuerySyntaxError(ServiceError):
    """The query text does not parse; ``position`` is the 0-based character offset."""

    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.position = position


@dataclass(frozen=True)
class QuerySpec:
    scope: str
    record_type: str | None = None
    where: Expr | None = None
    order_by: list[tuple[str, Literal["asc", "desc"]]] = field(
        default_factory=list[tuple[str, Literal["asc", "desc"]]]
    )
    limit: int | None = 500
    offset: int = 0
    include_voided: bool = False


def parse(text: str) -> Expr | None:
    """Parse query text into an AST; blank text gives None. Raises QuerySyntaxError."""
    raise NotImplementedError


def run_query(uow: UnitOfWork, spec: QuerySpec) -> list[dict[str, Any]]:
    """Matching records as envelope dicts, ordered by ``spec.order_by`` then ``id``."""
    raise NotImplementedError


def count_query(uow: UnitOfWork, spec: QuerySpec) -> int:
    """Number of matching records (ignores limit, offset and order_by)."""
    raise NotImplementedError
