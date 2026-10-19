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
