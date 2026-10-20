# P1-I8-T08 — Lake marts: documents and schedule history

Status: ready
Tier: haiku
Labels: lake
Depends on: P1-I8-S1 to S2 on `p1/i8` (the stubs are in the tree); no other ticket
Branch: `p1/i8-t08-lake-marts`

## Goal
The lake gets the two gold marts of this increment. `packages/tl-lake/src/tl_lake/doc_marts.py` is new and holds `build_document_marts(con)`, which builds `mart_document_status`, `mart_document_turnaround` and `mart_document_issues` from the silver tables of documents and revisions. `packages/tl-lake/src/tl_lake/xer_marts.py` gains `build_schedule_history(con)`, which builds `mart_schedule_history` (one row per published schedule snapshot, with the slip of the project finish against the snapshot before it and the activities added and removed) from the silver schedule tables. Both functions raise `NotImplementedError` today. You write them by the STEPS comments so two provided test files pass. The supervisor wires them into the sync and the XER pass at the merge; you do not touch `sync.py`, `xer.py` or `schema.py`.

## Brief references (pasted)
> **Brief 28.2 (layers).** *Gold (marts)*: progress by cost code and period; weld/NDE statistics; IWP readiness history; completions burn-down; **schedule trend (float erosion, slip by activity across XER snapshots)**; commercial exposure; data conformance; cross-project benchmarks. *Source: SQL models over silver (versioned in repo, tested).* **Brief 28.4 (uses).** Heavy reports and dashboards (moved off the transactional database); schedule analytics from XER snapshot history (P6 never needs to be queried directly); cross-project benchmarking (RFI turnaround, punch closure, ...).
>
> **ADR-0016 (confidentiality) as it reaches the lake.** The lake is read by every user and by agents. Silver holds only records the lowest reader may read (a restricted or privileged document is not in it), so a mart built from silver holds none of them, in a row or in a count. That is why the marts read silver only and never the ledger.

### Specification
- A mart is a table rebuilt whole: `DROP TABLE IF EXISTS` then `CREATE TABLE ... AS SELECT`. Two builds of the same silver give the same rows.
- Table names are fully qualified with `table_ref(name)` (it gives `lake.main."name"`). DuckDB is the engine: `TRY_CAST`, `DATE_DIFF('day', from, to)`, `LAG(...) OVER (...)` and `COUNT(*) FILTER (WHERE ...)` work. The lake is a DuckLake catalog, so keep statements simple and do not create views or indexes.
- Column names and the order of columns are what the tests read with `SELECT *`; keep them exactly as in the docstrings.
- Silver tables may be missing (a ledger with no documents module, no schedule): `build_document_marts` returns after dropping the marts. `build_schedule_history` is only called when the schedule tables exist.

### Learnings that apply
> **L-P1-I7A-11.** The stubs are not wired into the sync while they raise: the supervisor adds the calls at the merge. Do not wire them.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports, so `doc_marts.py` carries `# ruff: noqa: F401` and a `# pyright: reportUnusedImport=false, ...` line. Remove both with the STEPS comments when the body is written, and remove every import the finished file does not use.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes: run it with a 600 000 ms timeout (or in the background and wait). Run `uv run ruff format <file>` first.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-lake/src/tl_lake/doc_marts.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false
"""The document marts of the lake (P1-I8-T08; brief 28.2 gold, 28.4 uses).

STUB: this file is the interface P1-I8-T08 implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.

Marts are rebuilt from silver whenever the document tables changed, so a mart never disagrees with
the silver it came from. Silver already holds only the documents and revisions the lowest reader
may read (``tl_lake.sync``, ADR-0016), so a mart holds none of the others, in a row or in a count.

* ``mart_document_status``: one row per project, discipline, document type and current revision
  status: how many documents, and the first and last issue date among them.
* ``mart_document_turnaround``: one row per project and discipline: documents with an issued
  revision, issued revisions, the average and the longest gap in days between a document's
  consecutive issued revisions.
* ``mart_document_issues``: one row per project and month: revisions issued and documents involved.

Voided documents are in none of them. No document at all means no mart (and a stale one is dropped).
"""

from __future__ import annotations

from tl_lake.duck import Duck, lake_tables, table_ref

DOCUMENT_TABLE = "cur_documents_document"
REVISION_TABLE = "cur_documents_revision"
RECORD_TABLE = "cur_core_record"
STATUS_TABLE = "mart_document_status"
TURNAROUND_TABLE = "mart_document_turnaround"
ISSUES_TABLE = "mart_document_issues"
MARTS = (STATUS_TABLE, TURNAROUND_TABLE, ISSUES_TABLE)


