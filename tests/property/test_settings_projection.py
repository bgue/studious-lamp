"""Settings projection determinism: a rebuild gives the rows the live run gave (P0-I8-A, D6).

The projector reads only the event, so replaying the ledger must reproduce ``cur_setting`` and
``cur_setting_lock`` exactly, and the resolved values with them. ``setting_effect_applied`` is not
a projection and must survive the rebuild. Run with ``pytest tests/property -k settings``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core import settings as S
from tl_core.services.errors import SettingError
from tl_core.settings.effects import mark_applied
from tl_core.util import utcnow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "settings"))

from settings_world import ALICE, SRC, World, definitions_in_force  # noqa: E402

LAYERS = ["company", "project:P1", "project:P2"]
KEYS = ["t.limit", "t.plain", "t.advanced"]

operation = st.one_of(
    st.tuples(st.just("set"), st.sampled_from(KEYS), st.sampled_from(LAYERS), st.integers(0, 120)),
    st.tuples(st.just("reset"), st.sampled_from(KEYS), st.sampled_from(LAYERS), st.just(0)),
    st.tuples(st.just("lock"), st.just("t.limit"), st.sampled_from([None, 40, 70]), st.booleans()),
    st.tuples(st.just("later"), st.sampled_from(KEYS), st.sampled_from(LAYERS), st.integers(1, 3)),
)


def apply(world: World, op: tuple[Any, ...]) -> None:
    kind, key, a, b = op
    value: Any
    try:
        with open_uow(world.db) as uow:
            if kind in ("set", "later"):
                value = b if key == "t.limit" else f"v{b}"
                when = utcnow() + timedelta(hours=b) if kind == "later" else None
                S.set_setting(
                    uow, key=key, layer=a, value=value, actor=ALICE, source=SRC,
                    reason="r", applies_at=when,
                )  # fmt: skip
            elif kind == "reset":
                S.reset_setting(uow, key=key, layer=a, actor=ALICE, source=SRC, reason="r")
            else:
                bounds = None if a is None else {"maximum": a}
                S.lock_setting(
                    uow, key=key, locked=b, bounds=bounds, actor=ALICE, source=SRC, reason="r"
                )
    except SettingError:
        pass  # a refusal (locked, out of bounds, a value that does not fit) leaves nothing behind


def observe(world: World) -> dict[str, Any]:
    horizon = utcnow() + timedelta(hours=10)
    seen: dict[str, Any] = {
        "rows": world.rows("cur_setting"),
        "locks": world.rows("cur_setting_lock"),
    }
    for key in KEYS:
        for project in (None, "P1", "P2"):
            for moment in (None, horizon):
                got = world.get(key, project=project, at=moment)
                seen[f"{key}/{project}/{moment is None}"] = got.model_dump()
    return seen


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(ops=st.lists(operation, min_size=1, max_size=14))
def test_settings_projection_rebuild_equals_the_live_run(
    new_db: Callable[[], DbTarget], ops: list[tuple[Any, ...]]
) -> None:
    with definitions_in_force():
        world = World(new_db())
        for op in ops:
            apply(world, op)
        with open_uow(world.db) as uow:
            mark_applied(uow.conn(), ["restart"], applied_by="server")
        before = observe(world)
        rebuild_projections(world.db)
        assert observe(world) == before
        with open_uow(world.db, readonly=True) as uow:
            applied = uow.conn().execute(text("SELECT effect FROM setting_effect_applied")).all()
        assert [row.effect for row in applied] == ["restart"]
