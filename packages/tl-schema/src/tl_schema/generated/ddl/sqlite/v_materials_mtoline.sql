CREATE VIEW IF NOT EXISTS v_materials_mtoline AS
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
  t.mto_id AS mto_id,
  t.line_no AS line_no,
  t.project_item_id AS project_item_id,
  t.qty AS qty,
  t.uom AS uom,
  t.tag_id AS tag_id,
  t.work_package_id AS work_package_id,
  t.reserved_qty AS reserved_qty,
  t.issued_qty AS issued_qty
FROM cur_materials_mto_line AS t
JOIN cur_core_record AS r ON r.id = t.id;
