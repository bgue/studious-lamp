CREATE OR REPLACE VIEW v_engineering_tag_class AS
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
  t.label AS label,
  t.family AS family,
  t.required_psets_json AS required_psets_json,
  t.itr_templates_json AS itr_templates_json,
  t.mnemonics_json AS mnemonics_json,
  t.lifecycle AS lifecycle,
  t.superseded_by AS superseded_by,
  t.edition AS edition
FROM cur_engineering_tag_class AS t
JOIN cur_core_record AS r ON r.id = t.id;
