CREATE VIEW IF NOT EXISTS v_materials_inventory_location AS
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
  t.kind AS kind,
  t.parent_id AS parent_id,
  t.depth AS depth,
  t.retired AS retired
FROM cur_materials_location AS t
JOIN cur_core_record AS r ON r.id = t.id;
