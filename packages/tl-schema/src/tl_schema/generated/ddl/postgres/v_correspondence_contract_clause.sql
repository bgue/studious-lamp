CREATE OR REPLACE VIEW v_correspondence_contract_clause AS
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
  t.contract AS contract,
  t.clause_number AS clause_number,
  t.time_bar_days AS time_bar_days,
  t.time_bar_day_type AS time_bar_day_type,
  t.notice_requirements AS notice_requirements,
  t.required_recipients_json AS required_recipients_json,
  t.service_method AS service_method,
  t.contract_document_id AS contract_document_id,
  t.domains_json AS domains_json,
  t.is_active AS is_active
FROM cur_correspondence_contract_clause AS t
JOIN cur_core_record AS r ON r.id = t.id;
