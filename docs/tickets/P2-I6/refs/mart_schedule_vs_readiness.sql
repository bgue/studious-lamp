WITH pairs AS (
    SELECT
        h.scope, h.schedule_code, h.snapshot_number,
        r.iwp_id, r.seq, r.ready
    FROM mart_schedule_history h
    JOIN mart_iwp_readiness_history r
      ON r.scope = h.scope AND r.today <= CAST(h.data_date AS DATE)
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY h.scope, h.schedule_code, h.snapshot_number, r.iwp_id ORDER BY r.seq DESC
    ) = 1
),
counted AS (
    SELECT
        scope, schedule_code, snapshot_number,
        COUNT(*) AS iwps_evaluated,
        COUNT(*) FILTER (WHERE ready) AS iwps_ready,
        COUNT(*) FILTER (WHERE NOT ready) AS iwps_not_ready,
        MAX(seq) AS as_of_seq
    FROM pairs
    GROUP BY scope, schedule_code, snapshot_number
)
SELECT
    h.scope, h.schedule_code, h.snapshot_number, h.data_date, h.latest_early_finish,
    h.finish_slip_days,
    COALESCE(c.iwps_evaluated, 0) AS iwps_evaluated,
    COALESCE(c.iwps_ready, 0) AS iwps_ready,
    COALESCE(c.iwps_not_ready, 0) AS iwps_not_ready,
    CASE WHEN c.iwps_evaluated > 0
         THEN ROUND(100.0 * c.iwps_ready / c.iwps_evaluated, 1) END AS ready_pct,
    c.as_of_seq
FROM mart_schedule_history h
LEFT JOIN counted c
  ON c.scope = h.scope AND c.schedule_code = h.schedule_code
 AND c.snapshot_number = h.snapshot_number
ORDER BY h.scope, h.schedule_code, h.snapshot_number
