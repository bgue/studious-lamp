CREATE OR REPLACE VIEW v_correspondence_party AS
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
  t.code AS code,
  t.project_role AS project_role,
  t.email_domains_json_json AS email_domains_json_json,
  t.is_active AS is_active
FROM cur_correspondence_party AS t
JOIN cur_core_record AS r ON r.id = t.id;
