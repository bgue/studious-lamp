"""Project calendars: loading, working days, counting, refusing what they do not cover (T04)."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest
from corrworld import FIXTURES
from tl_mod_correspondence import calendars as cal


@pytest.fixture(scope="module")
def p123() -> cal.Calendar:
    return cal.load_calendar("P123-default@1", FIXTURES)


def d(text: str) -> date:
    return date.fromisoformat(text)


def test_the_fixture_calendar_loads_with_its_reference_and_range(p123: cal.Calendar) -> None:
    assert p123.ref == "P123-default@1" and p123.scope == "project:P123"
    assert p123.covers_from == d("2026-01-01") and p123.covers_to == d("2028-12-31")
    assert p123.rest_weekdays == frozenset({5, 6})
    assert d("2026-12-25") in p123.holidays and len(p123.holidays) == 18


def test_a_weekday_is_working_a_weekend_and_a_holiday_are_not(p123: cal.Calendar) -> None:
    assert p123.is_working(d("2026-10-19"))  # Monday
    assert not p123.is_working(d("2026-10-17"))  # Saturday
    assert not p123.is_working(d("2026-10-18"))  # Sunday
    assert not p123.is_working(d("2026-12-25"))  # Christmas, a Friday
    assert not p123.is_working(d("2026-12-28"))  # observed Boxing Day, a Monday


@pytest.mark.parametrize(
    ("start", "count", "expected"),
    [
        ("2026-10-16", 1, "2026-10-19"),  # Friday + 1 is Monday
        ("2026-10-17", 1, "2026-10-19"),  # a Saturday start: day zero is not counted
        ("2026-10-19", 5, "2026-10-26"),
        ("2026-10-19", 0, "2026-10-19"),
        ("2026-12-23", 2, "2026-12-29"),  # skips the 25th, the weekend and the 28th
        ("2026-04-02", 1, "2026-04-07"),  # Good Friday and Easter Monday in between
        ("2026-10-19", 20, "2026-11-16"),
    ],
)
def test_working_days_are_counted_after_the_start_day(
    p123: cal.Calendar, start: str, count: int, expected: str
) -> None:
    assert p123.add_days(d(start), count, "working") == d(expected)


def test_calendar_days_need_no_calendar_and_cross_everything(p123: cal.Calendar) -> None:
    assert p123.add_days(d("2026-10-17"), 14, "calendar") == d("2026-10-31")
    far = d("2040-01-01")  # outside the coverage: a calendar-day count does not read it
    assert p123.add_days(far, 3, "calendar") == d("2040-01-04")
    assert p123.count_days(d("2040-01-01"), d("2040-01-05"), "calendar") == 4


@pytest.mark.parametrize(
    ("after", "upto", "expected"),
    [
        ("2026-10-16", "2026-10-19", 1),
        ("2026-10-19", "2026-10-26", 5),
        ("2026-10-19", "2026-10-19", 0),
        ("2026-10-20", "2026-10-19", 0),  # not later: zero, never negative
        ("2026-12-23", "2026-12-29", 2),
    ],
)
def test_counting_working_days_between_two_dates(
    p123: cal.Calendar, after: str, upto: str, expected: int
) -> None:
    assert p123.count_days(d(after), d(upto), "working") == expected


def test_counting_and_adding_agree(p123: cal.Calendar) -> None:
    start = d("2026-11-02")
    for n in range(0, 60):
        end = p123.add_days(start, n, "working")
        assert p123.count_days(start, end, "working") == n


def test_a_working_count_that_leaves_the_covered_range_is_refused(p123: cal.Calendar) -> None:
    with pytest.raises(cal.CalendarRangeError, match="outside the range"):
        p123.add_days(d("2028-12-28"), 5, "working")
    with pytest.raises(cal.CalendarRangeError):
        p123.add_days(d("2025-12-31"), 1, "working")
    with pytest.raises(cal.CalendarRangeError):
        p123.count_days(d("2028-12-01"), d("2029-01-05"), "working")
    with pytest.raises(cal.CalendarRangeError):
        p123.is_working(d("2029-01-01"))


def test_the_last_covered_day_is_usable(p123: cal.Calendar) -> None:
    assert p123.add_days(d("2028-12-27"), 1, "working") == d("2028-12-28")
    assert p123.is_working(d("2028-12-29"))


def test_bad_arguments_are_value_errors(p123: cal.Calendar) -> None:
    with pytest.raises(ValueError, match="day_type"):
        p123.add_days(d("2026-10-19"), 1, "weekly")
    with pytest.raises(ValueError, match="count"):
        p123.add_days(d("2026-10-19"), -1, "working")
    with pytest.raises(ValueError, match="count"):
        p123.add_days(d("2026-10-19"), cal.MAX_SPAN_DAYS + 1, "calendar")
    with pytest.raises(ValueError, match="span"):
        p123.count_days(d("2026-01-01"), d("2040-01-01"), "calendar")
    with pytest.raises(ValueError, match="day_type"):
        p123.count_days(d("2026-01-01"), d("2026-01-05"), "x")


def test_the_longest_legal_working_walk_stays_inside_the_bound(p123: cal.Calendar) -> None:
    started = time.perf_counter()
    end = p123.add_days(d("2026-01-01"), 600, "working")
    assert end > d("2028-04-01") and time.perf_counter() - started < 1.0


GOOD = """
id: T-1
version: 1
scope: company
name: Test
rest_days: [sun]
covers_from: "2026-01-01"
covers_to: "2026-12-31"
holidays:
  - { date: "2026-05-01", name: Labour Day }
