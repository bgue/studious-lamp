CREATE OR REPLACE VIEW v_materials_stock_lot AS
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
  t.project_item_id AS project_item_id,
  t.heat_no AS heat_no,
  t.receipt_id AS receipt_id,
  t.receipt_line AS receipt_line,
  t.uom AS uom,
  t.issued_net AS issued_net
FROM cur_materials_lot AS t
JOIN cur_core_record AS r ON r.id = t.id;
