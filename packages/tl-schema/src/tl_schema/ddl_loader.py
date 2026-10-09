"""Read the committed, generated DDL for a current-state table at runtime."""

from __future__ import annotations

from importlib.resources import files

from tl_schema.generators.ddl_types import Dialect


def statements(table: str, dialect: Dialect) -> list[str]:
    """The idempotent CREATE statements for ``table`` (for example ``cur_core_record``).

    Reads ``tl_schema/generated/ddl/<dialect>/<table>.sql``, which ``just gen`` writes. Statements
    are separated by a blank line and each ends with ``;``.
    """
    resource = files("tl_schema.generated").joinpath("ddl", dialect, f"{table}.sql")
    text = resource.read_text(encoding="utf-8")
    return [block.strip() for block in text.split("\n\n") if block.strip()]
