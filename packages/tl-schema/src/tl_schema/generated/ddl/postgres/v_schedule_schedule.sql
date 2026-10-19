CREATE OR REPLACE VIEW v_schedule_schedule AS
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
  t.code AS code,
  t.schedule_type AS schedule_type,
  t.owner AS owner,
  t.p6_project AS p6_project,
  t.current_snapshot_id AS current_snapshot_id,
  t.current_snapshot_number AS current_snapshot_number,
  t.current_data_date AS current_data_date
FROM cur_schedule_schedule AS t
JOIN cur_core_record AS r ON r.id = t.id;
