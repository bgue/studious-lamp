-- P2-I6-T02: movements per scope, month (YYYY-MM of recorded_at) and kind, with the scope's
-- stock today from cur_materials_stock (on_hand_now; lots_in_stock_now counts lots with on_hand > 0).
-- Reads silver only; silver holds readable rows only (brief 28.2).
WITH mv AS (
    SELECT
        scope,
        strftime(CAST(recorded_at AS TIMESTAMP), '%Y-%m') AS period,
        kind,
        lot_id,
        cost_code_id,
        qty
    FROM cur_materials_movement
),
grp AS (
    SELECT
        scope,
        period,
        kind,
        COUNT(*) AS movements,
        COUNT(DISTINCT lot_id) AS lots,
        SUM(qty) AS qty,
        COUNT(DISTINCT cost_code_id) AS cost_codes
    FROM mv
    GROUP BY scope, period, kind
),
stock AS (
    SELECT
        scope,
        SUM(on_hand) AS on_hand_now,
        COUNT(DISTINCT lot_id) FILTER (WHERE on_hand > 0) AS lots_in_stock_now
    FROM cur_materials_stock
    GROUP BY scope
)
SELECT
    g.scope,
    g.period,
    g.kind,
    g.movements,
    g.lots,
    g.qty,
    g.cost_codes,
    COALESCE(s.on_hand_now, 0.0) AS on_hand_now,
    COALESCE(s.lots_in_stock_now, 0) AS lots_in_stock_now
FROM grp g
LEFT JOIN stock s ON s.scope = g.scope
