CREATE VIEW IF NOT EXISTS v_awp_weekly_plan AS
SELECT
  r.id AS id,
  r.key AS key,
  r.type AS record_type,
  r.scope AS scope,
  r.title AS title,
  r.description AS description,
  r.status AS status,
  r.voided AS voided,
  r.version AS version,
  r.conformance AS conformance,
  r.psets_json AS psets_json,
  r.created_at AS created_at,
  r.updated_at AS updated_at,
  t.week AS week,
  t.week_start AS week_start,
  t.ppc AS ppc,
  t.closed_at AS closed_at
FROM cur_awp_weekly_plan AS t
JOIN cur_core_record AS r ON r.id = t.id;
