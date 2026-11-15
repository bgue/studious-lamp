CREATE OR REPLACE VIEW v_qr_scan_code AS
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
  t.code_hash AS code_hash,
  t.target_id AS target_id,
  t.target_type AS target_type,
  t.label_text AS label_text,
  t.size AS size,
  t.issued_by AS issued_by,
  t.issued_at AS issued_at,
  t.expires_on AS expires_on,
  t.revoked_at AS revoked_at,
  t.revoked_by AS revoked_by,
  t.revoke_reason AS revoke_reason,
  t.replaced_by_id AS replaced_by_id
FROM cur_qr_scan_code AS t
JOIN cur_core_record AS r ON r.id = t.id;
