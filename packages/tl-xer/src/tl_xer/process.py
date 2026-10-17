"""Read, validate and type one XER file: the whole pure step the envelope runs (P1-I4-T03, T04).

``process(data, options)`` is a pure function of its arguments: the same bytes and options give the
same ``Outcome``, byte for byte (no clock, no randomness, no environment). It never raises: a file
it cannot read is an outcome with status ``refused`` and one fixed problem, a file it reads and
finds wrong is ``invalid`` with the problems, and only a file with no error is ``valid`` and
carries the typed snapshot and the raw bundle.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from tl_xer import limits
from tl_xer.bundle import write_bundle
from tl_xer.problems import Problems
from tl_xer.reader import RawXer, read_xer
from tl_xer.refusals import XerRefusal
from tl_xer.typed import TOO_LARGE_MESSAGE, Options, Snapshot, analyse, as_json_value

Status = Literal["valid", "invalid", "refused"]
REPORT_VERSION = 1
#: Said in the report of a file read as Windows-1252: it is the P6 default, and it is also what a
#: UTF-8 file with one stray byte becomes, so a person who sees odd accents knows why.
CP1252_NOTE = "the file is not valid UTF-8, so it was read as Windows-1252 (the P6 default)"


def canonical(value: Any) -> bytes:
    """Canonical JSON: sorted keys, no spaces, UTF-8, no NaN."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


@dataclass(frozen=True)
class Outcome:
    status: Status
    report: dict[str, Any]
    snapshot: Snapshot | None = None
    typed_json: bytes | None = None  # canonical JSON of the snapshot
    typed_sha256: str | None = None
    raw_gz: bytes | None = None
    raw_sha256: str | None = None


def _report(
    status: Status,
    problems: Problems,
    raw: RawXer | None,
    snapshot: Snapshot | None,
    options: Options,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    if raw is not None:
        counts["tables"] = len(raw.tables)
        counts["cells"] = raw.cells
    if snapshot is not None:
        counts.update(snapshot.counts())
    return {
        "report_version": REPORT_VERSION,
        "status": status,
        "p6_version": raw.header[0] if raw is not None and raw.header else None,
        "encoding": raw.encoding if raw is not None else None,
        "encoding_note": CP1252_NOTE if raw is not None and raw.encoding == "cp1252" else None,
        "project_option": options.project,
        "project": snapshot.project if snapshot is not None else None,
        "counts": counts,
        "tables": [
            {"name": t.name, "columns": len(t.columns), "rows": len(t.rows)}
            for t in (raw.tables if raw is not None else ())
        ],
        "error_count": problems.errors,
        "warning_count": problems.warnings,
        "problem_count": problems.count,
        "truncated": problems.truncated,
        "problems": [p.as_dict() for p in problems.kept],
    }


def refused(refusal: XerRefusal, options: Options) -> Outcome:
    problems = Problems()
    message = refusal.message
    if refusal.table:
        message += (
            f" (table {refusal.table}" + (f", row {refusal.row}" if refusal.row else "") + ")"
        )
    problems.error(
        refusal.code, message[: limits.MAX_MESSAGE_CHARS], table=refusal.table, row=refusal.row
    )
    return Outcome("refused", _report("refused", problems, None, None, options))


def process(data: bytes, options: Options, *, keep_snapshot: bool = True) -> Outcome:
    """Read, validate and type ``data``.

    ``keep_snapshot=False`` drops the typed rows once their JSON is made (the child of the
    envelope sends bytes only), before the raw bundle is written: the two never coexist.
    """
    try:
        raw = read_xer(data)
    except XerRefusal as refusal:
        return refused(refusal, options)
    except MemoryError:
        raise  # the envelope turns it into a limit breach; it is not a bad file
    except Exception:  # noqa: BLE001 - a parser bug must not become a crash of the job
        return refused(XerRefusal("parser_error"), options)
    problems = Problems()
    try:
        snapshot = analyse(raw, options, problems)
    except MemoryError:
        raise
    except Exception:  # noqa: BLE001
        problems.error("parser_error", "the file could not be checked")
        snapshot = None
    if snapshot is None or problems.errors:
        return Outcome("invalid", _report("invalid", problems, raw, None, options))
    typed_json = canonical(as_json_value(snapshot))
    if len(typed_json) > limits.MAX_TYPED_JSON:  # the text budget makes this unreachable: a belt
        problems.error("typed_too_large", TOO_LARGE_MESSAGE)
        return Outcome("invalid", _report("invalid", problems, raw, None, options))
    report = _report("valid", problems, raw, snapshot, options)
    kept: Snapshot | None = snapshot if keep_snapshot else None
    del snapshot
    raw_gz, raw_sha256 = write_bundle(raw)
    return Outcome(
        "valid",
        report,
        snapshot=kept,
        typed_json=typed_json,
        typed_sha256=hashlib.sha256(typed_json).hexdigest(),
        raw_gz=raw_gz,
        raw_sha256=raw_sha256,
    )
