"""Run untrusted work in a process of its own, inside a resource envelope (FANOUT D9, D10).

Reading a stranger's PDF, or applying a stranger's regular expression to a stranger's cells, can
loop for ever, eat all the memory or crash a native library, and the code that does it cannot
always bound itself. So the pipeline never does it in the worker. :func:`run_in_envelope` starts a
fresh interpreter for one call and gives it:

* a **scrubbed environment**: ``PATH``, ``PYTHONPATH``, ``LANG`` and the locale variables, and
  nothing else (no ``TL_*``, no secrets, no session material);
* **no inherited descriptors** (``close_fds``, a pipe of its own for the answer) and a session of
  its own, so ``SIGKILL`` reaches anything it started;
* the bytes it works on over a pipe: a JSON header and a data block, framed with lengths. The child
  is given no path;
* ``RLIMIT_AS`` (``memory_limit_mb``) and ``RLIMIT_CPU`` (the wall clock rounded up). **If a limit
  cannot be set the call fails as a breach**; it never runs without it;
* a wall clock in the parent (``timeout_s``); on expiry the whole process group gets ``SIGTERM``,
  then ``SIGKILL`` after a short grace, and is reaped.

The answer is a one-byte tag, a length and bytes. **Nothing from the child is ever unpickled**: the
parent reads at most ``max_answer`` bytes and hands them to a JSON parser. A breach (clock, memory,
CPU, death by signal, exit without an answer, a limit that cannot be set) raises
:class:`Breach` with no detail: no trace, no path.

Rlimits bound time and memory; they do not confine the filesystem or the network (a seccomp or
namespace sandbox is a follow-up in the risk register). The child runs plugin code as the same
user, with no secrets in its environment and no descriptors of the worker's.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import select
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal

from tl_core.derivation.types import (
    EXTRACT_MAX_MEMORY_BYTES,
    EXTRACT_MAX_SECONDS,
    MAX_SOURCE_BYTES,
)

DEFAULT_TIMEOUT_S = float(EXTRACT_MAX_SECONDS)
DEFAULT_MEMORY_LIMIT_MB = EXTRACT_MAX_MEMORY_BYTES // (1024 * 1024)
#: How long a child gets to leave after it is asked to, before it is killed.
KILL_GRACE_S = 1.0
#: The largest answer the parent reads. A text table from a source of ``MAX_SOURCE_BYTES`` can
#: grow when parsed (a compressed spreadsheet), so four times the source bound; more is refused.
MAX_ANSWER_BYTES = 4 * MAX_SOURCE_BYTES
#: The largest header the child reads (the source description, options, a schema).
MAX_HEADER_BYTES = 8 * 1024 * 1024
#: What the child's environment may hold.
ENV_ALLOWED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "LC_CTYPE")

TAG_LIMIT = b"L"  # the child could not set its limits, or ran out of memory
TAG_ERROR = b"X"  # the child's entry raised
_BOOT = (
    "import sys; from tl_core.derivation.envelope import child_main; "
    "child_main(int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))"
)

Reason = Literal["limit", "crash", "too_large"]
Entry = Callable[[Mapping[str, Any], bytes], tuple[bytes, bytes]]


class Breach(Exception):  # noqa: N818 - a name for what happened, not an error class
    """The call broke the envelope. ``reason`` is all there is to know; there is no detail."""

    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


@dataclass(frozen=True)
class Answer:
    tag: bytes
    payload: bytes


def scrubbed_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of a child: the allowed variables of ``source`` (default: this process)."""
    found = os.environ if source is None else source
    return {name: found[name] for name in ENV_ALLOWED if name in found}


# --- the child -------------------------------------------------------------------------------


def _limit(megabytes: int, cpu_seconds: int) -> bool:
    """Set the limits; ``False`` if any could not be set (the caller then refuses to run)."""
    try:
        import resource
    except ImportError:
        return False  # no way to limit: refuse to run (POSIX only)
    try:
        if megabytes >= 0:
            limit = megabytes * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        if cpu_seconds >= 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    except (ValueError, OSError, OverflowError):
        return False
    return True


