"""``seed``: a synthetic project in the dev ledger, through the API (brief 25.2, 25.3, D12)."""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import time
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from tl_mcp.dev.errors import DevGuardError, DevToolFailure
from tl_mcp.dev.runtime import DevContext, guarded

MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
TAIL_CHARS = 4000
TERMINATE_GRACE_S = 10
SEED_SCRIPT = "dev/seed/seed.sh"

_RUN_RE = re.compile(r"^run (\S+)$", re.MULTILINE)
_SCOPE_RE = re.compile(r"^scope (\S+)$", re.MULTILINE)
_RECORDS_RE = re.compile(r"^seeded (\d+) records$", re.MULTILINE)


class SeedOutput(BaseModel):
    """The answer of ``seed``."""

    ok: bool  # exit code 0 and not timed out
    scale: str
    exit_code: int  # -1 if timed out
    timed_out: bool
    run: str | None  # the simulator run id ("run <id>")
    scope: str | None  # the project scope the run wrote ("scope project:sim-...")
    records: int | None  # "seeded <n> records"
    api_port: int  # the loopback port an API was started on, if the script started one
    output_tail: str  # the last 4000 characters of the script's output
    duration_s: float


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _signal_group(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:  # the group is already gone
        pass


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _records(text: str) -> int | None:
    found = _first(_RECORDS_RE, text)
    return int(found) if found is not None else None


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=MUTATING)
    def seed(
        scale: Annotated[
            Literal["xs", "s", "m"],
            Field(description="xs: 3 working days, s: 10, m: 30."),
        ] = "xs",
        timeout_s: Annotated[
            int, Field(ge=1, le=1800, description="Seconds before the run is stopped.")
        ] = 600,
    ) -> SeedOutput:
        """Seed the dev ledger with a synthetic project, written through the API by the simulator.

        Runs dev/seed/seed.sh (the same script as `just seed`): it starts a short-lived API on a
        free loopback port if none answers, plays the simulator through it, and stops that API
        again.
        Each call adds one more simulated project (a new run id and scope); existing data is kept.
        Scales: xs (3 working days, about 15 s measured), s (10 working days) and m (30 working
        days), which take longer; only xs has a measured cost. Needs a SQLite dev database; a
        Postgres target is refused. Returns the run id, the scope, the record count and the tail of
        the script's output. A run that outlives `timeout_s` is stopped and returned with
        timed_out=true.
        """
        with guarded(ctx, "seed", {"scale": scale}):
            if ctx.target.kind != "sqlite":
                raise DevGuardError("seed needs a SQLite dev database")
            script = ctx.repo_root / SEED_SCRIPT
            if not script.is_file():
                raise DevToolFailure("dev/seed/seed.sh is missing")
            assert ctx.target.path is not None
            db_dir = ctx.target.path.parent
            port = _free_loopback_port()
            extra = {
                "TL_DB": str(ctx.target.path),
                "TL_API_URL": f"http://127.0.0.1:{port}",
                "TL_TOKENS": str(db_dir / "seed-tokens.json"),
                "TL_SIM_DIR": str(db_dir / "sim"),
            }
            started = time.monotonic()
            proc = subprocess.Popen(
                ["bash", str(script), scale],
                cwd=ctx.repo_root,
                env=ctx.child_env(extra),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            timed_out = False
            try:
                out, _ = proc.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _signal_group(proc.pid, signal.SIGTERM)  # the script's EXIT trap stops its API
                try:
                    out, _ = proc.communicate(timeout=TERMINATE_GRACE_S)
                except subprocess.TimeoutExpired:
                    _signal_group(proc.pid, signal.SIGKILL)
                    out, _ = proc.communicate()
            duration = time.monotonic() - started
            return SeedOutput(
                ok=proc.returncode == 0 and not timed_out,
                scale=scale,
                exit_code=-1 if timed_out else int(proc.returncode),
                timed_out=timed_out,
                run=_first(_RUN_RE, out),
                scope=_first(_SCOPE_RE, out),
                records=_records(out),
                api_port=port,
                output_tail=out[-TAIL_CHARS:],
                duration_s=round(duration, 3),
            )
