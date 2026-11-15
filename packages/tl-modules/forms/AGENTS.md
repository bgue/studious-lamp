# AGENTS.md: tl-mod-forms

Rules of the root `AGENTS.md` apply. Local rules:

- Tables `cur_forms_*` are generated; never hand-write DDL (use `ddl_for`).
- `forms_intake_body` is operational: no projector writes it, a rebuild never clears it, and the archive, the lake,
  feeds and webhooks never read it. Only the intake endpoint and the purge job (S6, S7c) write it.
- No event, field, log line or error text holds an intake code, a salt or a body. Intake codes appear as hashes.
- `IntakeItem.Received` carries no typed text. No payload slot is named `code`, `token`, `url`, `body` or `salt`.
- Events are immutable; a withdrawn form is a `Submission.Voided` event, never an edit.
- A draft submission takes no number until it is submitted.
- Answers are confidential text: never put them in a log line, an error text, a feed card or a webhook body.
- Tests live in `tests/`.
