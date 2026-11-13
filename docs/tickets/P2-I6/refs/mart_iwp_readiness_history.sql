WITH evaluated AS (
    SELECT
        e.scope,
        json_extract_string(e.payload, '$.iwp_id') AS iwp_id,
        e.seq,
        json_extract_string(e.payload, '$.evaluated_at') AS evaluated_at,
        CAST(json_extract_string(e.payload, '$.today') AS DATE) AS today,
        CAST(json_extract(e.payload, '$.ready') AS BOOLEAN) AS ready,
        CAST(json_extract(e.payload, '$.checks') AS JSON[]) AS checks
    FROM events e
    WHERE e.event_type = 'IWP.ReadinessEvaluated'
),
counted AS (
    SELECT
        scope, iwp_id, seq, evaluated_at, today, ready,
        len(checks) AS checks_total,
        len(list_filter(checks, c -> json_extract_string(c, '$.state') = 'blocked'))
            AS checks_blocked,
        len(list_filter(checks, c -> json_extract_string(c, '$.state') = 'pending'))
            AS checks_pending,
        COALESCE(
            list_aggregate(
                list_sort(
                    list_transform(
                        list_filter(checks, c -> json_extract_string(c, '$.state') = 'blocked'),
                        c -> json_extract_string(c, '$.name')
                    )
                ),
                'string_agg', ','
            ),
            ''
        ) AS blocked_names
    FROM evaluated
)
SELECT
    scope, iwp_id, seq, evaluated_at, today, ready,
    checks_total, checks_blocked, checks_pending, blocked_names,
    (
        LAG(seq) OVER w IS NULL
        OR ready IS DISTINCT FROM LAG(ready) OVER w
        OR blocked_names IS DISTINCT FROM LAG(blocked_names) OVER w
    ) AS changed
FROM counted
WINDOW w AS (PARTITION BY iwp_id ORDER BY seq)
ORDER BY iwp_id, seq
