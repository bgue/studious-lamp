CREATE OR REPLACE VIEW v_materials_poline_ref AS
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
  t.po_number AS po_number,
  t.line_no AS line_no,
  t.project_item_id AS project_item_id,
  t.qty_ordered AS qty_ordered,
  t.uom AS uom,
  t.promised_date AS promised_date,
  t.supplier_text AS supplier_text,
  t.qty_received AS qty_received
FROM cur_materials_po_line AS t
JOIN cur_core_record AS r ON r.id = t.id;
