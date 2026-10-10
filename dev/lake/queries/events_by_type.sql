-- How many ledger events of each event_type, most frequent first (ties by event_type).
SELECT event_type, count(*) AS n
FROM events
GROUP BY event_type
ORDER BY n DESC, event_type
