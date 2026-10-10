"""Numbering property: any mix of creates gives unique keys, contiguous per counter (P0-I3).

Run with ``pytest tests/property -k numbering``. The creates here are sequential; concurrent
creators are covered by ``test_concurrent_creators_never_get_the_same_key`` in
``tests/services/test_numbering.py``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.numbering.config import NumberingPattern, NumberingRegistry, use_numbering
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record

PATTERN = NumberingPattern(
    id="p",
    record_type="core.Record",
    scope="project:*",
    template="{project}-{type}-{discipline}-{seq:3}",
    type_code="REC",
    reserved=[(3, 4)],
)
creates = st.lists(
    st.tuples(st.sampled_from(["P1", "P2"]), st.sampled_from(["PIP", "ELE", "CIV"])),
    min_size=1,
    max_size=25,
)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(plan=creates)
def test_numbering_keys_are_unique_and_contiguous_per_counter(
    new_db: Callable[[], DbTarget],
    plan: list[tuple[str, str]],
) -> None:
    with use_numbering(NumberingRegistry([PATTERN])):
        db = new_db()
        create_schema(db)
        keys: list[str] = []
        per_counter: dict[tuple[str, str], list[int]] = defaultdict(list)
        for project, discipline in plan:
            with open_uow(db) as uow:
                result = handle_create_record(
                    uow,
                    CreateRecord(
                        actor="user:dev",
                        source="test",
                        scope=f"project:{project}",
                        record_type="core.Record",
                        title="t",
                        numbering={"discipline": discipline},
                    ),
                )
            assert result.key is not None
            keys.append(result.key)
            per_counter[(project, discipline)].append(int(result.key.rsplit("-", 1)[1]))
        assert len(keys) == len(set(keys))
        for sequences in per_counter.values():
            expected = [n for n in range(1, len(sequences) + 5) if n not in (3, 4)]
            assert sequences == expected[: len(sequences)]
