"""Layer resolution, pure: origin, the modified marker, locks, bounds, schedules, pending effect."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from tl_core.settings.instants import to_us
from tl_core.settings.resolver import Entry, Lock, Snapshot, in_force, resolve_from
from tl_core.settings.types import SettingDefinition

KEY = "t.number"
UI_KEY = "ui.t.pref"
SEC = 1_000_000


def defn(key: str = KEY, *, scopes: list[str] | None = None, **extra: Any) -> SettingDefinition:
    return SettingDefinition.model_validate(
        {
            "key": key,
            "type": "int",
            "default": 10,
            "description": "d",
            "scopes": scopes or ["platform", "company", "project"],
            "lockable": True,
            "since": "0.1.0",
            **extra,
        }
    )


def entry(layer: str, value: Any, seq: int, at: int, *, reset: bool = False) -> Entry:
    return Entry(layer=layer, seq=seq, effective_us=at * SEC, reset=reset, value=value)


def view(
    entries: list[Entry],
    *,
    lock: Lock | None = None,
    project: str | None = None,
    user: str | None = None,
    at: int = 100,
    d: SettingDefinition | None = None,
    applied: dict[str, tuple[int, int]] | None = None,
) -> Any:
    d = d or defn()
    snapshot = Snapshot(
        entries={d.key: entries},
        locks={d.key: lock} if lock is not None else {},
        applied=applied or {},
    )
    return resolve_from(d, snapshot, project=project, user=user, at_us=at * SEC)


def test_with_nothing_set_the_default_comes_from_the_platform() -> None:
    got = view([])
    assert (got.value, got.origin, got.modified_here, got.locked, got.scheduled) == (
        10,
        "default",
        False,
        False,
        [],
    )


def test_the_most_specific_layer_wins_and_names_itself() -> None:
    entries = [entry("company", 20, 1, 1), entry("project:P1", 30, 2, 2)]
    assert (view(entries, project="P1").value, view(entries, project="P1").origin) == (
        30,
        "project",
    )
    assert (view(entries, project="P2").value, view(entries, project="P2").origin) == (
        20,
        "company",
    )
    assert (view(entries).value, view(entries).origin) == (20, "company")


def test_the_marker_follows_the_layer_being_viewed() -> None:
    entries = [entry("company", 20, 1, 1)]
    assert view(entries).modified_here is True  # viewing the company, which set it
    assert view(entries, project="P1").modified_here is False  # inherited, not modified here
    both = [*entries, entry("project:P1", 30, 2, 2)]
    assert view(both, project="P1").modified_here is True


def test_a_later_entry_replaces_an_earlier_one_at_the_same_layer() -> None:
    entries = [entry("company", 20, 1, 1), entry("company", 25, 2, 2)]
    assert view(entries).value == 25


def test_a_reset_gives_the_layer_back_to_what_is_above_it() -> None:
    entries = [
        entry("company", 20, 1, 1),
        entry("project:P1", 30, 2, 2),
        entry("project:P1", None, 3, 3, reset=True),
    ]
    got = view(entries, project="P1")
    assert (got.value, got.origin, got.modified_here) == (20, "company", False)


def test_a_scheduled_change_takes_effect_at_its_time_and_not_before() -> None:
    entries = [entry("company", 20, 1, 1), entry("company", 99, 2, 500)]
    before = view(entries, at=100)
    assert before.value == 20
    assert [(s.new_value, s.seq) for s in before.scheduled] == [(99, 2)]
    assert before.scheduled[0].applies_at == "1970-01-01T00:08:20.000000Z"
    after = view(entries, at=500)
    assert after.value == 99 and after.scheduled == []


def test_scheduled_changes_are_listed_soonest_first_and_a_reset_shows_no_value() -> None:
    entries = [
        entry("company", 5, 1, 900),
        entry("company", None, 2, 300, reset=True),
        entry("company", 7, 3, 600),
    ]
    got = view(entries, at=100)
    assert [(s.seq, s.new_value) for s in got.scheduled] == [(2, None), (3, 7), (1, 5)]


def test_a_change_recorded_later_but_applying_earlier_wins_until_the_later_one_applies() -> None:
    # recorded in this order: schedule 7 for t=500 (seq 2), then set 8 now (seq 3, t=100)
    entries = [entry("company", 5, 1, 1), entry("company", 7, 2, 500), entry("company", 8, 3, 100)]
    assert view(entries, at=200).value == 8
    assert view(entries, at=600).value == 7


def test_equal_instants_are_decided_by_seq() -> None:
    entries = [entry("company", 1, 4, 100), entry("company", 2, 5, 100)]
    assert view(entries).value == 2
    assert in_force(entries, "company", 100 * SEC) == entries[1]


def test_a_lock_makes_projects_ignore_their_own_value_but_not_the_company_one() -> None:
    entries = [entry("company", 20, 1, 1), entry("project:P1", 30, 2, 2)]
    got = view(entries, lock=Lock(locked=True), project="P1")
    assert (got.value, got.origin, got.locked, got.modified_here) == (20, "company", True, False)
    assert view(entries, lock=Lock(locked=True)).value == 20


def test_bounds_make_projects_ignore_a_value_outside_them() -> None:
    bounded = Lock(bounds={"maximum": 25})
    entries = [entry("company", 20, 1, 1), entry("project:P1", 30, 2, 2)]
    got = view(entries, lock=bounded, project="P1")
    assert (got.value, got.origin, got.bounds) == (20, "company", {"maximum": 25})
    inside = [entry("project:P1", 22, 1, 1)]
    assert view(inside, lock=bounded, project="P1").value == 22


def test_the_company_value_is_not_bounded_by_its_own_bounds() -> None:
    assert view([entry("company", 99, 1, 1)], lock=Lock(bounds={"maximum": 25})).value == 99


def test_the_user_layer_only_exists_for_keys_that_allow_it() -> None:
    plain = [entry("user:alice", 77, 1, 1)]
    assert view(plain, user="alice").value == 10  # t.number has no user layer
    ui = defn(
        UI_KEY,
        scopes=["platform", "user"],
        type="enum",
        default="a",
        validation={"choices": ["a", "b"]},
    )
    entries = [entry("user:alice", "b", 1, 1)]
    got = view(entries, user="alice", d=ui)
    assert (got.value, got.origin, got.modified_here) == ("b", "user", True)
    assert view(entries, user="bob", d=ui).value == "a"


def test_the_viewed_layer_is_the_most_specific_one_the_key_allows() -> None:
    entries = [entry("company", 20, 1, 1)]
    assert view(entries, project="P1", user="alice").modified_here is False  # viewing project
    assert view(entries, user="alice").modified_here is True  # no user layer: company


def test_a_platform_only_key_has_no_viewed_layer() -> None:
    d = defn(scopes=["platform"])
    got = view([entry("company", 5, 1, 1)], d=d)
    assert (got.value, got.origin, got.modified_here, got.scheduled) == (10, "default", False, [])


def test_a_layer_the_key_does_not_allow_is_ignored() -> None:
    d = defn(scopes=["platform", "company"])
    got = view([entry("project:P1", 5, 1, 1)], project="P1", d=d)
    assert got.value == 10


def test_a_live_key_owes_no_effect() -> None:
    assert view([entry("company", 20, 1, 1)]).pending_effect is None


def test_a_key_that_needs_a_restart_owes_it_until_one_happens() -> None:
    d = defn(effect="restart")
    entries = [entry("company", 20, 5, 10)]
    assert view(entries, d=d).pending_effect == "restart"
    assert view(entries, d=d, applied={"restart": (4, 5 * SEC)}).pending_effect == "restart"
    assert view(entries, d=d, applied={"restart": (5, 10 * SEC)}).pending_effect is None
    assert view(entries, d=d, applied={"restart": (9, 50 * SEC)}).pending_effect is None


def test_a_rebuild_also_satisfies_a_reindex() -> None:
    d = defn(effect="reindex")
    entries = [entry("company", 20, 5, 10)]
    assert view(entries, d=d).pending_effect == "reindex"
    assert view(entries, d=d, applied={"rebuild": (7, 20 * SEC)}).pending_effect is None
    assert view(entries, d=d, applied={"restart": (7, 20 * SEC)}).pending_effect == "reindex"


def test_a_scheduled_change_owes_its_effect_only_once_it_applies() -> None:
    d = defn(effect="rebuild")
    entries = [entry("company", 20, 5, 500)]
    assert view(entries, d=d, at=100).pending_effect is None
    assert view(entries, d=d, at=600).pending_effect == "rebuild"
    # a rebuild at t=300 (after the entry was recorded, before it applied) does not cover it
    early = {"rebuild": (9, 300 * SEC)}
    assert view(entries, d=d, at=600, applied=early).pending_effect == "rebuild"
    late = {"rebuild": (9, 550 * SEC)}
    assert view(entries, d=d, at=600, applied=late).pending_effect is None


def test_the_next_change_of_a_key_is_the_earliest_future_entry() -> None:
    snapshot = Snapshot(entries={KEY: [entry("company", 1, 1, 50), entry("company", 2, 2, 700)]})
    assert snapshot.next_change_us(KEY, 100 * SEC) == 700 * SEC
    assert snapshot.next_change_us(KEY, 700 * SEC) is None
    assert snapshot.next_change_us("other", 0) is None


# --- an oracle written from the rules, not from the code ---------------------------------------

LAYERS = ["company", "project:P1", "user:u1"]
entry_strategy = st.builds(
    lambda layer, value, at, reset: (layer, value, at, reset),
    st.sampled_from(LAYERS),
    st.integers(0, 6),
    st.integers(1, 50),
    st.booleans(),
)


def oracle(
    items: list[tuple[str, int, int, bool]],
    locked: bool,
    maximum: int | None,
    project: str | None,
    at: int,
) -> tuple[int, str]:
    """Value and origin by the module's rules; ``items`` are in recording order (seq = index)."""

    def holds(layer: str) -> int | None:
        live = [(t, i, v, r) for i, (lay, v, t, r) in enumerate(items) if lay == layer and t <= at]
        if not live:
            return None
        _, _, value, reset = max(live, key=lambda x: (x[0], x[1]))
        return None if reset else value

    order = ([f"project:{project}"] if project else []) + ["company"]
    for layer in order:
        value = holds(layer)
        if value is None:
            continue
        if layer.startswith("project:") and (locked or (maximum is not None and value > maximum)):
            continue
        return value, layer.split(":")[0]
    return 10, "default"


@settings(max_examples=300, deadline=None)
@given(
    st.lists(entry_strategy, max_size=8),
    st.booleans(),
    st.one_of(st.none(), st.integers(0, 6)),
    st.sampled_from([None, "P1"]),
    st.integers(0, 60),
)
def test_resolution_matches_an_independent_oracle(
    items: list[tuple[str, int, int, bool]],
    locked: bool,
    maximum: int | None,
    project: str | None,
    at: int,
) -> None:
    entries = [
        Entry(layer, i + 1, t * SEC, reset, None if reset else v)
        for i, (layer, v, t, reset) in enumerate(items)
        if layer != "user:u1"  # t.number has no user layer
    ]
    kept = [item for item in items if item[0] != "user:u1"]
    bounds = None if maximum is None else {"maximum": maximum}
    got = view(entries, lock=Lock(locked, bounds), project=project, at=at)
    assert (got.value, got.origin) == oracle(kept, locked, maximum, project, at)


def test_to_us_is_exact_for_microseconds() -> None:
    assert to_us(datetime(1970, 1, 1, 0, 0, 1, 5, tzinfo=UTC)) == 1_000_005
