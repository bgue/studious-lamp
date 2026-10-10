"""Run state on disk: one directory per run under the simulation directory.

    <sim_dir>/<run_id>/run.json          the scenario, the day, key counters, actor tokens (0600)
    <sim_dir>/<run_id>/ground_truth.ndjson

``run.json`` is replaced atomically, so a crash leaves the previous complete state. A step that is
interrupted (the process died between the first write of an actor and the saved state) leaves
``in_progress`` set: the ground-truth log may then be missing writes the server has, so the run
refuses to go on (``RunInterruptedError``) and must be recreated.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tl_sim.scenario import InjectSpec, Scenario

RUN_ID = re.compile(r"[A-Za-z][A-Za-z0-9]{0,23}")  # letters and digits: it becomes part of a key


class RunError(Exception):
    """A run cannot be created, found or continued. The message says what to do."""


class RunInterruptedError(RunError):
    """A step did not finish; the ground-truth log may be incomplete."""


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    scenario: Scenario
    day: int = 0  # working days played so far
    seeded: bool = False  # the template's records exist
    key_counters: dict[str, int] = Field(default_factory=dict[str, int])
    tokens: dict[str, str] = Field(default_factory=dict[str, str])  # actor identity -> token
    pending: list[InjectSpec] = []  # injections queued for the next day that is played
    in_progress: str | None = None  # "<day>:<actor>" while a step runs
    created_at: datetime  # the caller supplies it: the state never reads the wall clock

    @property
    def scope(self) -> str:
        return f"project:sim-{self.run_id}"


class RunStore:
    """Creates, loads and saves run directories."""

    def __init__(self, base: Path) -> None:
        self.base = base

    def run_dir(self, run_id: str) -> Path:
        if RUN_ID.fullmatch(run_id) is None:
            raise RunError(f"run id {run_id!r} must be a letter then letters and digits")
        return self.base / run_id

    def log_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "ground_truth.ndjson"

    def exists(self, run_id: str) -> bool:
        return (self.run_dir(run_id) / "run.json").exists()

    def runs(self) -> list[str]:
        if not self.base.is_dir():
            return []
        return sorted(p.name for p in self.base.iterdir() if (p / "run.json").exists())

    def save(self, state: RunState) -> None:
        directory = self.run_dir(state.run_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "run.json"
        scratch = directory / f"run.json.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        fd = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # tokens are secrets
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(state.model_dump_json(indent=2) + "\n")
            os.replace(scratch, target)
        finally:
            scratch.unlink(missing_ok=True)

    def load(self, run_id: str) -> RunState:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            known = ", ".join(self.runs()) or "none"
            raise RunError(f"no run {run_id!r} in {self.base} (runs: {known})")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return RunState.model_validate(data)

    def only_run(self) -> str:
        """The run id when exactly one run exists (so the CLI can leave ``--run`` out)."""
        runs = self.runs()
        if len(runs) != 1:
            raise RunError(f"say which run: {', '.join(runs) if runs else 'there are none'}")
        return runs[0]
