CREATE OR REPLACE VIEW v_cost_cost_snapshot AS
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
  t.period AS period,
  t.revision AS revision,
  t.as_of AS as_of,
  t.currency AS currency,
  t.source_name AS source_name,
  t.source_sha256 AS source_sha256,
  t.row_count AS row_count,
  t.new_code_count AS new_code_count,
  t.revised_code_count AS revised_code_count
FROM cur_cost_cost_snapshot AS t
JOIN cur_core_record AS r ON r.id = t.id;
