"""Query language entry points (P0-I4 contract; workstream A replaces the bodies).

Rules every implementation keeps:
- SQL is built only from allow-listed envelope columns and bound parameters; no caller text is
  spliced into SQL.
- Pset paths compile to EXISTS sub-queries over ``cur_pset_values`` (the long-form typed index,
  brief 5.4), so filters stay dialect-neutral.
- Linked / CountLinked / MissingLink compile over ``cur_links`` (both directions). Only live links
  count: status ``active``, ``stale`` or ``broken``; ``suggested`` links (not yet accepted, brief
  7.3) and ``retracted`` links are excluded.
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
    from tl_core.query.parser import parse_text

    return parse_text(text)


#: A filtered count of up to this many rows tests them one by one for visibility (a lookup each)
#: instead of listing every hidden record of the ledger first.
COUNT_EACH_LIMIT = 3000


def run_query(uow: UnitOfWork, spec: QuerySpec) -> list[dict[str, Any]]:
    """Matching records as envelope dicts, ordered by ``spec.order_by`` then ``id``."""
    from sqlalchemy import text

    from tl_core import confidentiality
    from tl_core.query.compiler import compile_query
    from tl_core.services.queries import envelope_from_row

    if spec.limit is not None and spec.offset == 0:
        # the first ``limit`` readable rows: the page is read, then its hidden rows are dropped
        # (and more read if some were): the cost follows the page, not the hidden records
        listed = compile_query(spec, visibility="none")
        found = confidentiality.visible_rows(
            uow.conn(), listed.sql, listed.params, limit=spec.limit, id_expr="r.id"
        )
        return [envelope_from_row(row._mapping) for row in found]
    compiled = compile_query(spec)
    rows = uow.conn().execute(text(compiled.sql), compiled.params).mappings().all()
    return [envelope_from_row(row) for row in rows]


def count_query(uow: UnitOfWork, spec: QuerySpec) -> int:
    """Number of matching records (ignores limit, offset and order_by)."""
    from sqlalchemy import text

    from tl_core import confidentiality
    from tl_core.query.compiler import compile_query

    conn = uow.conn()
    if spec.where is not None and confidentiality.hidden_sql() is not None:
        # a filter usually leaves few rows: count them, and when they are few test each one
        raw = compile_query(spec, count=True, visibility="none")
        seen = int(conn.execute(text(raw.sql), raw.params).scalar_one())
        if seen == 0:
            return 0
        if seen <= COUNT_EACH_LIMIT:
            each = compile_query(spec, count=True, visibility="each")
            return int(conn.execute(text(each.sql), each.params).scalar_one())
    compiled = compile_query(spec, count=True)
    return int(conn.execute(text(compiled.sql), compiled.params).scalar_one())
