CREATE OR REPLACE VIEW v_awp_cwp AS
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
  t.cwa_id AS cwa_id,
  t.planned_start AS planned_start,
  t.planned_finish AS planned_finish,
  t.budget_hours AS budget_hours,
  t.quantities_json AS quantities_json,
  t.contractor_text AS contractor_text
FROM cur_awp_cwp AS t
JOIN cur_core_record AS r ON r.id = t.id;
