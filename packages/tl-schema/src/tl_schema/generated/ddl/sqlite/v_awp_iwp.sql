CREATE VIEW IF NOT EXISTS v_awp_iwp AS
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
  t.discipline AS discipline,
  t.cwp_id AS cwp_id,
  t.planned_start AS planned_start,
  t.planned_finish AS planned_finish,
  t.foreman AS foreman,
  t.estimated_hours AS estimated_hours,
  t.crew_text AS crew_text,
  t.signoffs_json AS signoffs_json
FROM cur_awp_iwp AS t
JOIN cur_core_record AS r ON r.id = t.id;
