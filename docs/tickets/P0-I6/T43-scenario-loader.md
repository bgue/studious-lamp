# P0-I6-T43 — Scenario and template loader

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the base `p0/i6c` already has the actor base, `tl_sim.testing` and the stub)
Branch: `p0/i6c-t43-scenario-loader`

## Goal
Scenarios and seed templates can be loaded from YAML: `load_scenario` reads a bundled name or a file path into a `Scenario`, `load_template` reads a seed template, and every failure is a `ScenarioError` that names the file and the field. The stub has the signatures and docstrings; the four functions raise `NotImplementedError`. The data files under `dev/seed/` already exist. A provided test file (25 tests) must pass.

## Brief references (pasted)
> **29.5** A simulator generates realistic project activity by acting through the suite's public MCP server and API, as if it were a project team. Deterministic actors do the bulk mechanics; roles include the document controller (registers revisions, transmittals), the planner (clears constraints) and the welding foreman / crew (records, photos, feed posts). Time compression: `sim_advance(days=...)` runs a working day in seconds. Determinism: seeded randomness, so a scenario replays identically.
> **29.1** Dogfood the open interfaces: the simulator uses only the public API and MCP.
> FANOUT D6: simulator v0 is fully deterministic and makes no LLM calls.

### Specification
The stub's docstrings are the specification. In detail:

- `seed_dir()`: `Path(os.environ["TL_SEED_DIR"])` when that variable is set and not empty; otherwise `dev/seed` in the repository, found from this file: `Path(__file__).resolve().parents[4] / "dev" / "seed"`.
- `bundled_scenarios()`: sorted stems of `seed_dir() / "scenarios" / "*.yaml"`; an empty list when the directory does not exist.
- `load_scenario(source)`: a `Path`, or a string that contains `/` or ends with `.yaml` or `.yml`, is a file path; any other string is a bundled name, read from `seed_dir() / "scenarios" / f"{name}.yaml"`. An unknown name is a `ScenarioError` that names the directory searched and lists the bundled scenarios.
- `load_template(name)`: `name` must match `[a-z0-9][a-z0-9._-]*` (else `ScenarioError(f"template name {name!r} must be lowercase letters, digits, . _ -")`, which also blocks `../`); the file is `seed_dir() / "templates" / f"{name}.yaml"`; a missing file is `ScenarioError(f"template {name!r} not found: no file {path}")`.
- Reading (shared by both): a file larger than `MAX_BYTES` is `ScenarioError(f"{path}: file is {size} bytes, more than the {MAX_BYTES} allowed")`, checked before parsing; read as UTF-8 and parse with `yaml.safe_load` only (never `yaml.load`); a read or YAML error is `ScenarioError(f"{path}: not valid YAML: {exc}")` (an unreadable path is `ScenarioError(f"{path}: cannot read: ...")`); a top level that is not a mapping is `ScenarioError(f"{path}: expected a mapping at the top level")`.
- Validation: `Scenario.model_validate` / `Template.model_validate`. A pydantic `ValidationError` becomes `ScenarioError(f"{path}: " + "; ".join(f"{dotted location}: {message}" ...))`, where the dotted location is the error's `loc` joined with `.` (`actors.crew.reject_rate`), or `(top level)` when empty.
- The data files `dev/seed/scenarios/*.yaml` and `dev/seed/templates/*.yaml` already exist; do not edit them.

**Imports to add:** `import os`, `import re`, `from typing import Any`, `import yaml` (PyYAML, already a dependency of the package), `from pydantic import BaseModel, ValidationError`. A generic helper `def _validate[M: BaseModel](model: type[M], data: dict[str, Any], path: Path) -> M` (Python 3.12 syntax) avoids repeating the error handling.

