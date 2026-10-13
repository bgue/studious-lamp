CREATE OR REPLACE VIEW v_documents_rendition AS
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
  t.kind AS kind,
  t.file_id AS file_id,
  t.filename AS filename,
  t.content_type AS content_type,
  t.size AS size,
  t.sha256 AS sha256,
  t.page_count AS page_count,
  t.is_current AS is_current,
  t.superseded_by AS superseded_by
FROM cur_documents_rendition AS t
JOIN cur_core_record AS r ON r.id = t.id;
