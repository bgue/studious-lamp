CREATE VIEW IF NOT EXISTS v_schedule_activity_ref AS
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
  t.schedule_id AS schedule_id,
  t.schedule_code AS schedule_code,
  t.activity_id AS activity_id,
  t.first_snapshot_id AS first_snapshot_id,
  t.first_snapshot_number AS first_snapshot_number,
  t.present AS present,
  t.last_seen_snapshot_id AS last_seen_snapshot_id,
  t.last_seen_number AS last_seen_number
FROM cur_schedule_activity_ref AS t
JOIN cur_core_record AS r ON r.id = t.id;
