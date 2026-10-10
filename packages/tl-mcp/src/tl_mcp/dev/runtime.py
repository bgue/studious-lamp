"""What every dev tool shares: the context, the audit line and the error mapping.

A dev tool body runs inside :func:`guarded`. It turns a refusal by the dev-data guard into a
``ToolError`` that starts with ``refused:``, turns the failures a tool can expect into short
messages, and appends one JSON line to the audit file for every call, accepted or not.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from tl_mcp.dev.errors import DevGuardError, DevToolFailure
from tl_mcp.dev.guard import DevTarget

log = logging.getLogger("tl_mcp.dev")
log.addHandler(logging.NullHandler())  # a library prints nothing until the application opts in

#: Environment variables a child process (pytest, the seed script) may inherit. Everything else,
#: including any credential in the server's environment, is dropped.
CHILD_ENV_KEYS = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "VIRTUAL_ENV",
    "UV_CACHE_DIR",
    "UV_PROJECT_ENVIRONMENT",
    "TL_PG_URL",
)
AUDIT_VALUE_CHARS = 200


@dataclass(frozen=True)
class DevContext:
    """The repository, the one database the dev tools use, and where they write.

    ``audit_path=None`` turns the audit file off (tests). ``target`` is already checked by
    :func:`tl_mcp.dev.guard.resolve_target`; a tool never builds its own.
    """

    repo_root: Path
    target: DevTarget
    audit_path: Path | None = None
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))

    @property
    def dev_dir(self) -> Path:
        return self.repo_root / "dev"

    @property
    def data_dir(self) -> Path:
        """``dev/data``: git-ignored; reports and snapshots the tools write go below it."""
        return self.dev_dir / "data"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "test-reports"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    def child_env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """A minimal environment for a child process: allow-listed variables plus ``extra``.

        ``TL_ENV`` is always ``dev``, so the child never sees a real environment's settings.
        """
        env = {k: self.environ[k] for k in CHILD_ENV_KEYS if k in self.environ}
        env["TL_ENV"] = "dev"
        env.update(extra or {})
        return env


def _short(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= AUDIT_VALUE_CHARS else text[:AUDIT_VALUE_CHARS] + "..."


def audit(ctx: DevContext, tool: str, outcome: str, detail: Mapping[str, Any]) -> None:
    """Append one line to the audit file; never raises (an audit failure must not hide the call).

    The line is ASCII-escaped, so one record is always one line (``str.splitlines`` splits on
    U+2028 and U+0085).
    """
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool,
        "outcome": outcome,
        "detail": {k: _short(v) for k, v in detail.items()},
    }
    log.info("%s %s", tool, outcome)
    if ctx.audit_path is None:
        return
    try:
        ctx.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with ctx.audit_path.open("a", encoding="ascii") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    except OSError:
        log.warning("could not write the audit line for %s", tool)


@contextmanager
def guarded(
    ctx: DevContext,
    tool: str,
    detail: Mapping[str, Any] | None = None,
    *,
    error: type[Exception] = ToolError,
) -> Iterator[None]:
    """Run a tool body: audit the call and map expected failures to ``error`` with a clear text."""
    info = dict(detail or {})
    try:
        yield
    except (ToolError, ResourceError):
        audit(ctx, tool, "error", info)
        raise
    except DevGuardError as exc:
        audit(ctx, tool, "refused", {**info, "why": str(exc)})
        text = str(exc)
        raise error(text if text.startswith("refused") else f"refused: {text}") from exc
    except DevToolFailure as exc:
        audit(ctx, tool, "error", {**info, "why": str(exc)})
        raise error(str(exc)) from exc
    except OSError as exc:  # its text can carry a server path: say only what kind of failure
        audit(ctx, tool, "error", {**info, "why": type(exc).__name__})
        raise error(f"{type(exc).__name__}: {exc.strerror or 'file error'}") from exc
    except (ValueError, LookupError) as exc:
        audit(ctx, tool, "error", {**info, "why": type(exc).__name__})
        raise error(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    except BaseException:
        audit(ctx, tool, "failed", info)
        raise
    audit(ctx, tool, "ok", info)
