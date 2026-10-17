"""The entry the resource envelope runs in its child process (P1-I4-T03).

``entry(header, data)`` is called by ``tl_core.derivation.envelope.child_main`` with the JSON header
the parent sent and the bytes of the file. It answers a tag and a payload made of:

1. a frame (an 8-byte big-endian length and its bytes) of metadata, canonical JSON: the report,
   the SHA-256 of the typed frame and of the uncompressed raw text;
2. a frame of the typed snapshot, canonical JSON (empty unless the file is valid);
3. the rest: the raw bundle, gzip bytes (empty unless the file is valid).

Nothing is pickled. The parent checks every length and every cell before it uses any of it
(``tl_xer.run``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tl_xer import limits
from tl_xer.process import Outcome, canonical, process, refused
from tl_xer.refusals import XerRefusal
from tl_xer.typed import Options

TAG_OK = b"K"


def frame(data: bytes) -> bytes:
    return len(data).to_bytes(8, "big") + data


def options_from(header: Mapping[str, Any]) -> Options:
    given = header.get("options")
    if not isinstance(given, Mapping):
        return Options()
    project: Any = given.get("project")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if project is None or (isinstance(project, str) and len(project) <= limits.MAX_ID_CHARS):
        return Options(project=project)
    raise ValueError("bad options")


def entry(header: Mapping[str, Any], data: bytes) -> tuple[bytes, bytes]:
    try:
        options = options_from(header)
    except ValueError:
        return TAG_OK, frame(
            canonical(_meta(refused(XerRefusal("parser_error"), Options())))
        ) + frame(b"")
    outcome = process(data, options)
    typed = outcome.typed_json or b""
    raw = outcome.raw_gz or b""
    return TAG_OK, frame(canonical(_meta(outcome))) + frame(typed) + raw


def _meta(outcome: Outcome) -> dict[str, Any]:
    return {
        "report": outcome.report,
        "typed_sha256": outcome.typed_sha256,
        "raw_sha256": outcome.raw_sha256,
    }
