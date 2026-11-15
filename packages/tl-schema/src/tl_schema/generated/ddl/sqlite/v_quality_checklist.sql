CREATE VIEW IF NOT EXISTS v_quality_checklist AS
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
  t.checklist_version AS checklist_version,
  t.questions_json AS questions_json,
  t.question_count AS question_count,
  t.supersedes_id AS supersedes_id,
  t.published_by AS published_by,
  t.published_on AS published_on,
  t.retired_on AS retired_on
FROM cur_quality_checklist AS t
JOIN cur_core_record AS r ON r.id = t.id;
