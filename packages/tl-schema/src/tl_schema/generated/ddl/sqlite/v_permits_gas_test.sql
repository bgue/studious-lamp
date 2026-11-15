CREATE VIEW IF NOT EXISTS v_permits_gas_test AS
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
  t.permit_id AS permit_id,
  t.taken_at AS taken_at,
  t.tester AS tester,
  t.instrument_text AS instrument_text,
  t.o2_pct AS o2_pct,
  t.lel_pct AS lel_pct,
  t.h2s_ppm AS h2s_ppm,
  t.co_ppm AS co_ppm,
  t.result AS result,
  t.note AS note
FROM cur_permits_gas_test AS t
JOIN cur_core_record AS r ON r.id = t.id;
