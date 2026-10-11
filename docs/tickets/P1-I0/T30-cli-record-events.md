# P1-I0-T30 — `tl record` and `tl events` on a SQLite path or a Postgres URL

Status: abandoned
Tier: haiku
Labels: cli
Depends on: P1-I0-S30, S32, S33
Branch: (none)

Abandoned: `tl record create` is called by the provided tests of every other command group, so on Postgres no other ticket's tests could pass until `record.py` took a `DbTarget` (the independence rule of L-P0-I6A-5). The supervisor made the same edit as the base commit P1-I0-S34 (`record.py`, `events.py`; tests `test_cli_e2e.py` and `test_cli_numbering.py`, 33 passed on both adapters) instead of spending the first batch on it.
