"""``tl new projector <module>.<name>`` (stub: ticket P0-I8-T49 builds ``plan_projector``)."""

from __future__ import annotations

from collections.abc import Sequence

from tl_cli.scaffold.engine import Plan
from tl_cli.scaffold.names import ProjectorName


def plan_projector(projector: ProjectorName, events: Sequence[str]) -> Plan:
    """The files of a new projector inside an existing module. Not built yet."""
    raise NotImplementedError("tl new projector is built by ticket P0-I8-T49")
