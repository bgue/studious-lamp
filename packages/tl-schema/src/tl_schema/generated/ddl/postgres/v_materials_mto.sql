CREATE OR REPLACE VIEW v_materials_mto AS
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
  t.derived_document_id AS derived_document_id,
  t.revision_id AS revision_id,
  t.line_count AS line_count
FROM cur_materials_mto AS t
JOIN cur_core_record AS r ON r.id = t.id;
