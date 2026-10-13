"""The psets a record's class binds to it (ADR-0010; brief 9 M2: the class drives mandatory psets).

The core asks through ``ModuleSpec.bound_psets`` whenever it validates, forms or evaluates a
record of one of the module's types. Only a tag has a class. A tag keeps the psets of its class
even after the class is retired (a retired class stops taking new tags, not binding old ones).
"""

from __future__ import annotations

from sqlalchemy import Connection

from tl_mod_engineering import registry
from tl_mod_engineering.names import COMPANY, TAG


def bound_psets(conn: Connection, record_type: str, record_id: str) -> tuple[str, ...]:
    """The names of the psets the record's class requires, in the class's order; ``()`` if none."""
    if record_type != TAG:
        return ()
    tag = registry.get_tag(conn, record_id)
    if tag is None or tag.class_code is None:
        return ()
    classes = registry.find_tag_classes(conn, COMPANY, code=tag.class_code)
    return tuple(classes[-1].required_psets) if classes else ()