def _read_exactly(stream: BinaryIO, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = stream.read(min(remaining, 1 << 20))
        if not chunk:
            raise EOFError
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _send(out: BinaryIO, tag: bytes, payload: bytes) -> None:
    out.write(tag + len(payload).to_bytes(8, "big") + payload)
    out.flush()


def child_main(answer_fd: int, entry: str, memory_mb: int, cpu_seconds: int) -> None:
    """The child's whole life: limit, read the input, call ``entry``, answer, exit."""
    out = os.fdopen(answer_fd, "wb")
    try:
        if not _limit(memory_mb, cpu_seconds):
            _send(out, TAG_LIMIT, b"")
            return
        stdin = sys.stdin.buffer
        size = int.from_bytes(_read_exactly(stdin, 8), "big")
        if size > MAX_HEADER_BYTES:
            raise ValueError("header too large")
        header: Mapping[str, Any] = json.loads(_read_exactly(stdin, size))
        data = _read_exactly(stdin, int.from_bytes(_read_exactly(stdin, 8), "big"))
        module_name, _, attribute = entry.partition(":")
        function: Entry = getattr(importlib.import_module(module_name), attribute)
        tag, payload = function(header, data)
        _send(out, tag, payload)
    except MemoryError:
        _send(out, TAG_LIMIT, b"")
    except BaseException:  # noqa: BLE001 - the parent learns only that it failed
        _send(out, TAG_ERROR, b"")
    finally:
        out.close()


# --- the parent ------------------------------------------------------------------------------


def _feed(process: subprocess.Popen[bytes], header: bytes, data: bytes) -> None:
    """Write the framed input; a child that never reads is killed by the clock, not waited for."""
    try:
        assert process.stdin is not None
        process.stdin.write(len(header).to_bytes(8, "big") + header)
        process.stdin.write(len(data).to_bytes(8, "big"))
        process.stdin.write(data)
        process.stdin.close()
    except (BrokenPipeError, OSError, ValueError):
        pass


def _read_answer(fd: int, deadline: float, max_answer: int) -> Answer:
    buffer = bytearray()
    wanted: int | None = None
    while wanted is None or len(buffer) < wanted:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Breach("limit")
        ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        if not ready:
            continue
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            raise Breach("crash")  # closed before a whole answer: died, or exited silently
        buffer += chunk
        if wanted is None and len(buffer) >= 9:
            size = int.from_bytes(buffer[1:9], "big")
            if size > max_answer:
                raise Breach("too_large")
            wanted = 9 + size
    return Answer(bytes(buffer[:1]), bytes(buffer[9:wanted]))


def _end(process: subprocess.Popen[bytes]) -> None:
    """Make sure the child and anything it started are gone: ``SIGTERM``, grace, ``SIGKILL``."""
    for sig, wait in ((signal.SIGTERM, KILL_GRACE_S), (signal.SIGKILL, None)):
        try:
            os.killpg(process.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_in_envelope(
    entry: str,
    header: Mapping[str, Any],
    data: bytes,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    max_answer: int = MAX_ANSWER_BYTES,
) -> Answer:
    """Call ``entry`` (``"module:function"`` taking ``(header, data)``) in a child; its answer.

    ``entry`` returns ``(tag, payload)``. Raises :class:`Breach` when the envelope is broken.
    A tag of ``TAG_LIMIT`` or ``TAG_ERROR`` is a breach too, so callers see only real answers.
    """
    read_fd, write_fd = os.pipe()
    cpu = max(1, math.ceil(timeout_s))
    try:
        process = subprocess.Popen(  # noqa: S603 - our own interpreter and our own module
            [
                sys.executable,
                "-c",
                _BOOT,
                str(write_fd),
                entry,
                str(-1 if memory_limit_mb is None else memory_limit_mb),
                str(cpu),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=scrubbed_environment(),
            pass_fds=(write_fd,),
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        os.close(read_fd)
        os.close(write_fd)
        raise Breach("crash") from exc
    os.close(write_fd)
    feeder = threading.Thread(
        target=_feed, args=(process, json.dumps(dict(header)).encode(), data), daemon=True
    )
    feeder.start()
    try:
        answer = _read_answer(read_fd, time.monotonic() + timeout_s, max_answer)
    finally:
        os.close(read_fd)
        _end(process)
        feeder.join(timeout=KILL_GRACE_S)
    if answer.tag == TAG_LIMIT:
        raise Breach("limit")
    if answer.tag == TAG_ERROR:
        raise Breach("crash")
    return answer
