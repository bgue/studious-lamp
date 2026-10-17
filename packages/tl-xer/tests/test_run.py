"""The envelope round trip and the parent's distrust of the child's answer (P1-I4-T03)."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from typing import Any

import pytest
from tl_xer import limits, run, typed, wire
from tl_xer.child import TAG_OK, entry, frame
from tl_xer.process import canonical, process
from tl_xer.result import LIMIT_MESSAGE, XerLimitError
from tl_xer.run import read_xer_file
from tl_xer.typed import Options
from xersupport import drop_table, encode, first_text, replace_once


def valid_payload() -> tuple[bytes, dict[str, Any], dict[str, Any], bytes]:
    """The payload of a valid file, and its pieces: meta, typed (as objects), raw gzip."""
    tag, payload = entry({"options": {"project": None}}, encode(first_text()))
    assert tag == TAG_OK
    view = memoryview(payload)
    meta_bytes, at = wire._take(view, 0)  # pyright: ignore[reportPrivateUsage]
    typed_bytes, at = wire._take(view, at)  # pyright: ignore[reportPrivateUsage]
    return payload, json.loads(bytes(meta_bytes)), json.loads(bytes(typed_bytes)), payload[at:]


def build(
    meta: dict[str, Any], typed: dict[str, Any] | None, raw_gz: bytes, *, fix_hash: bool = True
) -> bytes:
    typed_bytes = canonical(typed) if typed is not None else b""
    if fix_hash and typed is not None:
        meta = {**meta, "typed_sha256": hashlib.sha256(typed_bytes).hexdigest()}
    return frame(canonical(meta)) + frame(typed_bytes) + raw_gz


def test_the_envelope_gives_what_the_pure_function_gives() -> None:
    data = encode(first_text())
    direct = process(data, Options())
    through = read_xer_file(data)
    assert through.status == direct.status == "valid"
    assert through.report == direct.report
    assert through.snapshot is not None and direct.snapshot is not None
    assert through.snapshot.tables == {
        k: [tuple(r) for r in v] for k, v in direct.snapshot.tables.items()
    }
    assert (through.typed_sha256, through.raw_sha256) == (direct.typed_sha256, direct.raw_sha256)
    assert through.raw_gz is not None and through.typed_sha256 is not None


def test_the_same_bytes_give_the_same_result_twice() -> None:
    data = encode(first_text())
    one, two = read_xer_file(data), read_xer_file(data)
    assert (one.report, one.typed_sha256, one.raw_sha256) == (
        two.report,
        two.typed_sha256,
        two.raw_sha256,
    )
    assert one.raw_gz == two.raw_gz


def test_a_bad_file_is_a_normal_result_not_an_exception() -> None:
    refused = read_xer_file(b"not a schedule")
    assert refused.status == "refused" and refused.snapshot is None and refused.raw_gz is None
    assert [p["code"] for p in refused.report["problems"]] == ["not_xer"]
    invalid = read_xer_file(encode(drop_table(first_text(), "TASK")))
    assert invalid.status == "invalid" and invalid.typed_sha256 is None


def test_the_project_option_reaches_the_child() -> None:
    row = "%R\t2\tOTHER\t1\t2026-10-05 08:00\t\t\t"
    text = replace_once(first_text(), "\r\n%T\tCALENDAR", f"\r\n{row}\r\n%T\tCALENDAR")
    assert read_xer_file(encode(text)).status == "invalid"
    assert read_xer_file(encode(text), Options(project="DEMO-RACK")).status == "valid"


def test_a_file_over_the_byte_limit_is_refused_without_a_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("no child may be started")

    monkeypatch.setattr(run, "run_in_envelope", forbidden)
    monkeypatch.setattr(limits, "MAX_BYTES", 10)
    result = read_xer_file(b"x" * 11)
    assert result.status == "refused" and result.report["problems"][0]["code"] == "too_large"


def test_a_breach_of_the_clock_is_a_limit_error_with_no_detail() -> None:
    with pytest.raises(XerLimitError) as caught:
        read_xer_file(encode(first_text()), timeout_s=0.001)
    assert caught.value.reason == "limit" and str(caught.value) == LIMIT_MESSAGE


def test_a_breach_of_the_memory_limit_is_a_limit_error() -> None:
    with pytest.raises(XerLimitError) as caught:
        read_xer_file(encode(first_text()), memory_limit_mb=30)
    assert caught.value.reason in {"limit", "crash"}


def test_an_answer_past_its_bound_is_refused_by_the_parent() -> None:
    with pytest.raises(XerLimitError) as caught:
        read_xer_file(encode(first_text()), max_answer=100)
    assert caught.value.reason == "too_large"


def test_an_entry_that_does_not_exist_is_a_crash_not_a_traceback() -> None:
    with pytest.raises(XerLimitError) as caught:
        read_xer_file(b"x", entry="tl_xer.child:nothing")
    assert caught.value.reason == "crash"


def test_a_project_option_over_the_id_limit_is_refused_in_the_child() -> None:
    tag, payload = entry({"options": {"project": "x" * 100}}, encode(first_text()))
    result = wire.decode(payload)
    assert tag == TAG_OK and result.status == "refused"
    assert result.report["problems"][0]["code"] == "parser_error"


# --- the parent does not believe the child -----------------------------------------------------


def test_the_valid_payload_decodes() -> None:
    payload, *_ = valid_payload()
    assert wire.decode(payload).status == "valid"


@pytest.mark.parametrize("cut", [0, 4, 7, 12])
def test_a_payload_cut_short_is_a_crash(cut: int) -> None:
    payload, *_ = valid_payload()
    with pytest.raises(XerLimitError) as caught:
        wire.decode(payload[:cut])
    assert caught.value.reason == "crash"


def test_a_frame_that_claims_more_than_the_payload_holds_is_a_crash() -> None:
    with pytest.raises(XerLimitError):
        wire.decode((10_000).to_bytes(8, "big") + b"{}")


def test_a_typed_frame_that_does_not_match_its_digest_is_a_crash() -> None:
    _, meta, typed, raw = valid_payload()
    typed["project"]["short_name"] = "TAMPERED"
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw, fix_hash=False))


def test_a_raw_bundle_that_does_not_match_its_digest_is_a_crash() -> None:
    _, meta, typed, raw = valid_payload()
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(b"something else\n")
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, out.getvalue()))
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, b"not gzip"))


def mutate(table: str, edit: Any) -> Any:
    def apply(typed: dict[str, Any]) -> None:
        edit(typed["tables"][table])

    return apply


@pytest.mark.parametrize(
    "edit",
    [
        mutate("activities", lambda t: t["rows"][0].__setitem__(0, 5)),  # text expected
        mutate("activities", lambda t: t["rows"][0].__setitem__(8, "80")),  # number expected
        mutate("activities", lambda t: t["rows"][0].__setitem__(8, True)),
        mutate("activities", lambda t: t["rows"][0].__setitem__(24, "no")),  # bool expected
        mutate("activities", lambda t: t["rows"][0].__setitem__(26, 1.5)),  # int expected
        mutate(
            "activities", lambda t: t["rows"][0].__setitem__(0, "x" * (limits.MAX_FIELD_CHARS + 1))
        ),
        mutate("activities", lambda t: t["rows"][0].pop()),
        mutate("activities", lambda t: t["rows"][0].append(1)),
        mutate("activities", lambda t: t["columns"].reverse()),
        mutate("activities", lambda t: t.__setitem__("rows", "none")),
        mutate("relationships", lambda t: t["rows"][0].__setitem__(0, None)),  # not optional
    ],
)
def test_a_cell_of_the_wrong_kind_or_shape_is_a_crash(edit: Any) -> None:
    _, meta, typed, raw = valid_payload()
    edit(typed)
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))


def test_a_number_that_is_not_finite_is_a_crash() -> None:
    _, meta, typed, raw = valid_payload()
    text = canonical(typed).replace(b"72.0", b"NaN", 1)
    assert b"NaN" in text
    meta = {**meta, "typed_sha256": hashlib.sha256(text).hexdigest()}
    with pytest.raises(XerLimitError):
        wire.decode(frame(canonical(meta)) + frame(text) + raw)


def test_unknown_tables_and_keys_in_the_typed_frame_are_a_crash() -> None:
    _, meta, typed, raw = valid_payload()
    typed["tables"]["extra"] = {"columns": [], "rows": []}
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))
    _, meta, typed, raw = valid_payload()
    typed["surprise"] = 1
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))
    _, meta, typed, raw = valid_payload()
    typed["project"]["extra"] = "x"
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))


def test_more_rows_than_a_table_may_hold_is_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    payload, *_ = valid_payload()
    monkeypatch.setitem(typed.TABLE_LIMITS, "activities", 20)
    with pytest.raises(XerLimitError):
        wire.decode(payload)


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.__setitem__("status", "maybe"),
        lambda r: r["problems"].append({"severity": "fatal", "code": "x", "message": "m"}),
        lambda r: r["problems"].append(
            {"severity": "error", "code": "x", "message": "m" * (limits.MAX_MESSAGE_CHARS + 1)}
        ),
        lambda r: r["problems"].extend(
            [{"severity": "error", "code": "x", "message": "m"}] * (limits.MAX_PROBLEMS + 1)
        ),
        lambda r: r["counts"].__setitem__("activities", -1),
        lambda r: r["counts"].__setitem__("activities", "21"),
        lambda r: r.__setitem__("tables", [{"name": 1, "columns": 1, "rows": 1}]),
        lambda r: r.__setitem__("p6_version", "9" * 300),
        lambda r: r.pop("error_count"),
    ],
)
def test_a_report_with_a_bad_field_is_a_crash(edit: Any) -> None:
    _, meta, typed, raw = valid_payload()
    edit(meta["report"])
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))


def test_a_report_keeps_only_the_keys_it_knows() -> None:
    _, meta, typed, raw = valid_payload()
    meta["report"]["injected"] = "<script>"
    assert "injected" not in wire.decode(build(meta, typed, raw)).report


def test_a_non_valid_report_must_come_without_a_snapshot_or_bundle() -> None:
    _, meta, typed, raw = valid_payload()
    meta["report"]["status"] = "invalid"
    with pytest.raises(XerLimitError):
        wire.decode(build(meta, typed, raw))
    assert wire.decode(build(meta, None, b"")).status == "invalid"
