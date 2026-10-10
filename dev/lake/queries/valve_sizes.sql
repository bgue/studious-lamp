-- Records with a nominal valve size (the promoted valve_data.size_in column), by key.
SELECT key, pset__valve_data__size_in AS size_in
FROM cur_core_record
WHERE pset__valve_data__size_in IS NOT NULL
ORDER BY key
