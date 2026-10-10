-- The ledger seq the lake is current to: the greatest last_seq recorded in _tl_sync.
SELECT max(last_seq) AS as_of_seq
FROM _tl_sync
