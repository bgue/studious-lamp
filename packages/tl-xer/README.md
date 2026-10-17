# tl-xer (`tl_xer`)

A security-reviewed reader of Primavera P6 XER files, which are untrusted input: it tokenises, validates against the XER document schema and types a schedule, in the resource envelope (§9 M11, ADR-0015 §2 and §3).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_xer.run.read_xer_file` | function | The entry for callers: reads bytes in the envelope (child process, scrubbed environment, memory/CPU/wall-clock limits) and returns an `XerResult`. Raises only `XerLimitError` |
| `tl_xer.result.XerResult` / `XerLimitError` | class | The status, the report, the typed snapshot, the raw bundle and the hashes; the one exception (fixed text) |
| `tl_xer.process.process` | function | The pure step the envelope runs: bytes to an `Outcome`. A function of the bytes alone |
| `tl_xer.reader.read_xer` | function | Bytes to raw tables (encoding decision, markers, bounds) |
| `tl_xer.typed` | module | `analyse` (the XER document schema checks), `Options`, `Snapshot`, `parse_date`, `parse_number` |
| `tl_xer.problems` | module | The report's problems: a code, a place and a fixed message |
| `tl_xer.bundle` | module | The raw bundle (every table verbatim, batched JSON lines in gzip): `write_bundle`, `verify_bundle`, `read_bundle` |
| `tl_xer.wire` | module | `decode`: the checks the parent makes on the child's answer before a result exists |
| `tl_xer.limits` | module | Every bound in one place, with `answer_bound` |
| `tl_xer.synth` | module | Synthetic P6 schedules as XER bytes (`make_xer`, `week_pair`, `slipped`) for tests, the demo and the simulated planner |

## Depends on / used by
- Depends on: `tl_core` (the envelope `tl_core.derivation.envelope`). Standard library only otherwise: no PyPI XER library.
- Used by: `tl_mod_schedule` (the build job), `tl_cli` (demo), `tl_sim` (the planner).

## Commands
```
just test -- packages/tl-xer
uv run pytest packages/tl-xer/tests/test_largest.py -q   # the worst legal files: seconds and megabytes
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `timeout_s` of `read_xer_file` | 60 s | Wall clock of the child |
| `memory_limit_mb` | 1024 | Address space of the child |
| `Options.project` | none | The P6 project to read when a file holds several |

The bounds (50 MiB, 300 tables, 200 columns, 400 000 rows per table, 1 200 000 rows, 20 million weighted cells, 32 000 characters per field, 60 000 activities, 200 000 relationships, dates 1990 to 2100) are in `limits.py` and ADR-0015 §2. Over a bound the file is refused, never cut.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I4. Last interface change: P1-I4 (ADR-0015).
