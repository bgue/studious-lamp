CREATE OR REPLACE VIEW v_materials_item_master AS
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
  t.category AS category,
  t.base_uom AS base_uom,
  t.size_text AS size_text,
  t.rating_text AS rating_text,
  t.material_code AS material_code,
  t.consumable AS consumable,
  t.retired AS retired
FROM cur_materials_item_master AS t
JOIN cur_core_record AS r ON r.id = t.id;
