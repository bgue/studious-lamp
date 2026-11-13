-- P2-I6-T02: one row per IWP.ReadinessEvaluated event (brief 28.2), read from bronze events only.
-- Columns: counts of checks by state, the sorted blocked check names, and changed (first row, or
-- ready or blocked_names differs from the IWP's previous row in the same scope, by seq).
-- Never selects detail, resolve_via or facts_hash.
WITH ev AS (
    SELECT
        scope,
        json_extract_string(payload, '$.iwp_id') AS iwp_id,
        seq,
        json_extract_string(payload, '$.evaluated_at') AS evaluated_at,
        TRY_CAST(json_extract_string(payload, '$.today') AS DATE) AS today,
        TRY_CAST(json_extract_string(payload, '$.ready') AS BOOLEAN) AS ready,
        from_json(json_extract(payload, '$.checks'), '[{"name":"VARCHAR","state":"VARCHAR"}]') AS checks
    FROM events
    WHERE event_type = 'IWP.ReadinessEvaluated'
),
counted AS (
    SELECT
        scope,
        iwp_id,
        seq,
        evaluated_at,
        today,
        ready,
        COALESCE(len(checks), 0) AS checks_total,
        COALESCE(len(list_filter(checks, c -> c.state = 'blocked')), 0) AS checks_blocked,
        COALESCE(len(list_filter(checks, c -> c.state = 'pending')), 0) AS checks_pending,
        COALESCE(
            array_to_string(
                list_sort(list_transform(list_filter(checks, c -> c.state = 'blocked'), c -> c.name)),
                ','
            ),
            ''
        ) AS blocked_names
    FROM ev
)
SELECT
    scope,
    iwp_id,
    seq,
    evaluated_at,
    today,
    ready,
    checks_total,
    checks_blocked,
    checks_pending,
    blocked_names,
    (LAG(seq) OVER w IS NULL)
        OR (ready IS DISTINCT FROM LAG(ready) OVER w)
        OR (blocked_names IS DISTINCT FROM LAG(blocked_names) OVER w) AS changed
FROM counted
WINDOW w AS (PARTITION BY scope, iwp_id ORDER BY seq)
