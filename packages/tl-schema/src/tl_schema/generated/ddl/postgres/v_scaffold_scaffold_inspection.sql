CREATE OR REPLACE VIEW v_scaffold_scaffold_inspection AS
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
  t.scaffold_id AS scaffold_id,
  t.inspector AS inspector,
  t.inspected_on AS inspected_on,
  t.result AS result,
  t.tag AS tag,
  t.note AS note
FROM cur_scaffold_scaffold_inspection AS t
JOIN cur_core_record AS r ON r.id = t.id;
