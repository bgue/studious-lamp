CREATE OR REPLACE VIEW v_schemareg_adoption AS
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
  t.package AS package,
  t.semver AS semver,
  t.previous_semver AS previous_semver,
  t.worst_class AS worst_class,
  t.impact_sha256 AS impact_sha256,
  t.adopted_by AS adopted_by,
  t.adopted_at AS adopted_at
FROM cur_schemareg_adoption AS t
JOIN cur_core_record AS r ON r.id = t.id;
