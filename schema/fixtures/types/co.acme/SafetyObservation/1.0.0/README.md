# co.acme.SafetyObservation 1.0.0

Example managed extension record type (brief 31): a site safety observation. The whole body is stored in
the ledger as pset values, so every field is filterable (`psets.co_acme_safety_observation.severity:high`).

Register it with `tl types sync schema/fixtures/types`.
