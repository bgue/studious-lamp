"""Reading an email in a process of its own (D9 envelope), and the answer back.

``parse_eml_isolated`` is what a command calls. It hands the bytes to a fresh interpreter with a
clock, a memory limit and a scrubbed environment (``tl_core.derivation.envelope``), where
``entry`` runs ``eml.parse_eml``, and reads back a bounded answer: a JSON description of the
message and the attachments' bytes, framed by lengths. A refusal is answered with its fixed text; a
breach of the envelope (time, memory, a crash) is refused with a fixed text too and no detail. The
parent never unpickles anything, and never holds more than the answer bound.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, Final

from tl_core.derivation.envelope import Breach, run_in_envelope

from tl_mod_correspondence.eml import (
    EmlAddress,
    EmlAttachment,
    EmlLimits,
    EmlRefused,
    ParsedMessage,
    parse_eml,
)

ENTRY: Final = "tl_mod_correspondence.eml_isolated:entry"
TAG_MESSAGE: Final = b"M"
TAG_REFUSED: Final = b"F"
TIMEOUT_S: Final = 20.0
MEMORY_MB: Final = 512
BREACHED: Final = "the message could not be read safely (it took too long or too much memory)"


def entry(header: Mapping[str, Any], data: bytes) -> tuple[bytes, bytes]:
    """Runs in the child: parse, and answer ``M`` + JSON + attachments, or ``F`` + the reason."""
    limits = EmlLimits.from_dict(dict(header.get("limits", {})))
    try:
        parsed = parse_eml(data, limits)
    except EmlRefused as exc:
        return TAG_REFUSED, str(exc).encode("utf-8")
    described = asdict(parsed)
    sizes = [len(a.data) for a in parsed.attachments]
    for item in described["attachments"]:
        del item["data"]
    described["attachment_sizes"] = sizes
    blob = json.dumps(described).encode("utf-8")
    body = b"".join(a.data for a in parsed.attachments)
    return TAG_MESSAGE, len(blob).to_bytes(8, "big") + blob + body


def _address(value: Mapping[str, Any]) -> EmlAddress:
    return EmlAddress(name=value.get("name"), email=value.get("email"))


def parse_eml_isolated(
    data: bytes,
    limits: EmlLimits | None = None,
    *,
    timeout_s: float = TIMEOUT_S,
    memory_limit_mb: int = MEMORY_MB,
) -> ParsedMessage:
    """``eml.parse_eml`` in the envelope. Raises ``EmlRefused`` (a fixed text) for a message that is
    over a bound, unreadable, or that broke the envelope."""
    bounds = limits or EmlLimits()
    if len(data) > bounds.max_bytes:  # checked before a process is started
        raise EmlRefused("the message is larger than the limit")
    answer_bound = bounds.max_total_bytes + 4 * 1024 * 1024
    try:
        answer = run_in_envelope(
            ENTRY,
            {"limits": bounds.as_dict()},
            data,
            timeout_s=timeout_s,
            memory_limit_mb=memory_limit_mb,
            max_answer=answer_bound,
        )
    except Breach as exc:
        raise EmlRefused(BREACHED) from exc
    if answer.tag == TAG_REFUSED:
        raise EmlRefused(answer.payload.decode("utf-8", errors="replace")[:200])
    if answer.tag != TAG_MESSAGE:
        raise EmlRefused(BREACHED)
    payload = answer.payload
    size = int.from_bytes(payload[:8], "big")
    described = json.loads(payload[8 : 8 + size])
    sizes: list[int] = described.pop("attachment_sizes")
    rest = payload[8 + size :]
    attachments: list[EmlAttachment] = []
    offset = 0
    for meta, length in zip(described.pop("attachments"), sizes, strict=True):
        attachments.append(
            EmlAttachment(meta["filename"], meta["content_type"], rest[offset : offset + length])
        )
        offset += length
    return ParsedMessage(
        **{
            **described,
            "to": tuple(_address(a) for a in described["to"]),
            "cc": tuple(_address(a) for a in described["cc"]),
            "references": tuple(described["references"]),
            "attachments": tuple(attachments),
        }
    )
