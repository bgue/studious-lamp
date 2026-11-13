-- P2-I6-T02: per row of mart_schedule_history, IWP readiness as of its data date (brief 28.2).
-- Counts the latest readiness evaluation per IWP in the same scope with today <= the data date.
-- ready_pct is 1 dp (NULL with no IWP); as_of_seq is the greatest seq counted (NULL with none).
WITH per_snapshot AS (
    SELECT
        s.scope,
        s.schedule_code,
        s.snapshot_number,
        r.iwp_id,
        r.seq,
        r.ready,
        ROW_NUMBER() OVER (
            PARTITION BY s.scope, s.schedule_code, s.snapshot_number, r.iwp_id
            ORDER BY r.seq DESC
        ) AS rn
    FROM mart_schedule_history s
    JOIN mart_iwp_readiness_history r
        ON r.scope = s.scope
        AND r.today <= CAST(s.data_date AS DATE)
),
latest AS (
    SELECT scope, schedule_code, snapshot_number, iwp_id, seq, ready
    FROM per_snapshot
    WHERE rn = 1
)
SELECT
    s.scope,
    s.schedule_code,
    s.snapshot_number,
    s.data_date,
    s.latest_early_finish,
    s.finish_slip_days,
    COUNT(l.iwp_id) AS iwps_evaluated,
    COUNT(l.iwp_id) FILTER (WHERE l.ready) AS iwps_ready,
    COUNT(l.iwp_id) FILTER (WHERE NOT l.ready) AS iwps_not_ready,
    CAST(ROUND(100.0 * COUNT(l.iwp_id) FILTER (WHERE l.ready) / NULLIF(COUNT(l.iwp_id), 0), 1) AS DOUBLE) AS ready_pct,
    MAX(l.seq) AS as_of_seq
FROM mart_schedule_history s
LEFT JOIN latest l
    ON l.scope = s.scope
    AND l.schedule_code = s.schedule_code
    AND l.snapshot_number = s.snapshot_number
GROUP BY s.scope, s.schedule_code, s.snapshot_number, s.data_date, s.latest_early_finish, s.finish_slip_days
