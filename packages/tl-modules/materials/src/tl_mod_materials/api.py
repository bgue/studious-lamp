"""The surface other modules call: ``post_movements`` (phase2 contracts section 4).

Movements are events on the lot's stream (ADR-0022). :func:`post_movements` is what P2-I4-A
fulfilment calls to issue what a requisition asked for; the seven movement commands of
``MATERIALS_COMMANDS`` take the same path (``handlers.movements.post_batch``), so there is one
set of rules. Reads are in ``tl_mod_materials.views``.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_core.uow import UnitOfWork

from tl_mod_materials.errors import MovementRuleError
from tl_mod_materials.handlers.movements import Movement, PostedMovement, post_batch
from tl_mod_materials.limits import MAX_MOVEMENTS

__all__ = ["Movement", "PostedMovement", "post_movements"]


def post_movements(
    uow: UnitOfWork,
    movements: Sequence[PostedMovement],
    *,
    actor: str,
    source: str,
    by_module: bool = False,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> list[str]:
    """Post a batch of 1 to 200 movements of one kind in one project, all or nothing, in the
    caller's unit of work; the ids of the ``StockLot.Moved`` events, in batch order.

    Every rule of the kind applies (see ``handlers/movements.py``): a refusal raises with a fixed
    message naming the movement's index, and the caller's unit of work rolls back, so no event of
    the batch survives. The access word of the calling command (``materials.move``,
    ``materials.reserve``, ``materials.adjust``) is the caller's to check, as for every handler.

    ``by_module`` says the caller is a module that has already decided it may act (the allow-list
    of the lot's record type lists generic commands only, and movements are not one of them, so
    there is nothing for it to skip here); it loosens no rule of the movement.
    """
    del by_module  # accepted for the contract; no rule depends on it (see the docstring)
    if not 1 <= len(movements) <= MAX_MOVEMENTS:
        raise MovementRuleError(f"a batch holds 1 to {MAX_MOVEMENTS} movements")
    kinds = {m.kind for m in movements}
    scopes = {m.scope for m in movements}
    if len(kinds) != 1 or len(scopes) != 1:
        raise MovementRuleError("a batch is of one kind of movement in one project")
    events = post_batch(
        uow,
        kind=kinds.pop(),
        scope=scopes.pop(),
        movements=movements,
        actor=actor,
        source=source,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return [e.event_id for e in events]
