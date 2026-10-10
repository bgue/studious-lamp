# tl-sim (`tl_sim`)

A deterministic simulated project team that plays working days against a running suite through its public API (and MCP for proposals), keeps a ground-truth log of what it intended, and checks the suite against that log (§29.5, FANOUT D5, D6).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_sim.api.sim_create(env, scenario, run_id=None)` | function | Create a run (`project:sim-<run_id>`, `source=sim:<run_id>`), mint actor tokens, write the template's areas and lines |
| `tl_sim.api.sim_advance(env, run_id=None, days=1)` | function | Play working days; each actor acts in its own time slot |
| `tl_sim.api.sim_inject(env, run_id, event, args)` | function | Queue `material_late`, `design_revision` or `post` for the next day played |
| `tl_sim.api.sim_status(env, run_id=None)` | function | Day, next date, ground-truth counts by intent and its SHA-256 digest |
| `tl_sim.api.sim_assert(env, run_id=None)` | function | Compare the log with the suite (records, psets, links, workflow state, posts, proposals, event sources and times); returns `ok` and the failures |
| `tl_sim.types` | module | The frozen `SimClient`, `SimContext`, `GroundTruth` and `Actor` interface |
| `tl_sim.orchestrator.Simulation` | class | The loop behind the five operations, over a `Connector` |
| `tl_sim.client.HttpSimClient` | class | `SimClient` over `ApiClient`, MCP and the simulated clock |
| `tl_sim.actors` | package | `BaseActor`, `Recorder`, and the document controller, planner and crew |
| `tl_sim.scenario_loader.load_scenario(source)` | function | A scenario from YAML (`dev/seed/scenarios`) |
| `tl_sim.testing.FakeWorld` | class | An in-memory suite for tests |
| `tl sim ...` | CLI | The five operations plus `run` and `seed` (see Commands) |

## Depends on / used by
- Depends on: `tl_api` (client, dev tokens), `tl_core` (command models and error classes only), `mcp`, `pyyaml`, `typer`.
- Used by: `tl_cli` (the `tl sim` group), `just seed`, `just demo P0-I6-C`, the P0-I6 demo.

## Commands
```
just serve                                   # the API the simulator talks to (separate terminal)
uv run tl sim create north-unit-small        # run id printed, e.g. r3fa91c
uv run tl sim advance --days 1
uv run tl sim assert                         # exit 1 when the suite differs from the log
just seed xs                                 # a synthetic project in the dev ledger
just test -- packages/tl-sim
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_SIM_DIR` | `./dev/data/sim` | One directory per run: `run.json` (0600, holds dev tokens) and `ground_truth.ndjson` |
| `TL_API_URL` | `http://127.0.0.1:8765` | The running API |
| `TL_TOKENS` | `./dev/data/tokens.json` | The token file the API reads; `sim_create` adds one token per simulated actor |
| `TL_SEED_DIR` | `dev/seed` in the repository | `scenarios/*.yaml` and `templates/*.yaml` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I6 (workstream C). Simulator v0 has no LLM role agents and writes proposals only once the proposals service is wired.
