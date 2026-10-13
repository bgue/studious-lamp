CREATE OR REPLACE VIEW v_engineering_tag AS
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
  t.number AS number,
  t.class_code AS class_code,
  t.area AS area,
  t.mnemonic AS mnemonic,
  t.sequence AS sequence,
  t.segments_json AS segments_json,
  t.pattern_code AS pattern_code,
  t.number_status AS number_status,
  t.violations_json AS violations_json,
  t.origin AS origin
FROM cur_engineering_tag AS t
JOIN cur_core_record AS r ON r.id = t.id;
