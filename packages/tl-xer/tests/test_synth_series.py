"""The weekly series of synthetic updates (P1-I4): deterministic, valid, moving forward."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from tl_xer.process import process
from tl_xer.synth import Progress, Scenario, Spec, make_xer, next_week, series, week_pair
from tl_xer.typed import Options


def days_of(scenario: Scenario) -> dict[str, int]:
    return {s.code: s.days for s in scenario.specs}


def test_the_same_seed_gives_the_same_files_byte_for_byte_and_another_seed_other_slips() -> None:
    one = [make_xer(s) for s in series(3, 6)]
    assert one == [make_xer(s) for s in series(3, 6)]
    other = [make_xer(s) for s in series(4, 6)]
    assert one[0] == other[0]  # the first update is the demo's first file for every seed
    assert one[1:] != other[1:]


def test_each_update_is_a_week_after_the_one_before() -> None:
    scenarios = series(1, 6)
    assert len(scenarios) == 6 and scenarios[0] == week_pair()[0]
    assert [s.data_date for s in scenarios] == [
        date(2026, 10, 5) + timedelta(days=7 * n) for n in range(6)
    ]
    assert all(s.data_date.weekday() == 0 for s in scenarios)  # a Monday


def test_every_update_is_a_valid_p6_export_with_no_problem_at_all() -> None:
    for scenario in series(5, 8):
        outcome = process(make_xer(scenario), Options())
        assert outcome.status == "valid", scenario.data_date
        assert outcome.report["error_count"] == 0 and outcome.report["warning_count"] == 0


def test_work_only_moves_forward() -> None:
    scenarios = series(2, 10)
    for before, after in zip(scenarios, scenarios[1:], strict=False):
        for code, was in before.progress.items():
            now = after.progress[code]
            assert now.start == was.start and now.percent >= was.percent, code
            if was.finish is not None:
                assert now.finish == was.finish, code  # a finished activity stays as it was
        for code, now in after.progress.items():
            if now.finish is not None:
                assert now.finish.weekday() < 5 and now.finish >= now.start, code
                assert now.finish < after.data_date, code


def test_something_gets_done_or_started_over_the_series() -> None:
    scenarios = series(2, 10)
    first, last = scenarios[0], scenarios[-1]
    finished = lambda s: sum(1 for p in s.progress.values() if p.finish)  # noqa: E731
    assert finished(last) > finished(first)
    assert len(last.progress) > len(first.progress)


def test_one_to_three_activities_slip_each_week() -> None:
    scenarios = series(7, 12)
    for before, after in zip(scenarios, scenarios[1:], strict=False):
        slipped = {c for c, d in days_of(before).items() if days_of(after)[c] > d}
        assert 1 <= len(slipped) <= 3, after.data_date
        for code in slipped:
            assert 1 <= days_of(after)[code] - days_of(before)[code] <= 4
            assert code not in {c for c, p in before.progress.items() if p.finish}  # not finished


def test_an_activity_that_slips_makes_no_progress_that_week() -> None:
    before = series(7, 3)[1]
    after = next_week(before, 7, 2)
    for code, days in days_of(after).items():
        if days > days_of(before)[code] and code in before.progress:
            assert after.progress[code].percent == before.progress[code].percent


def test_every_third_week_an_inspection_is_added_after_an_unfinished_activity() -> None:
    scenarios = series(9, 8)
    added = [
        (n, {s.code for s in b.specs} - {s.code for s in a.specs})
        for n, (a, b) in enumerate(zip(scenarios, scenarios[1:], strict=False), start=1)
    ]
    assert [(n, sorted(c)) for n, c in added] == [
        (1, []),
        (2, []),
        (3, ["A2503"]),
        (4, []),
        (5, []),
        (6, ["A2506"]),
        (7, []),
    ]
    extra = next(s for s in scenarios[3].specs if s.code == "A2503")
    assert 2 <= extra.days <= 5 and len(extra.preds) == 1 and extra.wbs == "CON"
    (pred,) = extra.preds
    assert pred in {s.code for s in scenarios[2].specs}
    assert not scenarios[2].progress.get(pred, None) or scenarios[2].progress[pred].finish is None


def test_a_series_starts_where_it_is_told_to() -> None:
    second = week_pair()[1]
    scenarios = series(1, 3, start=second)
    assert scenarios[0] == second and scenarios[1].data_date == second.data_date + timedelta(days=7)


def test_a_series_has_between_one_and_fifty_two_updates() -> None:
    assert series(1, 1) == (week_pair()[0],)
    assert len(series(1, 52)) == 52
    for bad in (0, 53, -1):
        with pytest.raises(ValueError, match="1 to 52"):
            series(1, bad)


def slip_sets(seed: int, weeks: int) -> list[set[str]]:
    scenarios = series(seed, weeks)
    return [
        {c for c, d in days_of(a).items() if days_of(b)[c] > d}
        for a, b in zip(scenarios, scenarios[1:], strict=False)
    ]


def test_the_number_and_the_length_of_the_slips_and_the_inspections_vary_over_the_seeds() -> None:
    counts: set[int] = set()
    lengths: set[int] = set()
    afters: set[str] = set()
    for seed in range(1, 7):
        scenarios = series(seed, 25)
        counts |= {len(s) for s in slip_sets(seed, 25)}
        for a, b in zip(scenarios, scenarios[1:], strict=False):
            lengths |= {days_of(b)[c] - d for c, d in days_of(a).items() if days_of(b)[c] > d}
            for spec in b.specs:
                if spec.code.startswith("A25") and spec.code not in days_of(a):
                    afters.add(spec.preds[0])
    assert counts == {1, 2, 3} and lengths == {1, 2, 3, 4}
    assert len(afters) > 2


def test_other_seeds_slip_other_activities() -> None:
    assert slip_sets(1, 6) != slip_sets(2, 6)
    assert slip_sets(1, 6) == slip_sets(1, 6)


def test_extra_inspections_last_two_to_five_days_when_they_are_added() -> None:
    lengths: set[int] = set()
    for seed in range(1, 9):
        scenarios = series(seed, 25)
        for a, b in zip(scenarios, scenarios[1:], strict=False):
            lengths |= {s.days for s in b.specs if s.code not in days_of(a)}
    assert lengths == {2, 3, 4, 5}


def test_a_working_week_advances_an_activity_by_its_share_of_the_duration() -> None:
    start = Scenario(
        "X",
        date(2026, 10, 5),
        (
            Spec("A", "Ten days", "CON", 10),
            Spec("B", "Five days", "CON", 5),
            Spec("M", "Milestone", "CON", 0, ("B",)),
        ),
        {"A": Progress(date(2026, 9, 28), 20.0), "B": Progress(date(2026, 9, 28), 0.0)},
        deadline=date(2026, 12, 3),
    )
    advanced = finished = 0
    for seed in range(1, 25):
        after = next_week(start, seed, 98)  # (week 98 adds no inspection)
        slipped = {c for c, d in days_of(after).items() if d > days_of(start)[c]}
        if "A" not in slipped:
            assert after.progress["A"].percent == 70.0  # 20 + 100 * 5 / 10
            advanced += 1
        else:
            assert after.progress["A"].percent == 20.0  # a slipped activity stands still
        if "B" not in slipped:
            # five days of five: exactly 100 percent finishes it on the Friday before the data date
            assert after.progress["B"].finish == date(2026, 10, 9)
            assert after.progress["B"].percent == 100
            assert after.progress["M"] == Progress(date(2026, 10, 9), 100, date(2026, 10, 9))
            finished += 1
        else:
            assert after.progress["B"].percent == 0.0
    assert advanced > 0 and finished > 0


def test_the_activities_that_slip_and_the_one_an_inspection_follows_are_chosen_by_the_seed() -> (
    None
):
    slipped: set[str] = set()
    afters: set[str] = set()
    for seed in range(1, 11):
        scenarios = series(seed, 4)
        slipped |= slip_sets(seed, 2)[0]  # week 1
        afters |= {s.preds[0] for s in scenarios[3].specs if s.code == "A2503"}
    assert len(slipped) > 3  # alphabetical order would slip only the first three activities
    assert len(afters) > 2
