# P2-IP-X4-F1: agent filings under the X2 S1 explicit-grant rule

Fallout of P2-X2 S1 on the integration base (`p2/ip-x4`, addf814c): an agent files only under an
explicit admin module grant; a role derived from the account role does not count.

Goal: every test on this base that files as an agent in the forms, qr, quality, permits and
p2/ip code gets an account and an explicit grant through the existing helper. No assertion
weakened, no product code.

Allowed paths: `tests/confidentiality/test_forms_rows.py`, `packages/tl-modules/forms/tests/**`,
and any other test file the grep below finds failing.

Method: grep `agent:` actors with propose/submit/MCP write tools in the forms, qr, quality,
permits tests, `tests/confidentiality`, `tests/services`, `dev/accept`; run the module gates;
fix each failure with `harness.grant_filing` (same body as `tests/services/conftest.py`).

Out of scope: the `SUBJECT_LINKS[6:]` pin that QR-S2 owns.

Gate: `just gate tests/confidentiality/test_forms_rows.py`; `just gate packages/tl-modules/forms/tests`;
`just gate packages/tl-modules/{quality,permits,qr}/tests`; `just check`.
