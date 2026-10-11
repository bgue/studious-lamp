"""``ChangeSetting``: the command behind ``propose_setting_change`` (brief 30.4; P0-I8 D3).

An agent never sets a value directly. It proposes a ``ChangeSetting`` (MCP
``propose_setting_change``); a person accepts the proposal and the command then runs as that
person (``tl_core.services.proposals.accept_proposal``). The handler is the same one the API
route ``POST /commands/ChangeSetting`` runs for a person.

``layer`` is ``company``, ``project:<id>`` or ``user:<id>``; ``scope`` must be the ledger scope
of that layer (``project:<id>`` for a project layer, else ``company``), so a proposal sits in the
review queue of the scope it changes. ``reset`` true takes the layer's own value away (``value``
is then ignored). The command carries ``accept_risk`` for a person who runs it directly; a
proposal never carries it (the accepting person decides, see ``proposals.accept_proposal``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import model_validator

from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import SettingScopeError
from tl_core.settings.layers import parse_layer, stream_id
from tl_core.settings.service import change_setting
from tl_core.uow import UnitOfWork


class ChangeSetting(Command):
    key: str
    layer: str
    value: Any = None
    reset: bool = False
    reason: str | None = None
    accept_risk: bool = False
    applies_at: datetime | None = None

    @model_validator(mode="after")
    def check_layer_and_scope(self) -> ChangeSetting:
        try:
            ref = parse_layer(self.layer)
        except SettingScopeError as exc:
            raise ValueError(str(exc)) from exc
        if self.scope != ref.scope:
            raise ValueError(
                f"the scope of layer {self.layer!r} is {ref.scope!r}, not {self.scope!r}"
            )
        return self


def handle_change_setting(uow: UnitOfWork, cmd: ChangeSetting) -> CommandResult:
    """Set (or reset) ``cmd.key`` at ``cmd.layer`` as ``cmd.actor``; see ``settings.service``.

    The result is the setting's stream (``setting:<layer>:<key>``); ``events`` is empty when the
    layer already held the value. Raises the ``SettingError`` subclasses of
    :func:`~tl_core.settings.service.change_setting`.
    """
    outcome = change_setting(
        uow,
        key=cmd.key,
        layer=cmd.layer,
        value=cmd.value,
        reset=cmd.reset,
        actor=cmd.actor,
        source=cmd.source,
        reason=cmd.reason,
        accept_risk=cmd.accept_risk,
        applies_at=cmd.applies_at,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
    )
    layer = parse_layer(cmd.layer)
    return CommandResult(
        stream_id=stream_id(layer, cmd.key),
        key=None,
        version=outcome.version,
        events=outcome.events,
    )
