CREATE VIEW IF NOT EXISTS v_schemareg_waiver AS
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
  t.project AS project,
  t.path AS path,
  t.number AS number,
  t.reason AS reason,
  t.expires AS expires,
  t.requested_by AS requested_by,
  t.approver AS approver,
  t.approved_at AS approved_at,
  t.revoked_by AS revoked_by,
  t.revoked_at AS revoked_at
FROM cur_schemareg_waiver AS t
JOIN cur_core_record AS r ON r.id = t.id;