"""


def test_a_minimal_calendar_parses() -> None:
    parsed = cal.parse_calendar(GOOD)
    assert parsed.ref == "T-1@1" and parsed.rest_weekdays == frozenset({6})
    assert parsed.is_working(d("2026-10-17")) and not parsed.is_working(d("2026-05-01"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("rest_days: [sun]", "rest_days: [sun, sun]"),
        ("rest_days: [sun]", "rest_days: [funday]"),
        ("rest_days: [sun]", "rest_days: [mon, tue, wed, thu, fri, sat, sun]"),
        ("version: 1", "version: 0"),
        ("scope: company", "scope: everywhere"),
        ("id: T-1", "id: ../T"),
        ('covers_to: "2026-12-31"', 'covers_to: "2025-12-31"'),
        ('covers_to: "2026-12-31"', 'covers_to: "2090-12-31"'),
        ('{ date: "2026-05-01", name: Labour Day }', '{ date: "2027-05-01", name: Labour Day }'),
        ('{ date: "2026-05-01", name: Labour Day }', '{ date: "2026-05-01" }'),
        ('{ date: "2026-05-01", name: Labour Day }', "{ date: not-a-date, name: x }"),
        ("name: Test", "name: Test\nsurprise: 1"),
    ],
)
def test_a_bad_calendar_is_refused_with_its_source_named(change: str, message: str) -> None:
    with pytest.raises(cal.CalendarError, match="bad.yaml"):
        cal.parse_calendar(GOOD.replace(change, message), source="bad.yaml")


def test_a_holiday_listed_twice_is_refused() -> None:
    text = GOOD + '  - { date: "2026-05-01", name: Again }\n'
    with pytest.raises(cal.CalendarError, match="twice"):
        cal.parse_calendar(text)


def test_text_that_is_not_a_mapping_or_not_yaml_is_refused() -> None:
    for text in ("- a\n- b\n", "just text", "a: [unclosed", "&a [*a]"):
        with pytest.raises(cal.CalendarError):
            cal.parse_calendar(text, source="x")


def test_an_alias_bomb_is_refused_quickly() -> None:
    bomb = "a: &a [x,x,x,x,x,x,x,x,x]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
    bomb += "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]\nholidays: *c\n" + GOOD.split("holidays:")[0]
    started = time.perf_counter()
    with pytest.raises(cal.CalendarError):
        cal.parse_calendar(bomb)
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize(
    "ref", ["../x@1", "a/b@1", "x", "x@0", "x@-1", "x@1.5", "@1", "x@", "x@01"]
)
def test_a_reference_that_is_not_code_at_version_is_refused(ref: str) -> None:
    with pytest.raises(cal.CalendarError):
        cal.split_ref(ref)


def test_loading_reads_only_the_calendars_folder(tmp_path: Path) -> None:
    (tmp_path / "calendars").mkdir()
    (tmp_path / "calendars" / "T-1@1.yaml").write_text(GOOD)
    (tmp_path / "secret@1.yaml").write_text(GOOD.replace("T-1", "secret"))
    assert cal.load_calendar("T-1@1", tmp_path).ref == "T-1@1"
    with pytest.raises(cal.CalendarError, match="no calendar"):
        cal.load_calendar("T-1@2", tmp_path)
    with pytest.raises(cal.CalendarError):
        cal.load_calendar("../secret@1", tmp_path)
    assert cal.list_calendars(tmp_path) == ["T-1@1"]
    assert cal.list_calendars(tmp_path / "nowhere") == []


def test_a_file_that_declares_another_reference_is_refused(tmp_path: Path) -> None:
    (tmp_path / "calendars").mkdir()
    (tmp_path / "calendars" / "T-1@2.yaml").write_text(GOOD)  # the file says version 1
    with pytest.raises(cal.CalendarError, match="declares"):
        cal.load_calendar("T-1@2", tmp_path)


def test_an_oversized_or_non_utf8_file_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "calendars"
    folder.mkdir()
    (folder / "T-1@1.yaml").write_text(GOOD + "# " + "x" * cal.MAX_FILE_BYTES)
    with pytest.raises(cal.CalendarError, match="larger"):
        cal.load_calendar("T-1@1", tmp_path)
    (folder / "T-1@1.yaml").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(cal.CalendarError, match="UTF-8"):
        cal.load_calendar("T-1@1", tmp_path)


def test_the_fixture_directory_lists_its_calendar() -> None:
    assert "P123-default@1" in cal.list_calendars(FIXTURES)