def build_document_marts(con: Duck) -> None:
    """Replace the three document marts from the silver tables of the lake.

    Silver columns the SQL may use: ``cur_core_record`` (``id``, ``voided``);
    ``cur_documents_document`` (``id``, ``scope``, ``discipline``, ``doc_type``,
    ``current_revision_status``, ``current_revision_issued_on``); ``cur_documents_revision``
    (``id``, ``scope``, ``document_id``, ``ordinal``, ``issued_on``). All text is VARCHAR; the
    issue dates are text that starts ``YYYY-MM-DD`` or is empty or is not a date at all.
    """
    # STEPS
    # 1. DROP TABLE IF EXISTS for each name in MARTS (use table_ref(name)).
    # 2. Stop (return) when lake_tables(con) lacks any of DOCUMENT_TABLE, REVISION_TABLE or
    #    RECORD_TABLE, or when the document table has no row (SELECT count(*)).
    # 3. mart_document_status: CREATE TABLE ... AS SELECT d.scope, COALESCE(d.discipline, '-') AS
    #    discipline, COALESCE(d.doc_type, '-') AS doc_type, COALESCE(d.current_revision_status,
    #    '-') AS status, COUNT(*) AS documents, MIN(NULLIF(d.current_revision_issued_on, '')) AS
    #    first_issued_on, MAX(NULLIF(...)) AS last_issued_on FROM document d JOIN record r ON
    #    r.id = d.id WHERE NOT r.voided, grouped by scope and the three COALESCE expressions,
    #    ordered by scope, discipline, doc_type, status.
    # 4. mart_document_turnaround: a CTE `issued` of revisions rv joined to their document d (on
    #    d.id = rv.document_id) and its record r (not voided) where the issue date
    #    TRY_CAST(SUBSTR(rv.issued_on, 1, 10) AS DATE) is not NULL (columns scope = rv.scope,
    #    discipline = COALESCE(d.discipline, '-'), document_id, ordinal, issued_date); a CTE `gaps`
    #    with gap_days = DATE_DIFF('day', LAG(issued_date) OVER (PARTITION BY document_id ORDER
    #    BY ordinal), issued_date); then SELECT scope, discipline, COUNT(DISTINCT document_id) AS
    #    documents, COUNT(*) AS issued_revisions, ROUND(AVG(gap_days), 1) AS
    #    avg_days_between_issues, MAX(gap_days) AS longest_gap_days GROUP BY scope, discipline
    #    ORDER BY scope, discipline.
    # 5. mart_document_issues: SELECT rv.scope, SUBSTR(rv.issued_on, 1, 7) AS month, COUNT(*) AS
    #    revisions_issued, COUNT(DISTINCT rv.document_id) AS documents over the same join and
    #    filter as step 4, grouped by scope and month, ordered by scope, month.
    raise NotImplementedError("STEPS: see the comments")
```

`packages/tl-lake/src/tl_lake/xer_marts.py` (the whole file; you complete `build_schedule_history`, the rest stays as it is):
```python
"""The marts built from the schedule tables of the lake (P1-I4; brief 28).

A mart is a table rebuilt from silver whenever the schedule tables changed (``tl_lake.xer`` calls
``build_marts`` inside its transaction), so it never disagrees with the silver it came from.

* ``mart_float_trend``: one row per activity per published snapshot (Published or Superseded: the
  history a planner reads), oldest data date first, with the float of the snapshot before it and
  the change in days (negative: erosion).
"""

from __future__ import annotations

from tl_lake.duck import Duck, table_ref

FLOAT_TREND_TABLE = "mart_float_trend"
SCHEDULE_HISTORY_TABLE = "mart_schedule_history"


def build_marts(con: Duck) -> None:
    """Rebuild every mart from the silver schedule tables."""
    build_float_trend(con)


def build_float_trend(con: Duck) -> None:
    """Replace ``mart_float_trend``.

    Columns: ``scope`` (the project: two may both have a schedule ``MAIN``), ``schedule_code``,
    ``activity_id``, ``name``, ``snapshot_number``, ``data_date``, ``state``,
    ``total_float_days``, ``previous_float_days``, ``float_change_days``, ``eroded``, ``critical``,
    ``status``, ``percent_complete``, ``early_start``, ``early_finish``. The previous
    float is that of the activity in the published snapshot before this one (``NULL`` for the
    first, or when the activity was not in it), and ``eroded`` is true when the change is below
    zero.
    """
    con.execute(f"DROP TABLE IF EXISTS {table_ref(FLOAT_TREND_TABLE)}")
    con.execute(
        f"""
        CREATE TABLE {table_ref(FLOAT_TREND_TABLE)} AS
        SELECT
            a.scope,
            a.schedule_code,
            a.activity_id,
            a.name,
            a.snapshot_number,
            a.data_date,
            s.state,
            a.total_float_days,
            LAG(a.total_float_days) OVER w AS previous_float_days,
            ROUND(a.total_float_days - LAG(a.total_float_days) OVER w, 2) AS float_change_days,
            COALESCE(a.total_float_days - LAG(a.total_float_days) OVER w < 0, FALSE) AS eroded,
            a.critical,
            a.status,
            a.percent_complete,
            a.early_start,
            a.early_finish
        FROM {table_ref("schedule_activity")} a
        JOIN {table_ref("schedule_snapshot")} s ON s.snapshot_id = a.snapshot_id
        WHERE s.state IN ('Published', 'Superseded')
        WINDOW w AS (
            PARTITION BY a.scope, a.schedule_code, a.activity_id ORDER BY a.snapshot_number
        )
        ORDER BY a.scope, a.schedule_code, a.activity_id, a.snapshot_number
        """
    )


