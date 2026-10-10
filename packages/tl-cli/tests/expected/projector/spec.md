# Projector: inspection_weld_counts

Status: draft. Written by: TODO.

## Purpose
TODO: what `proj_inspection_weld_counts` is for and who reads it.

## Handles
| Event type |
|---|
| Weld.Created |

## Table `proj_inspection_weld_counts`
| Column | Type | Meaning |
|---|---|---|
| stream_id | TEXT | the stream (record) the events belong to |
| n | INTEGER | how many handled events the stream has |
| last_seq | INTEGER | ledger seq of the last handled event |

## Registering it
Add `WeldCountsProjector()` to the registry your application builds (`tl_core.projection.defaults.default_registry` for the built-in ones). A projector must be deterministic: `tests/test_projector_weld_counts.py` checks that a rebuild gives the same rows. The current-state table of a record type is generated from its schema, not written here.