Learnings that apply:
- pyright is `standard` for `packages/tl-sim`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format packages/tl-sim` and `uv run ruff check packages/tl-sim` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte (`cp`). Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T43.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. Always work from your worktree root and use `uv run`; never run Python from inside `packages/tl-sim/src/tl_sim`, where `types.py` would shadow the standard library.
- No new dependencies. ruff's autofix removed the unused imports of the stub; add the ones listed as *Imports to add*.
- `just test` is known red in `tests/api/test_client_roundtrip.py` (another workstream adds the feed methods to `ApiClient`). Any other failure is yours. Your acceptance is `uv run pytest packages/tl-sim -q` plus `just check`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-sim/src/tl_sim/scenario.py (existing, final; the types the loader returns)
class Scenario(Strict):
    scenario: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
    seed: int = Field(ge=0)
    start: date
    duration_days: int = Field(default=5, ge=1)  # working days `tl sim run` and `just seed` play
    working_days: list[Weekday] = ["mon", "tue", "wed", "thu", "fri"]
    template: str = Field(default="small-piping", pattern=r"^[a-z0-9][a-z0-9._-]*$")
    actors: ActorsConfig = ActorsConfig()
    inject: list[InjectSpec] = []

    @field_validator("working_days")
    @classmethod
    def _some_working_days(cls, value: list[Weekday]) -> list[Weekday]:
        if not value:
            raise ValueError("working_days must not be empty")
        return list(dict.fromkeys(value))

class Template(Strict):
    """The project that exists before day 0: areas and the piping lines in them."""

    template: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    description: str = ""
    areas: Annotated[list[AreaSpec], Field(min_length=1)]
    valve_sizes_in: list[float] = [2, 3, 4, 6, 8]
    manufacturers: list[str] = ["Crane", "Velan", "Emerson"]
    disciplines: list[str] = ["Piping", "Mechanical", "Civil", "Instrumentation"]
```

```python
# packages/tl-sim/src/tl_sim/scenario_loader.py (existing stub; keep MAX_BYTES, ScenarioError and the docstrings)
"""Scenario and template loading from YAML into ``tl_sim.scenario`` models.

Scenarios live in ``<seed dir>/scenarios/<name>.yaml`` and seed templates in
``<seed dir>/templates/<name>.yaml``. The seed directory is ``TL_SEED_DIR`` when set, else
``dev/seed`` in the repository. ``load_scenario`` also takes a path to any YAML file. Every failure
is a ``ScenarioError`` whose message names the file, so a CLI can print it as it is.
"""

from __future__ import annotations

from pathlib import Path

from tl_sim.scenario import Scenario, Template

MAX_BYTES = 256 * 1024


class ScenarioError(Exception):
    """A scenario or template file cannot be read or is invalid. The message names the file."""


def seed_dir() -> Path:
    """The directory holding ``scenarios/`` and ``templates/``: ``TL_SEED_DIR``, else dev/seed."""
    raise NotImplementedError("STUB (P0-I6-T43)")


def bundled_scenarios() -> list[str]:
    """Names of the scenario files in ``seed_dir()/scenarios``, sorted, without ``.yaml``."""
    raise NotImplementedError("STUB (P0-I6-T43)")


def load_scenario(source: str | Path) -> Scenario:
    """A scenario from a YAML path, or from a bundled name such as ``north-unit-small``."""
    raise NotImplementedError("STUB (P0-I6-T43)")


def load_template(name: str) -> Template:
    """The seed template ``seed_dir()/templates/<name>.yaml``."""
    raise NotImplementedError("STUB (P0-I6-T43)")
```


## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-sim/src/tl_sim/scenario_loader.py`
- `packages/tl-sim/src/tl_sim/scenario.py`
- `dev/seed/scenarios/north-unit-small.yaml`
- `dev/seed/templates/small-piping.yaml`
- `docs/tickets/P0-I6/provided/c-test_scenario_loader.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-sim/src/tl_sim/scenario_loader.py` (edit)
- `packages/tl-sim/tests/test_scenario_loader.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T43.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/c-test_scenario_loader.py.txt packages/tl-sim/tests/test_scenario_loader.py`
2. Implement the four functions, add the imports.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-sim -q
just check
```
Expected: 25 tests pass in the new file and the whole `packages/tl-sim` run stays green; `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the output of `uv run python -c "from tl_sim.scenario_loader import bundled_scenarios; print(bundled_scenarios())"` run from the repository root.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or if the provided test cannot pass without changing a file outside *Allowed paths*.
- Stop after two attempts at the same failing test.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
