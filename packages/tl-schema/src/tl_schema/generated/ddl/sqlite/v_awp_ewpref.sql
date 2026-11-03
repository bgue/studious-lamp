CREATE VIEW IF NOT EXISTS v_awp_ewpref AS
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
  t.package_no AS package_no,
  t.status_text AS status_text,
  t.forecast_date AS forecast_date,
  t.actual_date AS actual_date,
  t.constraint_source AS constraint_source,
  t.source_system AS source_system
FROM cur_awp_ewp_ref AS t
JOIN cur_core_record AS r ON r.id = t.id;
