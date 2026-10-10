-- Per pset: how many distinct records have a value, and how many values there are in total.
SELECT pset,
       count(DISTINCT record_id) AS records,
       count(*) AS "values"
FROM pset_values
GROUP BY pset
ORDER BY pset
