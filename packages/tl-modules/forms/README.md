# tl-mod-forms

Forms (ADR-0031, ADR-0032, `docs/build-spec/module-designs/forms-eval.md`): templates, submissions with drafts and
public zero-login intake. Four record types (`forms.Template`, `forms.Submission`, `forms.IntakeCode`,
`forms.IntakeItem`) with tables `cur_forms_*`, and one operational table, `forms_intake_body`, that no event
produces.

This piece (P2-FORMS S2) holds the schema, the projectors and the names. Commands, views, routes, the CLI, the tools
and the intake endpoint come later (S3, S6, S7c). The module declares no `confidential` source yet: the
confidentiality rows are added with the subject rows before any read path ships.
