-- How many links there are for each relation and status.
SELECT relation, status, count(*) AS n
FROM links
GROUP BY relation, status
ORDER BY relation, status
