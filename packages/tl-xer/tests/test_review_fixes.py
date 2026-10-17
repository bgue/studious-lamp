"""Fixes of the security review of the XER reader (P1-I4): each fails when its bound is removed."""

from __future__ import annotations

import gzip
import io
import json
import time
from typing import Any

import pytest
from tl_xer import bundle, limits, wire
from tl_xer.child import TAG_OK, entry
from tl_xer.process import CP1252_NOTE, process
from tl_xer.reader import read_xer
from tl_xer.result import XerLimitError
from tl_xer.typed import Options, parse_date, parse_number
from xersupport import add_row, codes, drop_table, encode, first_text, replace_once, set_cell


def run(text: str):  # noqa: ANN201
    return process(encode(text), Options())


def problem_codes(text: str) -> list[object]:
    return codes(run(text).report["problems"])


# --- 3. the text of the typed rows is bounded by the size of the file -----------------------------


def amplified(names: int = 21) -> str:
    """Every activity links the one activity code, whose name is 500 characters long."""
    text = set_cell(first_text(), "ACTVCODE", 1, "actv_code_name", "N" * 500)
    for row in range(1, names + 1):
        text = set_cell(text, "TASKACTV", row, "actv_code_id", "11")
    return text


def test_a_code_copied_into_every_link_cannot_make_more_text_than_the_file_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = amplified()
    assert run(text).status == "valid"  # under the real bound it is a small file
    monkeypatch.setattr(limits, "TYPED_TEXT_FACTOR", 1)
    monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", 0)
    outcome = run(text)
    assert outcome.status == "invalid" and outcome.snapshot is None and outcome.raw_gz is None
    found = [p for p in outcome.report["problems"] if p["code"] == "typed_too_large"]
    assert found[0]["table"] == "TASKACTV" and found[0]["severity"] == "error"
    assert "repeated for every activity" in found[0]["message"]
    assert run(first_text()).status == "valid"  # a file that does not amplify fits the same bound


def test_every_typed_table_is_charged_against_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "TYPED_TEXT_FACTOR", 0)
    monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", 1)
    assert [p["table"] for p in run(first_text()).report["problems"]] == ["PROJWBS"]
    monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", 300)  # the WBS fits; the activities do not
    assert [p["table"] for p in run(first_text()).report["problems"]] == ["TASK"]


def smallest_extra(text: str, monkeypatch: pytest.MonkeyPatch) -> int:
    """The least ``TYPED_TEXT_EXTRA`` (with a factor of 0) under which ``text`` is valid."""
    monkeypatch.setattr(limits, "TYPED_TEXT_FACTOR", 0)
    low, high = 0, 1 << 20
    while low < high:
        middle = (low + high) // 2
        monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", middle)
        if run(text).status == "valid":
            high = middle
        else:
            low = middle + 1
    return low


def test_the_bound_counts_bytes_not_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = replace_once(first_text(), "Install pipe rack supports", "N" * 90)
    wide = replace_once(first_text(), "Install pipe rack supports", "\u20ac" * 90)  # 3 bytes each
    # the activity name is charged once: 90 bytes, or 270
    assert smallest_extra(wide, monkeypatch) - smallest_extra(plain, monkeypatch) == 180


def without(text: str, *tables: str) -> str:
    for table in tables:
        text = drop_table(text, table)
    return text


