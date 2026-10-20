CREATE VIEW IF NOT EXISTS v_correspondence_correspondence_thread AS
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
  t.subject_key AS subject_key,
  t.domain AS domain,
  t.state AS state,
  t.governing_item_id AS governing_item_id,
  t.item_count AS item_count,
  t.last_item_on AS last_item_on
FROM cur_correspondence_correspondence_thread AS t
JOIN cur_core_record AS r ON r.id = t.id;
