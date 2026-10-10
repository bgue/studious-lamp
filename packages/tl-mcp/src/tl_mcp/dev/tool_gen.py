"""``gen``: the codegen drift report, and with ``apply`` the regeneration (brief 25.4).

The regeneration is what ``just gen`` does.
"""

from __future__ import annotations

import difflib
import io
import threading
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.runtime import DevContext, guarded

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

MAX_DIFF_FILES = 5
MAX_DIFF_CHARS = 20000
CUT_MARK = "... (cut)\n"

# The generators change the working directory of the whole process (contextlib.chdir) while they
# run, and the server runs sync tools on worker threads. Two gen calls must therefore never overlap:
# the lock serialises the whole report, writes included.
_GENERATE_LOCK = threading.Lock()


class DriftItem(BaseModel):
    """One committed generated file that does not match what the generators produce."""

    path: str  # posix, relative to generated/
    kind: Literal["missing", "differs", "stale"]


class GenOutput(BaseModel):
    """The answer of ``gen``."""

    in_sync: bool  # no drift after any apply
    file_count: int  # generated files the generators produce
    drift: list[DriftItem]  # after any apply
    diff: str  # unified diff of up to 5 differing files (current against generated), capped
    applied: bool  # this call wrote the generated files


def _lines(text: str) -> list[str]:
    # Split on "\n" only: str.splitlines also splits on characters such as U+2028.
    return io.StringIO(text).readlines()


def _drift_items(found: list[str]) -> list[DriftItem]:
    # Each line is "<kind>: <path>", as tl_schema.generate.problems writes it.
    items: list[DriftItem] = []
    for line in found:
        kind, _, path = line.partition(": ")
        items.append(DriftItem.model_validate({"path": path, "kind": kind}))
    return items


def _diff(out_dir: Path, files: dict[str, str], drift: list[DriftItem]) -> str:
    chunks: list[str] = []
    differing = [item.path for item in drift if item.kind == "differs"][:MAX_DIFF_FILES]
    for path in differing:
        current = _lines((out_dir / path).read_bytes().decode("utf-8"))
        wanted = _lines(files[path])
        chunks.extend(
            difflib.unified_diff(current, wanted, fromfile=f"a/{path}", tofile=f"b/{path}")
        )
    text = "".join(chunks)
    if len(text) > MAX_DIFF_CHARS:
        text = text[:MAX_DIFF_CHARS] + CUT_MARK
    return text


def gen_report(schema_dir: Path, out_dir: Path, *, apply: bool) -> GenOutput:
    """Run every generator and compare the result with the files under ``out_dir``.

    With ``apply`` and any drift, the generated files are written (what ``just gen`` does) and the
    drift is taken again. So ``in_sync``, ``drift`` and ``diff`` describe the state after any write;
    ``applied`` says whether this call wrote anything.
    """
    # Imported here, not at module level, so that starting the dev server stays quick.
    from tl_schema import generate

    with _GENERATE_LOCK:
        files = generate.outputs(schema_dir)
        found = generate.problems(out_dir, files)
        applied = False
        if apply and found:
            generate.write(out_dir, files)
            applied = True
            found = generate.problems(out_dir, files)
        drift = _drift_items(found)
        return GenOutput(
            in_sync=not drift,
            file_count=len(files),
            drift=drift,
            diff=_diff(out_dir, files, drift),
            applied=applied,
        )


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=WRITES)
    def gen(
        apply: Annotated[
            bool,
            Field(description="Regenerate the files that differ, as `just gen` does."),
        ] = False,
    ) -> GenOutput:
        """Report codegen drift: the committed files under the tl_schema generated directory that
        are missing, differ from the schema generators' output, or are stale, with a unified diff
        of up to five differing files.

        Without `apply` nothing is written. With `apply` the generated files are regenerated (what
        `just gen` does) and the report is taken again; `applied` says whether files were written.
        """
        generated = ctx.repo_root / "packages" / "tl-schema" / "src" / "tl_schema" / "generated"
        with guarded(ctx, "gen", {"apply": apply}):
            if apply and not generated.resolve().is_relative_to(ctx.repo_root.resolve()):
                raise DevGuardError("the generated directory resolves outside the repository")
            return gen_report(ctx.repo_root / "schema" / "core", generated, apply=apply)
