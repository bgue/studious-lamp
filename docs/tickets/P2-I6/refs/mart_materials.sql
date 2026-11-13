WITH moved AS (
    SELECT
        scope,
        substr(recorded_at, 1, 7) AS period,
        kind,
        COUNT(*) AS movements,
        COUNT(DISTINCT lot_id) AS lots,
        CAST(SUM(qty) AS DOUBLE) AS qty,
        COUNT(DISTINCT cost_code_id) AS cost_codes
    FROM cur_materials_movement
    GROUP BY scope, substr(recorded_at, 1, 7), kind
),
stocked AS (
    SELECT
        scope,
        CAST(SUM(on_hand) AS DOUBLE) AS on_hand_now,
        COUNT(DISTINCT lot_id) AS lots_in_stock_now
    FROM cur_materials_stock
    GROUP BY scope
)
SELECT
    m.scope, m.period, m.kind, m.movements, m.lots, m.qty, m.cost_codes,
    COALESCE(s.on_hand_now, 0.0) AS on_hand_now,
    COALESCE(s.lots_in_stock_now, 0) AS lots_in_stock_now
FROM moved m
LEFT JOIN stocked s ON s.scope = m.scope
ORDER BY m.scope, m.period, m.kind
