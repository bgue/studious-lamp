CREATE VIEW IF NOT EXISTS v_awp_iwpcloseout AS
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
  t.iwp_id AS iwp_id,
  t.actual_hours AS actual_hours,
  t.remaining_punch AS remaining_punch,
  t.feedback AS feedback,
  t.actuals_file_id AS actuals_file_id
FROM cur_awp_iwp_closeout AS t
JOIN cur_core_record AS r ON r.id = t.id;
