CREATE VIEW IF NOT EXISTS v_materials_receipt AS
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
  t.po_line_id AS po_line_id,
  t.supplier_text AS supplier_text,
  t.delivery_ref AS delivery_ref,
  t.received_on AS received_on,
  t.location_id AS location_id,
  t.inspected_by AS inspected_by,
  t.inspected_on AS inspected_on,
  t.decided_by AS decided_by,
  t.decided_on AS decided_on,
  t.rejection_reason AS rejection_reason
FROM cur_materials_receipt AS t
JOIN cur_core_record AS r ON r.id = t.id;
