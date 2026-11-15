CREATE VIEW IF NOT EXISTS v_permits_isolation AS
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
  t.point_text AS point_text,
  t.point_record_id AS point_record_id,
  t.energy AS energy,
  t.method AS method,
  t.lock_number AS lock_number,
  t.tag_number AS tag_number,
  t.applied_by AS applied_by,
  t.applied_at AS applied_at,
  t.verified_by AS verified_by,
  t.verified_at AS verified_at,
  t.removed_by AS removed_by,
  t.removed_at AS removed_at
FROM cur_permits_isolation AS t
JOIN cur_core_record AS r ON r.id = t.id;
