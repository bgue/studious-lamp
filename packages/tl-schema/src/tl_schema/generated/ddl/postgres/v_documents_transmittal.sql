CREATE OR REPLACE VIEW v_documents_transmittal AS
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
  t.number AS number,
  t.direction AS direction,
  t.purpose AS purpose,
  t.due_date AS due_date,
  t.issued_on AS issued_on,
  t.response_code AS response_code,
  t.response_note AS response_note,
  t.responded_on AS responded_on,
  t.recipients_json AS recipients_json,
  t.item_count AS item_count
FROM cur_documents_transmittal AS t
JOIN cur_core_record AS r ON r.id = t.id;
