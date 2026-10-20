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
