"""The raw bundle (bronze) and the synthetic schedules (P1-I4-T03)."""

from __future__ import annotations

import gzip
import io
from datetime import date

import pytest
from tl_xer import bundle, limits
from tl_xer.reader import read_xer
from tl_xer.synth import (
    Progress,
    Scenario,
    Spec,
    from_index,
    make_xer,
    schedule,
    slipped,
    to_index,
    week_pair,
)
from xersupport import encode, first_text, second_text

# --- the bundle --------------------------------------------------------------------------------


def test_a_bundle_round_trips_every_table_verbatim() -> None:
    raw = read_xer(encode(first_text()))
    blob, digest = bundle.write_bundle(raw)
    bundle.verify_bundle(blob, digest)
    head, tables = bundle.read_bundle(blob)
    assert head["header"] == list(raw.header) and head["encoding"] == "cp1252"
    seen = []
    for table in tables:
        original = raw.table(table.name)
        assert original is not None
        assert table.columns == original.columns
        assert tuple(table.rows) == original.rows
        seen.append(table.name)
    assert seen == [t.name for t in raw.tables]


def test_a_bundle_is_the_same_bytes_every_time() -> None:
    raw = read_xer(encode(first_text()))
    one, two = bundle.write_bundle(raw), bundle.write_bundle(raw)
    assert one == two
    assert bundle.write_bundle(read_xer(encode(second_text())))[1] != one[1]
    assert one[0][4:8] == b"\x00\x00\x00\x00"  # the gzip header holds no time stamp
    assert one[0][3] & 0x08 == 0  # ... and no file name


def test_a_damaged_or_foreign_bundle_is_refused() -> None:
    blob, digest = bundle.write_bundle(read_xer(encode(first_text())))
    with pytest.raises(bundle.BundleError):
        bundle.verify_bundle(blob, "0" * 64)
    with pytest.raises(bundle.BundleError):
        bundle.verify_bundle(blob[: len(blob) // 2], digest)
    with pytest.raises(bundle.BundleError):
        bundle.verify_bundle(b"plain bytes", digest)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(b'{"kind": "something-else", "version": 1}\n')
    with pytest.raises(bundle.BundleError):
        bundle.read_bundle(out.getvalue())


def test_a_bundle_that_inflates_past_its_bound_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    blob, digest = bundle.write_bundle(read_xer(encode(first_text())))
    monkeypatch.setattr(limits, "MAX_BUNDLE_BYTES", 500)
    with pytest.raises(bundle.BundleError):
        bundle.verify_bundle(blob, digest)


# --- the synthetic schedules -------------------------------------------------------------------


def test_working_day_indexes_skip_weekends() -> None:
    friday, monday = date(2026, 10, 9), date(2026, 10, 12)
    assert to_index(monday) == to_index(friday) + 1
    assert to_index(date(2026, 10, 10)) == to_index(monday)  # a Saturday means the next Monday
    assert from_index(to_index(friday)) == friday
    assert from_index(to_index(date(2026, 1, 5))) == date(2026, 1, 5)


def test_the_pair_is_the_same_bytes_every_call() -> None:
    assert make_xer(week_pair()[0]) == make_xer(week_pair()[0])
    assert make_xer(week_pair()[0]) != make_xer(week_pair()[1])


def test_a1230_exists_in_both_files_and_its_float_erodes_from_nine_days_to_four() -> None:
    first, second = (schedule(s) for s in week_pair())
    one, two = first["A1230"], second["A1230"]
    assert (one.total_float_days, two.total_float_days) == (9, 4)
    assert str(one.ef) == "2026-10-12" and str(two.ef) == "2026-10-19"


def test_the_second_file_has_a_removed_and_an_added_activity_and_a_new_critical_path() -> None:
    first, second = week_pair()
    codes_one = {s.code for s in first.specs}
    codes_two = {s.code for s in second.specs}
    assert codes_one - codes_two == {"A1990"} and codes_two - codes_one == {"A2500"}
    one, two = schedule(first), schedule(second)
    assert one["A1120"].total_float_days == 4 and two["A1120"].total_float_days == -1


def test_the_file_is_windows_1252_with_crlf_and_an_en_dash() -> None:
    data = make_xer(week_pair()[0])
    assert b"\r\n" in data and b"\x96" in data  # 0x96 is the en dash in Windows-1252
    assert not data.isascii()
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")


def test_a_network_with_a_loop_or_a_missing_predecessor_is_refused() -> None:
    loop = Scenario(
        "X", date(2026, 10, 5), (Spec("A", "a", "CON", 1, ("B",)), Spec("B", "b", "CON", 1, ("A",)))
    )
    with pytest.raises(ValueError):
        schedule(loop)
    missing = Scenario("X", date(2026, 10, 5), (Spec("A", "a", "CON", 1, ("Z",)),))
    with pytest.raises(ValueError):
        schedule(missing)


def test_a_small_network_has_the_floats_a_forward_and_backward_pass_gives() -> None:
    specs = (
        Spec("A", "first", "CON", 2),
        Spec("B", "long way", "CON", 5, ("A",)),
        Spec("C", "short way", "CON", 1, ("A",)),
        Spec("D", "last", "CON", 1, ("B", "C")),
    )
    scenario = Scenario("X", date(2026, 10, 5), specs, deadline=date(2026, 10, 15))
    dates = schedule(scenario)
    assert dates["D"].total_float_days == 1
    assert dates["B"].total_float_days == 1 and dates["C"].total_float_days == 5
    assert dates["C"].free_float_days == 4


def test_a_completed_activity_has_actual_dates_and_no_float() -> None:
    specs = (Spec("A", "done", "CON", 2), Spec("B", "next", "CON", 2, ("A",)))
    scenario = Scenario(
        "X",
        date(2026, 10, 7),
        specs,
        {"A": Progress(date(2026, 10, 5), 100, date(2026, 10, 6))},
        date(2026, 10, 30),
    )
    dates = schedule(scenario)
    assert dates["A"].total_float_days is None and str(dates["A"].ef) == "2026-10-06"
    assert str(dates["B"].es) == "2026-10-07"


def test_slipped_moves_the_data_date_a_week_and_lengthens_the_named_activities() -> None:
    first = week_pair()[0]
    later = slipped(first, days=3, codes=("A1230",))
    assert later.data_date == date(2026, 10, 12)
    assert {s.code: s.days for s in later.specs}["A1230"] == 13
    assert {s.code: s.days for s in first.specs}["A1230"] == 10
    read_xer(make_xer(later))
