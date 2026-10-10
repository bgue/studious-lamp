# Run status

One line per increment, newest last. Format: `throughline-docs` skill §5.

| Time (UTC) | Increment | Outcome | Tickets | Gates | Demo | Trunk |
|---|---|---|---|---|---|---|
| 2026-10-09 18:30 | P0-I1 | done | merged 12 / taken over 0 / abandoned 0 (T12 done by supervisor) | check, test green; parity, tui n/a; supervisor pieces reviewed x4 | demo ok | dad8f4b |
| 2026-10-09 19:37 | P0-I2 | done (fanout: WS-A schema, WS-B TUI) | WS-A: 13 tickets merged, T05/T09 by supervisor; WS-B: 14 merged, T18 by supervisor; 0 abandoned | check, test 812, test-tui 179 green; parity n/a; supervisor pieces reviewed x8 | demo ok | 4ec0f63 |
| 2026-10-09 22:28 | P0-I3 | done | 16 tickets merged, 0 taken over, 0 abandoned; engines by supervisor | check, test 1424, test-tui 324 (23 snapshots) green; parity n/a; supervisor pieces reviewed | demo ok | 9c7dc11 |
| 2026-10-10 03:36 | P0-I5 | done (fanout: WS-A Postgres, WS-B webhooks) | WS-A: 13 merged (T01-T13), 0 taken over; WS-B: T20-T26 merged; 0 abandoned; T99 migration filed needs-human | check (licence gate), test 2580, test-parity 1234 on Postgres green; supervisor pieces reviewed x6 | demo ok | 75c0e51 |
