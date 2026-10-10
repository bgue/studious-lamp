"""The five simulation operations of brief 29.5 as a Python API: ``sim_create``, ``sim_advance``,
``sim_inject``, ``sim_status`` and ``sim_assert``.

Each takes a ``SimEnv`` (where the run files live, which server to talk to, which token file the
server reads) and returns plain JSON-able data, so the ``tl sim`` CLI and the MCP server
(``tl_sim.mcp_server``) are thin wrappers that only format what comes back.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tl_sim.connector import HttpConnector
from tl_sim.orchestrator import Simulation, default_run_id
from tl_sim.scenario_loader import load_bundled_scenario, load_scenario, load_template
from tl_sim.state import RunStore

DEFAULT_SIM_DIR = "./dev/data/sim"
DEFAULT_API_URL = "http://127.0.0.1:8765"
DEFAULT_TOKENS = "./dev/data/tokens.json"
DEFAULT_DB = "./dev/data/tl.db"

Authorizer = Callable[[str, str, str], None]
"""``hook(actor, action, resource)``: raises to refuse (the shape of ``tl_api.auth.authorize``)."""


@dataclass(frozen=True)
class SimEnv:
    """Where a run lives. ``from_env`` reads ``TL_SIM_DIR``, ``TL_API_URL``, ``TL_TOKENS``."""

    sim_dir: Path = Path(DEFAULT_SIM_DIR)
    api_url: str = DEFAULT_API_URL
    tokens_path: Path = Path(DEFAULT_TOKENS)
    db_path: Path = Path(DEFAULT_DB)  # the ledger file the MCP server (the agent) opens

    @staticmethod
    def from_env() -> SimEnv:
        return SimEnv(
            sim_dir=Path(os.environ.get("TL_SIM_DIR", DEFAULT_SIM_DIR)),
            api_url=os.environ.get("TL_API_URL", DEFAULT_API_URL),
            tokens_path=Path(os.environ.get("TL_TOKENS", DEFAULT_TOKENS)),
            db_path=Path(os.environ.get("TL_DB", DEFAULT_DB)),
        )


def _open(env: SimEnv, run_id: str | None) -> Simulation:
    store = RunStore(env.sim_dir)
    rid = run_id or store.only_run()
    connector = HttpConnector(env.api_url, env.tokens_path, run_id=rid, db_path=env.db_path)
    return Simulation.open(rid, store=store, connector=connector)


def sim_create(
    env: SimEnv, scenario: str | Path, *, run_id: str | None = None, bundled_only: bool = False
) -> dict[str, Any]:
    """Create a run from a scenario (a YAML path or a bundled name) and write the seed records.

    ``bundled_only`` (the MCP server) accepts a bundled name and nothing else: never a path.
    """
    loaded = load_bundled_scenario(str(scenario)) if bundled_only else load_scenario(scenario)
    rid = run_id or default_run_id(loaded)
    connector = HttpConnector(env.api_url, env.tokens_path, run_id=rid, db_path=env.db_path)
    sim = Simulation.create(
        loaded,
        load_template(loaded.template),
        store=RunStore(env.sim_dir),
        connector=connector,
        run_id=rid,
    )
    return {"run_id": sim.state.run_id, "scope": sim.state.scope, **_status(sim)}


def sim_advance(env: SimEnv, run_id: str | None = None, *, days: int = 1) -> dict[str, Any]:
    """Play ``days`` working days. Returns the dates played and the ground truth written."""
    sim = _open(env, run_id)
    result = sim.advance(days)
    return {
        "run_id": sim.state.run_id,
        "dates": [d.isoformat() for d in result.days],
        "steps": result.steps,
        "ground_truth_written": result.truth,
        **_status(sim),
    }


def sim_inject(
    env: SimEnv, run_id: str | None, event: str, args: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Queue an event (``material_late``, ``design_revision``, ``post``) for the next day played."""
    sim = _open(env, run_id)
    spec = sim.inject(event, **(args or {}))
    return {"run_id": sim.state.run_id, "queued": spec.model_dump(mode="json")}


def sim_status(env: SimEnv, run_id: str | None = None) -> dict[str, Any]:
    sim = _open(env, run_id)
    return {"run_id": sim.state.run_id, **_status(sim)}


def sim_assert(env: SimEnv, run_id: str | None = None) -> dict[str, Any]:
    """Compare the ground truth with what the suite holds. ``ok`` is false on any failure."""
    sim = _open(env, run_id)
    report = sim.assert_()
    return {
        "run_id": sim.state.run_id,
        "ok": report.ok,
        "checked": report.checked,
        "counts": report.counts,
        "failures": [asdict(f) for f in report.failures],
    }


def _status(sim: Simulation) -> dict[str, Any]:
    status = sim.status()
    data = asdict(status)
    data["next_date"] = status.next_date.isoformat()
    data["last_date"] = status.last_date.isoformat() if status.last_date else None
    del data["run_id"]
    return data
