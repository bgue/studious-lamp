CREATE OR REPLACE VIEW v_requisitions_general_requisition AS
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
  t.general_type AS general_type,
  t.kind AS kind,
  t.subject AS subject,
  t.requester AS requester,
  t.need_by AS need_by,
  t.location_text AS location_text,
  t.priority AS priority,
  t.for_record_id AS for_record_id,
  t.approved_by AS approved_by,
  t.approved_at AS approved_at,
  t.reject_reason AS reject_reason,
  t.work_order_id AS work_order_id
FROM cur_requisitions_general_requisition AS t
JOIN cur_core_record AS r ON r.id = t.id;
