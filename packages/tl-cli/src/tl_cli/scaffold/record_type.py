"""``tl new record-type <module>.<Class>`` (stub: ticket P0-I8-T48 builds ``plan_record_type``)."""

from __future__ import annotations

from tl_cli.scaffold.engine import Plan
from tl_cli.scaffold.names import RecordTypeName


def plan_record_type(record_type: RecordTypeName) -> Plan:
    """The files of a new record type inside an existing module. Not built yet."""
    raise NotImplementedError("tl new record-type is built by ticket P0-I8-T48")
