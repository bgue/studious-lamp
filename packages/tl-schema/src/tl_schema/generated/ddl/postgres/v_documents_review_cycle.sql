CREATE OR REPLACE VIEW v_documents_review_cycle AS
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
  t.revision_id AS revision_id,
  t.document_id AS document_id,
  t.round AS round,
  t.state AS state,
  t.due_date AS due_date,
  t.outcome AS outcome,
  t.opened_on AS opened_on,
  t.closed_on AS closed_on
FROM cur_documents_review_cycle AS t
JOIN cur_core_record AS r ON r.id = t.id;