def build_schedule_history(con: Duck) -> None:
    """Replace ``mart_schedule_history`` (P1-I8-T08; STUB until the ticket merges).

    One row per published snapshot (Published or Superseded) of a schedule, oldest first, with
    columns ``scope``, ``schedule_code``, ``snapshot_number``, ``data_date``, ``state``,
    ``activities``, ``critical_activities``, ``complete_activities`` (percent complete at 100 or
    more), ``avg_percent_complete`` (one decimal), ``latest_early_finish`` (the project finish as
    the latest early finish of its activities), ``finish_slip_days`` (days that finish moved
    against the snapshot before; positive is later; NULL for the first), ``activities_added`` and
    ``activities_removed`` (activity ids that are not in the snapshot before / that are not in this
    one; NULL for the first). A snapshot without activity rows is left out.

    Silver columns the SQL may use: ``schedule_snapshot`` (``snapshot_id``, ``scope``,
    ``schedule_code``, ``number``, ``state``, ``data_date``); ``schedule_activity``
    (``snapshot_id``, ``activity_id``, ``critical``, ``percent_complete``, ``early_finish``).
    """
    # STEPS
    # 1. DROP TABLE IF EXISTS the mart (table_ref(SCHEDULE_HISTORY_TABLE)).
    # 2. CREATE TABLE ... AS with a CTE `counts` (per snapshot_id of schedule_activity: COUNT(*) AS
    #    activities, COUNT(*) FILTER (WHERE critical) AS critical_activities, COUNT(*) FILTER
    #    (WHERE percent_complete >= 100) AS complete_activities, ROUND(AVG(percent_complete), 1) AS
    #    avg_percent_complete, MAX(early_finish) AS latest_early_finish) and a CTE `series`
    #    (published snapshots joined to counts, with LAG(snapshot_id) and LAG(latest_early_finish)
    #    over a window partitioned by scope and schedule_code ordered by number; the WHERE on state
    #    comes before the window, so a Void snapshot between two published ones is skipped).
    # 3. The final SELECT adds finish_slip_days = DATE_DIFF('day', previous_finish,
    #    latest_early_finish), and activities_added / activities_removed as correlated COUNT(*)
    #    subqueries with NOT EXISTS against the previous snapshot (NULL when there is none), and is
    #    ordered by scope, schedule_code, snapshot_number.
    raise NotImplementedError("STEPS: see the comments")
```

From `tl_lake.duck` (read-only): `Duck` is the DuckDB connection type; `table_ref(name) -> str`; `lake_tables(con) -> dict[str, list[tuple[str, str]]]` (table name to `(column, type)` pairs).

## Context (read these, nothing else)
- `packages/tl-lake/src/tl_lake/doc_marts.py`
- `packages/tl-lake/src/tl_lake/xer_marts.py`
- `docs/tickets/P1-I8/provided/t08a-test_doc_marts.py.txt`
- `docs/tickets/P1-I8/provided/t08b-test_schedule_history_mart.py.txt`
- `packages/tl-lake/src/tl_lake/duck.py` (`table_ref`, `lake_tables`, `open_lake`; do not edit)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-lake/src/tl_lake/doc_marts.py` (modify)
- `packages/tl-lake/src/tl_lake/xer_marts.py` (modify: only `build_schedule_history`)
- `packages/tl-lake/tests/test_doc_marts.py` (create: a byte-for-byte copy of the provided file)
- `packages/tl-lake/tests/test_schedule_history_mart.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T08.md` (create: your report; commit it)

## Steps
1. Copy the two provided tests to the paths above. Do not edit the copies (they are ruff-clean and pyright-clean as provided).
2. Run them once; they fail against the stubs.
3. Implement the two functions by their STEPS. Remove the STUB paragraph and the two directive lines of `doc_marts.py`, every STEPS comment, and the `raise NotImplementedError` lines. Remove unused imports.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-lake
uv run pytest packages/tl-lake/tests/test_doc_marts.py packages/tl-lake/tests/test_schedule_history_mart.py -q
uv run pytest packages/tl-lake/tests/test_xer.py -q
just check
```
Expected: `22 passed` for the two provided files (13 and 9 test functions); the existing XER tests still pass (the function you add is not called by them); `just check` is clean (run it with a 600 000 ms timeout).

## Tests to add
None beyond the provided files. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided files.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T08.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
