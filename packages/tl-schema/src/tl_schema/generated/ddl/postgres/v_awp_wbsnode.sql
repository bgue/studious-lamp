CREATE OR REPLACE VIEW v_awp_wbsnode AS
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
  t.parent_id AS parent_id,
  t.depth AS depth,
  t.position AS position,
  t.retired AS retired
FROM cur_awp_wbs_node AS t
JOIN cur_core_record AS r ON r.id = t.id;