@pytest.mark.parametrize(
    ("dropped", "last_table"),
    [
        (("ACTVTYPE", "ACTVCODE", "TASKACTV", "UDFTYPE", "UDFVALUE"), "TASKPRED"),
        (("UDFTYPE", "UDFVALUE"), "TASKACTV"),
        ((), "UDFVALUE"),
    ],
)
def test_the_relationships_the_codes_and_the_user_fields_are_each_charged(
    dropped: tuple[str, ...], last_table: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One byte under the least that fits, the table charged last is the one that fails."""
    text = without(first_text(), *dropped)
    least = smallest_extra(text, monkeypatch)
    monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", least - 1)
    outcome = run(text)
    found = [p for p in outcome.report["problems"] if p["code"] == "typed_too_large"]
    assert outcome.status == "invalid" and [p["table"] for p in found][0] == last_table
    monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", least)
    assert run(text).status == "valid"


def test_no_file_may_have_more_typed_text_than_the_absolute_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "TYPED_TEXT_FACTOR", 1000)
    monkeypatch.setattr(limits, "TYPED_TEXT_EXTRA", 1 << 30)
    assert run(first_text()).status == "valid"
    monkeypatch.setattr(limits, "MAX_TYPED_TEXT", 50)
    assert [p["table"] for p in run(first_text()).report["problems"]][:1] == ["PROJWBS"]


def test_the_typed_json_is_bounded_as_a_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_TYPED_JSON", 100)
    outcome = run(first_text())
    assert outcome.status == "invalid" and outcome.snapshot is None and outcome.raw_gz is None
    assert codes(outcome.report["problems"]) == ["typed_too_large"]


def test_a_small_file_is_allowed_a_small_answer_and_none_more_than_the_ceiling() -> None:
    small, large = limits.answer_bound(10_000), limits.answer_bound(limits.MAX_BYTES)
    assert small < large <= limits.MAX_ANSWER_BYTES
    assert small == 3 * 10_000 + (16 + 48 + 8) * (1 << 20)
    assert limits.answer_bound(10**12) == limits.MAX_ANSWER_BYTES
    # the demo files are well inside it
    from tl_xer.child import entry

    _, payload = entry({"options": {"project": None}}, encode(first_text()))
    assert len(payload) < small


def test_the_read_passes_the_size_bound_to_the_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from tl_core.derivation.envelope import run_in_envelope as real
    from tl_xer import run

    seen: list[int] = []

    def watching(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["max_answer"])
        return real(*args, **kwargs)

    monkeypatch.setattr(run, "run_in_envelope", watching)
    data = encode(first_text())
    assert run.read_xer_file(data).status == "valid"
    assert seen == [limits.answer_bound(len(data))]


def test_the_answer_bound_follows_the_text_bound() -> None:
    assert limits.MAX_TYPED_TEXT == limits.TYPED_TEXT_FACTOR * limits.MAX_BYTES + (16 << 20)
    assert limits.MAX_ANSWER_BYTES == limits.MAX_TYPED_JSON + limits.MAX_BYTES + (8 << 20)
    assert limits.MAX_TYPED_JSON > limits.MAX_TYPED_TEXT


# --- 4. the raw bundle is read in chunks, and a line is bounded ----------------------------------


def gz_of(data: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(data)
    return out.getvalue()


def test_the_stream_is_read_in_chunks_never_all_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    sizes: list[int | None] = []

    class Watching(gzip.GzipFile):
        def read(self, size: int | None = -1) -> bytes:  # type: ignore[override]
            sizes.append(size)
            return super().read(size)

    monkeypatch.setattr(gzip, "GzipFile", Watching)
    blob, digest = bundle.write_bundle(read_xer(encode(first_text())))
    sizes.clear()
    bundle.verify_bundle(blob, digest)
    assert sizes and all(size is not None and 0 < size <= 64 * 1024 for size in sizes)


def test_a_bundle_of_one_enormous_line_is_refused_before_it_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "MAX_BUNDLE_LINE_BYTES", 200_000)
    blob = gz_of(b"\x00" * 20_000_000)  # a few kilobytes compressed, one line of zeros
    started = time.monotonic()
    with pytest.raises(bundle.BundleError, match="longer than its bound"):
        bundle.verify_bundle(blob, "0" * 64)
    assert time.monotonic() - started < 2


def test_a_line_just_under_the_bound_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_BUNDLE_LINE_BYTES", 100_000)
    line = b"x" * 99_000 + b"\n"
    blob = gz_of(line)
    bundle.verify_bundle(blob, __import__("hashlib").sha256(line).hexdigest())


def test_the_total_is_counted_chunk_by_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_BUNDLE_BYTES", 300_000)
    blob = gz_of((b"y" * 999 + b"\n") * 1000)  # 1 MB in short lines
    with pytest.raises(bundle.BundleError, match="inflates past its bound"):
        bundle.verify_bundle(blob, "0" * 64)


def test_a_bundle_without_a_last_newline_still_has_its_digest_counted() -> None:
    data = b'{"kind":"xer-raw","version":2,"header":[],"encoding":"ascii"}\n{"a'
    bundle.verify_bundle(gz_of(data), __import__("hashlib").sha256(data).hexdigest())


def test_a_deeply_nested_line_is_a_bundle_error_not_a_recursion_error() -> None:
    nested = b"[" * 200_000 + b"]" * 200_000 + b"\n"
    with pytest.raises(bundle.BundleError):
        bundle.read_bundle(gz_of(nested))
    head = b'{"kind":"xer-raw","version":2,"header":[],"encoding":"ascii"}\n'
    table = b'{"table":"T","columns":["a"],"rows":1}\n'
    _, tables = bundle.read_bundle(gz_of(head + table + nested))
    with pytest.raises(bundle.BundleError):
        for item in tables:
            list(item.rows)


def test_rows_are_written_in_batches_and_read_back_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "BUNDLE_BATCH_ROWS", 2)
    raw = read_xer(encode(first_text()))
    blob, digest = bundle.write_bundle(raw)
    bundle.verify_bundle(blob, digest)
    lines = gzip.decompress(blob).split(b"\n")
    sizes = [len(json.loads(line)) for line in lines[1:] if line.startswith(b"[")]
    assert max(sizes) == 2 and sum(sizes) == sum(len(t.rows) for t in raw.tables)
    _, tables = bundle.read_bundle(blob)
    assert [(t.name, list(t.rows)) for t in tables] == [(t.name, list(t.rows)) for t in raw.tables]


def test_a_batch_is_also_cut_by_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "BUNDLE_BATCH_CHARS", 10)
    blob, _ = bundle.write_bundle(read_xer(encode(first_text())))
    lines = [
        json.loads(line) for line in gzip.decompress(blob).split(b"\n") if line.startswith(b"[")
    ]
    assert all(len(batch) == 1 or sum(map(len, batch[0])) < 10 for batch in lines)
    assert any(len(batch) == 1 for batch in lines)


def test_a_table_with_more_rows_than_it_says_is_a_bundle_error() -> None:
    head = b'{"kind":"xer-raw","version":2,"header":[],"encoding":"ascii"}\n'
    text = head + b'{"table":"T","columns":["a"],"rows":1}\n[["1"],["2"]]\n'
    _, tables = bundle.read_bundle(gz_of(text))
    with pytest.raises(bundle.BundleError, match="more rows"):
        for table in tables:
            list(table.rows)


def test_the_parent_turns_recursion_and_memory_errors_into_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag, payload = entry({"options": {"project": None}}, encode(first_text()))
    assert tag == TAG_OK and wire.decode(payload).status == "valid"
    for error in (RecursionError, MemoryError):

        def boom(*_: Any, error: type[Exception] = error, **__: Any) -> Any:
            raise error

        with monkeypatch.context() as m:
            m.setattr(json, "loads", boom)
            with pytest.raises(XerLimitError) as caught:
                wire.decode(payload)
        assert caught.value.reason == "crash"


def test_a_typed_frame_nested_past_the_recursion_limit_is_a_crash() -> None:
    from test_run import build, valid_payload

    _, meta, _, raw = valid_payload()
    deep = {"project": 1, "tables": json.loads("[" * 900 + "]" * 900)}
    # json.dumps itself would recurse: build the bytes by hand
    typed_bytes = b'{"project":{},"tables":' + b"[" * 100_000 + b"]" * 100_000 + b"}"
    import hashlib

    from tl_xer.child import frame
    from tl_xer.process import canonical

    meta = {**meta, "typed_sha256": hashlib.sha256(typed_bytes).hexdigest()}
    with pytest.raises(XerLimitError) as caught:
        wire.decode(frame(canonical(meta)) + frame(typed_bytes) + raw)
    assert caught.value.reason == "crash"
    assert deep and build


# --- 5. dates ----------------------------------------------------------------------------------


def test_dates_are_written_with_explicit_widths_and_checked_for_the_year() -> None:
    assert parse_date("2026-10-05 08:00") == "2026-10-05T08:00"
    assert parse_date("1990-01-01") == "1990-01-01T00:00"
    assert parse_date("2100-12-31 23:59") == "2100-12-31T23:59"
    for bad in ("0999-01-05", "1989-12-31", "2101-01-01", "0001-01-01", "9999-12-31"):
        with pytest.raises(ValueError, match="year|date"):
            parse_date(bad)


def test_every_stamp_sorts_as_text_the_way_it_sorts_as_a_date() -> None:
    stamps = [parse_date(f"{y}-{m:02d}-15 08:00") for y in (1990, 2026, 2100) for m in (1, 12)]
    assert all(s is not None and len(s) == 16 for s in stamps)
    assert stamps == sorted(s for s in stamps if s is not None)


def test_a_date_with_digits_of_another_script_is_not_a_date() -> None:
    for bad in ("２０２６-10-05", "2026-١٠-05", "2026-10-05 ٠٨:00"):
        with pytest.raises(ValueError):
            parse_date(bad)
    with pytest.raises(ValueError):
        parse_number("١٢")
    with pytest.raises(ValueError):
        parse_number("1.٥")


def test_a_data_date_outside_the_years_makes_the_file_invalid() -> None:
    text = set_cell(first_text(), "PROJECT", 1, "last_recalc_date", "2999-10-05 08:00")
    assert problem_codes(text) == ["bad_date"]
    text = set_cell(first_text(), "TASK", 1, "early_start_date", "0999-10-05 08:00")
    assert "bad_date" in problem_codes(text)


def test_a_version_written_with_other_digits_is_not_a_version() -> None:
    head = "ERMHDR\t20.12"
    wide = first_text().replace(head, "ERMHDR\t\uff12\uff10.12", 1)
    assert head not in wide
    assert codes(process(encode(wide, "utf-8"), Options()).report["problems"]) == ["bad_version"]


# --- 10. ids, the project id and the encoding note --------------------------------------------


@pytest.mark.parametrize(
    ("table", "row", "column", "code"),
    [
        ("TASK", 1, "task_id", "bad_task_id"),
        ("PROJWBS", 2, "wbs_id", "text_too_long"),
        ("PROJWBS", 2, "parent_wbs_id", "text_too_long"),
        ("PROJECT", 1, "proj_id", "text_too_long"),
    ],
)
def test_an_id_over_the_limit_is_an_invalid_snapshot_with_a_report(
    table: str, row: int, column: str, code: str
) -> None:
    long_id = "9" * (limits.MAX_ID_CHARS + 1)
    outcome = run(set_cell(first_text(), table, row, column, long_id))
    assert outcome.status == "invalid" and outcome.snapshot is None
    assert code in codes(outcome.report["problems"])


def test_a_calendar_id_over_the_limit_is_an_invalid_snapshot_with_a_report() -> None:
    long_id = "9" * (limits.MAX_ID_CHARS + 1)
    text = set_cell(first_text(), "CALENDAR", 1, "clndr_id", long_id)
    for row in range(1, 22):
        text = set_cell(text, "TASK", row, "clndr_id", long_id)
    outcome = run(text)
    assert outcome.status == "invalid" and outcome.snapshot is None
    tables = [p["table"] for p in outcome.report["problems"] if p["code"] == "text_too_long"]
    assert "TASK" in tables  # the activities name it


def test_a_calendar_the_project_names_as_its_default_is_checked_too() -> None:
    long_id = "9" * (limits.MAX_ID_CHARS + 1)
    text = add_row(first_text(), "CALENDAR", [long_id, "Long", "8", "40", "172", "2000"])
    text = set_cell(text, "PROJECT", 1, "clndr_id", long_id)
    outcome = run(text)
    problems = [(p["code"], p["table"]) for p in outcome.report["problems"]]
    assert outcome.status == "invalid" and problems == [("text_too_long", "CALENDAR")]


def test_an_id_of_exactly_the_limit_is_accepted() -> None:
    ok = "9" * limits.MAX_ID_CHARS
    text = first_text()
    assert run(set_cell(text, "TASK", 1, "task_id", ok)).status in {"valid", "invalid"}
    only = run(set_cell(text, "PROJECT", 1, "proj_id", ok))
    assert "text_too_long" not in codes(only.report["problems"])


def test_a_project_id_with_spaces_is_the_same_project_everywhere() -> None:
    text = first_text()
    for row in range(1, 22):
        text = set_cell(text, "TASK", row, "proj_id", " 1 ")
    for row in range(1, 5):
        text = set_cell(text, "PROJWBS", row, "proj_id", "1  ")
    outcome = run(text)
    assert outcome.status == "valid", outcome.report["problems"]
    assert outcome.snapshot is not None and outcome.snapshot.counts()["activities"] == 21
    assert outcome.snapshot.counts()["wbs"] == 4


def test_a_file_read_as_windows_1252_says_so_and_a_utf8_one_does_not() -> None:
    cp = process(encode(first_text()), Options())
    assert cp.report["encoding"] == "cp1252" and cp.report["encoding_note"] == CP1252_NOTE
    utf = process(encode(first_text(), "utf-8"), Options())
    assert utf.report["encoding"] == "utf-8" and utf.report["encoding_note"] is None
    ascii_only = first_text().replace("–", "-")
    assert process(encode(ascii_only), Options()).report["encoding_note"] is None
    stray = encode(first_text(), "utf-8").replace(b"Install", b"Inst\xe9ll", 1)
    assert process(stray, Options()).report["encoding_note"] == CP1252_NOTE


def test_the_parent_refuses_an_encoding_note_it_does_not_know() -> None:
    from test_run import build, valid_payload

    _, meta, typed, raw = valid_payload()
    meta["report"]["encoding_note"] = "trust me"
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))
    meta["report"]["encoding_note"] = CP1252_NOTE
    assert wire.decode(build(meta, typed, raw)).status == "valid"


@pytest.mark.parametrize("char", ["\x00", "\x85", chr(0x202E), chr(0x2028), chr(0x2066), "\x7f"])
def test_the_parent_rechecks_text_cells_for_characters_the_reader_refused(char: str) -> None:
    from test_run import build, valid_payload

    _, meta, typed, raw = valid_payload()
    typed["tables"]["activities"]["rows"][0][2] = f"Install {char} supports"
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))
    typed["tables"]["activities"]["rows"][0][2] = "Install supports"
    assert wire.decode(build(meta, typed, raw)).status == "valid"


def test_the_child_sends_bytes_only_and_keeps_no_typed_rows_when_asked() -> None:
    kept = process(encode(first_text()), Options())
    dropped = process(encode(first_text()), Options(), keep_snapshot=False)
    assert kept.snapshot is not None and dropped.snapshot is None
    assert dropped.status == "valid" and dropped.report == kept.report
    assert (dropped.typed_json, dropped.typed_sha256, dropped.raw_sha256) == (
        kept.typed_json,
        kept.typed_sha256,
        kept.raw_sha256,
    )
    assert dropped.raw_gz == kept.raw_gz


def test_the_typed_json_shares_the_rows_and_is_the_same_text() -> None:
    from tl_xer.process import canonical
    from tl_xer.typed import as_json_value

    outcome = process(encode(first_text()), Options())
    assert outcome.snapshot is not None
    value = as_json_value(outcome.snapshot)
    assert value["tables"]["activities"]["rows"] is outcome.snapshot.tables["activities"]
    assert canonical(value) == outcome.typed_json
    assert json.loads(outcome.typed_json or b"")["tables"]["activities"]["rows"][0][0] == "A1000"
