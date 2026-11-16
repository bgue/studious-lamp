# P2-X4 T04, T05, T06 (staged; each becomes its own ticket file in round 5, from the merged T02 and T03)

T04 (lite, docs): `docs/runbooks/new-module.md` from `docs/templates/runbook.md`: the steps `tl new module`, add a record type, add a command row (access word, `meta.delegation`, unique name), what the
three surfaces look like, the closed-by-default tool and the allow row, hidden equals missing, no errors hook (new modules raise core error classes; DEFERRED line), the TUI note (screens still import
modules by name; a module without screens reads through generic record views). Allowed: that file, `docs/runbooks/README.md`. Depends T02b (merged), S5 not needed. Interfaces to paste in r5 from T02b: the three templates (routes.py, tools.py, cli.py), the hook lines, closed-tool rule (`mcp.<name>_ping`), `tl new module` next steps.
T05 (full): `dev/demos/P2-X4.sh` + `dev/demos/p2_x4_demo.py` for the seven demo clauses on both adapters (clauses 1 and 2 on a scaffolded module in a temp root; clauses 3 to 5 on `ext_demo`; 6 on a fake
module with a missing ref; 7 `tl_api.openapi --compat`). Depends T02b, S5 (was T03). Loader: `tests/ext_demo/load.py` `ext_demo_spec()`; clauses 3 to 5 call it; the demo runs no gate, only `tl`/API/MCP calls on both adapters.
T06 (lite): `AGENTS.md` "Where things go" rows (new-module guide, hooks), `docs/templates/package-readme.md` line, and the I4B/IP follow-ups noted in STATE. Depends T05.
