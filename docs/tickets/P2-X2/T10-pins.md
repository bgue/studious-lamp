# P2-X2-T10: pins after the DONE gate

Branch p2/x2-t10-pins, base p2/x2@6e70ffa4.

1. Settings count 33 -> 34 (S2 added `ai.agents.max_pending_per_project`) in the four tui settings test files
   (embedded, fakes, remote, settings screen). The fakes read the platform definitions, so no hand list changed;
   no snapshot depended on the count.
2. `test_plain_walk.py::test_admin_ctrl_d_walk_shows_technical_text_then_hides_it` (f7 on RecordScreen, plain
   vs Ctrl+D on then off): re-run on this tree it passes, alone and in the gate. X2 changed no screen the f7
   walk reaches (T03 touched only the accounts screen). Treated as a load-sensitive timing flake of the walk
   (the first full run was under a heavy concurrent job); no product or test change.
3. `tests/parity/test_webhooks_parity.py::test_every_catalog_event_type_is_delivered_and_valid`: the expected
   delivered set also excludes `STREAM_BUMP_EVENT_TYPES` (as T07 did in the contract test).

Acceptance: `just check`; gate on the tui files and the walk; gate and gate-pg on the webhook parity test.
