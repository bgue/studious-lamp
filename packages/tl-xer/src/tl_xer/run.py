"""Read an XER file in the resource envelope (P1-I4-T03).

``read_xer_file`` is the one call the rest of the system makes. The reading happens in a child
process (``tl_core.derivation.envelope.run_in_envelope``: a scrubbed environment, no inherited
descriptors, address-space and CPU limits, a wall clock, the process group ended afterwards); the
answer is checked by ``tl_xer.wire`` before a ``XerResult`` exists. A child that crashes, runs out
of time or memory, or answers something malformed raises ``XerLimitError`` with no detail (fixed
text, no trace, no path); a file that is merely bad is a normal result with status ``refused`` or
``invalid``.

The worker holds the file, the checked answer (bounded by ``limits.MAX_ANSWER_BYTES`` and the
per-table limits) and nothing else.
"""

from __future__ import annotations

from tl_core.derivation.envelope import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIMEOUT_S,
    Breach,
    run_in_envelope,
)

from tl_xer import limits
from tl_xer.process import refused
from tl_xer.refusals import XerRefusal
from tl_xer.result import LIMIT_MESSAGE, XerLimitError, XerResult
from tl_xer.typed import Options
from tl_xer.wire import decode

ENTRY = "tl_xer.child:entry"

__all__ = ["ENTRY", "LIMIT_MESSAGE", "XerLimitError", "XerResult", "read_xer_file"]


def read_xer_file(
    data: bytes,
    options: Options | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    max_answer: int = limits.MAX_ANSWER_BYTES,
    entry: str = ENTRY,
) -> XerResult:
    """Read, validate and type ``data`` in the envelope. Raises only ``XerLimitError``."""
    chosen = options or Options()
    if len(data) > limits.MAX_BYTES:
        outcome = refused(XerRefusal("too_large"), chosen)
        return XerResult(outcome.status, outcome.report)
    try:
        answer = run_in_envelope(
            entry,
            {"options": {"project": chosen.project}},
            data,
            timeout_s=timeout_s,
            memory_limit_mb=memory_limit_mb,
            max_answer=max_answer,
        )
    except Breach as breach:
        raise XerLimitError(breach.reason) from None
    return decode(answer.payload)
