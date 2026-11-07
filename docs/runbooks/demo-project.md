# Runbook — build the demo project P200 and read it with the clients

Purpose: build the demo project P200 (North Refinery, Hydrotreater Unit 2 expansion) in a new ledger, then open it with the REST API and the TUI. The same project feeds the screenshot tour, the demos and the client walk-throughs. Plan: `docs/tickets/P2-SEED/README.md`.

## What it is
P200 is a brownfield industrial project with six areas (pipe rack, process unit, tank farm, utilities, substation and control room, tie-ins to the live plant), eight disciplines and four contractors. The generator writes its engineering tags, documents with revisions, correspondence, work packages and materials into one ledger. The build is deterministic: the same seed gives the same rows.

## When to use
- Trigger: you need a realistic, filled ledger to demonstrate or test a screen, a report or a client.
- Trigger: the tour or a demo reports missing P200 data (`just tour wave1` seeds from this project).

## Before you start
- Access needed: none beyond a checkout of the repository and `uv sync`. The generator writes a new ledger on your machine; it does not touch a shared database.
- The ledger is a SQLite file (default `dev/data/demo-project.db`) or a `postgresql://` URL (`docs/runbooks/run-on-postgres.md`). Do not paste a URL with a password into a ticket.
- Run it through `just demo-project`, not `python -m dev.seed.demo_project` directly: the recipe sets `TL_ENV=dev`, which the object store needs (the direct call stops with `TL_OBJECT_SECRET is not set`).
- The generator builds a fresh ledger each time. It refuses a ledger that already holds P200 and changes nothing in it.

## 1. Build it

```
just demo-project                                  # dev/data/demo-project.db
just demo-project /path/to/new-demo.db             # any new SQLite file
just demo-project <postgresql-url>                 # a Postgres URL (placeholder; see run-on-postgres.md)
just demo-project /path/to/other.db --seed 7       # another seed
```

The recipe takes a SQLite path or a `postgresql://` URL and passes any further flags to the generator. Flags:

| Flag | Meaning | Default |
|---|---|---|
| `--db` | SQLite path or `postgresql://` URL (the recipe sets it from its first argument) | `dev/data/demo-project.db` |
| `--seed` | seed of the random draws | `2026` |
| `--sections` | comma list of `core,engineering,documents,correspondence,awp,materials,quality` | all, in that order |
| `--objects` | directory of the file store | `TL_OBJECT_ROOT` |

Expected output: one line per section (`engineering: 434 records, 868 events, 5.3s`), a summary table, and a last line that says clients read the ledger with `TL_SCHEMA_DIR=dev/data/demo-project-schema`. The final `total` row for the default build is about 2034 records and 7965 events. A section whose record types are not installed prints `quality: skipped, quality.PunchItem not installed` and the build continues.

Checks:
- Run the same command on the same file again. Expected: `error: ... already holds project P200; use a new database`, and the recipe exits 1. Use a new file name.
- `--sections core,engineering` builds only those two sections (about 9 seconds). A section can depend on the records of the sections before it: `--sections core,awp` fails with `the discipline is not a value of the code list Discipline`. When you pick a subset, keep the earlier sections it builds on. Use the default when unsure.

## 2. Read it with the clients

Clients of the demo ledger need the P200 working calendar, which lives in the overlay directory the generator builds:

```
TL_SCHEMA_DIR=dev/data/demo-project-schema
```

API (REST and SSE) on the demo ledger:

```
TL_DB=dev/data/demo-project.db TL_SCHEMA_DIR=dev/data/demo-project-schema just serve
curl -s localhost:8765/health
```

Expected: `{"status":"ok"}`. Use `just serve --port 9000` for another port. Creating a token for the API is in `docs/runbooks/api-and-mcp-dev.md`.

TUI on the demo ledger. The command is the one the `just tui` recipe runs (`uv run python -m tl_tui`, `justfile` lines 66–68), with the demo ledger's variables set. The TUI reads them as `TL_DB` and `TL_PROJECT` (`packages/tl-tui/src/tl_tui/main.py`). `TL_ENV=dev` is the default `justfile` line 6 exports.

```
TL_ENV=dev TL_DB=dev/data/demo-project.db TL_SCHEMA_DIR=dev/data/demo-project-schema TL_PROJECT=P200 uv run python -m tl_tui
```

Not run as a launch: the TUI is interactive. Its flags were checked with `uv run python -m tl_tui --help`, which exits 0. Do not use `just tui` on this ledger: that recipe first runs `tl init --dev` on the ledger it is given.

The sign-in screen asks for a username and password from the table in section 3. Keys and screens are in `docs/runbooks/tui-dev.md`.

## 3. The people

Every demo account has the same password, `p200-demo-pass`. It is demo data only; never use it on a real ledger.

| Username | Name | Job | Notes |
|---|---|---|---|
| `mokafor` | Marta Okafor | Project administrator | admin role |
| `ipetrov` | Ivan Petrov | Document controller | document controller role |
| `lhartmann` | Lena Hartmann | Project engineer | awp user |
| `treyes` | Tomas Reyes | Materials coordinator | materials superuser, awp user |
| `cbrooks` | Callum Brooks | Foreman, piping | awp user |
| `pnair` | Priya Nair | Foreman, civil | awp user |
| `hsato` | Hana Sato | Quality inspector | |
| `odoyle` | Owen Doyle | RFI author | |
| `gwhitfield` | Grace Whitfield | Client representative (read only) | viewer on every module |

## 4. Volumes

| Module | Volume |
|---|---|
| Engineering | 300+ tags over the areas |
| Documents | 80+ documents with revisions, some superseded |
| Correspondence | 30+ RFIs plus letters and transmittals, some overdue |
| Work packaging | 40–60 CWPs, a WBS of about 100 nodes, 12 CWAs, a path of construction with two versions |
| Materials | 150+ items, 150–250 stock lots, 300+ movements, 40–60 receipts (some without MTR), 150 take-off lines with real shortages |
| Quality | punch items, switched on when the record type is installed |

## 5. The fixed names

Some records have fixed numbers so that drawings, fixtures and checks can name them. The generator never reuses these numbers for other records.

- Tags: `200-V-1027`, `300-T-101`.
- Documents: `P200-200-PID-4701` (restricted), `P200-200-PID-4702` (with a superseded revision).

Source: `dev/seed/demo_project/anchors.py`.

## 6. Determinism

Two builds with the same seed on fresh ledgers give the same rows. The test compares the record counts and a hash of the sorted keys per record type. The keys of `documents.ProcessingJob` (machine ids, `JOB-<ulid>`) are random, so they are left out of the key hash; their count is still compared. Test: `tests/tools/test_demo_project.py`.

## 7. The tour

The screenshot tour uses this project:

```
just tour wave1
```

It writes to `docs/reports/tour/wave1`. The tour seeds its own ledger from the generator, so it does not need a ledger you built in section 1.

## 8. Extending the project

- To add a section, write a module in `dev/seed/demo_project/` with a build function that takes the world and its own random generator.
- Register it in `SECTIONS` in `dev/seed/demo_project/registry.py` with the record types it needs. Keep the section name in `ORDER` in the same file.
- A section whose record types are not installed is skipped with one line; the build does not fail.
- The `quality` section is in the package but is skipped until `quality.PunchItem` is installed. Quality is the next section to switch on.
- Add a test in `tests/tools/` next to the existing `test_demo_project*.py` files.
