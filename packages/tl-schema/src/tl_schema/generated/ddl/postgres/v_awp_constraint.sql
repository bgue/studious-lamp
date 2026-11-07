CREATE OR REPLACE VIEW v_awp_constraint AS
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
  t.constraint_type AS constraint_type,
  t.source AS source,
  t.owner AS owner,
  t.need_by AS need_by,
  t.description_text AS description_text,
  t.check_name AS check_name,
  t.raised_at AS raised_at,
  t.cleared_at AS cleared_at,
  t.cleared_by AS cleared_by,
  t.clear_reason AS clear_reason,
  t.suppress_hash AS suppress_hash
FROM cur_awp_constraint AS t
JOIN cur_core_record AS r ON r.id = t.id;
