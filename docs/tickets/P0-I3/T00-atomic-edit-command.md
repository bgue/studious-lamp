# P0-I3-T00 — A single atomic edit command for a record form

Status: draft
Tier: sonnet
Labels: core, tui
Depends on: P0-I2 (workstreams A and B merged)
Branch: `p0/i3-t00-atomic-edit-command`

## Goal
Saving a form in the TUI sends one `UpdateRecord` and then one `SetPsetValues` per (pset, layer) (`tl_tui/forms.py`), so a save is
not atomic: a failure after the first command leaves earlier changes applied, and the user is told. Introduce one command (for
example `EditRecord` with `changes` and a list of pset batches) that validates every part against the effective schema and appends all
events in one unit of work, with one `expected_version` check. `tl_tui.forms.save_record_edits` then makes a single call.

## Brief references
- §5.2 rules (events immutable, corrections are new events); §6.3 (`Pset.ValuesSet` records the effective schema hash); §10.2 (forms).

## Notes
- Origin: P0-I2 decision B16 (orchestrator ruling: acceptable for Phase 0, file a follow-up).
- Either P0-I3 (with the commands work) or P0-I4 (with the commands API). The `ClientInterface` change is additive.
- Open design point: the idempotency key and `correlation_id` should be shared by all events of one edit.

## Blocked

## Decision
