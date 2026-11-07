CREATE OR REPLACE VIEW v_materials_project_item AS
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
  t.item_master_id AS item_master_id,
  t.category AS category,
  t.uom AS uom,
  t.consumable AS consumable
FROM cur_materials_project_item AS t
JOIN cur_core_record AS r ON r.id = t.id;
