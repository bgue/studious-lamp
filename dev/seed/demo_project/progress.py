"""progress section of P200 (P2-SEED-T11): earned progress on the IWPs that release started.

The four In progress IWPs (release) get hand entries: ``RecordManualProgress`` marks a different
share of the manual steps of their scope items done (a steps share per IWP, drawn with the
section's own ``rng``). Two of the four get one scope item installed (``InstallScopeItem``), so a
step that a record proves moves too. Two IWPs that have no open blocking ``complete`` constraint
are then field-completed (``CompleteIwpField``), which writes the last progress figure. A started
IWP is never returned to Issued; a Field complete IWP is a finished package.

The steps come from the rules of credit in force (``engine.edition_for``); the scope items come
from ``engine.scope_items``. Every command runs through ``world.on(day)`` before TODAY, on the day
after release started them. The hand entries are made by the project engineer (the ``user`` word
holder on the roster). No raw SQL writes.
"""

from __future__ import annotations

import random
from datetime import timedelta

from tl_adapters.db import open_uow
from tl_mod_awp.commands import CompleteIwpField, InstallScopeItem, ManualStep, RecordManualProgress
from tl_mod_awp.handlers.progress import (
    handle_complete_iwp_field,
    handle_install_scope_item,
    handle_record_manual_progress,
)
from tl_mod_awp.progress import engine

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, TODAY, World

#: the person who enters progress by hand (the project engineer, ``user`` word in the roster)
RECORDER = "lhartmann"
#: the share of each started IWP's manual steps that is entered, in key order (cycled)
SHARES = (0.25, 0.5, 0.75, 1.0)
INSTALLS_COUNT = 2  # started IWPs that get one scope item installed
COMPLETE_COUNT = 2  # started IWPs that are field-completed
DAY_OFFSET = 1  # the day before TODAY (release started the IWPs on TODAY - 1)


def _started(world: World) -> list[tuple[str, str]]:
    return [
        (str(r["id"]), str(r["key"]))
        for r in world.rows(
            "SELECT r.id AS id, r.key AS key FROM cur_core_record r "
            "WHERE r.type = 'awp.IWP' AND r.status = 'In progress' ORDER BY r.key"
        )
    ]


def _items_and_manual(world: World, iwp: str) -> tuple[list[str], list[tuple[str, str]]]:
    """The scope item ids of the IWP (key order) and its manual steps as (item id, step name)."""
    with open_uow(world.target, readonly=True) as uow:
        conn = uow.conn()
        items = sorted(engine.scope_items(conn, iwp), key=lambda item: item.key)
        rules = engine.edition_for(conn, PROJECT)
    manual = [
        (item.id, step.name)
        for item in items
        for step in rules.steps_for(item.commodity)
        if step.evidence == "manual"
    ]
    return [item.id for item in items], manual


def _blocked_complete(world: World, iwps: list[str]) -> set[str]:
    """The IWPs with an open or assigned blocking ``complete`` constraint (the move is refused)."""
    found = world.rows(
        "SELECT DISTINCT c.subject_id AS s FROM cur_core_constraint c "
        "JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.phase = 'complete' AND c.severity = 'blocking' "
        "AND coalesce(r.status, 'Open') IN ('Open', 'Assigned')"
    )
    blocked = {str(r["s"]) for r in found}
    return {i for i in iwps if i in blocked}


def build(world: World, rng: random.Random) -> None:
    day = TODAY - timedelta(days=DAY_OFFSET)
    started = _started(world)
    if not started:
        raise RuntimeError("no IWP is In progress: the release section must run first")

    for position, (iwp, _key) in enumerate(started):
        items, manual = _items_and_manual(world, iwp)
        share = SHARES[position % len(SHARES)]
        taken = max(1, round(share * len(manual)))
        picked = sorted(rng.sample(manual, min(taken, len(manual))))
        with world.on(day):
            world.run(
                handle_record_manual_progress,
                RecordManualProgress,
                by=RECORDER,
                iwp_id=iwp,
                steps=[ManualStep(scope_item_id=i, step=s, done=True) for i, s in picked],
                expected_version=world.version(iwp),
            )
        if position < INSTALLS_COUNT and items:
            item = rng.choice(items)
            with world.on(day):
                world.run(
                    handle_install_scope_item,
                    InstallScopeItem,
                    by=RECORDER,
                    record_id=item,
                    expected_version=world.version(item),
                )

    blocked = _blocked_complete(world, [iwp for iwp, _key in started])
    unblocked = [iwp for iwp, _key in started if iwp not in blocked]
    if len(unblocked) < COMPLETE_COUNT:
        raise RuntimeError("too few In progress IWPs can be field-completed")
    for iwp in sorted(rng.sample(unblocked, COMPLETE_COUNT)):
        with world.on(day):
            world.run(
                handle_complete_iwp_field,
                CompleteIwpField,
                by=RECORDER,
                iwp_id=iwp,
                expected_version=world.version(iwp),
                at=day,
            )


register("progress", build, needs=("awp.IWP",))
