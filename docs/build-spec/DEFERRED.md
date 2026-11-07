# Deferred side quests

Owner rule (2026-11-07): log major side quests and defer them; do none of them now unless they block the work in hand.
One line each: what, why it waits, and the phase it belongs to. Newest at the bottom of each group.

## Security reviews
| Item | Why deferred | Phase |
|---|---|---|
| Wider security review of the terminal release (beyond the release-path checks) | Release needs only the sign-in, token and server-connection paths checked | Phase 2 exit |
| Web security re-check of everything added since SEC-C4 (web look v2, wave 2 web twins) | The web stays off in production until its next review; it runs with the web increment | Web increment after wave 4 |
| Project membership on reads: unknown or not-a-member project answers the one 404 page (web and API); `item_projects` filtered by membership | Projects are not a read boundary in the MVP (roles-mvp §7) | Phase 3 I8 |
| Wave security reviews for P2-I2 to I5 beyond the per-increment Sec rows | Owner: security reviews are owner-optional; keep to what release needs | Phase 2 exit |

## Test runs
| Item | Why deferred | Phase |
|---|---|---|
| Full per-folder run more often than once per wave close | Each ticket's own gate is the rule | wave closes only |
| The whole parity suite on Postgres | Dedicated time | Phase 2 exit |
| Phase mutation sweep (30–60 mutants) | Dedicated time | Phase 2 exit |
| `test_stream.py` can hang; a stream test flakes under load (passes alone) | Not blocking; a bounded timeout is the fix | Phase 2 exit |
| The web test seed fails on Postgres (Q4) | The web tests run on SQLite | Web increment after wave 4 |

## Refactors
| Item | Why deferred | Phase |
|---|---|---|
| Pinned module, command and tool lists computed from the registries instead of written by hand | They break on every merge of two modules (wave 1 close: 25 fixes) | Phase 2 exit |
| Tests in other packages import the materials acceptance scripts through `sys.path` (L-P2-I3-1) | Works; move shared fixtures to a test helper package | Phase 2 exit |
| `dev/gate.sh` per-folder mode as the default whole run | The four-part run no longer fits 16 GB; a script does it today | wave 3 close |
| `refresh_preview.sh` leaves the tools out when it stops on a conflict | Replaced by the demo project generator for the tour | with item 1 (generator) |

## Nice-to-haves and small follow-ups
| Item | Why deferred | Phase |
|---|---|---|
| Six materials terminal screens have no technical-mode rows (D, E, I, M, S, W) | Missing feature, not a break | wave 3 |
| `tl mat move reserve --for-line` should take the take-off line key, not its record id | Usability; the runbook points at the API for the id | wave 3 |
| Locations web page: tree indent and lot counts (WEB1 D46) | Cosmetic | Web increment after wave 4 |
| WBS reload keeps a reinstated node's old title (S7 F6); the CWA target has the same reload shape | The demo needs the same tree only | wave 3 |
| `tl awp worker` has no access word; spec §3 role wording | Docs and a small gate | wave 3 |
| P2-W0 follow-ups: Add property shown to readers who would be refused; technical-mode label gaps; RFI panel overdue uses the wall clock | Small UX items | Phase 2 exit |
| Web pages for the wave 3 and 4 logs; create forms (old P2-WEB2) | Owner: CLI and TUI first | Web increment after wave 4 |
| TUI inside the web page as a second mode | See the drawings and model panel spec for the recommendation | not planned |
