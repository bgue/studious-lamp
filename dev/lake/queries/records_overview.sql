-- One row per record: key, title, voided flag, conformance and the last ledger seq that touched it.
SELECT key, title, voided, conformance, last_seq
FROM cur_core_record
ORDER BY key
