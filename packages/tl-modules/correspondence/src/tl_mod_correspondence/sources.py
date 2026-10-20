"""Register sources: records of other modules that appear in the master register (D3).

The master register is one list over the correspondence items plus the lines of the **sources** a
domain names (``item_source`` in its file). A source is code in this module, not SQL in a file:
it reads the other module's registry (which applies that module's own confidentiality) and maps
each row to a ``RegisterLine``. ``documents.transmittal`` is the first: the I2 transmittals of
a project appear as Document-control items of subtype ``transmittal``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection
from tl_mod_documents import registry as documents

from tl_mod_correspondence.names import DOMAIN_DOCUMENT_CONTROL

KIND_ITEM: Final = "item"
KIND_TRANSMITTAL: Final = "transmittal"


@dataclass(frozen=True)
class RegisterLine:
    """One line of the master register: an item, or a row a source maps to the same shape."""

    kind: str  # item or transmittal
    record_id: str
    scope: str
    number: str
    subject: str
    domain: str | None
    subtype: str | None
    direction: str
    state: str
    on: str | None  # received, issued or sent date
    counterparty: str | None
    response_due: str | None
    confidentiality: str
    thread_id: str | None = None


Source = Callable[[Connection, str, int], list[RegisterLine]]


def _transmittals(conn: Connection, scope: str, limit: int) -> list[RegisterLine]:
    lines: list[RegisterLine] = []
    for row in documents.list_transmittals(conn, scope, limit=limit):
        names = [str(r.get("name") or "") for r in row.recipients if r.get("name")]
        lines.append(
            RegisterLine(
                kind=KIND_TRANSMITTAL,
                record_id=row.id,
                scope=row.scope,
                number=row.number,
                subject=row.title,
                domain=DOMAIN_DOCUMENT_CONTROL,
                subtype="transmittal",
                direction="out" if row.direction == "outgoing" else "in",
                state=row.state,
                on=row.issued_on or row.created_at[:10],
                counterparty=names[0] if names else None,
                response_due=row.due_date,
                confidentiality="internal",
            )
        )
    return lines


SOURCES: Final[dict[str, Source]] = {"documents.transmittal": _transmittals}
SOURCE_NAMES: Final = frozenset(SOURCES)
