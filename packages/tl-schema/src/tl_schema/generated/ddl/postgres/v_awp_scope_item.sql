CREATE OR REPLACE VIEW v_awp_scope_item AS
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
  t.commodity AS commodity,
  t.description_text AS description_text,
  t.qty AS qty,
  t.uom AS uom,
  t.est_hours AS est_hours,
  t.cwp_id AS cwp_id
FROM cur_awp_scope_item AS t
JOIN cur_core_record AS r ON r.id = t.id;
